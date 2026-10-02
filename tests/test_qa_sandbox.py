"""Website QA inside the Docker sandbox: the planted site served from the sandbox itself."""

import pytest

from ai_browser import testpages
from ai_browser.engine import Engine
from ai_browser.skills import Catalog

pytestmark = pytest.mark.docker


async def test_qa_runs_in_the_sandbox(tmp_path):
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    try:
        assert "ready" in (await engine.sandbox_start(fresh=True)).text
        base, _ = testpages.serve(engine.sandboxes, engine.info)
        result = await engine.qa(base + "qa/index.html")
        lines = result.text.splitlines()
        assert lines[0].startswith("qa http://localhost:8000/qa/index.html — 6 pages"), result.text
        assert lines[1].startswith("issues: 3 high · 3 medium · 1 low · 1 link couldn't be checked"), result.text
    finally:
        await engine.close()
