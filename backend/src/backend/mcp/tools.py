"""MCP tools made from route functions (issue 1096 step 2).

A tool takes the parameters of its route, with the route's own types and limits, so the tool
refuses each value that the route refuses. A parameter that the route reads through a dependency
(the findings filters, `as_of`) becomes a tool parameter too, and the dependency runs on it. The
request is a bare one that carries only the app: the routes behind tools read nothing else from
it. The principal is the token's, widened for the read (`auth.reader`).

A tool with several routes (`kinds`) takes a `kind` and the parameters of all its routes; a
parameter that the chosen route does not take is refused, and one that it needs must be there.

Each answer goes back as compact JSON text, one time: no structured copy, which doubled the size
in the step 0 probe. An answer longer than `JAVV_MCP_MAX_ANSWER_CHARS` drops rows from the end
of its longest list and says so in `cut`."""

import contextvars
import inspect
import json
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.params import Depends
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

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
class ReadTool:
    """One tool. `routes` maps each `kind` to its route function; a tool with one route has one
    entry under the key "". `params` replaces a route parameter (annotation, default); `paged`
    tools hold one open search for each token (Q4)."""

    name: str
    description: str
    routes: dict[str, Callable[..., Any]]
    params: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    paged: bool = False


@dataclass(frozen=True)
class _Dep:
    fn: Callable[..., Any]
    params: dict[str, inspect.Parameter]


@dataclass
class _RoutePlan:
    fn: Callable[..., Any]
    request: str | None = None
    principal: str | None = None
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


def _plan(fn: Callable[..., Any]) -> _RoutePlan:
    plan = _RoutePlan(fn=fn)
    for name, param in inspect.signature(fn, eval_str=True).parameters.items():
        if param.annotation is Request:
            plan.request = name
        elif _is_principal(param.annotation):
            plan.principal = name
        elif (dep := _dependency(param.annotation, param.default)) is not None:
            sub = inspect.signature(dep, eval_str=True).parameters
            nested = [n for n, p in sub.items() if _dependency(p.annotation, p.default)]
            if nested:  # an authoring error: a tool cannot fill a dependency of a dependency
                raise TypeError(f"{fn.__name__}.{name}: nested dependency {nested}")
            plan.deps[name] = _Dep(dep, dict(sub))
        else:
            plan.plain[name] = param
    return plan


async def _call(plan: _RoutePlan, app: FastAPI, principal: Principal, args: dict[str, Any]) -> Any:
    call: dict[str, Any] = {}
    if plan.request is not None:
        call[plan.request] = Request({"type": "http", "app": app, "headers": []})
    if plan.principal is not None:
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
    rows from its end until it fits, and `cut` says how many it kept."""
    text = json.dumps(answer, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return text
    lists = [k for k, v in answer.items() if isinstance(v, list) and v]
    if not lists:
        raise ToolError(f"the answer has {len(text)} characters, over the cap of {limit}")
    key = max(lists, key=lambda k: len(json.dumps(answer[k], default=str)))
    rows: list[Any] = answer[key]
    keep = len(rows)
    while keep > 0:
        keep -= 1
        trimmed = {
            **answer,
            key: rows[:keep],
            "cut": {
                "field": key,
                "kept": keep,
                "had": len(rows),
                "reason": f"the answer was over {limit} characters: ask for fewer rows",
            },
        }
        text = json.dumps(trimmed, separators=(",", ":"), default=str)
        if len(text) <= limit:
            return text
    raise ToolError(f"the answer is over the cap of {limit} characters: narrow the filters")


# Q4: for each (token, tool), the open search of its last first page
_walks: dict[tuple[str, str], str] = {}
_MAX_WALKS = 100_000


async def _close_last_walk(app: FastAPI, principal: Principal, tool: str) -> None:
    pit_id = _walks.pop((principal.user_id, tool), None)
    if pit_id is not None and pit_guard.holds(principal.user_id, pit_id):
        await app.state.opensearch.delete_pit(body={"pit_id": [pit_id]})
        pit_guard.release_pit(principal.user_id, pit_id)


def _keep_walk(principal: Principal, tool: str, answer: Any) -> None:
    cursor = answer.get("next_cursor") if isinstance(answer, dict) else None
    if not cursor:
        _walks.pop((principal.user_id, tool), None)
        return
    if len(_walks) >= _MAX_WALKS:
        _walks.clear()  # the slots still free themselves at the PIT horizon
    _walks[(principal.user_id, tool)] = cursor_pit_id(cursor)


def build(tool: ReadTool, app: FastAPI) -> Callable[..., Any]:
    """The tool function that the SDK registers: its signature is the route parameters."""
    plans = {kind: _plan(fn) for kind, fn in tool.routes.items()}
    grouped = len(plans) > 1
    params: dict[str, inspect.Parameter] = {}
    for plan in plans.values():
        for name, param in plan.tool_params().items():
            annotation, default = tool.params.get(name, (param.annotation, param.default))
            if grouped:  # each route checks its own required parameters at the call
                default = None if default is _EMPTY else default
            if name in params and params[name].annotation != annotation:
                prior = params[name].annotation
                raise TypeError(f"{tool.name}.{name}: {prior} and {annotation} differ")
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
                raise ToolError(f"this kind does not take {', '.join(extra)}")
            needed = [n for n, p in accepted.items() if p.default is _EMPTY and n not in given]
            if needed:
                raise ToolError(f"this kind needs {', '.join(needed)}")
            args = given
        if tool.paged and args.get("cursor") is None:
            await _close_last_walk(app, principal, tool.name)
        try:
            answer = await _call(plan, app, principal, args)
        except HTTPException as exc:
            raise RouteError(exc.status_code, exc.detail) from None
        if tool.paged:
            _keep_walk(principal, tool.name, answer)
        return cut_to_fit(answer, get_settings().mcp_max_answer_chars)

    run.__name__ = tool.name
    run.__doc__ = tool.description
    run.__signature__ = inspect.Signature(ordered, return_annotation=str)  # type: ignore[attr-defined]
    return run


READ_ONLY = ToolAnnotations(read_only_hint=True)
