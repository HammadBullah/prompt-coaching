"""Tiny dependency-free HTTP server: JSON API under /api plus the static front-end."""
import base64
import hmac
import json
import mimetypes
import os
import re
import sys
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import bank, db, parsing, service
from .demo import load_demo, sample_csv_text

mimetypes.add_type("application/manifest+json", ".webmanifest")
STATIC_DIR = os.path.join(db.BASE_DIR, "static")
SPLITS = ("equal", "income", "p1", "p2")
FREQS = ("weekly", "biweekly", "monthly", "quarterly", "yearly")


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def need(body, key, cast=None):
    if key not in body or body[key] in (None, ""):
        raise ApiError(f"Missing field: {key}")
    v = body[key]
    if cast:
        try:
            v = cast(v)
        except (TypeError, ValueError):
            raise ApiError(f"Invalid value for {key}")
    return v


def valid_date(v, key="date"):
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise ApiError(f"Invalid {key} (use YYYY-MM-DD)")


def valid_month(v):
    if not v or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
        raise ApiError("Invalid month (use YYYY-MM)")
    return v


def opt_int(v):
    return None if v in (None, "", "null") else int(v)


# ------------------------------------------------------------------ handlers
# Each handler: (conn, params(dict of url groups), query(dict), body(dict)) -> json-able


def h_bootstrap(conn, p, q, b):
    service.materialize_recurring(conn)
    return {"settings": db.get_settings(conn), "people": db.rows(conn, "SELECT * FROM people ORDER BY id"),
            "categories": db.rows(conn, "SELECT * FROM categories ORDER BY kind DESC, name"),
            "today": date.today().isoformat(), "month": service.current_month(),
            "has_data": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] > 0}


def h_summary(conn, p, q, b):
    service.materialize_recurring(conn)
    return service.summary(conn, valid_month(q.get("month", service.current_month())))


def h_trends(conn, p, q, b):
    return service.trends(conn, valid_month(q.get("month", service.current_month())), int(q.get("n", 6)))


TX_SELECT = """SELECT t.*, c.name AS category_name, c.icon AS category_icon FROM transactions t
               LEFT JOIN categories c ON c.id = t.category_id"""


def h_tx_list(conn, p, q, b):
    where, args = [], []
    if q.get("month"):
        lo, hi = service.month_bounds(valid_month(q["month"]))
        where.append("t.date BETWEEN ? AND ?")
        args += [lo, hi]
    if q.get("q"):
        where.append("(t.description LIKE ? OR t.note LIKE ?)")
        args += [f"%{q['q']}%"] * 2
    if q.get("category_id"):
        where.append("t.category_id = ?")
        args.append(int(q["category_id"]))
    if q.get("person_id") == "joint":
        where.append("t.person_id IS NULL")
    elif q.get("person_id"):
        where.append("t.person_id = ?")
        args.append(int(q["person_id"]))
    if q.get("type"):
        where.append("t.type = ?")
        args.append(q["type"])
    if q.get("uncategorised"):
        where.append("t.category_id IS NULL AND t.type != 'transfer'")
    sql = TX_SELECT + (" WHERE " + " AND ".join(where) if where else "") + \
        " ORDER BY t.date DESC, t.id DESC LIMIT ?"
    return db.rows(conn, sql, args + [int(q.get("limit", 500))])


def tx_fields(conn, body, partial=False):
    out = {}
    if "date" in body or not partial:
        out["date"] = valid_date(need(body, "date"))
    if "amount_cents" in body or not partial:
        out["amount_cents"] = abs(need(body, "amount_cents", int))
    if "description" in body or not partial:
        out["description"] = str(body.get("description", "")).strip()[:300]
    if "note" in body:
        out["note"] = str(body["note"])[:500]
    if "category_id" in body:
        out["category_id"] = opt_int(body["category_id"])
    if "person_id" in body:
        pid = opt_int(body["person_id"])
        if pid not in (None, 1, 2):
            raise ApiError("person_id must be 1, 2 or null (joint)")
        out["person_id"] = pid
    if "split" in body:
        if body["split"] not in SPLITS:
            raise ApiError("Invalid split")
        out["split"] = body["split"]
    if "type" in body:
        if body["type"] not in ("income", "expense", "transfer"):
            raise ApiError("Invalid type")
        out["type"] = body["type"]
    return out


