import csv
import io

from ai_browser.qa.model import Issue, PageResult, QARun, SizeResult
from ai_browser.qa.report import summary, write_report
from ai_browser.workfs import WorkDir

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 20 + b"\xff\xd9"


def sample_run() -> QARun:
    sizes = {name: SizeResult(name, name == "mobile", 210 if name == "mobile" else 0,
                              ['div.wide-table "Wide"'] if name == "mobile" else [], JPEG, JPEG, 390, 900)
             for name in ("desktop", "tablet", "mobile")}
    page = PageResult("https://s.com/", final_url="https://s.com/", status=200,
                      title='<script>alert("x")</script> & co', sizes=sizes, seconds=1.2)
    issues = [Issue("high", "broken link", "https://s.com/missing (404)", ["https://s.com/"], extra="Old <b>offers</b>"),
              Issue("medium", "console error", 'Failed: "quoted" & <tag>', ["https://s.com/"])]
    issues += [Issue("low", "link timed out", f"https://o{n}.com/ (timeout)", ["https://s.com/"]) for n in range(12)]
    return QARun("https://s.com/", "https://s.com", "sandbox", 1_790_000_000.0, 3.4, [page], issues,
                 [("https://o.com/x", "403")], ["https://s.com/logout"], 0)


def test_report_files_escape_page_text(tmp_path):
    work = WorkDir(tmp_path / "work", "t1")
    paths = write_report(work, sample_run())
    html = work.to_host(paths.html).read_text(encoding="utf-8")
    assert "<script>alert" not in html and "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; co" in html
    assert "Old &lt;b&gt;offers&lt;/b&gt;" in html and "data:image/jpeg;base64," in html
    assert 'href="shots/01-home-mobile.jpg"' in html
    rows = list(csv.reader(io.StringIO(work.to_host(paths.csv).read_text(encoding="utf-8"))))
    assert rows[0] == ["severity", "kind", "detail", "pages_count", "pages", "sizes", "extra"]
    assert len(rows) == 1 + 14 and rows[1][:2] == ["high", "broken link"]
    assert work.to_host(paths.shots + "/01-home-desktop.jpg").read_bytes() == JPEG


def test_summary_lists_counts_and_at_most_ten_issues(tmp_path):
    work = WorkDir(tmp_path / "work", "t1")
    run = sample_run()
    text = summary(run, write_report(work, run))
    lines = text.splitlines()
    assert lines[0].startswith("qa https://s.com/ — 1 page in 3.4 s")
    assert lines[1] == ("issues: 1 high · 1 medium · 12 low · 1 link couldn't be checked · "
                        "1 action link not followed")
    assert sum(1 for line in lines if line[:3].strip().rstrip(".").isdigit()) == 10
    assert any(line.startswith("report: /work/t1/qa/s.com-") for line in lines)



def test_errors_from_browser_extensions_are_not_the_sites():
    from ai_browser.qa.page import page_issues

    page = PageResult("https://s.com/", final_url="https://s.com/", status=200,
                      exceptions=[("TypeError: x", "chrome-extension://abc/content.js:3")],
                      console=[("extension says no", "chrome-extension://abc/content.js:9")],
                      failed=[("chrome-extension://abc/icon.png", "Image", "net::ERR_FILE_NOT_FOUND")])
    assert page_issues(page, "https://s.com") == []
