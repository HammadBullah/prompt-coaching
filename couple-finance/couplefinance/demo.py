"""Demo data so you can explore the app before feeding it real numbers."""
import csv
import io
import random
from datetime import date, timedelta

from .service import add_months, materialize_recurring


def _cat(conn, name):
    return conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()[0]


def load_demo(conn, today=None):
    today = today or date.today()
    rnd = random.Random(42)
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM people")}
    if names.get(1) == "Me":
        conn.execute("UPDATE people SET name = 'Alex' WHERE id = 1")
    if names.get(2) == "Partner":
        conn.execute("UPDATE people SET name = 'Sam' WHERE id = 2")
    start = add_months(today.replace(day=1), -4)

    recurring = [  # name, type, cents, category, person, split, freq, day
        ("Salary Alex", "income", 290000, "Salary", 1, "equal", "monthly", 25),
        ("Salary Sam", "income", 225000, "Salary", 2, "equal", "monthly", 27),
        ("Rent", "expense", 105000, "Rent / Mortgage", 1, "income", "monthly", 1),
        ("Vattenfall energy", "expense", 13500, "Utilities", 2, "income", "monthly", 5),
        ("Ziggo internet", "expense", 5500, "Internet & Phone", 1, "equal", "monthly", 8),
    ]
    for name, typ, cents, cat, person, split, freq, day in recurring:
        conn.execute("INSERT INTO recurring (name,type,amount_cents,category_id,person_id,split,frequency,start_date)"
                     " VALUES (?,?,?,?,?,?,?,?)",
                     (name, typ, cents, _cat(conn, cat), person, split, freq, start.replace(day=day).isoformat()))

    def tx(d, typ, cents, desc, cat=None, person=None, split="income"):
        conn.execute("INSERT INTO transactions (date,type,amount_cents,description,category_id,person_id,split)"
                     " VALUES (?,?,?,?,?,?,?)",
                     (d.isoformat(), typ, cents, desc, _cat(conn, cat) if cat else None, person, split))

    # subscriptions / insurance the app has NOT been told about -> the detector will suggest them
    m = start
    while m <= today:
        for day, desc, cents, cat, person in [(3, "Netflix", 1399, "Subscriptions", 1),
                                               (12, "Spotify Family", 1799, "Subscriptions", 2),
                                               (15, "Zilveren Kruis zorgverzekering", 28600, "Insurance", 1),
                                               (18, "Basic-Fit Naaldwijk", 2499, "Health", 2)]:
            d = m.replace(day=day)
            if d <= today:
                tx(d, "expense", cents, desc, cat, person, "equal")
        m = add_months(m, 1)

    shops = [("Albert Heijn 1421 Naaldwijk", 1800, 6500, "Groceries"), ("Jumbo Monster", 1500, 7200, "Groceries"),
             ("Lidl Naaldwijk", 1200, 4800, "Groceries"), ("Kruidvat 8841", 500, 2200, "Personal care"),
             ("Thuisbezorgd.nl", 2200, 4200, "Eating out"), ("Restaurant De Kade", 3800, 9200, "Eating out"),
             ("NS Reizigers", 450, 2400, "Transport"), ("Shell Westland", 4500, 7500, "Transport"),
             ("Bol.com", 1500, 6000, "Shopping"), ("Pathé Den Haag", 1800, 3600, "Entertainment"),
             ("Action Naaldwijk", 600, 2500, "Household"), ("Kiosk De Hoek", 300, 1400, None),
             ("Zorg & Gezond Apotheek", 500, 2500, "Health")]
    weights = [9, 7, 5, 3, 4, 2, 4, 2, 2, 1, 2, 2, 1]
    d = start
    while d <= today:
        for _ in range(rnd.choice([0, 1, 1, 2])):
            desc, lo, hi, cat = rnd.choices(shops, weights)[0]
            tx(d, "expense", rnd.randrange(lo, hi, 5), desc, cat, rnd.choice([1, 2, None]),
               "equal" if cat in ("Groceries", "Household") else "income")
        d += timedelta(days=1)
    # a couple of personal purchases and one side income
    tx(today - timedelta(days=40), "income", 35000, "Freelance design job", "Side income", 2, "equal")
    tx(today - timedelta(days=9), "expense", 5999, "Steam games", "Entertainment", 1, "p1")
    tx(today - timedelta(days=20), "expense", 8900, "Zalando", "Shopping", 2, "p2")

    for name, cents in [("Groceries", 55000), ("Eating out", 20000), ("Entertainment", 10000)]:
        conn.execute("UPDATE categories SET budget_cents = ? WHERE name = ?", (cents, name))

    goals = [("Holiday in Japan", "🗾", 450000, add_months(today, 11).isoformat(), 2, 90000),
             ("Emergency fund (3 months)", "🛟", 600000, None, 1, 210000),
             ("New laptop", "💻", 150000, add_months(today, 5).isoformat(), 3, 30000),
             ("House deposit", "🏡", 2500000, add_months(today, 36).isoformat(), 2, 320000)]
    for name, icon, target, deadline, prio, saved in goals:
        cur = conn.execute("INSERT INTO goals (name,icon,target_cents,deadline,priority) VALUES (?,?,?,?,?)",
                           (name, icon, target, deadline, prio))
        conn.execute("INSERT INTO goal_contributions (goal_id,date,amount_cents,note) VALUES (?,?,?,?)",
                     (cur.lastrowid, start.isoformat(), saved, "Starting balance"))
    conn.commit()
    materialize_recurring(conn, today)


