import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_tmp = tempfile.mkdtemp()
os.environ["COUPLE_FINANCE_DB"] = os.path.join(_tmp, "test.db")
os.environ["CF_QUIET"] = "1"

from couplefinance import db, parsing, service  # noqa: E402
from couplefinance.demo import load_demo, write_sample_csv  # noqa: E402
from couplefinance.server import Handler  # noqa: E402


class ParsingTests(unittest.TestCase):
    def test_amounts(self):
        cases = {"1.234,56": 1234.56, "1,234.56": 1234.56, "-12,50": -12.5, "€ 12.5": 12.5, "1.234": 1234.0,
                 "0,5": 0.5, "(10,00)": -10.0}
        for text, val in cases.items():
            self.assertEqual(parsing.parse_amount(text), val, text)
        self.assertIsNone(parsing.parse_amount("abc"))

    def test_dates(self):
        self.assertEqual(parsing.parse_date("20260926"), "2026-09-26")
        self.assertEqual(parsing.parse_date("26-09-2026"), "2026-09-26")
        self.assertEqual(parsing.parse_date("03/04/2026"), "2026-04-03")   # day first
        self.assertIsNone(parsing.parse_date("nonsense"))

    def test_ing_csv(self):
        csv_text = ('"Datum","Naam / Omschrijving","Rekening","Tegenrekening","Code","Af Bij","Bedrag (EUR)",'
                    '"Mutatiesoort","Mededelingen"\n'
                    '"20260901","Albert Heijn 1234","NL1","NL2","BA","Af","23,45","Betaalautomaat","Pasvolgnr 1"\n'
                    '"20260925","Werkgever","NL1","NL2","OV","Bij","2.500,00","Overschrijving","Salaris"\n')
        r = parsing.parse_bank_csv(csv_text)
        self.assertEqual([x["amount_cents"] for x in r["rows"]], [-2345, 250000])

    def test_semicolon_debit_credit(self):
        text = "Date;Description;Debit;Credit\n01-09-2026;Tesco;12,30;\n02-09-2026;Pay;;1500,00\n"
        r = parsing.parse_bank_csv(text)
        self.assertEqual([x["amount_cents"] for x in r["rows"]], [-1230, 150000])

    def test_headerless(self):
        r = parsing.parse_bank_csv("2026-09-01,Coffee shop,-3.50\n2026-09-02,Lunch place,-9.00\n")
        self.assertEqual(len(r["rows"]), 2)
        self.assertEqual(r["rows"][0]["amount_cents"], -350)

    def test_duplicate_hashes_in_one_file_stay_distinct(self):
        rows = [{"date": "2026-09-01", "description": "Coffee", "amount_cents": -300}] * 2
        h = parsing.row_hashes(rows)
        self.assertNotEqual(h[0], h[1])
        self.assertEqual(h, parsing.row_hashes(rows))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        if os.path.exists(db.DB_PATH):
            os.remove(db.DB_PATH)
        self.conn = db.connect()
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def cat(self, name):
        return self.conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()[0]

    def test_rules_seeded(self):
        m = service.matcher(self.conn)
        self.assertEqual(m.match("Albert Heijn 1421 Naaldwijk"), self.cat("Groceries"))
        self.assertEqual(m.match("AH Amsterdam"), self.cat("Groceries"))
        self.assertIsNone(m.match("Ahold something"))        # 'ah' must not match inside words
        self.assertEqual(m.match("Netflix International"), self.cat("Subscriptions"))

    def test_recurring_generation_is_idempotent(self):
        self.conn.execute("INSERT INTO recurring (name,type,amount_cents,frequency,start_date) VALUES "
                          "('Rent','expense',100000,'monthly','2026-05-31')")
        today = date(2026, 9, 15)
        self.assertEqual(service.materialize_recurring(self.conn, today), 4)   # May 31, Jun 30, Jul 31, Aug 31
        self.assertEqual(service.materialize_recurring(self.conn, today), 0)
        dates = [r[0] for r in self.conn.execute("SELECT date FROM transactions ORDER BY date")]
        self.assertIn("2026-06-30", dates)      # clamped to end of month
        self.assertEqual(service.materialize_recurring(self.conn, date(2026, 10, 31)), 2)

    def test_settlement_income_split(self):
        for pid, amt in ((1, 300000), (2, 100000)):
            self.conn.execute("INSERT INTO transactions (date,type,amount_cents,description,person_id) "
                              "VALUES ('2026-09-25','income',?,'Salary',?)", (amt, pid))
        # person 1 pays 1000 rent split by income (75/25) -> person 2 owes 250
        self.conn.execute("INSERT INTO transactions (date,type,amount_cents,description,person_id,split) "
                          "VALUES ('2026-09-01','expense',100000,'Rent',1,'income')")
        # person 2 pays 100 groceries split equally -> person 1 owes 50
        self.conn.execute("INSERT INTO transactions (date,type,amount_cents,description,person_id,split) "
                          "VALUES ('2026-09-02','expense',10000,'Groceries',2,'equal')")
        s = service.summary(self.conn, "2026-09", date(2026, 10, 1))
        st = s["settlement"]
        self.assertEqual((st["from_person"], st["to_person"], st["amount_cents"]), (2, 1, 20000))
        self.assertEqual(s["savings_cents"], 400000 - 110000)

    def test_transfers_excluded(self):
        self.conn.execute("INSERT INTO transactions (date,type,amount_cents,description) "
                          "VALUES ('2026-09-02','transfer',50000,'To savings')")
        s = service.summary(self.conn, "2026-09", date(2026, 10, 1))
        self.assertEqual(s["expense_cents"], 0)

    def test_learning_applies_to_other_uncategorised(self):
        for d in ("Kiosk De Hoek", "Kiosk de hoek 22"):
            self.conn.execute("INSERT INTO transactions (date,type,amount_cents,description) "
                              "VALUES ('2026-09-02','expense',300,?)", (d,))
        n = service.learn_rule(self.conn, "Kiosk De Hoek", self.cat("Groceries"))
        self.assertEqual(n, 2)

    def test_demo_and_detection(self):
        today = date.today()
        load_demo(self.conn, today)
        sug = service.detect_recurring(self.conn)
        names = " ".join(s["name"].lower() for s in sug)
        for expected in ("netflix", "spotify", "zilveren kruis", "basic-fit"):
            self.assertIn(expected, names)
        self.assertNotIn("rent", names)        # already tracked
        g = service.goals_overview(self.conn, today)
        self.assertEqual(len(g["goals"]), 4)
        self.assertTrue(all(x["planned_monthly_cents"] >= 0 for x in g["goals"]))
        s = service.summary(self.conn, service.current_month(today), today)
        self.assertGreater(s["income_cents"], 0)
        self.assertEqual(len(service.trends(self.conn, service.current_month(today), 6)), 6)

    def test_import_reconciles_with_recurring_and_skips_duplicates(self):
        self.conn.execute("INSERT INTO recurring (name,type,amount_cents,category_id,frequency,start_date) VALUES "
                          "('Rent','expense',105000,?, 'monthly','2026-09-01')", (self.cat("Rent / Mortgage"),))
        service.materialize_recurring(self.conn, date(2026, 9, 10))
        parsed = [{"date": "2026-09-02", "description": "Woningbouw huur", "amount_cents": -105000},
                  {"date": "2026-09-03", "description": "Jumbo", "amount_cents": -2350}]
        items = service.classify_import_rows(self.conn, parsed, 1)
        self.assertEqual([i["status"] for i in items], ["matches_bill", "new"])
        res = service.commit_import(self.conn, items, 1, "equal")
        self.assertEqual((res["added"], res["matched_bills"]), (1, 1))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 2)
        items2 = service.classify_import_rows(self.conn, parsed, 1)
        self.assertEqual([i["status"] for i in items2], ["duplicate", "duplicate"])

    def test_goal_plan(self):
        today = date(2026, 9, 30)
        for m, inc, exp in (("2026-06", 400000, 300000), ("2026-07", 400000, 300000), ("2026-08", 400000, 300000)):
            self.conn.execute("INSERT INTO transactions (date,type,amount_cents,description) VALUES (?,?,?,?)",
                              (m + "-10", "income", inc, "x"))
            self.conn.execute("INSERT INTO transactions (date,type,amount_cents,description) VALUES (?,?,?,?)",
                              (m + "-11", "expense", exp, "y"))
        self.conn.execute("INSERT INTO goals (name,target_cents,deadline) VALUES ('Trip',120000,'2027-03-30')")
        self.conn.execute("INSERT INTO goals (name,target_cents) VALUES ('Fund',500000)")
        ov = service.goals_overview(self.conn, today)
        self.assertEqual(ov["avg_monthly_savings_cents"], 100000)
        trip = next(g for g in ov["goals"] if g["name"] == "Trip")
        self.assertAlmostEqual(trip["required_monthly_cents"], 120000 / 6.0, delta=1500)
        fund = next(g for g in ov["goals"] if g["name"] == "Fund")
        self.assertGreater(fund["planned_monthly_cents"], 0)
        self.assertTrue(trip["on_track"])


