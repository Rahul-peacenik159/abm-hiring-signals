"""python -m hiring_signals run --accounts sample-data/accounts.csv
python -m hiring_signals summary out"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import analyze, ats
from .common import Http, Snapshots, load_yaml, read_accounts, score_rows, summary_or_note as summary_markdown, write_outputs

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_FIELDS = ["account_domain", "company", "score", "top_play", "ats", "board", "open_roles", "new_roles",
                  "new_target_roles", "leadership_roles", "keywords_found", "competitors_found",
                  "top_functions", "errors"]


def cmd_run(args) -> None:
    rules = analyze.Rules(load_yaml(args.config))
    accounts = read_accounts(args.accounts, args.domains)
    if not accounts:
        sys.exit("No accounts: pass --accounts file.csv (domain, optional ats + board columns) or --domains")
    http = Http("abm-hiring-signals/0.1 (+https://github.com/Rahul-peacenik159/abm-hiring-signals)",
                min_interval=args.delay)
    snaps = Snapshots(args.out, "jobs")
    recent = args.recent_days or rules.cfg.get("recent_days", 30)
    all_rows, summaries, errors = [], [], 0
    print(f"Checking job boards for {len(accounts)} accounts")
    for i, acc in enumerate(accounts, 1):
        domain = acc["domain"] or acc.get("company", "")
        base = {"account_domain": domain, "company": acc.get("company", "")}
        try:
            found = ats.detect_board(http, acc, try_careers_page=not args.no_detect)
        except Exception as exc:  # network trouble for one account never stops the run
            found, err = None, f"{type(exc).__name__}: {exc}"[:200]
        else:
            err = "" if found else "no public Greenhouse/Lever/Ashby board found (add ats + board columns)"
        if not found:
            errors += 1
            summaries.append({**base, "score": 0, "errors": err})
            print(f"  [{i}/{len(accounts)}] --  {domain:<30} {err[:60]}")
            continue
        ats_name, board, jobs = found
        rows, summary, keys = analyze.analyse_account(domain, jobs, rules, snaps.seen_before(domain), recent,
                                                      ats_name, board)
        snaps.record(domain, keys)
        score, play = score_rows(rows)
        summaries.append({**base, **summary, "score": score, "top_play": play, "errors": ""})
        all_rows += rows
        print(f"  [{i}/{len(accounts)}] ok  {domain:<30} {ats_name}:{board:<18} roles={len(jobs):<4} "
              f"new={summary['new_roles']:<3} score={score}")

    stamp = snaps.save()
    new_items = sum(1 for r in all_rows if r["signal_type"] == "new_role")
    out = write_outputs(args.out, all_rows, summaries, SUMMARY_FIELDS, {
        "repo": "abm-hiring-signals", "run_at": stamp, "accounts": len(accounts), "errors": errors,
        "previous_run": snaps.previous_name, "new_items": new_items,
        "new_means": "new since previous run" if snaps.previous_name else f"posted in the last {recent} days"})
    print(f"\nWrote {len(all_rows)} signals to {out}/ (accounts_summary.csv, signals.csv, signals.jsonl)")


def cmd_summary(args) -> None:
    cols = [("account_domain", "Account"), ("score", "Score"), ("top_play", "Top play"), ("ats", "ATS"),
            ("open_roles", "Open roles"), ("new_target_roles", "New target roles"),
            ("leadership_roles", "Leadership roles"), ("keywords_found", "Keywords"),
            ("competitors_found", "Competitors"), ("top_functions", "Top functions"), ("errors", "Errors")]
    print(summary_markdown(Path(args.out) / "accounts_summary.csv", cols, "Hiring signals"))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="hiring_signals", description="Hiring signals from public job boards")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="check job boards and write signals")
    r.add_argument("--accounts", help="CSV with domain (and optional company, ats, board) columns")
    r.add_argument("--domains", nargs="*", help="domains on the command line")
    r.add_argument("--config", default=str(ROOT / "config" / "rules.yaml"))
    r.add_argument("--out", default="out")
    r.add_argument("--recent-days", type=int, help="first run: jobs posted within N days count as new")
    r.add_argument("--no-detect", action="store_true", help="don't read careers pages to find the board")
    r.add_argument("--delay", type=float, default=0.5, help="seconds between requests to the same host")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("summary", help="markdown table of the last run")
    s.add_argument("out", nargs="?", default="out")
    s.set_defaults(func=cmd_summary)
    args = ap.parse_args(argv)
    args.func(args)
