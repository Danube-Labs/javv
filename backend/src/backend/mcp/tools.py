"""MCP tools made from route functions (issue 1096 steps 2 and 3).

A tool takes the parameters of its route, with the route's own types and limits, so the tool
refuses each value that the route refuses. A parameter that the route reads through a dependency
(the findings filters, `as_of`) becomes a tool parameter too, and the dependency runs on it. The
request is a bare one that carries only the app: the routes behind tools read nothing else from
it. A read tool gives the route the token's principal widened for the read (`auth.reader`), and
skips the route's permission check: a token reads all data (D4). A write tool (`needs`) gives the
token's principal as it is, and runs the route's permission check on it first, as FastAPI does.

A tool with several routes (`kinds`) takes a `kind` and the parameters of all its routes, each
one optional with no default of its own; a parameter that the chosen route does not take is
refused, one that it needs must be there, and one left out takes the route's default.

Each answer goes back as compact JSON text, one time: no structured copy, which doubled the size
in the step 0 probe. An answer longer than `JAVV_MCP_MAX_ANSWER_CHARS` drops rows from the end
of its longest list and says so in `cut`; a page with a next page is refused instead."""

import contextvars
import inspect
import json
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.params import Depends
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic.fields import FieldInfo
from starlette.exceptions import HTTPException  # the base of FastAPI's and TypedHTTPException

from backend.auth.principal import Principal
from backend.core.settings import get_settings
from backend.mcp.auth import reader
from backend.query import pit_guard
from backend.query.search import cursor_pit_id

current_principal: contextvars.ContextVar[Principal | None] = contextvars.ContextVar(
    "mcp_principal", default=None
)

_EMPTY = inspect.Parameter.empty


class RouteError(ToolError):
    """A route answered with an HTTP error; the agent gets its status and its text."""

    def __init__(self, status: int, detail: Any) -> None:
        text = detail if isinstance(detail, str) else json.dumps(detail, default=str)
        super().__init__(f"{status}: {text}")
        self.status = status


@dataclass(frozen=True)
class Tool:
    """One tool. `routes` maps each `kind` to its route function; a tool with one route has one
    entry under the key "". `params` replaces a route parameter (annotation, default); a `hidden`
    parameter is not offered and the route takes its default; `paged` tools hold one open search
    for each token (Q4). A write tool `needs` a permission: a token without it does not see the
    tool and cannot call it (D5)."""

    name: str
    description: str
    routes: dict[str, Callable[..., Any]]
    params: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    hidden: tuple[str, ...] = ()
    paged: bool = False
    needs: str | None = None

    @property
    def annotations(self) -> ToolAnnotations:
        return READ_ONLY if self.needs is None else WRITES


@dataclass(frozen=True)
class _Dep:
    fn: Callable[..., Any]
    params: dict[str, inspect.Parameter]


@dataclass
class _RoutePlan:
    fn: Callable[..., Any]
    request: str | None = None
    principal: str | None = None
    gate: Callable[..., Any] | None = None  # the route's permission check on the principal
    plain: dict[str, inspect.Parameter] = field(default_factory=dict)
    deps: dict[str, _Dep] = field(default_factory=dict)

    def tool_params(self) -> dict[str, inspect.Parameter]:
        return {**self.plain, **{n: p for d in self.deps.values() for n, p in d.params.items()}}


def _dependency(annotation: Any, default: Any) -> Callable[..., Any] | None:
    if typing.get_origin(annotation) is typing.Annotated:
        for meta in typing.get_args(annotation)[1:]:
            if isinstance(meta, Depends):
                return meta.dependency
    if isinstance(default, Depends):
        return default.dependency
    return None


def _is_principal(annotation: Any) -> bool:
    base = typing.get_args(annotation)[0] if typing.get_origin(annotation) else annotation
    return base is Principal


def _parts(annotation: Any) -> tuple[Any, list[Any]]:
    if typing.get_origin(annotation) is typing.Annotated:
        base, *metas = typing.get_args(annotation)
        return base, metas
    return annotation, []


def _optional(annotation: Any) -> Any:
    """The annotation that also takes None, with its limits kept on the inner type."""
    base, metas = _parts(annotation)
    if isinstance(base, types.UnionType) and type(None) in typing.get_args(base):
        return annotation
    if metas:
        return typing.Annotated[(base | None, *metas)]  # pyright: ignore[reportInvalidTypeArguments]
    return base | None


