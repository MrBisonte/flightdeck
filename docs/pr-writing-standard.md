# PR writing standard

Rules for every PR: the title, the body, and the squash message. They apply to
human and agent authors alike.

## Title
- Conventional Commits prefix: `feat:`, `fix:`, `docs:`, `chore:`.
- Plain and lowercase. State the change, not a thesis or a slogan.
- Good: `fix: maze unplayable after the 55x33 resize`.
- Bad: `A better, more playable maze experience`.

## Body: what to record
Record what changed and why. Nothing else.
- No process narration. No tooling, no agent workflow, no "how it was found".
  State "the freeze is fixed" and the root cause, not "a monitored run caught it".
- No first person. No "I", no "we".
- No roadmap as fact. The unbuilt stays out; link a ROADMAP entry if it must be named.
- Verification is bare numbers: `typecheck 0, 2384 of 2384 tests`. A result, not a story.

## Body: how to write it
- Register is ASD Simplified Technical English: shortest possible, one fact per
  sentence, present tense, active voice, objective.
- One or two sentences of prose, then bullets or a table. Complex detail goes in
  a table, never a paragraph.
- State each fact once. Do not repeat in prose what a table already carried.
- No em dashes anywhere. Split the sentence, or use a colon.
- No hype words: delve, leverage, robust, seamless, comprehensive, powerful,
  rich, streamline, utilize (use "use").

## Squash message
- Preview it before merge and wait for approval.
- Conventional Commits, terse, same rules as the body. A title, then a short
  paragraph of what changed and why.

## Integration PR
One PR lands several branches together. Each branch keeps its own PR with the
full description, and the integration PR indexes them.

| Part | Rule |
|---|---|
| Branches | Stacked in merge order, each cut from the one before |
| Branch PRs | One per branch, full body, base is the branch before |
| Integration PR | Head is the tip of the stack, base is `main` |
| Title | `type: integrate <round>, #first to #last` |
| Body | One sentence: what lands, in which order. A table, one row per PR. One line for an outcome that spans PRs |
| Table row | The change, in one line. A decision record is named, not restated |
| Verification | Stays in the branch PRs. CI runs on the integration PR |
| After opening | Close each branch PR with a comment: `Included in #N` |
| Merge | Once, with a merge commit, so each branch commit stays in `git log` |
| A branch PR already merged | Named in the opening sentence, left out of the table |

Body:
```
Lands #22 to #29 in order. #21 is already on `main`. Each row links the full description.

| PR | Change |
|---|---|
| #22 | Reference files declare `valid_from`, so history survives a fresh build. ADR 0003 |
| #23 | Run states are Type 2, and `run_pulse` joins them as-of. ADR 0004 |
| #25 | `spans.event_id` keys `spans`. Export span id collisions: 0 |

HLAD risks closed: 1, 9.
```

## Example

Title: `fix: recorder no-frames alarm fires on static screens`

Body:
```
The `no-frames` alarm fired on the static screens (menu, gameover, chooser).
Those screens keep the frame clock idle on purpose, so 11 of the 17 alarms
were false.

- The alarm now fires only in running states, the same gate `logic-freeze` uses.
- `loop-dead` still fires on any screen, because a dead loop is a real fault anywhere.
- A new recorder test checks that the menu stays quiet. Reverting the fix makes it fail.

typecheck 0. 2350 of 2350 tests pass.
```

## In this repository

Verification names the check and its result. It carries no pass tally:
`120 of 120 tests pass` belongs in a QA PR, not here. A revert proof belongs,
because it states a result: reverting the default makes the gate refuse the
file.
