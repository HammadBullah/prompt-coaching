"""Automatic bank sync through Enable Banking (free "Restricted Production" for your own accounts).

Flow: sign JWT (RS256) -> POST /auth -> user approves at the bank -> redirect with ?code -> POST /sessions
      -> GET /accounts/{uid}/transactions  (repeated by the background sync).
Only the standard library is needed. RS256 signing uses `cryptography` if installed, else the `openssl` CLI.
"""
import base64
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from . import db, service
from .parsing import clean_description

API_URL = os.environ.get("EB_API_URL", "https://api.enablebanking.com")
SYNC_LOCK = threading.Lock()


class BankError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ keys / JWT

def key_path():
    return os.path.join(os.path.dirname(db.DB_PATH), "enablebanking.pem")


def save_private_key(pem_text):
    pem = pem_text.strip()
    if "PRIVATE KEY" not in pem:
        raise BankError("That doesn't look like a private key. It should start with -----BEGIN PRIVATE KEY-----")
    os.makedirs(os.path.dirname(key_path()), exist_ok=True)
    fd = os.open(key_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(pem + "\n")
    try:                                   # fail early if the key can't be used
        sign_rs256(b"test")
    except BankError:
        os.remove(key_path())
        raise


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def sign_rs256(data):
    path = key_path()
    if not os.path.exists(path):
        raise BankError("No private key saved yet.")
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        with open(path, "rb") as fh:
            key = serialization.load_pem_private_key(fh.read(), password=None)
        return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    except ImportError:
        pass
    except Exception as e:
        raise BankError(f"Could not use the private key: {e}")
    try:
        res = subprocess.run(["openssl", "dgst", "-sha256", "-sign", path], input=data, capture_output=True, timeout=20)
    except FileNotFoundError:
        raise BankError("Signing needs either the `openssl` command or `pip install cryptography`.")
    if res.returncode != 0:
        raise BankError("Could not use the private key: " + res.stderr.decode(errors="replace").strip()[:200])
    return res.stdout


def make_jwt(app_id, now=None):
    now = int(now or time.time())
    header = b64url(json.dumps({"typ": "JWT", "alg": "RS256", "kid": app_id}).encode())
    body = b64url(json.dumps({"iss": "enablebanking.com", "aud": "api.enablebanking.com",
                              "iat": now, "exp": now + 3600}).encode())
    signing_input = header + b"." + body
    return (signing_input + b"." + b64url(sign_rs256(signing_input))).decode()


# ------------------------------------------------------------------ API client

class Client:
    def __init__(self, app_id, base=None):
        self.app_id, self.base = app_id, (base or API_URL).rstrip("/")

    def request(self, method, path, params=None, body=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + make_jwt(self.app_id),
                                              "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                msg = json.loads(raw).get("message") or raw
            except ValueError:
                msg = raw
            raise BankError(f"{msg} (HTTP {e.code})", e.code)
        except urllib.error.URLError as e:
            raise BankError(f"Could not reach the bank service: {e.reason}", 503)

    def aspsps(self, country):
        return self.request("GET", "/aspsps", {"country": country}).get("aspsps", [])

    def start_auth(self, aspsp, country, state, redirect_url, valid_until):
        return self.request("POST", "/auth", body={
            "access": {"valid_until": valid_until.strftime("%Y-%m-%dT%H:%M:%SZ")},
            "aspsp": {"name": aspsp, "country": country}, "state": state,
            "redirect_url": redirect_url, "psu_type": "personal"})

    def create_session(self, code):
        return self.request("POST", "/sessions", body={"code": code})

    def transactions(self, uid, date_from, date_to=None):
        out, key = [], None
        for _ in range(60):                # hard cap on pages
            params = {"date_from": date_from}
            if date_to:
                params["date_to"] = date_to
            if key:
                params["continuation_key"] = key
            page = self.request("GET", f"/accounts/{uid}/transactions", params)
            out += page.get("transactions") or []
            key = page.get("continuation_key")
            if not key:
                break
        return out


# ------------------------------------------------------------------ config / state

def get_config(conn):
    s = db.get_settings(conn)
    return {"app_id": s.get("eb_app_id", ""), "redirect_url": s.get("eb_redirect_url", "https://localhost:8765/callback"),
            "has_key": os.path.exists(key_path()), "sync_hours": int(s.get("sync_hours", "6") or 6)}


def save_config(conn, app_id=None, pem=None, redirect_url=None, sync_hours=None):
    if pem:
        save_private_key(pem)
    for k, v in (("eb_app_id", app_id), ("eb_redirect_url", redirect_url), ("sync_hours", sync_hours)):
        if v not in (None, ""):
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, str(v).strip()))
    conn.commit()


