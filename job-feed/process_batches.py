#!/usr/bin/env python3
"""
Job-feed processor.

Reads batch files from job-feed/inbox/*.json, normalises + dedupes them
against previously seen jobs, then updates:
  - data/jobs.json       (all jobs, newest first — powers the dashboard)
  - data/seen_ids.json   (dedup keys)
  - data/all_jobs.csv    (spreadsheet export)
  - out/jobs_feed.md     (append-only human-readable "new jobs" feed)
  - data/meta.json       (last run timestamp + stats)

Usage:  python3 job-feed/process_batches.py
"""
import csv
import hashlib
import json
import os
import re
import shutil
import urllib.parse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
INBOX = os.path.join(ROOT, "inbox")
OUT = os.path.join(ROOT, "out")
PROCESSED = os.path.join(INBOX, "processed")
CONFIG_PATH = os.path.join(ROOT, "config.json")

JOBS_JSON = os.path.join(DATA, "jobs.json")
SEEN_JSON = os.path.join(DATA, "seen_ids.json")
CSV_PATH = os.path.join(DATA, "all_jobs.csv")
META_JSON = os.path.join(DATA, "meta.json")
FEED_MD = os.path.join(OUT, "jobs_feed.md")


def ensure_dirs():
    for d in (DATA, INBOX, OUT, PROCESSED):
        os.makedirs(d, exist_ok=True)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def norm_key(title, company):
    raw = f"{title} {company}".lower()
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    raw = re.sub(r"\b(junior|graduate|grad|trainee|entry level|remote|hybrid)\b", "", raw)
    return re.sub(r"\s+", " ", raw).strip()


