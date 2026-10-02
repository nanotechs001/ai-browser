# Mission Control visuals: measurements

Spec: `docs/superpowers/specs/2026-10-02-mission-visuals-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-mission-visuals.md`.

## The budget on the M5 (`test_the_budget`, `AIB_PERF=1`)

20 working agents, the Brain thinking, 1280 × 760, over 3 s.

**The budget is not shown to be met.** Of 12 runs, 3 met every line (pass B). The style recalc time missed its line
in the other 9, and the Brain's GPU time missed its line in 5 of the 12. Every run was made while another branch was
being built on this machine, and no run on an idle machine exists yet. The load is the likely cause, but that isn't
shown: pass B met every line at a load of 5 to 7, while pass D missed at 4.5 to 6.1. Spec decision 10 says "This plan
is done when the M5 numbers meet the budget", so on these numbers the plan is not done.

Each cell holds the numbers the test printed, run 1 / run 2 / run 3. Load is the 1-minute load average.

| Pass | Who, when | Load | Recalc time (≤ 60 ms) | Task time (≤ 250 ms) | GPU a frame (≤ 1.5 ms) | Budget |
|---|---|---|---|---|---|---|
| A | implementer, Task 12 | 5 to 7 | 75.1 / 86.0 / 60.3 ms | 186 / 209 / 158 ms | 1.37 / 1.55 / 0.82 ms | missed 3 of 3 |
| B | implementer, Task 12, the same hour, the same code | 5 to 7 | 44.8 / 52.1 / 51.1 ms | 119 / 138 / 135 ms | 0.80 / 0.77 / 0.93 ms | met 3 of 3 |
| C | the branch's reviewer | 5.5 to 8.7 | 79.1 / 90.0 / 64.2 ms | 193 / 214 / 164 ms | 1.56 / 1.50 / 0.92 ms | missed 3 of 3 |
| D | the review's fix pass, 2026-10-03 | 4.5 to 6.1 | 78.1 / 95.2 / 78.6 ms | 190 / 221 / 188 ms | 1.63 / 1.52 / 1.54 ms | missed 3 of 3 |

- **Met in every run that printed them** (A, B and D; C reported only the three columns above): no layouts
  (`LayoutCount` 0), at most one style recalc a frame (180 or 181 for as many rAF frames), 90 or 91 cloud draws (at
  most 92), 1 WebGL context, and 8000 points.
- **Task time** met its line in all 12 runs.

**What is still open:**
1. Run `AIB_PERF=1 uv run pytest tests/test_mission_visuals.py::test_the_budget -q -p no:randomly -s` three times on
   an idle machine (no parallel build) and add the numbers here.
2. If an idle run still misses, the levers are the user's call, because each one changes the design:
   - for the recalc time, fewer animated layers per worker, or a canvas per station (decision 10's steps; see "Where
     the recalc time goes" below);
   - for the GPU time, fewer points at the start than the spec's 8000.

**Where the recalc time goes** (thread CPU time of the style recalcs, from a trace, with CSS overrides in one open
page, four rounds each, medians, under the same load):
- 20 animated stations: 86 ms; 10: 48 ms; 5: 33 ms; 1: 13 ms. That is about 10 ms fixed, plus about 3.8 ms for each
  working station, with its six animated layers (the scan line, both hands, the head, the face and the blink).
- The scan lines alone, with every worker still: 33 ms. Without the scan lines, with the workers animated: 86 ms,
  against 71 ms with them in the same run. So the scan lines' share is within the noise, not the 22-25 ms the
  rehearsal's probe suggested (that number was their cost with nothing else animated, fixed cost included).
- Look-alike scan lines (px keyframes instead of %, the `translate` property, `will-change`) didn't lower it.
- 1500 extra CSS rules on the parts didn't multiply the cost, so Blink reuses each layer's base style: the cost is
  per animated layer per frame, with no cheaper form of the same animation.
- So, if an idle machine misses 60 ms, the levers are fewer animated layers per worker or a canvas per station
  (decision 10's steps). Both change the design, which is the user's call.

## Checked by eye

Screenshots (`AIB_SHOTS`), compared with `docs/superpowers/prototypes/mission-visuals/brain2.png` and `gallery.png`:

| Screenshot | What to see | Seen |
|---|---|---|
| brain-idle, brain-thinking, brain-alert, brain-speaking | a brain (two hemispheres with folds, the cerebellum, the stem) in blue-violet, cyan, amber-coral, mint | yes |
| brain-turned | the room turned, the Brain still facing the user | yes |
| room-1, room-6, room-14, room-20 | desks with workers, no card covering another, every name readable | yes (the Brain is amber in these: the two replies from brain-alert are still waiting) |
| poses | the six poses: typing, waiting, a raised hand, a thumbs up, slumped with a drop of sweat, dozing in grey | yes |
| arrival | the spark on its way, the new desk's worker below the desk or popping up | yes (the spark beside the new desk, its worker still below it) |
| reduced | the same room, still | yes |
| dotted | the dotted brain silhouette, front to the left | yes |

## The full suite and the bench

| Run | Result |
|---|---|
| `uv run pytest -q -p no:randomly` | 616 passed, 2 skipped in 625.18s (the 2 skips: `test_the_budget` without `AIB_PERF`, `test_screenshots_for_the_eye` without `AIB_SHOTS`; Docker was running, so the Docker tests ran) |
| `uv run pytest -q -p no:randomly`, again in the review's fix pass (2026-10-03, at 52f6d90) | 616 passed, 2 skipped in 664.64s (the same 2 skips) |
| `uv run ai-browser bench` | all PASS (medians of 15 runs, against the budget): observe 1 / 100 ms, observe heavy page 10 / 300 ms, click step 50 / 150 ms, type step 50 / 150 ms, open local page 10 / 500 ms, screenshot 50 / 300 ms. Run with `AIB_HOME` set to a scratch folder, so the bench's throwaway sandbox left nothing in `~/.ai-browser` |

Both ran while another branch was being built on this machine (load average 6-11).

## On Windows

Not measured here. The Windows spec's manual laptop check runs `PERF_ROOM` (kept in `tests/test_mission_visuals.py`)
in Mission Control's DevTools, records 3 s in the Performance panel, and writes down layouts, style recalcs (count and
time) and total task time (decision 10). If style recalcs take more than 150 ms in 3 s there, decision 10's next steps
are the user's call: the hands on `steps()` timing (the plan's rehearsal found it doesn't lower the recalc time on the
M5), then a canvas per station, in a spec of its own.
