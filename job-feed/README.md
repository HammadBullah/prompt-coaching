# 📬 Job Feed — hourly UK tech job scraper

Automated feed of junior/graduate-friendly UK tech jobs (Python, AI/ML, Flutter, web, full-stack),
scored against Hammad's profile: **MSc Advanced Computer Science, UK Graduate visa (no sponsorship needed)**.

## What's inside

| File | Purpose |
|---|---|
| `config.json` | Keywords, scoring rules, optional Adzuna API keys |
| `scraper.py` | **Hourly scraper** (stdlib only) — runs on your machine / VPS / GitHub Actions |
| `process_batches.py` | Dedupe + scoring engine → updates CSV, Markdown feed, dashboard data |
| `dashboard.py` + `index.html` | Local live dashboard (search + filters), `python3 job-feed/dashboard.py` |
| `inbox/` | Drop-zone for raw batches (auto-processed and archived) |
| `data/jobs.json` | All jobs ever seen (powers the dashboard) |
| `data/all_jobs.csv` | Spreadsheet export of everything |
| `out/jobs_feed.md` | Human-readable "new jobs" log, newest batch at top |

## Where the jobs come from (public APIs/RSS, polite hourly polling)

Jobicy (UK remote) · Arbeitnow (EU/UK) · Remotive · RemoteOK · Python.org Jobs RSS ·
We Work Remotely RSS · **Adzuna** (optional free key — best UK coverage, see below).

## Option 1 — GitHub Actions (fully autonomous, recommended)

1. Copy `job-feed/github-actions-workflow.yml` to `.github/workflows/job-feed-hourly.yml`
   (this sandbox's GitHub token can't push workflow files directly), then merge into `main`
   — scheduled workflows only run from the default branch.
2. *(Optional)* Get a free API key at <https://developer.adzuna.com/>, then add repo
   secrets `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` (Settings → Secrets → Actions).
   This unlocks Adzuna — by far the richest UK board (Reed/Indeed-style listings).
3. Done. Actions scrapes hourly and commits new jobs into `job-feed/data/` + `out/jobs_feed.md`.
   Watch the feed file on GitHub, or enable GitHub Pages / download the CSV anytime.

## Option 2 — run it on your own machine

```bash
# single scrape (cron-friendly)
python3 job-feed/scraper.py --once

# or keep it running, scraping every hour
python3 job-feed/scraper.py --loop
```

Schedule with cron (Linux/macOS):

```cron
0 * * * * cd /path/to/prompt-coaching && python3 job-feed/scraper.py --once >> job-feed/data/cron.log 2>&1
```

or Windows Task Scheduler: action `python job-feed\scraper.py --once`, trigger hourly.

## Option 3 — view the dashboard

```bash
python3 job-feed/dashboard.py 8000
# open http://localhost:8000
```

## Tweak what gets scored as a "strong match"

Edit `config.json → scoring`:
- `role_keywords` — seniority words (junior, graduate, trainee…) — +3 each
- `tech_keywords` — your stack (python, flutter, machine learning…) — +2 each
- `dealbreakers_drop` — titles silently dropped (staff/principal/director…)

## Notes

- LinkedIn/Indeed are **not** scraped directly (their ToS forbid it and they block bots);
  their listings come in via search + Adzuna.
- Dedupe is by normalised *title + company*, so the same role reposted on 3 boards
  appears once.
