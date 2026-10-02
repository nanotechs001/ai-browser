# Mission Control visuals: measurements

Spec: `docs/superpowers/specs/2026-10-02-mission-visuals-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-mission-visuals.md`.

## The budget on the M5 (`test_the_budget`, `AIB_PERF=1`)

20 working agents, the Brain thinking, 1280 × 760, over 3 s. The machine was not quiet: another branch was being built
in parallel (load average 5 to 7), so these are three runs under load. Each cell holds the number the test printed.

| Measure | Budget | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|
| Layouts (`LayoutCount`) | fewer than 10 | 0 | 0 | 0 |
| Style recalcs (`RecalcStyleCount`) / rAF frames | at most one a frame | 181 / 181 | 181 / 181 | 180 / 180 |
| Style recalc time (`RecalcStyleDuration`) | at most 60 ms | 44.8 ms | 52.1 ms | 51.1 ms |
| Main-thread task time (`TaskDuration`) | at most 250 ms | 119 ms | 138 ms | 135 ms |
| Cloud draws | at most 92 | 90 | 91 | 90 |
| WebGL contexts | 1 | 1 | 1 | 1 |
| The Brain's GPU time | at most 1.5 ms a frame | 0.80 ms | 0.77 ms | 0.93 ms |
| Points | 8000 | 8000 | 8000 | 8000 |

The budget is met: every run meets every line, the middle run included.

**An earlier pass, the same hour, with the same code, failed on recalc time:** 75.1, 86.0 and 60.3 ms, with
task time at 186, 209 and 158 ms, GPU time at 1.37, 1.55 and 0.82 ms a frame, and the other lines as above. So the
recalc line follows the machine's load, as the plan's rehearsal warned (67-85 ms there). Re-measure on an idle
machine after the merge.

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

## On Windows

Not measured here. The Windows spec's manual laptop check runs `PERF_ROOM` (kept in `tests/test_mission_visuals.py`)
in Mission Control's DevTools, records 3 s in the Performance panel, and writes down layouts, style recalcs (count and
time) and total task time (decision 10). If style recalcs take more than 150 ms in 3 s there, decision 10's next steps
are the user's call: the hands on `steps()` timing (the plan's rehearsal found it doesn't lower the recalc time on the
M5), then a canvas per station, in a spec of its own.