class QuickAddTests(unittest.TestCase):
    def setUp(self):
        if os.path.exists(db.DB_PATH):
            os.remove(db.DB_PATH)
        self.conn = db.connect()
        db.init_db(self.conn)
        self.people = db.rows(self.conn, "SELECT id, name FROM people")
        self.cats = db.rows(self.conn, "SELECT id, name, kind FROM categories")
        self.m = service.matcher(self.conn)

    def q(self, text, **kw):
        return parsing.parse_quick(text, self.people, self.cats, self.m, today=date(2026, 9, 30), **kw)

    def test_basic(self):
        d = self.q("jumbo 23,50 yesterday")
        self.assertEqual((d["amount_cents"], d["date"], d["type"]), (2350, "2026-09-29", "expense"))
        self.assertIsNotNone(d["category_id"])

    def test_income_and_person(self):
        d = self.q("+2400 salary partner", default_person=1)
        self.assertEqual((d["type"], d["person_id"], d["amount_cents"]), ("income", 2, 240000))

    def test_joint_and_date(self):
        d = self.q("shared rent 950 01-09")
        self.assertIsNone(d["person_id"])
        self.assertEqual(d["date"], "2026-09-01")

    def test_no_amount(self):
        self.assertFalse(self.q("hello there")["ok"])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(db.DB_PATH):
            os.remove(db.DB_PATH)
        conn = db.connect()
        db.init_db(conn)
        conn.close()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_flow(self):
        st, boot = self.call("GET", "/api/bootstrap")
        self.assertEqual(st, 200)
        self.assertEqual(len(boot["people"]), 2)
        st, res = self.call("POST", "/api/quick", {"text": "albert heijn 12,40", "default_person_id": 1})
        self.assertTrue(res["ok"])
        self.assertEqual(res["transaction"]["category_name"], "Groceries")
        st, res = self.call("POST", "/api/transactions", {"date": "bad", "amount_cents": 5})
        self.assertEqual(st, 400)
        st, sm = self.call("GET", "/api/summary")
        self.assertEqual(sm["expense_cents"], 1240)
        st, g = self.call("POST", "/api/goals", {"name": "Trip", "target_cents": 100000, "saved_cents": 5000})
        self.assertEqual(st, 200)
        st, ov = self.call("GET", "/api/goals")
        self.assertEqual(ov["goals"][0]["saved_cents"], 5000)
        st, _ = self.call("POST", "/api/reset", {})
        self.assertEqual(st, 400)
        st, _ = self.call("GET", "/api/nope")
        self.assertEqual(st, 404)

    def test_import_endpoint(self):
        path = os.path.join(_tmp, "s.csv")
        write_sample_csv(path)
        with open(path) as fh:
            text = fh.read()
        st, prev = self.call("POST", "/api/import/preview", {"text": text, "person_id": 1})
        self.assertEqual(st, 200)
        self.assertGreater(prev["counts"]["new"], 20)
        st, res = self.call("POST", "/api/import/commit", {"rows": prev["rows"], "person_id": 1})
        self.assertGreater(res["added"], 20)
        st, prev2 = self.call("POST", "/api/import/preview", {"text": text, "person_id": 1})
        self.assertEqual(prev2["counts"]["new"], 0)


if __name__ == "__main__":
    unittest.main()