def h_tx_create(conn, p, q, b):
    f = tx_fields(conn, b)
    settings = db.get_settings(conn)
    f.setdefault("split", settings["default_split"])
    f.setdefault("person_id", None)
    f.setdefault("type", "expense")
    if f.get("category_id") is None and f["description"]:
        cid = service.matcher(conn).match(f["description"])
        if cid and service.type_for_category(conn, cid, f["type"]) in (f["type"], "transfer"):
            f["category_id"] = cid
    f["type"] = service.type_for_category(conn, f.get("category_id"), f["type"])
    cols = ", ".join(f)
    cur = conn.execute(f"INSERT INTO transactions ({cols}) VALUES ({', '.join('?' * len(f))})", list(f.values()))
    conn.commit()
    return db.rows(conn, TX_SELECT + " WHERE t.id = ?", (cur.lastrowid,))[0]


def h_tx_update(conn, p, q, b):
    tid = int(p["id"])
    old = conn.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone()
    if not old:
        raise ApiError("Not found", 404)
    f = tx_fields(conn, b, partial=True)
    if "category_id" in f:
        f["type"] = service.type_for_category(conn, f["category_id"], f.get("type", old["type"]))
    if f:
        conn.execute(f"UPDATE transactions SET {', '.join(k + '=?' for k in f)} WHERE id = ?",
                     list(f.values()) + [tid])
    learned = 0
    if b.get("learn") and f.get("category_id"):
        learned = service.learn_rule(conn, f.get("description", old["description"]), f["category_id"])
    conn.commit()
    row = db.rows(conn, TX_SELECT + " WHERE t.id = ?", (tid,))[0]
    row["auto_categorised_others"] = learned
    return row


def h_tx_delete(conn, p, q, b):
    conn.execute("DELETE FROM transactions WHERE id = ?", (int(p["id"]),))
    conn.commit()
    return {"ok": True}


def h_quick(conn, p, q, b):
    people = db.rows(conn, "SELECT id, name FROM people")
    cats = db.rows(conn, "SELECT id, name, kind FROM categories")
    draft = parsing.parse_quick(need(b, "text", str), people, cats, service.matcher(conn),
                                default_person=opt_int(b.get("default_person_id")))
    if not draft["ok"] or b.get("dry_run"):
        return draft
    draft.pop("ok")
    tx = h_tx_create(conn, {}, {}, draft)
    return {"ok": True, "transaction": tx}


def h_import_preview(conn, p, q, b):
    text = need(b, "text", str)
    parsed = parsing.parse_bank_csv(text)
    person_id = opt_int(b.get("person_id"))
    items = service.classify_import_rows(conn, parsed["rows"], person_id)
    return {"columns": parsed["columns"], "skipped": parsed["skipped"], "warnings": parsed["warnings"],
            "rows": items,
            "counts": {"new": sum(i["status"] == "new" for i in items),
                       "duplicate": sum(i["status"] == "duplicate" for i in items),
                       "matches_bill": sum(i["status"] == "matches_bill" for i in items),
                       "uncategorised": sum(i["category_id"] is None and i["type"] != "transfer"
                                            and i["status"] != "duplicate" for i in items)}}


def h_import_commit(conn, p, q, b):
    person_id = opt_int(b.get("person_id"))
    if person_id not in (None, 1, 2):
        raise ApiError("Invalid person")
    split = b.get("default_split") or db.get_settings(conn)["default_split"]
    res = service.commit_import(conn, need(b, "rows", list), person_id, split)
    # learn from categories the user picked during review
    learned = 0
    for it in b["rows"]:
        if it.get("learn") and it.get("category_id") and not it.get("skip"):
            service.learn_rule(conn, it["description"], int(it["category_id"]))
            learned += 1
    service.recategorize_uncategorized(conn)
    res["rules_learned"] = learned
    res["suggestions"] = len(service.detect_recurring(conn))
    return res