def _same(where: str, prior: Any, annotation: Any) -> None:
    """Several routes of a tool take one parameter, so it must have one type and one set of
    limits. Each route declares its own `Query()`, so the limits are compared, not the objects."""

    def shape(a: Any) -> tuple[Any, str]:
        base, metas = _parts(a)
        limits = [
            (m.metadata, m.default, m.alias) if isinstance(m, FieldInfo) else m for m in metas
        ]
        return base, repr(limits)

    if shape(prior) != shape(annotation):
        raise TypeError(f"{where}: {prior} and {annotation} differ")


def _checks_permission(gate: Callable[..., Any] | None) -> bool:
    """Is this the dependency of a permission check (`require_capability`), which takes the
    principal only? The sign-in dependency also gives a principal, but reads the request."""
    if gate is None:
        return False
    params = list(inspect.signature(gate, eval_str=True).parameters.values())
    return len(params) == 1 and _is_principal(params[0].annotation)


def _plan(fn: Callable[..., Any]) -> _RoutePlan:
    plan = _RoutePlan(fn=fn)
    for name, param in inspect.signature(fn, eval_str=True).parameters.items():
        if param.annotation is Request:
            plan.request = name
        elif _is_principal(param.annotation):
            plan.principal = name
            plan.gate = _dependency(param.annotation, param.default)
        elif (dep := _dependency(param.annotation, param.default)) is not None:
            sub = inspect.signature(dep, eval_str=True).parameters
            nested = [n for n, p in sub.items() if _dependency(p.annotation, p.default)]
            if nested:  # an authoring error: a tool cannot fill a dependency of a dependency
                raise TypeError(f"{fn.__name__}.{name}: nested dependency {nested}")
            plan.deps[name] = _Dep(dep, dict(sub))
        else:
            plan.plain[name] = param
    return plan


async def _call(
    plan: _RoutePlan, app: FastAPI, principal: Principal, args: dict[str, Any], *, write: bool
) -> Any:
    call: dict[str, Any] = {}
    if plan.request is not None:
        call[plan.request] = Request({"type": "http", "app": app, "headers": []})
    if plan.principal is not None:
        if write:  # `build` checked that a write route has its gate
            call[plan.principal] = await plan.gate(principal)  # type: ignore[misc]
        else:
            call[plan.principal] = reader(principal)
    for name in plan.plain:
        if name in args:
            call[name] = args[name]
    for name, dep in plan.deps.items():
        value = dep.fn(**{n: args[n] for n in dep.params if n in args})
        call[name] = await value if inspect.isawaitable(value) else value
    return await plan.fn(**call)