def client_for(conn):
    cfg = get_config(conn)
    if not cfg["app_id"] or not cfg["has_key"]:
        raise BankError("Bank sync isn't set up yet: add your Enable Banking application ID and private key first.")
    return Client(cfg["app_id"])


def status(conn):
    cfg = get_config(conn)
    conns = db.rows(conn, "SELECT * FROM bank_connections ORDER BY id")
    now = datetime.now(timezone.utc)
    for c in conns:
        c["accounts"] = db.rows(conn, "SELECT * FROM bank_accounts WHERE connection_id = ?", (c["id"],))
        try:
            vu = datetime.fromisoformat(c["valid_until"].replace("Z", "+00:00"))
            c["days_left"] = (vu - now).days
        except (ValueError, AttributeError):
            c["days_left"] = None
        if c["days_left"] is not None and c["days_left"] < 0:
            c["status"] = "expired"
    return {"config": cfg, "connections": conns, "last_sync": db.get_settings(conn).get("last_sync_at")}


# ------------------------------------------------------------------ connect flow

def list_banks(conn, country):
    banks = client_for(conn).aspsps(country.upper())
    out = [{"name": b["name"], "country": b.get("country", country.upper()), "logo": b.get("logo"),
            "max_days": int(b["maximum_consent_validity"] / 86400) if b.get("maximum_consent_validity") else None}
           for b in banks if "personal" in (b.get("psu_types") or ["personal"])]
    return sorted(out, key=lambda b: b["name"].lower())


def begin_connect(conn, person_id, aspsp, country, max_days=None):
    cfg = get_config(conn)
    days = min(int(max_days or 90), 180)
    state = str(uuid.uuid4())
    valid_until = datetime.now(timezone.utc) + timedelta(days=days) - timedelta(minutes=5)
    res = client_for(conn).start_auth(aspsp, country.upper(), state, cfg["redirect_url"], valid_until)
    conn.execute("INSERT INTO bank_auth (state, person_id, aspsp_name, aspsp_country) VALUES (?,?,?,?)",
                 (state, person_id, aspsp, country.upper()))
    conn.commit()
    return {"url": res["url"], "state": state}


def parse_callback(text):
    """Accepts the full redirect URL, a '?code=..&state=..' query or just the code."""
    text = (text or "").strip()
    if "code=" not in text and "error=" not in text:
        return {"code": text, "state": None} if text and " " not in text else {}
    q = text.split("?", 1)[1] if "?" in text else text
    q = q.split("#", 1)[0]
    parsed = {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}
    return parsed