# recurring ----------------------------------------------------------------

def rec_fields(body, partial=False):
    out = {}
    if "name" in body or not partial:
        out["name"] = str(need(body, "name")).strip()[:100]
    if "type" in body or not partial:
        out["type"] = need(body, "type")
        if out["type"] not in ("income", "expense"):
            raise ApiError("type must be income or expense")
    if "amount_cents" in body or not partial:
        out["amount_cents"] = abs(need(body, "amount_cents", int))
    if "frequency" in body or not partial:
        out["frequency"] = need(body, "frequency")
        if out["frequency"] not in FREQS:
            raise ApiError("Invalid frequency")
    if "start_date" in body or not partial:
        out["start_date"] = valid_date(need(body, "start_date"), "start_date")
    if "end_date" in body:
        out["end_date"] = valid_date(body["end_date"], "end_date") if body["end_date"] else None
    if "category_id" in body:
        out["category_id"] = opt_int(body["category_id"])
    if "person_id" in body:
        out["person_id"] = opt_int(body["person_id"])
    if "split" in body:
        if body["split"] not in SPLITS:
            raise ApiError("Invalid split")
        out["split"] = body["split"]
    if "active" in body:
        out["active"] = 1 if body["active"] else 0
    if "last_generated" in body:
        out["last_generated"] = body["last_generated"] or None
    return out


def h_rec_list(conn, p, q, b):
    service.materialize_recurring(conn)
    data = service.recurring_overview(conn)
    data["upcoming"] = service.upcoming(conn, int(q.get("days", 30)))
    return data


def h_rec_create(conn, p, q, b):
    f = rec_fields(b)
    f.setdefault("split", db.get_settings(conn)["default_split"])
    if b.get("mark_generated_until"):
        f["last_generated"] = valid_date(b["mark_generated_until"])
    cur = conn.execute(f"INSERT INTO recurring ({', '.join(f)}) VALUES ({', '.join('?' * len(f))})",
                       list(f.values()))
    rid = cur.lastrowid
    for tid in b.get("link_tx_ids", []):          # attach history found by the detector
        conn.execute("UPDATE transactions SET recurring_id = ? WHERE id = ?", (rid, int(tid)))
    conn.commit()
    service.materialize_recurring(conn)
    return {"id": rid}


def h_rec_update(conn, p, q, b):
    f = rec_fields(b, partial=True)
    if f:
        conn.execute(f"UPDATE recurring SET {', '.join(k + '=?' for k in f)} WHERE id = ?",
                     list(f.values()) + [int(p["id"])])
        conn.commit()
    return {"ok": True}


def h_rec_delete(conn, p, q, b):
    conn.execute("UPDATE transactions SET recurring_id = NULL WHERE recurring_id = ?", (int(p["id"]),))
    conn.execute("DELETE FROM recurring WHERE id = ?", (int(p["id"]),))
    conn.commit()
    return {"ok": True}


def h_rec_suggestions(conn, p, q, b):
    return service.detect_recurring(conn)


# goals --------------------------------------------------------------------

def h_goals(conn, p, q, b):
    return service.goals_overview(conn)


def goal_fields(body, partial=False):
    out = {}
    if "name" in body or not partial:
        out["name"] = str(need(body, "name")).strip()[:100]
    if "target_cents" in body or not partial:
        out["target_cents"] = need(body, "target_cents", int)
        if out["target_cents"] <= 0:
            raise ApiError("Target must be greater than 0")
    if "deadline" in body:
        out["deadline"] = valid_date(body["deadline"], "deadline") if body["deadline"] else None
    if "priority" in body:
        out["priority"] = max(1, min(3, int(body["priority"])))
    for k in ("icon", "note"):
        if k in body:
            out[k] = str(body[k])[:300]
    return out


