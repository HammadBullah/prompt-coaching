"""SQLite schema, connection helper and seed data."""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("COUPLE_FINANCE_DB", os.path.join(BASE_DIR, "data", "finance.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('income','expense','transfer')),
    bucket TEXT NOT NULL DEFAULT 'wants' CHECK (bucket IN ('needs','wants','none')),
    budget_cents INTEGER,
    icon TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                      -- YYYY-MM-DD
    type TEXT NOT NULL CHECK (type IN ('income','expense','transfer')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    description TEXT NOT NULL DEFAULT '',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    person_id INTEGER,                       -- who received / paid; NULL = joint account
    split TEXT NOT NULL DEFAULT 'equal' CHECK (split IN ('equal','income','p1','p2')),
    recurring_id INTEGER,
    import_hash TEXT UNIQUE,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);

CREATE TABLE IF NOT EXISTS recurring (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income','expense')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    person_id INTEGER,
    split TEXT NOT NULL DEFAULT 'equal' CHECK (split IN ('equal','income','p1','p2')),
    frequency TEXT NOT NULL CHECK (frequency IN ('weekly','biweekly','monthly','quarterly','yearly')),
    start_date TEXT NOT NULL,
    end_date TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    last_generated TEXT
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '🎯',
    target_cents INTEGER NOT NULL CHECK (target_cents > 0),
    deadline TEXT,
    priority INTEGER NOT NULL DEFAULT 2,     -- 1 high, 2 normal, 3 low
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goal_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,           -- negative = withdrawal
    person_id INTEGER,
    note TEXT NOT NULL DEFAULT ''
);
"""

# name, kind, bucket, icon
CATEGORIES = [
    ("Salary", "income", "none", "💼"),
    ("Side income", "income", "none", "🧾"),
    ("Benefits & allowances", "income", "none", "🏛️"),
    ("Other income", "income", "none", "➕"),
    ("Rent / Mortgage", "expense", "needs", "🏠"),
    ("Utilities", "expense", "needs", "💡"),
    ("Internet & Phone", "expense", "needs", "📶"),
    ("Insurance", "expense", "needs", "🛡️"),
    ("Groceries", "expense", "needs", "🛒"),
    ("Transport", "expense", "needs", "🚆"),
    ("Health", "expense", "needs", "💊"),
    ("Taxes", "expense", "needs", "🧮"),
    ("Household", "expense", "needs", "🧽"),
    ("Eating out", "expense", "wants", "🍽️"),
    ("Entertainment", "expense", "wants", "🎬"),
    ("Subscriptions", "expense", "wants", "🔁"),
    ("Shopping", "expense", "wants", "🛍️"),
    ("Travel", "expense", "wants", "✈️"),
    ("Personal care", "expense", "wants", "💇"),
    ("Gifts & donations", "expense", "wants", "🎁"),
    ("Other", "expense", "wants", "📦"),
    ("Transfer (own accounts)", "transfer", "none", "🔄"),
]

# pattern -> category. Mix of NL + international merchants; users extend these automatically.
RULES = {
    "Groceries": ["albert heijn", "ah to go", "ah", "jumbo", "lidl", "aldi", "plus", "dirk", "coop", "spar",
                  "picnic", "ekoplaza", "tesco", "sainsbury", "carrefour", "whole foods", "kruidvat groceries"],
    "Eating out": ["thuisbezorgd", "deliveroo", "uber eats", "mcdonald", "burger king", "kfc", "starbucks",
                   "restaurant", "cafe", "café", "pizza", "dominos", "subway", "lunchroom", "bar "],
    "Transport": ["ns groep", "ns reizigers", "ov-chipkaart", "ov chipkaart", "gvb", "ret ", "htm", "shell",
                  "bp ", "tango", "esso", "total", "tinq", "uber", "bolt", "parkeer", "q-park", "anwb"],
    "Subscriptions": ["netflix", "spotify", "disney", "hbo", "videoland", "youtube", "apple.com/bill", "icloud",
                      "amazon prime", "storytel", "playstation", "xbox", "adobe", "chatgpt", "openai"],
    "Utilities": ["vattenfall", "eneco", "essent", "greenchoice", "vitens", "evides", "oxxio", "budget energie",
                  "engie", "waterbedrijf", "energie", "electric", "water bill"],
    "Internet & Phone": ["ziggo", "kpn", "odido", "t-mobile", "vodafone", "simyo", "ben ", "lebara", "youfone",
                         "delta fiber", "telfort", "hollandsnieuwe"],
    "Insurance": ["zilveren kruis", "cz groep", "vgz", "menzis", "onvz", "a.s.r", "asr", "nn ", "centraal beheer",
                  "allianz", "verzekering", "insurance", "ohra", "fbto"],
    "Rent / Mortgage": ["huur", "rent", "hypotheek", "mortgage", "woningcorporatie", "vve"],
    "Taxes": ["belastingdienst", "gemeente", "waterschap", "cjib", "tax"],
    "Shopping": ["bol.com", "amazon", "zalando", "coolblue", "ikea", "h&m", "zara", "primark", "wehkamp",
                 "mediamarkt", "decathlon", "vinted"],
    "Household": ["action", "hema", "gamma", "praxis", "karwei", "blokker", "xenos"],
    "Personal care": ["kruidvat", "etos", "rituals", "kapper", "barber", "douglas", "hairdress"],
    "Health": ["apotheek", "pharmacy", "huisarts", "tandarts", "fysio", "dentist", "doctor", "opticien"],
    "Entertainment": ["pathe", "pathé", "cinema", "bioscoop", "steam", "ticketmaster", "theater", "museum",
                      "concert", "efteling"],
    "Travel": ["booking.com", "airbnb", "klm", "transavia", "ryanair", "easyjet", "hotel", "flixbus", "tui"],
    "Salary": ["salaris", "salary", "loon", "payroll", "wages"],
    "Benefits & allowances": ["toeslagen", "uwv", "svb", "kinderbijslag", "zorgtoeslag", "huurtoeslag"],
    "Transfer (own accounts)": ["oranje spaarrekening", "spaarrekening", "savings account", "eigen rekening",
                                "own account", "internal transfer"],
}

DEFAULT_SETTINGS = {
    "currency": "EUR",
    "locale": "nl-NL",
    "default_split": "income",
    "setup_done": "0",
}


def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0:
        conn.executemany("INSERT INTO people (id, name, color) VALUES (?,?,?)",
                         [(1, "Me", "#4f46e5"), (2, "Partner", "#e11d74")])
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        for name, kind, bucket, icon in CATEGORIES:
            conn.execute("INSERT INTO categories (name, kind, bucket, icon) VALUES (?,?,?,?)",
                         (name, kind, bucket, icon))
        ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories")}
        for cat, patterns in RULES.items():
            for p in patterns:
                conn.execute("INSERT OR IGNORE INTO rules (pattern, category_id) VALUES (?,?)",
                             (p.lower(), ids[cat]))
    conn.commit()


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_settings(conn):
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
