"""Mission Control's visuals: the Brain as a brain of glowing points (brainshape.js, blob.js) and a chibi office worker
at every station (chibi.js), against a real app server (agents on the fake claude) in a throwaway headless AI Browser.
The art holds no agent data, text stays text, and nothing is downloaded."""

from test_home import stack  # noqa: F401  (fixture)
from test_mission import CHROME, open_mission


async def shape(stack, body):
    """Runs `body` (statements ending in a return) in Mission Control, with brainshape.js imported as `shape`."""
    js = await open_mission(stack)
    return await js(f"(async () => {{ const shape = await import(chrome.runtime.getURL('brainshape.js')); {body} }})()")


# ---- brainshape.js ---------------------------------------------------------------------------------------------------

SUM = ("const sum = (array) => { let total = 0; for (let index = 0; index < array.length; index += 1)"
       " total = (total * 31 + Math.round(array[index] * 1e6)) % 1000000007; return total; };")


@CHROME
async def test_one_seed_always_gives_the_same_brain(stack):
    length, one, two, other = await shape(stack, SUM + "const points = shape.brainPoints(8000, 7);"
                                          " return [points.length, sum(points), sum(shape.brainPoints(8000, 7)),"
                                          " sum(shape.brainPoints(8000, 8))];")
    assert length == 48000 and one == two and one != other


@CHROME
async def test_the_brain_mixes_its_parts_exactly(stack):
    kinds, kind = await shape(stack, "const points = shape.brainPoints(8000, 7); const kinds = [0, 0, 0, 0];"
                                     " for (let index = 3; index < points.length; index += 6)"
                                     "  kinds[points[index]] += 1;"
                                     " return [kinds, shape.KIND];")
    assert kinds == [6400, 880, 400, 320]
    assert kind == {"cortex": 0, "cerebellum": 1, "stem": 2, "core": 3}


@CHROME
async def test_every_point_is_inside_the_brains_bounds(stack):
    outside = await shape(stack, "const points = shape.brainPoints(8000, 7); let outside = 0;"
                                 " for (let index = 0; index < points.length; index += 6) {"
                                 "  const [x, y, z, , fold, phase] = points.slice(index, index + 6);"
                                 "  if (!(Math.abs(x) <= 0.7 && y >= -0.85 && y <= 0.6 && Math.abs(z) <= 0.75"
                                 "        && fold >= 0 && fold <= 1 && phase >= 0 && phase <= 1)) outside += 1; }"
                                 " return outside;")
    assert outside == 0


@CHROME
async def test_the_hemispheres_have_a_gap_and_match(stack):
    closest, left, right = await shape(stack, "const points = shape.brainPoints(8000, 7);"
                                              " let closest = 1, left = 0, right = 0;"
                                              " for (let index = 0; index < points.length; index += 6) {"
                                              "  if (points[index + 3] !== shape.KIND.cortex) continue;"
                                              "  closest = Math.min(closest, Math.abs(points[index]));"
                                              "  if (points[index] > 0) left += 1; else right += 1; }"
                                              " return [closest, left, right];")
    assert closest >= 0.02
    assert abs(left - right) <= 0.1 * max(left, right), (left, right)


@CHROME
async def test_the_stem_and_cerebellum_sit_below_and_behind(stack):
    wrong = await shape(stack, "const points = shape.brainPoints(8000, 7); const wrong = { stem: 0, cerebellum: 0 };"
                               " for (let index = 0; index < points.length; index += 6) {"
                               "  const [x, y, z, kind] = points.slice(index, index + 4);"
                               "  if (kind === shape.KIND.stem && !(y <= -0.17 && Math.abs(x) < 0.15)) wrong.stem += 1;"
                               "  if (kind === shape.KIND.cerebellum && !(z < -0.2 && y < -0.1))"
                               "   wrong.cerebellum += 1; }"
                               " return wrong;")
    assert wrong == {"stem": 0, "cerebellum": 0}


@CHROME
async def test_any_first_points_are_an_even_sample(stack):
    kinds, left, right = await shape(stack, "const points = shape.brainPoints(8000, 7); const kinds = [0, 0, 0, 0];"
                                            " let left = 0, right = 0;"
                                            " for (let index = 0; index < 2000 * 6; index += 6) {"
                                            "  kinds[points[index + 3]] += 1;"
                                            "  if (points[index + 3] === 0) { if (points[index] > 0) left += 1;"
                                            "   else right += 1; } }"
                                            " return [kinds, left, right];")
    for count, share in zip(kinds, (0.80, 0.11, 0.05, 0.04)):
        assert abs(count / 2000 - share) <= 0.03, kinds
    assert abs(left - right) <= 0.15 * max(left, right), (left, right)


@CHROME
async def test_synapses_link_near_cortex_points(stack):
    links, typed, cortex, lengths, same = await shape(stack, (
        "const points = shape.brainPoints(8000, 7); const pairs = shape.synapses(points);"
        " let cortex = true, lengths = true;"
        " for (let index = 0; index < pairs.length; index += 2) {"
        "  const one = pairs[index], two = pairs[index + 1];"
        "  if (one >= 8000 || two >= 8000 || points[one * 6 + 3] !== 0 || points[two * 6 + 3] !== 0) cortex = false;"
        "  const length = Math.hypot(points[one * 6] - points[two * 6], points[one * 6 + 1] - points[two * 6 + 1],"
        "                            points[one * 6 + 2] - points[two * 6 + 2]);"
        "  if (length < 0.06 || length > 0.22) lengths = false; }"
        " const again = shape.synapses(shape.brainPoints(8000, 7));"
        " return [pairs.length / 2, pairs instanceof Uint16Array, cortex, lengths,"
        "         again.length === pairs.length && again.every((value, index) => value === pairs[index])];"))
    assert 0 < links <= 900 and typed and cortex and lengths and same
