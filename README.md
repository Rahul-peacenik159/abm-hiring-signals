# abm-hiring-signals

**Find accounts that are hiring for the problem you solve: new leaders, new teams, tools named in job posts, and competitors they already use. Free, from public job boards.**

Job posts are the most honest buying signal there is. A company hiring a "VP of Revenue Operations" or a "Founding Security Engineer" is about to buy tools, and the job description often names the tools they use today.

This repo reads the public job board APIs of **Greenhouse, Lever and Ashby** (no keys, no scraping), classifies every role, and turns what changed into scored ABM signals.

## What it finds

| Signal | Meaning | Default play |
|---|---|---|
| `leadership_hire` | New VP / Head / Director role in a function you sell to | `new_leader_first_90_days` |
| `first_hire_in_function` | A function that had no open roles last run, or a "Founding/First ..." title | `first_hire_window` |
| `hiring_spike` | 5+ new roles in your target functions | `team_buildout` |
| `competitor_in_job` | Job text names a competitor's product (they use it today) | `competitive_displacement` |
| `keyword_in_job` | Job text names a tool or initiative you care about | `initiative_match` |
| `new_role` | Each new role in a target function | `role_based_outreach` |
| `open_roles` | Total open roles, by function (info) | |

"New" means **new since the previous run**. On the very first run it means posted in the last 30 days (`--recent-days`).

## Quickstart (5 minutes, no keys)

```bash
git clone https://github.com/Rahul-peacenik159/abm-hiring-signals.git
cd abm-hiring-signals
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m hiring_signals run --accounts sample-data/accounts.csv
```

Open `out/accounts_summary.csv` in Google Sheets: one row per account with score, top play, leadership roles, keywords and competitors found. Every signal with its job link is in `out/signals.csv`.

**Your accounts:** a CSV with a `domain` column. Optional `ats` (`greenhouse` / `lever` / `ashby`) and `board` (the token in the board URL, e.g. `stripe` in `job-boards.greenhouse.io/stripe`) columns make it exact. Without them the tool reads the company's `/careers` page to find the board link, then tries the company name on each job board.

**Your product:** edit the `seller:` block in [`config/rules.yaml`](config/rules.yaml): target functions, keywords, competitors. Role families and weights are there too.

## Run it on GitHub (no installs)

**Actions** tab > **run** > **Run workflow** > pick the account list (or type domains) > **Run**. The results table appears on the run's Summary page; the CSVs are in the **results** artifact. Each run remembers the last one, so re-runs report only new roles. Uncomment the `schedule:` block in `.github/workflows/run.yml` for a weekly run.

> Public repo = public run results. Keep real prospect lists in a **private** copy (GitHub: + > Import repository > Private).

## n8n

[`n8n/hiring-signals-weekly.json`](n8n/hiring-signals-weekly.json): weekly trigger > accounts (with `ats` + `board`) > job board API > classify and score > BigQuery `abm.signals`. The classification code is also in [`n8n/classify-node.js`](n8n/classify-node.js).

## BigQuery

Load each run's `out/signals.jsonl` into the shared `abm.signals` table, then [`bigquery/10_hiring_trends.sql`](bigquery/10_hiring_trends.sql) shows hiring momentum per account and function over the last 4 weeks vs the previous 12.

## Limits and good manners

- Only companies that use Greenhouse, Lever or Ashby with a public board are covered (most venture-backed tech companies do; many enterprises use Workday or iCIMS, which aren't covered).
- Classification is keyword-based on job titles. Check the `evidence` before you quote a role in outreach.
- The tool waits between requests (`--delay`, default 0.5 s per host). Keep it that way.
- Company-level output only. No candidate or employee data is collected.

## Part of the open ABM bundles

Every repo writes the same `signals` format, so you can load them into one table or combine them with abm-activation-kit.

| Repo | What it adds |
|---|---|
| [abm-tech-footprint](https://github.com/Rahul-peacenik159/abm-tech-footprint) | what accounts run on their website, DNS and email; security and email posture |
| **abm-hiring-signals** (this repo) | who is hiring for what (Greenhouse, Lever, Ashby public job boards) |
| [abm-public-company-triggers](https://github.com/Rahul-peacenik159/abm-public-company-triggers) | SEC filings: exec changes, M&A, restructuring, keyword mentions, revenue trend |
| [abm-news-pulse](https://github.com/Rahul-peacenik159/abm-news-pulse) | news events per account from GDELT (funding, M&A, launches, leadership, layoffs) |
| [abm-tam-builder](https://github.com/Rahul-peacenik159/abm-tam-builder) | build the account universe from Wikidata, OpenStreetMap and US Census data |
| [abm-dev-community-signals](https://github.com/Rahul-peacenik159/abm-dev-community-signals) | which companies' engineers engage with your or competitors' GitHub repos; HN mentions |
| [abm-market-timing](https://github.com/Rahul-peacenik159/abm-market-timing) | topic and region demand: Wikipedia attention, news volume, Google Trends in BigQuery |
| [abm-public-sector-buyers](https://github.com/Rahul-peacenik159/abm-public-sector-buyers) | government buyers: USAspending awards, incumbents, SAM.gov open opportunities |
| [abm-activation-kit](https://github.com/Rahul-peacenik159/abm-activation-kit) | combine all signals, score, and push to HubSpot, LinkedIn audiences and 1:1 pages |

## License

Apache-2.0. Job data belongs to the companies that published it; this tool only reads their public job board APIs.