def h_goal_create(conn, p, q, b):
    f = goal_fields(b)
    cur = conn.execute(f"INSERT INTO goals ({', '.join(f)}) VALUES ({', '.join('?' * len(f))})", list(f.values()))
    gid = cur.lastrowid
    if b.get("saved_cents"):
        conn.execute("INSERT INTO goal_contributions (goal_id, date, amount_cents, note) VALUES (?,?,?,?)",
                     (gid, date.today().isoformat(), int(b["saved_cents"]), "Already saved"))
    conn.commit()
    return {"id": gid}


def h_goal_update(conn, p, q, b):
    f = goal_fields(b, partial=True)
    if f:
        conn.execute(f"UPDATE goals SET {', '.join(k + '=?' for k in f)} WHERE id = ?", list(f.values()) + [int(p["id"])])
        conn.commit()
    return {"ok": True}


def h_goal_delete(conn, p, q, b):
    conn.execute("DELETE FROM goals WHERE id = ?", (int(p["id"]),))
    conn.commit()
    return {"ok": True}


def h_contrib_create(conn, p, q, b):
    gid = int(p["id"])
    if not conn.execute("SELECT 1 FROM goals WHERE id = ?", (gid,)).fetchone():
        raise ApiError("Goal not found", 404)
    conn.execute("INSERT INTO goal_contributions (goal_id, date, amount_cents, person_id, note) VALUES (?,?,?,?,?)",
                 (gid, valid_date(b.get("date") or date.today().isoformat()), need(b, "amount_cents", int),
                  opt_int(b.get("person_id")), str(b.get("note", ""))[:200]))
    conn.commit()
    return {"ok": True}


def h_contribs(conn, p, q, b):
    return db.rows(conn, "SELECT * FROM goal_contributions WHERE goal_id = ? ORDER BY date DESC, id DESC",
                   (int(p["id"]),))


def h_contrib_delete(conn, p, q, b):
    conn.execute("DELETE FROM goal_contributions WHERE id = ?", (int(p["id"]),))
    conn.commit()
    return {"ok": True}


def h_sweep(conn, p, q, b):
    return {"moved": service.sweep_to_goals(conn, valid_month(b.get("month") or service.current_month()))}


# categories / rules / settings --------------------------------------------

def h_cat_update(conn, p, q, b):
    sets, args = [], []
    if "name" in b:
        sets.append("name=?"); args.append(str(b["name"]).strip())
    if "budget_cents" in b:
        sets.append("budget_cents=?"); args.append(opt_int(b["budget_cents"]) or None)
    if "bucket" in b and b["bucket"] in ("needs", "wants", "none"):
        sets.append("bucket=?"); args.append(b["bucket"])
    if "icon" in b:
        sets.append("icon=?"); args.append(str(b["icon"])[:4])
    if sets:
        conn.execute(f"UPDATE categories SET {', '.join(sets)} WHERE id=?", args + [int(p["id"])])
        conn.commit()
    return {"ok": True}


def h_cat_create(conn, p, q, b):
    kind = b.get("kind", "expense")
    if kind not in ("income", "expense"):
        raise ApiError("Invalid kind")
    try:
        cur = conn.execute("INSERT INTO categories (name, kind, bucket, icon, budget_cents) VALUES (?,?,?,?,?)",
                           (str(need(b, "name")).strip(), kind, b.get("bucket", "wants" if kind == "expense" else "none"),
                            str(b.get("icon", "📦"))[:4], opt_int(b.get("budget_cents")) or None))
    except Exception:
        raise ApiError("A category with that name already exists")
    conn.commit()
    return {"id": cur.lastrowid}


def h_cat_delete(conn, p, q, b):
    conn.execute("DELETE FROM categories WHERE id = ?", (int(p["id"]),))
    conn.commit()
    return {"ok": True}


def h_rules(conn, p, q, b):
    return db.rows(conn, "SELECT r.id, r.pattern, r.category_id, c.name AS category_name FROM rules r "
                         "JOIN categories c ON c.id = r.category_id ORDER BY c.name, r.pattern")


