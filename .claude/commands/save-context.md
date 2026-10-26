---
description: Save a session handoff snapshot to .claude/sessions/ for fast resume
---

Write a **session handoff** to `.claude/sessions/<YYYY-MM-DD>-<short-slug>.md` so a future session can
resume fast. Steps:

1. Gather current state (don't guess): `git rev-parse --short HEAD`, `git status -sb`,
   `gh pr list --state open`, and the active issue if any.
2. Use [`.claude/sessions/TEMPLATE.md`](../sessions/TEMPLATE.md) as the structure. Keep it **tight** — it's a
   fast-resume snapshot, not a report. Be concrete in **▶ Next step**.
3. File name: today's date + a short slug of the focus (e.g. `2026-07-02-m3-watermark-cas.md`).
4. The file is **gitignored by default** (local-only) — that's intended. Only `git add -f` it if the user
   asks to make it shared/durable.
5. Report the path you wrote.

If `$ARGUMENTS` is given, use it as the focus/slug; otherwise infer the focus from the recent conversation.