def finish_connect(conn, pasted):
    p = parse_callback(pasted)
    if p.get("error"):
        raise BankError(f"The bank connection was not approved: {p.get('error_description') or p['error']}")
    if not p.get("code"):
        raise BankError("I couldn't find the code in what you pasted. Paste the complete address from the browser "
                        "after you approved the connection.")
    state = p.get("state")
    pending = conn.execute("SELECT * FROM bank_auth WHERE state = ?", (state,)).fetchone() if state else \
        conn.execute("SELECT * FROM bank_auth ORDER BY rowid DESC LIMIT 1").fetchone()
    if not pending:
        raise BankError("This connection attempt is unknown or was already used. Start the connection again.")
    sess = client_for(conn).create_session(p["code"])
    cur = conn.execute("INSERT INTO bank_connections (person_id, aspsp_name, aspsp_country, session_id, valid_until, status)"
                       " VALUES (?,?,?,?,?,'active')",
                       (pending["person_id"], pending["aspsp_name"], pending["aspsp_country"], sess["session_id"],
                        (sess.get("access") or {}).get("valid_until") or
                        (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()))
    cid = cur.lastrowid
    for a in sess.get("accounts", []):
        iban = (a.get("account_id") or {}).get("iban") or ""
        if not a.get("uid"):
            continue
        conn.execute("INSERT OR IGNORE INTO bank_accounts (connection_id, uid, name, iban_tail, currency) VALUES (?,?,?,?,?)",
                     (cid, a["uid"], a.get("name") or a.get("product") or "Account", iban[-4:], a.get("currency") or "EUR"))
    conn.execute("DELETE FROM bank_auth WHERE state = ?", (pending["state"],))
    conn.commit()
    return cid


def disconnect(conn, conn_id):
    row = conn.execute("SELECT session_id FROM bank_connections WHERE id = ?", (conn_id,)).fetchone()
    if row:
        try:
            client_for(conn).request("DELETE", f"/sessions/{row['session_id']}")
        except BankError:
            pass                             # already gone at the bank - just forget it locally
    conn.execute("DELETE FROM bank_connections WHERE id = ?", (conn_id,))
    conn.commit()


# ------------------------------------------------------------------ transactions -> rows

def eb_to_row(t, account_uid):
    """Convert an Enable Banking transaction into the importer's row format (None = skip)."""
    if t.get("status") not in (None, "BOOK"):
        return None                          # pending transactions can still change
    try:
        amount = Decimal(str((t.get("transaction_amount") or {}).get("amount")))
    except (InvalidOperation, TypeError):
        return None
    credit = t.get("credit_debit_indicator") == "CRDT"
    d = t.get("booking_date") or t.get("value_date") or t.get("transaction_date")
    if not d:
        return None
    cents = int((abs(amount) * 100).to_integral_value())
    signed = cents if credit else -cents
    party = t.get("debtor" if credit else "creditor") or {}
    parts = []
    for v in [party.get("name")] + list(t.get("remittance_information") or []) + [t.get("note")]:
        v = clean_description(str(v)) if v else ""
        if v and v.lower() not in [p.lower() for p in parts]:
            parts.append(v)
    desc = " - ".join(parts)[:300] or (t.get("bank_transaction_code") or {}).get("description") or "Bank transaction"
    ref = t.get("entry_reference") or t.get("transaction_id")
    h = None
    if ref:
        h = "eb:" + hashlib.sha1(f"{account_uid}|{ref}|{d}|{signed}".encode()).hexdigest()
    return {"date": d[:10], "description": desc, "amount_cents": signed, "hash": h}


def sync_account(conn, client, acc, person_id, full=False, today=None):
    today = today or date.today()
    if acc["last_sync"] and not full:
        start = date.fromisoformat(acc["last_sync"]) - timedelta(days=7)
    else:
        start = today - timedelta(days=365)
    try:
        raw = client.transactions(acc["uid"], start.isoformat())
    except BankError as e:
        if acc["last_sync"] or e.status in (401, 403, 429, 503):
            raise
        raw = client.transactions(acc["uid"], (today - timedelta(days=89)).isoformat())   # bank limits history
    rows = [r for r in (eb_to_row(t, acc["uid"]) for t in raw) if r]
    items = service.classify_import_rows(conn, rows, person_id, fuzzy=True, scope=f"eb:{acc['uid']}")
    res = service.commit_import(conn, items, person_id, db.get_settings(conn)["default_split"])
    res["fetched"] = len(rows)
    return res


def sync_all(conn, full=False, only_conn=None):
    """Sync every connected account. Returns a summary list; never raises for a single failing bank."""
    if not SYNC_LOCK.acquire(blocking=False):
        raise BankError("A sync is already running.", 409)
    try:
        client = client_for(conn)
        results = []
        for c in db.rows(conn, "SELECT * FROM bank_connections WHERE status = 'active'"):
            if only_conn and c["id"] != only_conn:
                continue
            for acc in db.rows(conn, "SELECT * FROM bank_accounts WHERE connection_id = ?", (c["id"],)):
                entry = {"bank": c["aspsp_name"], "account": acc["name"], "person_id": c["person_id"]}
                try:
                    entry.update(sync_account(conn, client, acc, c["person_id"], full))
                    conn.execute("UPDATE bank_accounts SET last_sync = ?, last_error = NULL WHERE id = ?",
                                 (date.today().isoformat(), acc["id"]))
                except BankError as e:
                    entry["error"] = str(e)
                    conn.execute("UPDATE bank_accounts SET last_error = ? WHERE id = ?", (str(e)[:300], acc["id"]))
                    if e.status in (401, 403) and "rate" not in str(e).lower():
                        conn.execute("UPDATE bank_connections SET status = 'expired' WHERE id = ?", (c["id"],))
                conn.commit()
                results.append(entry)
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync_at', ?)",
                     (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
        conn.commit()
        service.materialize_recurring(conn)
        return results
    finally:
        SYNC_LOCK.release()


def background_loop(stop_event, check_every=900):
    """Runs inside the server: every 15 minutes, sync if the last sync is older than `sync_hours`."""
    while not stop_event.wait(check_every if getattr(background_loop, "started", False) else 20):
        background_loop.started = True
        try:
            conn = db.connect()
            try:
                cfg = get_config(conn)
                if not (cfg["app_id"] and cfg["has_key"]) or not conn.execute(
                        "SELECT 1 FROM bank_connections WHERE status='active'").fetchone():
                    continue
                last = db.get_settings(conn).get("last_sync_at")
                if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(hours=max(cfg["sync_hours"], 4)):
                    continue
                sync_all(conn)
            finally:
                conn.close()
        except Exception as e:                # never let the thread die
            print("background sync failed:", e)