def h_rule_create(conn, p, q, b):
    conn.execute("INSERT INTO rules (pattern, category_id) VALUES (?,?) ON CONFLICT(pattern) DO UPDATE SET "
                 "category_id = excluded.category_id", (str(need(b, "pattern")).strip().lower(), need(b, "category_id", int)))
    conn.commit()
    return {"applied": service.recategorize_uncategorized(conn)}


def h_rule_delete(conn, p, q, b):
    conn.execute("DELETE FROM rules WHERE id = ?", (int(p["id"]),))
    conn.commit()
    return {"ok": True}


def h_settings_update(conn, p, q, b):
    for k in ("currency", "locale", "default_split", "setup_done"):
        if k in b:
            if k == "default_split" and b[k] not in ("equal", "income"):
                raise ApiError("default_split must be equal or income")
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, str(b[k])))
    for person in b.get("people", []):
        conn.execute("UPDATE people SET name = ?, color = ? WHERE id = ?",
                     (str(person["name"]).strip()[:30] or "Person", str(person.get("color", "#888"))[:9], int(person["id"])))
    conn.commit()
    return h_bootstrap(conn, p, q, b)


def h_export(conn, p, q, b):
    tables = ["settings", "people", "categories", "transactions", "recurring", "rules", "goals", "goal_contributions"]
    return {t: db.rows(conn, f"SELECT * FROM {t}") for t in tables}


def h_demo(conn, p, q, b):
    if conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] and not b.get("force"):
        raise ApiError("You already have data. Reset first if you want demo data.", 409)
    load_demo(conn)
    return {"ok": True}



# bank sync ----------------------------------------------------------------

def bank_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except bank.BankError as e:
        raise ApiError(str(e), e.status if e.status in (400, 404, 409, 429) else 502 if e.status >= 500 else 400)


def h_bank_status(conn, p, q, b):
    return bank.status(conn)


def h_bank_config(conn, p, q, b):
    bank_call(bank.save_config, conn, b.get("app_id"), b.get("private_key"), b.get("redirect_url"), b.get("sync_hours"))
    return bank.status(conn)


def h_bank_banks(conn, p, q, b):
    return bank_call(bank.list_banks, conn, q.get("country", "NL"))


def h_bank_connect(conn, p, q, b):
    pid = opt_int(b.get("person_id"))
    if pid not in (None, 1, 2):
        raise ApiError("Invalid person")
    return bank_call(bank.begin_connect, conn, pid, need(b, "bank", str), need(b, "country", str), b.get("max_days"))


def h_bank_finish(conn, p, q, b):
    cid = bank_call(bank.finish_connect, conn, need(b, "redirect", str))
    try:
        result = bank.sync_all(conn, full=True, only_conn=cid)
    except bank.BankError as e:
        result = [{"error": str(e)}]
    return {"connection_id": cid, "sync": result}


def h_bank_sync(conn, p, q, b):
    results = bank_call(bank.sync_all, conn, bool(b.get("full")))
    return {"results": results, "added": sum(r.get("added", 0) for r in results),
            "suggestions": len(service.detect_recurring(conn))}


def h_bank_disconnect(conn, p, q, b):
    bank.disconnect(conn, int(p["id"]))
    return {"ok": True}


