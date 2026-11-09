# The voice of JAVV's docs

This file holds the voice rules for the text that JAVV shows to a reader: the Guide in the app,
the pages of the docs site, the steps under the videos and the release notes. It also holds the
sources of each rule, with links, so that a writer or a skill can check a rule at its source.

The rule for the Guide is an operator ruling (2026-11-09, issue 1142, row in
[`rulings.md`](rulings.md)). The operator asked for a guide with no first person and no third
person. The rule below comes from the style guides of Google, Microsoft, GitLab and Kubernetes,
and from Simplified Technical English (STE). The operator accepted it.

## The rules

| Rule | Do | Do not |
|---|---|---|
| 1. Do not write "we", "our", "us" or "I". | "Version 0.9.9 adds the Nomad jobs." | "In 0.9.9, we added the Nomad jobs." |
| 2. Address the reader as "you". | "When you revoke a risk acceptance, its findings become Open again." | "When a user revokes a risk acceptance, ..." |
| 3. Write a step as a command. Start the step with its verb. | "Select Save changes." | "You can now select Save changes." |
| 4. Tell where before what. | "On the Dashboards page, select Import." | "Select Import on the Dashboards page." |
| 5. A permission names the role that you need. | "To set a state, your role must allow triage." | "A user with the triage permission can set a state." |
| 6. A description has JAVV, a screen or the data as its subject. | "JAVV does not set it." | "Set by a person, never by JAVV." |
| 7. Other people stay in the third person only as the data of a screen. | "The podium shows the first three people." | "An admin sets both windows." |
| 8. Tell a test as a fact. | "Tested with: Nomad 2.1.1." "Safari is not tested." | "We tested it on Nomad 2.1.1." |
| 9. Use the active voice and the present tense. | "The scanner sends its results." | "The results will be sent by the scanner." |
| 10. Keep a sentence short: 20 words for a step, 25 words for a description. | Two short sentences. | One sentence that joins two facts with "and". |
| 11. Do not use an em dash or a semicolon. | Two sentences. | One sentence with a dash in it. |

### Exceptions

- `SECURITY.md` uses "we" for the promises of the maintainers to a reporter. The reader must know
  who replies. Google permits "we" when the author is a named organization.
- The passive voice is correct when the actor is not known or not important: "The file is
  deleted after 24 hours." Google, GitLab and Kubernetes give the same exception.
- A label in the app can name a column or a role that has the word "user" in it, for example the
  User column of the Audit log. That word is a name on the screen, not the reader.

## Where JAVV holds the rules

| Text | Check |
|---|---|
| The Guide (`frontend/src/components/about/guide/`) | `frontend/src/__tests__/guide-sections.spec.ts`: the expression `NOT_THE_READER` finds "we", "our", "us", "I", "a user", "the user", "an admin", "admins" and "a person". It is case sensitive after the first letter, so the User column does not match. |
| The docs site pages | `backend/tests/test_docs_site.py`: `test_published_pages_tell_tests_without_the_first_person`, `test_published_pages_carry_no_em_dash` and `test_published_docs_pages_pass_the_ste_linter`. |
| All new text | `development/scripts/ste-lint.py`: sentence length, semicolons, phrasal verbs and the passive voice. |
| The release notes | `development/scripts/check-release-notes.py`, and the `Release notes` workflow. |

## Sources

| Source | What it says |
|---|---|
| [Google: Second person](https://developers.google.com/style/person) | Address the reader in the second person, not the first person. Use the second person for what the reader does. Use the third person for what the software or an end user does. Google permits "we" for an organization named as the author. |
| [Google: Active voice](https://developers.google.com/style/voice) | "In general, use active voice." Make clear who does the action. The passive voice is correct when the reader does not need to know the actor. |
| [Google: Procedures](https://developers.google.com/style/procedures) | The first sentence of a step has an imperative verb. "In general, use one step for each action." Tell the reader where to do an action before the action. |
| [Microsoft: Person](https://learn.microsoft.com/en-us/style-guide/grammar/person) | "In general, use second-person pronouns (you, your)." "Avoid plural first person (we, us)." "Try to keep the focus on the customer, not Microsoft." |
| [Microsoft: Step-by-step instructions](https://learn.microsoft.com/en-us/style-guide/procedures-instructions/writing-step-by-step-instructions) | "Use a separate step for each instruction." Start each step with an imperative verb. Tell the customer where the action is before the action. |
| [Kubernetes: Documentation style guide](https://kubernetes.io/docs/contribute/style/style-guide/) | "Address the reader as 'you'." "Avoid using 'we'": the reader does not know if the "we" includes them. Do: "Version 1.4 includes ...". The guide also asks for the present tense and the active voice. |
| [GitLab: Language](https://docs.gitlab.com/development/documentation/styleguide/language/) | Use the active voice. Write from the customer's side: "Use merge requests to compare code", not "GitLab allows you to compare code". |
| [GitLab: Word list](https://docs.gitlab.com/development/documentation/styleguide/word_list/) | "we": avoid it, and tell what the user can do in GitLab. "you": "Use you instead of the user, the administrator or the customer." "please": do not use it. |
| [GitLab: Task topic type](https://docs.gitlab.com/development/documentation/topic_types/task/) | A task lists the roles that it needs in its prerequisites, and names the roles first. It avoids "Ensure that" and "You must have". A step tells the location, then the action. |
| [ASD-STE100](https://www.asd-ste100.org/) | Simplified Technical English: a procedure uses the imperative. A procedural sentence has at most 20 words, a descriptive sentence at most 25. Use the active voice. One instruction in each sentence. The specification is free on request from the ASD-STE100 site. |

The quotes come from the pages on 2026-11-09. A style guide can change. Read the page again
before you change a rule here.

## The skill made from this file

The skill [`.claude/skills/docs-voice/`](../../.claude/skills/docs-voice/SKILL.md) reads this
file first, then writes or checks the text. It has these parts:

1. The eleven rules and the exceptions above, with the Do and Do not examples.
2. The checks of the repository, run by exit code: `ste-lint.py` on the new text, and the test of
   the area (the Guide spec, or `test_docs_site.py`).
3. A pass over each sentence that names a person: is the person the reader (rule 2), a role (rule
   5) or the data of a screen (rule 7)?
4. No internal codes (issue numbers, decision codes, milestones) in text for users or operators.
