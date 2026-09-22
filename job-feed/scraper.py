#!/usr/bin/env python3
"""
Standalone hourly job scraper (stdlib only — no pip installs needed).

This is the version that runs SOMEWHERE WITH INTERNET (your laptop, a VPS,
a Raspberry Pi, or GitHub Actions). It fetches public job APIs/RSS feeds,
drops normalised batches into job-feed/inbox/, then runs process_batches.py
to dedupe and update the CSV / Markdown feed / dashboard data.

Sources (all free, public, polite to poll hourly):
  - Jobicy API        (remote jobs, UK filter)
  - Arbeitnow API     (EU/UK tech jobs)
  - Remotive API      (remote software dev jobs)
  - RemoteOK API      (remote jobs)
  - Python.org Jobs   (RSS — lots of UK Python roles)
  - We Work Remotely  (RSS — programming)
  - Adzuna            (optional, best UK coverage; free API key, see README)

Usage:
  python3 job-feed/scraper.py --once     # single scrape (for cron / Actions)
  python3 job-feed/scraper.py --loop     # scrape, then repeat every hour
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(ROOT, "inbox")
CONFIG = os.path.join(ROOT, "config.json")


def load_config():
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CFG = load_config()
UA = CFG.get("http", {}).get("user_agent", "personal-job-feed/1.0")
TIMEOUT = CFG.get("http", {}).get("timeout_seconds", 30)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def first_text(desc_html):
    """Best-effort plain-text first line of an HTML description."""
    text = re.sub(r"<[^>]+>", "\n", desc_html or "")
    for line in text.splitlines():
        line = clean(line)
        if line:
            return line[:200]
    return ""


# --------------------------------------------------------------------------
# Source adapters — each returns a list of normalised job dicts.
# --------------------------------------------------------------------------

def src_jobicy():
    out = []
    for url in (
        "https://jobicy.com/api/v2/remote-jobs?count=50&geo=uk",
        "https://jobicy.com/api/v2/remote-jobs?count=50&last24=1",
    ):
        try:
            data = json.loads(fetch(url))
        except Exception as e:
            print(f"  ! jobicy {url.split('?')[1] if '?' in url else ''}: {e}")
            continue
        for j in data.get("jobs", []):
            out.append({
                "title": clean(j.get("jobTitle")),
                "company": clean(j.get("companyName")),
                "location": clean(j.get("jobGeo")) or "Remote",
                "url": j.get("url") or "",
                "source": "Jobicy",
                "posted": (j.get("pubDate") or "")[:10],
                "tags": j.get("jobIndustry") or [],
            })
    return out


def src_arbeitnow():
    out = []
    for page in (1, 2):
        try:
            data = json.loads(fetch(f"https://www.arbeitnow.com/api/job-board-api?page={page}"))
        except Exception as e:
            print(f"  ! arbeitnow p{page}: {e}")
            break
        for j in data.get("data", []):
            out.append({
                "title": clean(j.get("title")),
                "company": clean(j.get("company_name")),
                "location": clean(j.get("location")),
                "url": j.get("url") or "",
                "source": "Arbeitnow",
                "posted": (j.get("created_at") or "")[:10],
                "tags": j.get("tags") or [],
            })
    return out


def src_remotive():
    out = []
    try:
        data = json.loads(fetch("https://remotive.com/api/remote-jobs?category=software-dev"))
    except Exception as e:
        print(f"  ! remotive: {e}")
        return out
    for j in data.get("jobs", []):
        out.append({
            "title": clean(j.get("title")),
            "company": clean(j.get("company_name")),
            "location": clean(j.get("candidate_region")) or "Remote",
            "url": j.get("url") or "",
            "source": "Remotive",
            "posted": (j.get("publication_date") or "")[:10],
            "tags": j.get("tags") or [],
        })
    return out


def src_remoteok():
    out = []
    try:
        data = json.loads(fetch("https://remoteok.com/api"))
    except Exception as e:
        print(f"  ! remoteok: {e}")
        return out
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first item is a legal notice
        out.append({
            "title": clean(j.get("position")),
            "company": clean(j.get("company")),
            "location": clean(j.get("location")) or "Remote",
            "url": j.get("url") or f"https://remoteok.com/l/{j.get('id')}",
            "source": "RemoteOK",
            "posted": (j.get("date") or "")[:10],
            "tags": j.get("tags") or [],
        })
    return out


def src_python_org():
    out = []
    try:
        xml = fetch("https://www.python.org/jobs/feed/rss/")
        root = ET.fromstring(xml)
    except Exception as e:
        print(f"  ! python.org: {e}")
        return out
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        desc = item.findtext("description") or ""
        out.append({
            "title": title,
            "company": "",
            "location": first_text(desc),
            "url": link,
            "source": "Python.org Jobs",
            "posted": (clean(item.findtext("pubDate")) or "")[:16],
            "tags": ["python"],
        })
    return out


def src_weworkremotely():
    out = []
    try:
        xml = fetch("https://weworkremotely.com/categories/remote-programming-jobs.rss")
        root = ET.fromstring(xml)
    except Exception as e:
        print(f"  ! weworkremotely: {e}")
        return out
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        company, role = "", title
        if ":" in title:
            company, role = [clean(x) for x in title.split(":", 1)]
        out.append({
            "title": role,
            "company": company,
            "location": "Remote",
            "url": clean(item.findtext("link")),
            "source": "We Work Remotely",
            "posted": (clean(item.findtext("pubDate")) or "")[:16],
            "tags": [],
        })
    return out


def src_adzuna():
    az = CFG.get("adzuna", {})
    app_id = os.environ.get("ADZUNA_APP_ID") or az.get("app_id")
    app_key = os.environ.get("ADZUNA_APP_KEY") or az.get("app_key")
    if not (app_id and app_key):
        return []
    out = []
    what = urllib.parse.quote(az.get("what", "junior python"))
    try:
        url = (
            "https://api.adzuna.com/v1/api/jobs/gb/search/1"
            f"?app_id={app_id}&app_key={app_key}&results_per_page=50"
            f"&what={what}&content-type=application/json"
        )
        data = json.loads(fetch(url))
    except Exception as e:
        print(f"  ! adzuna: {e}")
        return out
    for j in data.get("results", []):
        sal = ""
        if j.get("salary_min"):
            sal = f"£{int(j['salary_min']):,}"
            if j.get("salary_max") and j["salary_max"] != j["salary_min"]:
                sal += f" – £{int(j['salary_max']):,}"
        out.append({
            "title": clean(j.get("title")),
            "company": clean((j.get("company") or {}).get("display_name")),
            "location": clean((j.get("location") or {}).get("display_name")),
            "url": j.get("redirect_url") or "",
            "source": "Adzuna",
            "posted": (j.get("created") or "")[:10],
            "salary": sal,
            "tags": j.get("category", "").split("/")[::-1][:1],
        })
    return out


# --------------------------------------------------------------------------

import urllib.parse  # noqa: E402  (used by src_adzuna)


def run_once():
    os.makedirs(INBOX, exist_ok=True)
    sources = [
        ("jobicy", src_jobicy),
        ("arbeitnow", src_arbeitnow),
        ("remotive", src_remotive),
        ("remoteok", src_remoteok),
        ("python_org", src_python_org),
        ("weworkremotely", src_weworkremotely),
        ("adzuna", src_adzuna),
    ]
    all_jobs, ok = [], []
    for name, fn in sources:
        try:
            jobs = fn()
        except Exception as e:
            print(f"  ! {name} crashed: {e}")
            continue
        if jobs:
            ok.append(f"{name}({len(jobs)})")
            all_jobs.extend(jobs)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    batch_path = os.path.join(INBOX, f"batch_auto_{ts}.json")
    with open(batch_path, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=1)
    print(f"Fetched {len(all_jobs)} raw jobs from {', '.join(ok) or 'no sources'}")
    subprocess.run([sys.executable, os.path.join(ROOT, "process_batches.py")], check=False)


def main():
    p = argparse.ArgumentParser(description="Hourly job feed scraper")
    p.add_argument("--once", action="store_true", help="scrape once and exit (cron / GitHub Actions)")
    p.add_argument("--loop", action="store_true", help="scrape every hour forever")
    args = p.parse_args()
    if args.loop:
        interval = CFG.get("http", {}).get("interval_seconds", 3600)
        while True:
            print(f"--- scrape at {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
            try:
                run_once()
            except Exception as e:
                print(f"run failed: {e}")
            time.sleep(interval)
    else:
        run_once()


if __name__ == "__main__":
    main()