def h_ingest(conn, p, q, b):
    """Webhook for iPhone Shortcuts / Android automations: one payment in, token-protected."""
    data = {**q, **b}
    token = db.get_settings(conn).get("ingest_token", "")
    if not token or not hmac.compare_digest(str(data.get("token", "")), token):
        raise ApiError("Invalid token", 403)
    people_list = db.rows(conn, "SELECT id, name FROM people")
    pid = opt_int(data.get("person_id")) if data.get("person_id") not in (None, "") else None
    who = str(data.get("person", "")).strip().lower()
    if pid is None and who:
        pid = next((x["id"] for x in people_list if x["name"].lower() == who), None)
    if data.get("text"):
        draft = parsing.parse_quick(str(data["text"]), people_list, db.rows(conn, "SELECT id, name, kind FROM categories"),
                                    service.matcher(conn), default_person=pid)
        if not draft["ok"]:
            raise ApiError(draft["error"])
        draft.pop("ok")
    else:
        amount = parsing.parse_amount(data.get("amount"))
        if amount is None:
            raise ApiError("Missing or invalid amount")
        draft = {"date": parsing.parse_date(data.get("date")) or date.today().isoformat(),
                 "type": "income" if str(data.get("type", "")).lower() == "income" else "expense",
                 "amount_cents": abs(parsing.to_cents(amount)), "description": str(data.get("merchant") or data.get("description") or "Payment")[:200],
                 "person_id": pid}
    tx = h_tx_create(conn, {}, {}, draft)
    return {"ok": True, "transaction": {k: tx[k] for k in ("id", "date", "amount_cents", "description", "category_name")}}


def h_sample(conn, p, q, b):
    return {"text": sample_csv_text()}


def h_reset(conn, p, q, b):
    if b.get("confirm") != "DELETE":
        raise ApiError("Send {\"confirm\": \"DELETE\"} to wipe all transactions, bills and goals.")
    for t in ["goal_contributions", "goals", "transactions", "recurring"]:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
    return {"ok": True}


ROUTES = [
    ("GET", r"/api/bootstrap", h_bootstrap),
    ("GET", r"/api/summary", h_summary),
    ("GET", r"/api/trends", h_trends),
    ("GET", r"/api/transactions", h_tx_list),
    ("POST", r"/api/transactions", h_tx_create),
    ("PATCH", r"/api/transactions/(?P<id>\d+)", h_tx_update),
    ("DELETE", r"/api/transactions/(?P<id>\d+)", h_tx_delete),
    ("POST", r"/api/quick", h_quick),
    ("POST", r"/api/import/preview", h_import_preview),
    ("POST", r"/api/import/commit", h_import_commit),
    ("GET", r"/api/recurring", h_rec_list),
    ("GET", r"/api/recurring/suggestions", h_rec_suggestions),
    ("POST", r"/api/recurring", h_rec_create),
    ("PATCH", r"/api/recurring/(?P<id>\d+)", h_rec_update),
    ("DELETE", r"/api/recurring/(?P<id>\d+)", h_rec_delete),
    ("GET", r"/api/goals", h_goals),
    ("POST", r"/api/goals", h_goal_create),
    ("POST", r"/api/goals/sweep", h_sweep),
    ("PATCH", r"/api/goals/(?P<id>\d+)", h_goal_update),
    ("DELETE", r"/api/goals/(?P<id>\d+)", h_goal_delete),
    ("GET", r"/api/goals/(?P<id>\d+)/contributions", h_contribs),
    ("POST", r"/api/goals/(?P<id>\d+)/contributions", h_contrib_create),
    ("DELETE", r"/api/contributions/(?P<id>\d+)", h_contrib_delete),
    ("POST", r"/api/categories", h_cat_create),
    ("PATCH", r"/api/categories/(?P<id>\d+)", h_cat_update),
    ("DELETE", r"/api/categories/(?P<id>\d+)", h_cat_delete),
    ("GET", r"/api/rules", h_rules),
    ("POST", r"/api/rules", h_rule_create),
    ("DELETE", r"/api/rules/(?P<id>\d+)", h_rule_delete),
    ("PUT", r"/api/settings", h_settings_update),
    ("GET", r"/api/export", h_export),
    ("POST", r"/api/demo", h_demo),
    ("GET", r"/api/sample-csv", h_sample),
    ("GET", r"/api/bank/status", h_bank_status),
    ("PUT", r"/api/bank/config", h_bank_config),
    ("GET", r"/api/bank/banks", h_bank_banks),
    ("POST", r"/api/bank/connect", h_bank_connect),
    ("POST", r"/api/bank/finish", h_bank_finish),
    ("POST", r"/api/bank/sync", h_bank_sync),
    ("DELETE", r"/api/bank/connections/(?P<id>\d+)", h_bank_disconnect),
    ("GET", r"/api/ingest", h_ingest),
    ("POST", r"/api/ingest", h_ingest),
    ("POST", r"/api/reset", h_reset),
]
COMPILED = [(m, re.compile("^" + pat + "$"), fn) for m, pat, fn in ROUTES]


