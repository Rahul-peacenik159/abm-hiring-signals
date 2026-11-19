"""Pure logic: classify jobs and turn them into signals (no network)."""
from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from .common import now, parse_dt, signal

PACK = "hiring-signals"


class Rules:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.families = [(name, re.compile(rx, re.I)) for name, rx in cfg["families"].items()]
        self.leader = re.compile(cfg["leader_regex"], re.I)
        self.first = re.compile(cfg["first_hire_regex"], re.I)
        seller = cfg.get("seller", {})
        self.targets = set(seller.get("target_families", []))
        self.keywords = [k.lower() for k in seller.get("keywords", [])]
        self.competitors = [k.lower() for k in seller.get("competitors", [])]
        self.w = cfg.get("weights", {})
        self.p = cfg.get("plays", {})

    def family(self, title: str) -> str:
        for name, rx in self.families:
            if rx.search(title or ""):
                return name
        return "other"

    def is_leader(self, title: str) -> bool:
        return bool(self.leader.search(title or ""))


def _mentions(text: str, terms: list[str]) -> list[str]:
    low = (text or "").lower()
    return [t for t in terms if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low)]


def analyse_account(domain: str, jobs: list[dict], rules: Rules, seen_before: set | None,
                    recent_days: int, ats: str, board: str) -> tuple[list[dict], dict, list[str]]:
    """Returns (signal rows, summary dict, snapshot keys)."""
    cutoff = now() - timedelta(days=recent_days)
    families_now = Counter()
    rows: list[dict] = []
    new_target, leaders, kw_found, comp_found = [], [], Counter(), Counter()

    for j in jobs:
        j["family"] = rules.family(j["title"])
        families_now[j["family"]] += 1
        if seen_before is not None:
            j["is_new"] = j["id"] not in seen_before
        else:
            posted = parse_dt(j.get("posted_at"))
            j["is_new"] = bool(posted and posted >= cutoff)

    prev_families = {k.split(":", 1)[1] for k in (seen_before or set()) if k.startswith("family:")}

    for j in jobs:
        if not j["is_new"]:
            continue
        target = j["family"] in rules.targets
        ev = f"{j['title']} ({j['location'] or 'location n/a'})"
        if target:
            new_target.append(j)
            rows.append(signal(domain, "new_role", j["title"], pack=PACK, category=j["family"], role="trigger",
                               weight=rules.w.get("new_target_role", 0), play=rules.p.get("new_target_role", ""),
                               source=ats, evidence=ev, evidence_url=j["url"]))
            if rules.is_leader(j["title"]):
                leaders.append(j)
                rows.append(signal(domain, "leadership_hire", j["title"], pack=PACK, category=j["family"],
                                   role="trigger", weight=rules.w.get("leadership_hire", 0),
                                   play=rules.p.get("leadership_hire", ""), source=ats, evidence=ev,
                                   evidence_url=j["url"]))
        text = f"{j['title']} {j['text']}"
        for k in _mentions(text, rules.keywords):
            kw_found[k] += 1
            if kw_found[k] == 1:
                rows.append(signal(domain, "keyword_in_job", k, pack=PACK, category=j["family"], role="trigger",
                                   weight=rules.w.get("keyword_in_job", 0), play=rules.p.get("keyword_in_job", ""),
                                   source=ats, evidence=f"'{k}' in {j['title']}", evidence_url=j["url"]))
        for c in _mentions(text, rules.competitors):
            comp_found[c] += 1
            if comp_found[c] == 1:
                rows.append(signal(domain, "competitor_in_job", c, pack=PACK, category=j["family"],
                                   role="competitor", weight=rules.w.get("competitor_in_job", 0),
                                   play=rules.p.get("competitor_in_job", ""), source=ats,
                                   evidence=f"'{c}' in {j['title']}", evidence_url=j["url"]))

    # brand-new function: a target family with roles now, none in the previous run (or a "founding/first" title)
    for fam in sorted(rules.targets):
        fam_jobs = [j for j in jobs if j["family"] == fam]
        if not fam_jobs:
            continue
        first_title = next((j for j in fam_jobs if j["is_new"] and rules.first.search(j["title"])), None)
        new_function = seen_before is not None and fam not in prev_families
        if first_title or new_function:
            j = first_title or fam_jobs[0]
            rows.append(signal(domain, "first_hire_in_function", fam, pack=PACK, category=fam, role="trigger",
                               weight=rules.w.get("first_hire_in_function", 0),
                               play=rules.p.get("first_hire_in_function", ""), source=ats,
                               evidence=f"{j['title']}" + (" (no open roles in this function last run)" if new_function else ""),
                               evidence_url=j["url"]))

    spike = rules.cfg.get("spike_threshold", 5)
    if len(new_target) >= spike:
        rows.append(signal(domain, "hiring_spike", str(len(new_target)), pack=PACK, category="hiring",
                           role="trigger", weight=rules.w.get("hiring_spike", 0), play=rules.p.get("hiring_spike", ""),
                           source=ats, evidence=f"{len(new_target)} new roles in target functions"))

    rows.append(signal(domain, "open_roles", str(len(jobs)), pack=PACK, category="hiring", source=ats,
                       evidence="; ".join(f"{f}: {n}" for f, n in families_now.most_common(6)),
                       evidence_url=_board_url(ats, board)))

    summary = {
        "ats": ats, "board": board, "open_roles": len(jobs),
        "new_roles": sum(1 for j in jobs if j["is_new"]),
        "new_target_roles": len(new_target),
        "leadership_roles": "; ".join(j["title"] for j in leaders),
        "keywords_found": "; ".join(f"{k} ({n})" for k, n in kw_found.most_common()),
        "competitors_found": "; ".join(f"{k} ({n})" for k, n in comp_found.most_common()),
        "top_functions": "; ".join(f"{f} {n}" for f, n in families_now.most_common(4)),
    }
    keys = [j["id"] for j in jobs] + [f"family:{f}" for f in families_now]
    return rows, summary, keys


def _board_url(ats: str, board: str) -> str:
    return {"greenhouse": f"https://job-boards.greenhouse.io/{board}", "lever": f"https://jobs.lever.co/{board}",
            "ashby": f"https://jobs.ashbyhq.com/{board}"}.get(ats, "")
