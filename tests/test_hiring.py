import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hiring_signals import analyze, ats, cli, common
from hiring_signals.common import load_yaml

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def freeze_now(monkeypatch):
    fixed = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(common, "now", lambda: fixed)
    monkeypatch.setattr(analyze, "now", lambda: fixed)


@pytest.fixture
def rules():
    return analyze.Rules(load_yaml(ROOT / "config" / "rules.yaml"))


def load(name):
    return json.loads((FX / name).read_text())


def test_normalisers():
    gh = [ats.normalise_greenhouse(j) for j in load("greenhouse.json")["jobs"]]
    assert gh[0]["title"] == "VP, Revenue Operations" and "HubSpot" in gh[0]["text"] and "<" not in gh[0]["text"]
    assert gh[0]["department"] == "Revenue" and gh[0]["posted_at"].startswith("2026-11-08")
    lv = ats.normalise_lever(load("lever.json")[0])
    assert lv["department"] == "Go To Market" and lv["location"] == "London" and lv["posted_at"].startswith("2026-11")
    ab = [ats.normalise_ashby(j) for j in load("ashby.json")["jobs"]]
    assert ab[0]["department"] == "Engineering / Security" and ab[0]["remote"] is True


@pytest.mark.parametrize("html,expected", [
    ('<a href="https://boards.greenhouse.io/acme">Jobs</a>', ("greenhouse", "acme")),
    ('<a href="https://job-boards.greenhouse.io/acme/jobs/123">', ("greenhouse", "acme")),
    ('<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>', ("greenhouse", "acme")),
    ('<a href="https://jobs.lever.co/acme-inc">', ("lever", "acme-inc")),
    ('<iframe src="https://jobs.ashbyhq.com/Acme"></iframe>', ("ashby", "acme")),
    ("<p>no jobs here</p>", None),
])
def test_find_board_in_html(html, expected):
    assert ats.find_board_in_html(html) == expected


def test_role_families(rules):
    assert rules.family("VP, Revenue Operations") == "revops"
    assert rules.family("Senior Security Engineer") == "security"
    assert rules.family("Account Executive, Enterprise") == "sales"
    assert rules.family("Senior Backend Engineer") == "engineering"
    assert rules.family("Head of Data Science") == "data"
    assert rules.is_leader("Head of Security") and not rules.is_leader("Security Analyst")


def test_first_run_uses_recent_days(rules):
    jobs = [ats.normalise_greenhouse(j) for j in load("greenhouse.json")["jobs"]]
    rows, summary, keys = analyze.analyse_account("acme.com", jobs, rules, None, 30, "greenhouse", "acme")
    types = [(r["signal_type"], r["signal_value"]) for r in rows]
    assert ("leadership_hire", "VP, Revenue Operations") in types
    assert ("new_role", "Founding Product Marketing Manager") in types
    assert not any(v == "Senior Backend Engineer" for t, v in types if t == "new_role")
    assert {"hubspot", "salesforce", "account-based"} <= {v for t, v in types if t == "keyword_in_job"}
    assert ("competitor_in_job", "6sense") in types
    assert ("first_hire_in_function", "marketing") in types
    assert summary["open_roles"] == 3 and summary["new_roles"] == 2
    assert "101" in keys and "family:revops" in keys


def test_second_run_only_new_ids(rules):
    jobs = [ats.normalise_greenhouse(j) for j in load("greenhouse.json")["jobs"]]
    seen = {"101", "102", "103", "family:revops", "family:marketing", "family:engineering"}
    rows, summary, _ = analyze.analyse_account("acme.com", jobs, rules, seen, 30, "greenhouse", "acme")
    assert summary["new_roles"] == 0
    assert [r["signal_type"] for r in rows] == ["open_roles"]


def test_new_function_since_last_run(rules):
    jobs = [ats.normalise_lever(load("lever.json")[0])]
    rows, _, _ = analyze.analyse_account("acme.com", jobs, rules, {"family:engineering"}, 30, "lever", "acme")
    fh = [r for r in rows if r["signal_type"] == "first_hire_in_function"]
    assert fh and fh[0]["signal_value"] == "sales" and "no open roles" in fh[0]["evidence"]
    assert any(r["signal_type"] == "competitor_in_job" and r["signal_value"] == "zoominfo" for r in rows)


def test_cli_end_to_end(monkeypatch, tmp_path):
    payload = {"greenhouse": load("greenhouse.json")["jobs"], "ashby": load("ashby.json")["jobs"]}

    def fake_detect(http, acc, try_careers_page=True):
        if acc["domain"] == "acme.com":
            return "greenhouse", "acme", [ats.normalise_greenhouse(j) for j in payload["greenhouse"]]
        if acc["domain"] == "secure.io":
            return "ashby", "secure", [ats.normalise_ashby(j) for j in payload["ashby"] if j["isListed"]]
        return None

    monkeypatch.setattr(cli.ats, "detect_board", fake_detect)
    out = tmp_path / "out"
    cli.main(["run", "--domains", "acme.com", "secure.io", "nojobs.example", "--out", str(out)])
    rows = {r["account_domain"]: r for r in csv.DictReader(open(out / "accounts_summary.csv"))}
    assert int(rows["acme.com"]["score"]) > 0 and rows["acme.com"]["top_play"] == "new_leader_first_90_days"
    assert rows["nojobs.example"]["errors"].startswith("no public")
    info = json.loads((out / "run_info.json").read_text())
    assert info["previous_run"] is None and info["errors"] == 1
    cli.main(["run", "--domains", "acme.com", "secure.io", "--out", str(out)])
    assert json.loads((out / "run_info.json").read_text())["new_items"] == 0
    md = cli.summary_markdown(out / "accounts_summary.csv", [("account_domain", "Account")], "T")
    assert "Compared with previous run" in md