def sample_csv_text(today=None):
    """An ING-style export (Dutch headers, comma decimals, yyyymmdd dates) for trying the importer."""
    today = today or date.today()
    rnd = random.Random(7)
    rows = []
    first = today.replace(day=1)
    prev = add_months(first, -1)
    for base in (prev, first):
        def at(day):
            return base.replace(day=min(day, 28)).strftime("%Y%m%d")
        rows += [(at(25), "Werkgever BV salaris", "Bij", 2900.00, "Overschrijving", "Salaris Alex"),
                 (at(1), "Woningbouw Naaldwijk huur", "Af", 1050.00, "Incasso", "Huur"),
                 (at(5), "Vattenfall Klantenservice", "Af", 135.00, "Incasso", "Termijnbedrag energie"),
                 (at(8), "Ziggo Services", "Af", 55.00, "Incasso", "Internet en TV"),
                 (at(3), "Netflix International B.V.", "Af", 13.99, "Incasso", ""),
                 (at(12), "Spotify", "Af", 17.99, "Incasso", ""),
                 (at(15), "Zilveren Kruis Zorgverzekeraar", "Af", 286.00, "Incasso", "Premie"),
                 (at(20), "Oranje spaarrekening", "Af", 200.00, "Overschrijving", "Sparen")]
        for day in range(2, 28, 2):
            name = rnd.choice(["Albert Heijn 1421 Naaldwijk", "Jumbo Monster", "Lidl Naaldwijk",
                               "Thuisbezorgd.nl", "NS Groep IZI klant", "Bol.com", "Tankstation Shell",
                               "Café De Kroeg", "Hema Den Haag", "Kiosk De Hoek"])
            rows.append((at(day), name, "Af", round(rnd.uniform(6, 85), 2), "Betaalautomaat",
                         "Pasvolgnr 001 Transactie " + str(rnd.randrange(10**5, 10**6))))
    rows = [r for r in rows if r[0] <= today.strftime("%Y%m%d")]
    rows.sort(key=lambda r: r[0], reverse=True)
    fh = io.StringIO(newline="")
    w = csv.writer(fh, quoting=csv.QUOTE_ALL)
    w.writerow(["Datum", "Naam / Omschrijving", "Rekening", "Tegenrekening", "Code", "Af Bij",
                "Bedrag (EUR)", "Mutatiesoort", "Mededelingen"])
    for d, name, dirn, amt, kind, msg in rows:
        w.writerow([d, name, "NL00INGB0000000000", "NL00XXXX0000000000", "GT", dirn,
                    f"{amt:.2f}".replace(".", ","), kind, msg])
    return fh.getvalue()


def write_sample_csv(path, today=None):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(sample_csv_text(today))