def cut_to_fit(answer: dict[str, Any], limit: int) -> str:
    """The answer as compact JSON of at most `limit` characters: the longest top-level list loses
    rows from its end until it fits, and `cut` says how many it kept. A page with a next page is
    refused instead, because its cursor goes on after the last row of the full page, so the rows
    cut here would never be seen."""
    text = json.dumps(answer, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return text
    if answer.get("next_cursor"):
        raise ToolError(
            f"the page has {len(text)} characters, over the cap of {limit}: ask for a smaller size"
        )
    lists = [k for k, v in answer.items() if isinstance(v, list) and v]
    if not lists:
        raise ToolError(f"the answer has {len(text)} characters, over the cap of {limit}")
    key = max(lists, key=lambda k: len(json.dumps(answer[k], default=str)))
    rows: list[Any] = answer[key]

    def trimmed(keep: int) -> str:
        cut = {"field": key, "kept": keep, "had": len(rows), "reason": f"over {limit} characters"}
        return json.dumps(
            {**answer, key: rows[:keep], "cut": cut}, separators=(",", ":"), default=str
        )

    # the text grows with each row kept, so the most rows that fit is found by halving
    low, high = 0, len(rows) - 1
    if len(trimmed(low)) > limit:
        raise ToolError(f"the answer is over the cap of {limit} characters: narrow the filters")
    while low < high:
        mid = (low + high + 1) // 2
        if len(trimmed(mid)) <= limit:
            low = mid
        else:
            high = mid - 1
    return trimmed(low)


# Q4: for each (token, tool), the open search of its last first page
_walks: dict[tuple[str, str], str] = {}
_MAX_WALKS = 100_000
# (token, open search) of each search that a new first page closed. Its cursor would get the 410
# of an expired keep-alive, and an agent then reads that it waited too long (issue 1112).
_closed: set[tuple[str, str]] = set()

CLOSED_BY_NEW_SEARCH = (
    "cursor closed: a new search with this tool closed this search. Read all the pages that you "
    "need before you start a new search, or start this search again"
)


async def _close_last_walk(app: FastAPI, principal: Principal, tool: str) -> None:
    pit_id = _walks.pop((principal.user_id, tool), None)
    if pit_id is not None and pit_guard.holds(principal.user_id, pit_id):
        await app.state.opensearch.delete_pit(body={"pit_id": [pit_id]})
        pit_guard.release_pit(principal.user_id, pit_id)
        if len(_closed) >= _MAX_WALKS:
            _closed.clear()  # such a cursor then gets the keep-alive text of the route again
        _closed.add((principal.user_id, pit_id))


def _refuse_closed(principal: Principal, cursor: str) -> None:
    try:
        pit_id = cursor_pit_id(cursor)
    except ValueError:  # a past-time cursor holds no open search; a bad one is the route's 422
        return
    if (principal.user_id, pit_id) in _closed:
        raise RouteError(410, CLOSED_BY_NEW_SEARCH)


def _keep_walk(principal: Principal, tool: str, answer: Any) -> None:
    cursor = answer.get("next_cursor") if isinstance(answer, dict) else None
    if not cursor:
        _walks.pop((principal.user_id, tool), None)
        return
    try:
        pit_id = cursor_pit_id(cursor)
    except ValueError:  # a past-time findings cursor holds a key, not an open search
        _walks.pop((principal.user_id, tool), None)
        return
    if len(_walks) >= _MAX_WALKS:
        _walks.clear()  # the slots still free themselves at the PIT horizon
    _walks[(principal.user_id, tool)] = pit_id


def build(tool: Tool, app: FastAPI) -> Callable[..., Any]:
    """The tool function that the SDK registers: its signature is the route parameters."""
    plans = {kind: _plan(fn) for kind, fn in tool.routes.items()}
    write = tool.needs is not None
    for kind, plan in plans.items():
        if write and not _checks_permission(plan.gate):
            raise TypeError(f"{tool.name}.{kind}: a write route with no permission check")
    grouped = len(plans) > 1
    params: dict[str, inspect.Parameter] = {}
    for plan in plans.values():
        for name, param in plan.tool_params().items():
            if name in tool.hidden:
                # the route is called without it, so its default must be a plain value
                if param.default is _EMPTY or isinstance(param.default, FieldInfo):
                    raise TypeError(f"{tool.name}.{name}: hidden without a plain default")
                continue
            annotation, default = tool.params.get(name, (param.annotation, param.default))
            if grouped:
                # a value means "this kind takes it", so no parameter has a value of its own:
                # each route checks its required ones at the call and fills in its defaults
                default = None
                annotation = _optional(annotation)
            if name in params:
                _same(f"{tool.name}.{name}", params[name].annotation, annotation)
            params[name] = inspect.Parameter(
                name, inspect.Parameter.KEYWORD_ONLY, annotation=annotation, default=default
            )
    if grouped:
        kinds = tuple(plans)
        kind = inspect.Parameter(
            "kind",
            inspect.Parameter.KEYWORD_ONLY,
            annotation=Literal[kinds],  # pyright: ignore[reportInvalidTypeArguments]
        )
        params = {"kind": kind, **params}
    ordered = sorted(params.values(), key=lambda p: p.default is not _EMPTY)

    async def run(**args: Any) -> str:
        principal = current_principal.get()
        if principal is None:  # the gate sets it; a call without it is a wiring error
            raise ToolError("no principal")
        plan = plans[args.pop("kind")] if grouped else plans[""]
        if grouped:
            accepted = plan.tool_params()
            given = {k: v for k, v in args.items() if v is not None}
            if extra := sorted(set(given) - set(accepted)):
                takes = ", ".join(sorted(accepted)) or "no parameter"
                raise ToolError(f"this kind does not take {', '.join(extra)}. It takes {takes}")
            needed = [n for n, p in accepted.items() if p.default is _EMPTY and n not in given]
            if needed:
                raise ToolError(f"this kind needs {', '.join(needed)}")
            args = given
        if tool.paged and args.get("cursor") is None:
            await _close_last_walk(app, principal, tool.name)
        elif tool.paged:
            _refuse_closed(principal, args["cursor"])
        try:
            answer = await _call(plan, app, principal, args, write=write)
        except HTTPException as exc:
            raise RouteError(exc.status_code, exc.detail) from None
        if tool.paged:
            _keep_walk(principal, tool.name, answer)
        try:
            return cut_to_fit(answer, get_settings().mcp_max_answer_chars)
        except ToolError as exc:
            if write:  # so the agent does not make the change again
                raise ToolError(f"the tool made the change, but {exc}") from None
            raise

    run.__name__ = tool.name
    run.__doc__ = tool.description
    run.__signature__ = inspect.Signature(ordered, return_annotation=str)  # type: ignore[attr-defined]
    return run


READ_ONLY = ToolAnnotations(read_only_hint=True)
# the client asks the user before a write; the server still checks each call (D5)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=True)
