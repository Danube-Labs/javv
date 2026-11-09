---
name: docs-voice
description: Write or check text that a JAVV reader sees, in the voice of JAVV's docs. Use it for the Guide in the app, the pages of the docs site (docs/, docs/use/) and the steps under the videos. Use it also for the What's new of a release PR, PR bodies and issue comments. Use it before you write the text and again before you post or commit it.
argument-hint: "[file or text to write or check]"
user-invocable: true
---

# Docs voice

Target: **$ARGUMENTS** (none given: the text that this task writes).

The rules and their sources are in
[`development/memory-bank/docs-voice.md`](../../../development/memory-bank/docs-voice.md). That
file is the source of truth. This skill is the procedure. When the two do not agree, the file is
correct.

## 1. Read the rules

Read `development/memory-bank/docs-voice.md` with the Read tool before you write. It has the
eleven voice rules with a Do and a Do not example, three exceptions, the rules of Simplified
Technical English (STE) and the sources of each rule.

## 2. Choose the STE level

Choose the level from the type of text. Do not tell the level in the text.

| Level | Text |
|---|---|
| Strict | The Guide, the operator pages, the steps under the videos, error messages and other text in the app. All rules apply, and one word has one meaning. |
| Normal | PR bodies, issue comments, release notes, the memory bank. The structural rules apply. The word rules are advice. |

## 3. Read the source text for its meaning

When you rewrite a text, read all of it one time before you change a word. Know what it must
still say after the rewrite.

## 4. Write the text

- Address the reader as "you". Do not write "we", "our", "us" or "I".
- Write a step as a command that starts with its verb. Tell where before what.
- A permission names the role that you need.
- JAVV, a screen or the data is the subject of a description.
- Use the active voice and the simple tenses. A step has 20 words at most, a description 25
  words at most. Write one instruction in each sentence.
- Do not use an em dash or a semicolon. Use a list for three or more steps or conditions.
- Text for users and operators has no internal codes: no issue numbers, decision codes or
  milestones. Internal text (the memory bank, PR bodies) can name an issue as `issue NNN`.

## 5. Look for the six problems

Read each sentence and look for the six problems of `docs-voice.md`:

1. Synonym rotation: one thing or one action with two names.
2. Stacked hedges that tell no fact.
3. An action as a noun, in place of its verb.
4. Marketing words.
5. Run-on sentences.
6. Soft phrasal verbs.

## 6. Keep the meaning

- Keep each fact, condition, scope and number. If a shorter sentence loses one, keep the longer
  sentence. After the text, add one line that starts with "Kept as it is:" and names the phrase.
- Keep each hedge. "May have failed" is not "failed".
- Add no fact that the source does not give: no cause, frequency or mechanism.
- Do not change text that obeys the rules. Say that it obeys them.
- Stop when each sentence has one meaning, not when it is shortest. A rewrite changes the form,
  not what the text says.

## 7. Check each sentence that names a person

For each person in the text, ask who it is:

| Who | Rule |
|---|---|
| The reader | "you" (rule 2) |
| A role that a step needs | The role, as the condition of the reader: "your role must allow triage" (rule 5) |
| Somebody that a screen shows | The third person, as data: "The podium shows the first three people" (rule 7) |

## 8. Run the checks, and judge them by the exit code

| Text | Command | Pass |
|---|---|---|
| All text | `python3 development/scripts/ste-lint.py <files>` (or the text on stdin) | exit 0 |
| The Guide | `npx vitest run src/__tests__/guide-sections.spec.ts` from `frontend/` | exit 0 |
| The docs site | `JAVV_OPENSEARCH_URL=http://localhost:9 uv run pytest tests/test_docs_site.py` from `backend/` | exit 0 |
| The What's new of a release PR | `python3 development/scripts/check-release-notes.py <body file>` | exit 0 |

A text for GitHub (a PR body, an issue comment) also gets a grep for names, local paths, model
names and session links before the post. Post only when both checks pass.

## 9. When a rule does not fit

Do not change a rule in passing. If a text needs a new exception, stop and ask the operator. An
accepted change goes into `docs-voice.md` and `rulings.md` in the same PR.
