"""Bank sync tests against a local mock of the Enable Banking API (no network, no real credentials)."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_tmp = tempfile.mkdtemp()
os.environ["COUPLE_FINANCE_DB"] = os.path.join(_tmp, "bank.db")
os.environ["CF_QUIET"] = "1"

from couplefinance import bank, db, service  # noqa: E402

TODAY = date.today()
D = lambda n: (TODAY - timedelta(days=n)).isoformat()  # noqa: E731

TXS = [
    {"entry_reference": "r1", "transaction_amount": {"amount": "23.40", "currency": "EUR"}, "credit_debit_indicator": "DBIT",
     "status": "BOOK", "booking_date": D(3), "creditor": {"name": "Albert Heijn 1421"}, "remittance_information": ["Pas 123"]},
    {"entry_reference": "r2", "transaction_amount": {"amount": "2500.00", "currency": "EUR"}, "credit_debit_indicator": "CRDT",
     "status": "BOOK", "booking_date": D(5), "debtor": {"name": "Werkgever BV"}, "remittance_information": ["Salaris"]},
    {"entry_reference": "r3", "transaction_amount": {"amount": "9.99", "currency": "EUR"}, "credit_debit_indicator": "DBIT",
     "status": "PDNG", "booking_date": D(0), "creditor": {"name": "Pending shop"}},
    {"entry_reference": "r4", "transaction_amount": {"amount": "12.30", "currency": "EUR"}, "credit_debit_indicator": "DBIT",
     "status": "BOOK", "booking_date": D(2), "creditor": {"name": "Jumbo"}},
]
SEEN = {"auth": [], "tx_calls": [], "jwts": []}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self):
        SEEN["jwts"].append(self.headers.get("Authorization", ""))
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if url.path == "/aspsps":
            return self._send({"aspsps": [{"name": "ING", "country": "NL", "psu_types": ["personal"], "maximum_consent_validity": 15552000},
                                          {"name": "Business Only", "country": "NL", "psu_types": ["business"]}]})
        if url.path == "/auth":
            SEEN["auth"].append(body)
            return self._send({"url": "https://auth.example/start?x=1", "authorization_id": "a1"})
        if url.path == "/sessions" and self.command == "POST":
            if body.get("code") != "goodcode":
                return self._send({"message": "bad code"}, 400)
            return self._send({"session_id": "sess-1", "access": {"valid_until": (TODAY + timedelta(days=90)).isoformat() + "T00:00:00Z"},
                               "accounts": [{"uid": "acc-1", "account_id": {"iban": "NL00INGB0123456789"}, "name": "Oranje rekening", "currency": "EUR"}]})
        if url.path.startswith("/sessions/") and self.command == "DELETE":
            return self._send({"message": "OK"})
        if url.path == "/accounts/acc-1/transactions":
            SEEN["tx_calls"].append(q)
            if "continuation_key" not in q:                      # two pages
                return self._send({"transactions": TXS[:2], "continuation_key": "p2"})
            return self._send({"transactions": TXS[2:]})
        self._send({"message": "not found"}, 404)

    do_GET = do_POST = do_DELETE = _handle


def verify_jwt(token):
    head, body, sig = token.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    sig_bytes = base64.urlsafe_b64decode(pad(sig))
    pub = subprocess.run(["openssl", "rsa", "-in", bank.key_path(), "-pubout"], capture_output=True).stdout
    pub_file, sig_file = os.path.join(_tmp, "pub.pem"), os.path.join(_tmp, "sig.bin")
    with open(pub_file, "wb") as fh:
        fh.write(pub)
    with open(sig_file, "wb") as fh:
        fh.write(sig_bytes)
    r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", pub_file, "-signature", sig_file],
                       input=f"{head}.{body}".encode(), capture_output=True)
    return r.returncode == 0, json.loads(base64.urlsafe_b64decode(pad(head))), json.loads(base64.urlsafe_b64decode(pad(body)))


class BankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        bank.API_URL = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        pem = subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, check=True).stdout.decode()
        cls.pem = pem

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        if os.path.exists(db.DB_PATH):
            os.remove(db.DB_PATH)
        self.conn = db.connect()
        db.init_db(self.conn)
        SEEN["tx_calls"].clear()
        SEEN["auth"].clear()

    def tearDown(self):
        self.conn.close()

    def setup_bank(self):
        bank.save_config(self.conn, app_id="app-123", pem=self.pem, redirect_url="https://localhost:8765/callback")

    def connect(self, person=1):
        self.setup_bank()
        res = bank.begin_connect(self.conn, person, "ING", "NL", 180)
        return bank.finish_connect(self.conn, f"https://localhost:8765/callback?code=goodcode&state={res['state']}")

    def test_jwt_is_valid_rs256(self):
        self.setup_bank()
        ok, head, body = verify_jwt(bank.make_jwt("app-123"))
        self.assertTrue(ok)
        self.assertEqual((head["alg"], head["kid"], body["aud"], body["iss"]), ("RS256", "app-123", "api.enablebanking.com", "enablebanking.com"))
        self.assertLessEqual(body["exp"] - body["iat"], 86400)

    def test_rejects_bad_key(self):
        with self.assertRaises(bank.BankError):
            bank.save_private_key("not a key")

    def test_bank_list_filters_personal(self):
        self.setup_bank()
        banks = bank.list_banks(self.conn, "nl")
        self.assertEqual([b["name"] for b in banks], ["ING"])
        self.assertEqual(banks[0]["max_days"], 180)

    def test_connect_and_sync(self):
        cid = self.connect(person=2)
        self.assertEqual(SEEN["auth"][0]["aspsp"], {"name": "ING", "country": "NL"})
        self.assertEqual(SEEN["auth"][0]["psu_type"], "personal")
        results = bank.sync_all(self.conn, full=True)
        self.assertEqual(results[0]["added"], 3)              # pending skipped, pages followed
        self.assertEqual(len(SEEN["tx_calls"]), 2)
        rows = db.rows(self.conn, "SELECT * FROM transactions ORDER BY amount_cents")
        self.assertTrue(all(r["person_id"] == 2 for r in rows))
        ah = next(r for r in rows if r["amount_cents"] == 2340)
        self.assertIn("Albert Heijn", ah["description"])
        self.assertIsNotNone(ah["category_id"])               # auto-categorised
        self.assertEqual(ah["type"], "expense")
        self.assertEqual(next(r for r in rows if r["amount_cents"] == 250000)["type"], "income")
        # second sync is idempotent and only asks for recent days
        again = bank.sync_all(self.conn)
        self.assertEqual(again[0]["added"], 0)
        asked = date.fromisoformat(SEEN["tx_calls"][-1]["date_from"])
        self.assertGreaterEqual(asked, TODAY - timedelta(days=8))
        st = bank.status(self.conn)
        self.assertEqual(st["connections"][0]["accounts"][0]["iban_tail"], "6789")
        self.assertGreater(st["connections"][0]["days_left"], 80)
        bank.disconnect(self.conn, cid)
        self.assertEqual(bank.status(self.conn)["connections"], [])

    def test_no_double_count_with_manual_and_csv_entries(self):
        # you already quick-added the Jumbo purchase (1 day off) -> sync must not add it again
        self.conn.execute("INSERT INTO transactions (date,type,amount_cents,description,person_id) VALUES (?,?,?,?,?)",
                          (D(3), "expense", 1230, "jumbo", 1))
        self.connect()
        results = bank.sync_all(self.conn, full=True)
        self.assertEqual(results[0]["added"], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM transactions WHERE amount_cents=1230").fetchone()[0], 1)

    def test_parse_callback_variants(self):
        self.assertEqual(bank.parse_callback("https://x/callback?code=abc&state=s1")["code"], "abc")
        self.assertEqual(bank.parse_callback("?code=abc&state=s1")["state"], "s1")
        self.assertEqual(bank.parse_callback("abc123")["code"], "abc123")
        self.assertIn("error", bank.parse_callback("https://x/cb?error=access_denied&error_description=Cancelled"))

    def test_finish_errors(self):
        self.setup_bank()
        with self.assertRaises(bank.BankError):
            bank.finish_connect(self.conn, "garbage with spaces")
        res = bank.begin_connect(self.conn, 1, "ING", "NL")
        with self.assertRaises(bank.BankError):
            bank.finish_connect(self.conn, f"?code=wrong&state={res['state']}")
        with self.assertRaises(bank.BankError):
            bank.finish_connect(self.conn, "?error=access_denied&error_description=Cancelled")

    def test_ingest_webhook(self):
        from couplefinance import server
        token = db.get_settings(self.conn)["ingest_token"]
        with self.assertRaises(server.ApiError):
            server.h_ingest(self.conn, {}, {}, {"token": "nope", "amount": "5"})
        r = server.h_ingest(self.conn, {}, {}, {"token": token, "amount": "€ 12,50", "merchant": "Albert Heijn", "person": "me"})
        self.assertEqual(r["transaction"]["amount_cents"], 1250)
        self.assertEqual(r["transaction"]["category_name"], "Groceries")
        r = server.h_ingest(self.conn, {}, {"token": token, "text": "+50 refund bol.com"}, {})
        self.assertGreater(r["transaction"]["id"], 0)


class BankHttpTests(unittest.TestCase):
    """The same flow through the real HTTP API of the app (plus password protection and the /callback page)."""

    @classmethod
    def setUpClass(cls):
        from couplefinance.server import Handler
        cls.mock = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()
        bank.API_URL = f"http://127.0.0.1:{cls.mock.server_address[1]}"
        cls.pem = subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, check=True).stdout.decode()
        if os.path.exists(db.DB_PATH):
            os.remove(db.DB_PATH)
        c = db.connect()
        db.init_db(c)
        c.close()
        cls.app = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.app.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.app.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        for srv in (cls.mock, cls.app):
            srv.shutdown()
            srv.server_close()
        os.environ.pop("CF_PASSWORD", None)

    def call(self, method, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, method=method, headers=headers or {},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get("Content-Type", "").startswith("application/json") else raw.decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_full_flow(self):
        st, _ = self.call("GET", "/api/bank/banks?country=NL")
        self.assertEqual(st, 400)                                       # not configured yet
        st, res = self.call("PUT", "/api/bank/config", {"app_id": "app-1", "private_key": self.pem,
                                                        "redirect_url": "https://localhost:8765/callback"})
        self.assertTrue(res["config"]["has_key"])
        self.assertNotIn("private_key", json.dumps(res))
        st, banks = self.call("GET", "/api/bank/banks?country=NL")
        self.assertEqual(banks[0]["name"], "ING")
        st, conn = self.call("POST", "/api/bank/connect", {"person_id": 1, "bank": "ING", "country": "NL"})
        self.assertTrue(conn["url"].startswith("https://auth.example"))
        st, err = self.call("POST", "/api/bank/finish", {"redirect": "?code=wrong&state=" + conn["state"]})
        self.assertEqual(st, 400)
        st, fin = self.call("POST", "/api/bank/finish", {"redirect": f"https://localhost:8765/callback?code=goodcode&state={conn['state']}"})
        self.assertEqual(fin["sync"][0]["added"], 3)
        st, sy = self.call("POST", "/api/bank/sync", {})
        self.assertEqual(sy["added"], 0)
        st, status = self.call("GET", "/api/bank/status")
        self.assertEqual(len(status["connections"]), 1)
        self.assertEqual(self.call("DELETE", f"/api/bank/connections/{status['connections'][0]['id']}")[0], 200)

    def test_callback_page_and_password(self):
        st, page = self.call("GET", "/callback?code=zzz&state=unknown")
        self.assertEqual(st, 200)
        self.assertIn("Could not connect", page)
        os.environ["CF_PASSWORD"] = "s3cret"
        try:
            self.assertEqual(self.call("GET", "/api/bootstrap")[0], 401)
            auth = {"Authorization": "Basic " + base64.b64encode(b"user:s3cret").decode()}
            self.assertEqual(self.call("GET", "/api/bootstrap", headers=auth)[0], 200)
            self.assertEqual(self.call("GET", "/api/ingest?token=bad&amount=1")[0], 403)   # webhook: token, not password
        finally:
            os.environ.pop("CF_PASSWORD")


if __name__ == "__main__":
    unittest.main()
