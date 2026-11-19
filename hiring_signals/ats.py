"""Public job board APIs (read-only, no key needed) and board detection.

Greenhouse  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
Lever       GET https://api.lever.co/v0/postings/{site}?mode=json
Ashby       GET https://api.ashbyhq.com/posting-api/job-board/{name}
"""
from __future__ import annotations

import re

from .common import Http, normalise_domain, parse_dt, strip_html

ATS = ("greenhouse", "lever", "ashby")

_BOARD_PATTERNS = [
    ("greenhouse", re.compile(r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?(?:embed/job_board\?for=)?([a-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([a-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([a-z0-9_.-]+)", re.I)),
    ("lever", re.compile(r"api\.lever\.co/v0/postings/([a-z0-9_.-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-z0-9_.%-]+)", re.I)),
    ("ashby", re.compile(r"posting-api/job-board/([a-z0-9_.%-]+)", re.I)),
]
_IGNORE_TOKENS = {"embed", "js", "v1", "boards", "api", "jobs", "job_board", "static", "assets"}


def find_board_in_html(html: str) -> tuple[str, str] | None:
    """First job board link found on a careers page, e.g. ('greenhouse', 'stripe')."""
    for ats, rx in _BOARD_PATTERNS:
        for m in rx.finditer(html or ""):
            token = m.group(1).strip("/").lower()
            if token and token not in _IGNORE_TOKENS:
                return ats, token
    return None


def guess_tokens(domain: str, company: str = "") -> list[str]:
    label = normalise_domain(domain).split(".")[0] if domain else ""
    cands = [label, label.replace("-", ""), re.sub(r"[^a-z0-9]", "", (company or "").lower())]
    return [c for c in dict.fromkeys(cands) if c]


def fetch_jobs(http: Http, ats: str, token: str) -> list[dict] | None:
    """Normalised jobs, or None if the board does not exist."""
    if ats == "greenhouse":
        r = http.request("GET", f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"})
        if r.status_code != 200:
            return None
        return [normalise_greenhouse(j) for j in r.json().get("jobs", [])]
    if ats == "lever":
        r = http.request("GET", f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
        if r.status_code != 200 or not isinstance(r.json(), list):
            return None
        return [normalise_lever(j) for j in r.json()]
    if ats == "ashby":
        r = http.request("GET", f"https://api.ashbyhq.com/posting-api/job-board/{token}")
        if r.status_code != 200 or "jobs" not in r.json():
            return None
        return [normalise_ashby(j) for j in r.json().get("jobs", []) if j.get("isListed", True)]
    raise ValueError(f"unknown ATS {ats}")


def _job(id_, title, department, location, posted, url, text, remote=None) -> dict:
    dt = parse_dt(posted)
    return {"id": str(id_), "title": (title or "").strip(), "department": department or "",
            "location": location or "", "posted_at": dt.isoformat() if dt else "", "url": url or "",
            "text": text or "", "remote": remote}


def normalise_greenhouse(j: dict) -> dict:
    deps = ", ".join(d.get("name", "") for d in j.get("departments") or [])
    return _job(j.get("id"), j.get("title"), deps, (j.get("location") or {}).get("name"),
                j.get("first_published") or j.get("updated_at"), j.get("absolute_url"), strip_html(j.get("content", "")))


def normalise_lever(j: dict) -> dict:
    cats = j.get("categories") or {}
    text = " ".join(filter(None, [j.get("descriptionPlain"), j.get("additionalPlain"),
                                  " ".join(strip_html(l.get("content", "")) for l in j.get("lists") or [])]))
    return _job(j.get("id"), j.get("text"), cats.get("department") or cats.get("team"), cats.get("location"),
                j.get("createdAt"), j.get("hostedUrl"), text, j.get("workplaceType") == "remote")


def normalise_ashby(j: dict) -> dict:
    dep = " / ".join(filter(None, [j.get("department"), j.get("team")]))
    return _job(j.get("id"), j.get("title"), dep, j.get("location"), j.get("publishedAt"), j.get("jobUrl"),
                j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", "")), j.get("isRemote"))


def detect_board(http: Http, account: dict, try_careers_page: bool = True) -> tuple[str, str, list[dict]] | None:
    """Find the account's job board: explicit columns, careers page links, then name guesses."""
    ats, token = (account.get("ats") or "").lower(), account.get("board") or ""
    if ats in ATS and token:
        jobs = fetch_jobs(http, ats, token)
        return (ats, token, jobs) if jobs is not None else None
    domain = account.get("domain", "")
    if try_careers_page and domain:
        for path in ("/careers", "/jobs", "/company/careers", ""):
            try:
                r = http.request("GET", f"https://{domain}{path}", timeout=15)
            except Exception:
                continue
            if r.status_code < 400:
                found = find_board_in_html(r.text)
                if found:
                    jobs = fetch_jobs(http, *found)
                    if jobs is not None:
                        return found[0], found[1], jobs
    for token in guess_tokens(domain, account.get("company", "")):
        for ats in ATS:
            try:
                jobs = fetch_jobs(http, ats, token)
            except Exception:
                jobs = None
            if jobs:  # a guessed board must actually have jobs
                return ats, token, jobs
    return None