class Handler(BaseHTTPRequestHandler):
    server_version = "CoupleFinance/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("CF_QUIET") != "1":
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, payload, ctype="application/json; charset=utf-8", extra=None):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self, url):
        pw = os.environ.get("CF_PASSWORD")
        if not pw or url.path == "/api/ingest":        # the webhook has its own token
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(header[6:]).decode().partition(":")
                if hmac.compare_digest(given, pw):
                    return True
            except Exception:
                pass
        self._send(401, {"error": "Password required"}, extra={"WWW-Authenticate": 'Basic realm="Couple Finance"'})
        return False

    def _callback(self, url):
        """Bank redirect target when the app itself is reachable over https."""
        conn = db.connect()
        try:
            bank.finish_connect(conn, "?" + url.query)
            msg, target = "Bank connected! Redirecting…", "/#bank"
            try:
                bank.sync_all(conn, full=True)
            except bank.BankError:
                pass
        except bank.BankError as e:
            msg, target = f"Could not connect: {e}", "/#bank"
        finally:
            conn.close()
        page = (f'<meta charset="utf-8"><meta http-equiv="refresh" content="3;url={target}">'
                f'<body style="font:16px system-ui;padding:40px"><p>{msg}</p><p><a href="{target}">Back to the app</a></p>')
        self._send(200, page.encode(), "text/html; charset=utf-8")

    def _dispatch(self, method):
        url = urlparse(self.path)
        if not self._authorised(url):
            return
        if url.path == "/callback" and method == "GET":
            return self._callback(url)
        if url.path.startswith("/api/"):
            return self._api(method, url)
        if method != "GET":
            return self._send(405, {"error": "Method not allowed"})
        rel = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send(404, {"error": "Not found"})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype else ""))

    def _api(self, method, url):
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        body = {}
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "Invalid JSON"})
        path_matched = False
        for m, rx, fn in COMPILED:
            mo = rx.match(url.path)
            if not mo:
                continue
            path_matched = True
            if m != method:
                continue
            conn = db.connect()
            try:
                result = fn(conn, mo.groupdict(), q, body)
                extra = {}
                if url.path == "/api/export":
                    extra["Content-Disposition"] = 'attachment; filename="couple-finance-backup.json"'
                return self._send(200, result, extra=extra)
            except ApiError as e:
                return self._send(e.status, {"error": str(e)})
            except (ValueError, KeyError, TypeError) as e:
                return self._send(400, {"error": f"Bad request: {e}"})
            except Exception as e:                      # never drop the connection without an answer
                sys.stderr.write(f"Unexpected error on {method} {url.path}: {e!r}\n")
                return self._send(500, {"error": "Something went wrong on the server. Check the terminal for details."})
            finally:
                conn.close()
        self._send(405 if path_matched else 404, {"error": "Not found"})

    def do_GET(self): self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def do_PATCH(self): self._dispatch("PATCH")
    def do_PUT(self): self._dispatch("PUT")
    def do_DELETE(self): self._dispatch("DELETE")


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    conn = db.connect()
    db.init_db(conn)
    conn.close()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Couple Finance running on http://{host}:{port}  (data: {db.DB_PATH})")
    if host not in ("127.0.0.1", "localhost") and not os.environ.get("CF_PASSWORD"):
        print("WARNING: listening on the network without a password. Set CF_PASSWORD=... to protect your data.")
    stop = threading.Event()
    threading.Thread(target=bank.background_loop, args=(stop,), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")
    finally:
        stop.set()


if __name__ == "__main__":
    main()