def job_id(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def score_job(job, cfg):
    sc = cfg.get("scoring", {})
    text = " ".join([
        job.get("title", ""),
        job.get("location", ""),
        " ".join(job.get("tags") or []),
    ]).lower()
    score = 0
    for kw in sc.get("role_keywords", []):
        if kw in text:
            score += 3
    for kw in sc.get("tech_keywords", []):
        if kw in text:
            score += 2
    return score


def is_dealbreaker(job, cfg):
    text = (job.get("title", "") + " " + " ".join(job.get("tags") or [])).lower()
    for kw in cfg.get("scoring", {}).get("dealbreakers_drop", []):
        if kw in text:
            return True
    return False


def badge(score):
    if score >= 7:
        return "strong"
    if score >= 4:
        return "good"
    return "other"


# URLs that are *search/listing* pages, not actual job postings.
AGGREGATE_MARKERS = (
    "linkedin.com/jobs/junior-",
    "linkedin.com/jobs/python",
    "linkedin.com/jobs/graduate",
    "linkedin.com/jobs/search",
    "linkedin.com/jobs/software",
    "linkedin.com/jobs/flutter",
)


def is_direct(url):
    """True if the URL points at an actual job posting."""
    u = (url or "").lower()
    if not u:
        return False
    return not any(m in u for m in AGGREGATE_MARKERS)


def search_url_for(title, company):
    """Best-effort link that lands on the real posting: an exact-phrase Google search."""
    q = urllib.parse.quote(f'"{title}" "{company}" job')
    return f"https://www.google.com/search?q={q}"


def fix_links(job):
    """Ensure every job has a usable link; mark whether it's a direct posting."""
    url = job.get("url") or ""
    if is_direct(url):
        job["direct"] = True
    else:
        job["direct"] = False
        job["url"] = search_url_for(job.get("title", ""), job.get("company", ""))
    return job


def migrate_existing(jobs):
    """Backfill direct/search links for jobs stored before this logic existed."""
    changed = False
    for j in jobs:
        if "direct" not in j or (not j.get("direct") and "google.com/search" not in (j.get("url") or "")):
            before = j.get("url")
            fix_links(j)
            if j.get("url") != before:
                changed = True
    return changed


def process():
    ensure_dirs()
    cfg = load_json(CONFIG_PATH, {})
    jobs = load_json(JOBS_JSON, [])
    if migrate_existing(jobs):
        save_json(JOBS_JSON, jobs)
        print("Migrated stored jobs: non-direct links replaced with exact-phrase search links.")
    seen = set(load_json(SEEN_JSON, []))
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d %H:%M UTC")

    new_jobs = []
    batch_files = sorted(
        f for f in os.listdir(INBOX)
        if f.endswith(".json") and os.path.isfile(os.path.join(INBOX, f))
    )
    skipped_dupes = 0
    skipped_senior = 0
    for fname in batch_files:
        path = os.path.join(INBOX, fname)
        batch = load_json(path, [])
        source_default = fname
        for raw in batch:
            title = (raw.get("title") or "").strip()
            company = (raw.get("company") or "Unknown").strip()
            if not title:
                continue
            if is_dealbreaker({"title": title, "tags": raw.get("tags") or []}, cfg):
                skipped_senior += 1
                continue
            key = norm_key(title, company)
            if key in seen:
                skipped_dupes += 1
                continue
            seen.add(key)
            job = {
                "id": job_id(key),
                "title": title,
                "company": company,
                "location": raw.get("location") or "",
                "url": raw.get("url") or "",
                "source": raw.get("source") or source_default,
                "posted": raw.get("posted") or "",
                "salary": raw.get("salary") or "",
                "tags": [t.lower() for t in (raw.get("tags") or [])],
                "first_seen": ts,
            }
            job["score"] = score_job(job, cfg)
            job["badge"] = badge(job["score"])
            fix_links(job)
            new_jobs.append(job)
        shutil.move(path, os.path.join(PROCESSED, fname))

    if not new_jobs:
        save_json(META_JSON, {
            "last_run": ts,
            "new_last_run": 0,
            "total": len(jobs),
            "note": "no new jobs this run",
        })
        print(f"[{ts}] No new jobs (dupes skipped: {skipped_dupes}).")
        return

    new_jobs.sort(key=lambda j: j["score"], reverse=True)
    jobs = new_jobs + jobs
    save_json(JOBS_JSON, jobs)
    save_json(SEEN_JSON, sorted(seen))

    # CSV export
    fields = ["title", "company", "location", "salary", "posted", "source", "badge", "url", "first_seen"]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for j in jobs:
            w.writerow(j)

    # Markdown feed (append newest batch at top of file)
    strong = [j for j in new_jobs if j["badge"] == "strong"]
    lines = [f"\n## 🕐 {ts} — {len(new_jobs)} new jobs ({len(strong)} strong matches)\n"]
    for j in new_jobs:
        bits = [f"**[{j['title']}]({j['url']})**" if j["url"] else f"**{j['title']}**"]
        meta = [j["company"], j["location"], j.get("posted") or "", j.get("salary") or ""]
        bits.append(" · ".join(m for m in meta if m))
        mark = {"strong": "⭐⭐", "good": "⭐", "other": ""}[j["badge"]]
        bits.append(f"[{j['source']}]" + (f" {mark}" if mark else ""))
        lines.append("- " + " — ".join(bits))
    block = "\n".join(lines) + "\n"
    existing = ""
    if os.path.exists(FEED_MD):
        with open(FEED_MD, "r", encoding="utf-8") as f:
            existing = f.read()
    header = "# 📬 Job Feed — UK tech jobs (junior / graduate / Python / AI / Flutter)\n\nAuto-updated. Newest batches at the top.\n"
    if existing.startswith(header):
        existing = existing[len(header):]
    with open(FEED_MD, "w", encoding="utf-8") as f:
        f.write(header + block + existing)

    save_json(META_JSON, {
        "last_run": ts,
        "new_last_run": len(new_jobs),
        "total": len(jobs),
        "dupes_skipped": skipped_dupes,
        "senior_dropped": skipped_senior,
    })

    print(f"[{ts}] +{len(new_jobs)} new jobs ({len(strong)} strong). Total: {len(jobs)}.")
    for j in new_jobs[:10]:
        print(f"   {'⭐⭐' if j['badge']=='strong' else '  '} {j['title']} — {j['company']} ({j['location']})")


if __name__ == "__main__":
    process()
