"""Business logic: recurring generation, categorisation, monthly summary, settlement, goals, insights."""
import calendar
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from .db import get_settings, rows
from .parsing import RuleMatcher, merchant_key

SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}


# ---------------------------------------------------------------- small date helpers

def month_bounds(month):
    y, m = int(month[:4]), int(month[5:7])
    last = calendar.monthrange(y, m)[1]
    return f"{month}-01", f"{month}-{last:02d}"


def shift_month(month, delta):
    y, m = int(month[:4]), int(month[5:7])
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def add_months(d, n, anchor_day=None):
    idx = d.year * 12 + (d.month - 1) + n
    y, m = idx // 12, idx % 12 + 1
    day = min(anchor_day or d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def current_month(today=None):
    return (today or date.today()).strftime("%Y-%m")


def fmt_money(cents, currency="EUR"):
    sym = SYMBOLS.get(currency, currency + " ")
    sign = "-" if cents < 0 else ""
    return f"{sign}{sym}{abs(cents) / 100:,.2f}"


# ---------------------------------------------------------------- recurring items

STEP_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}
STEP_DAYS = {"weekly": 7, "biweekly": 14}
MONTHLY_FACTOR = {"weekly": 52 / 12, "biweekly": 26 / 12, "monthly": 1, "quarterly": 1 / 3, "yearly": 1 / 12}


def occurrences(rec, upto, after=None):
    """All due dates of a recurring item in (after, upto]."""
    start = date.fromisoformat(rec["start_date"])
    end = date.fromisoformat(rec["end_date"]) if rec.get("end_date") else None
    limit = min(upto, end) if end else upto
    after = date.fromisoformat(after) if isinstance(after, str) else after
    out, k = [], 0
    while True:
        if rec["frequency"] in STEP_DAYS:
            d = start + timedelta(days=STEP_DAYS[rec["frequency"]] * k)
        else:
            d = add_months(start, STEP_MONTHS[rec["frequency"]] * k, start.day)
        if d > limit:
            break
        if after is None or d > after:
            out.append(d)
        k += 1
        if k > 5000:
            break
    return out


def materialize_recurring(conn, today=None):
    """Create transactions for every recurring item that became due. Idempotent."""
    today = today or date.today()
    created = 0
    for rec in rows(conn, "SELECT * FROM recurring WHERE active = 1"):
        dates = occurrences(rec, today, rec["last_generated"])
        if not dates:
            continue
        for d in dates:
            conn.execute(
                "INSERT INTO transactions (date, type, amount_cents, description, category_id, person_id, split,"
                " recurring_id) VALUES (?,?,?,?,?,?,?,?)",
                (d.isoformat(), rec["type"], rec["amount_cents"], rec["name"], rec["category_id"],
                 rec["person_id"], rec["split"], rec["id"]))
            created += 1
        conn.execute("UPDATE recurring SET last_generated = ? WHERE id = ?", (dates[-1].isoformat(), rec["id"]))
    conn.commit()
    return created


def upcoming(conn, days=30, today=None):
    """Bills/income due after today within the next `days` days."""
    today = today or date.today()
    horizon = today + timedelta(days=days)
    out = []
    for rec in rows(conn, "SELECT * FROM recurring WHERE active = 1"):
        for d in occurrences(rec, horizon, today):
            out.append({"date": d.isoformat(), "name": rec["name"], "type": rec["type"],
                        "amount_cents": rec["amount_cents"], "person_id": rec["person_id"],
                        "recurring_id": rec["id"], "category_id": rec["category_id"]})
    return sorted(out, key=lambda x: x["date"])


def recurring_overview(conn):
    items = rows(conn, """SELECT r.*, c.name AS category_name, c.icon AS category_icon FROM recurring r
                          LEFT JOIN categories c ON c.id = r.category_id ORDER BY r.active DESC, r.type, r.name""")
    inc = exp = 0
    for r in items:
        r["monthly_cents"] = round(r["amount_cents"] * MONTHLY_FACTOR[r["frequency"]])
        if r["active"]:
            if r["type"] == "income":
                inc += r["monthly_cents"]
            else:
                exp += r["monthly_cents"]
    return {"items": items, "monthly_income_cents": inc, "monthly_expense_cents": exp}


# ---------------------------------------------------------------- categorisation

def matcher(conn):
    return RuleMatcher(rows(conn, "SELECT pattern, category_id FROM rules"))


def type_for_category(conn, category_id, fallback):
    if category_id is None:
        return fallback
    r = conn.execute("SELECT kind FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not r:
        return fallback
    if r["kind"] == "transfer":
        return "transfer"
    return r["kind"]


def learn_rule(conn, description, category_id):
    """Remember 'merchant -> category' and apply it to every other uncategorised transaction that matches."""
    key = merchant_key(description)
    if not key or category_id is None:
        return 0
    conn.execute("INSERT INTO rules (pattern, category_id) VALUES (?,?) "
                 "ON CONFLICT(pattern) DO UPDATE SET category_id = excluded.category_id", (key, category_id))
    return recategorize_uncategorized(conn)


def recategorize_uncategorized(conn):
    m = matcher(conn)
    kinds = {r["id"]: r["kind"] for r in conn.execute("SELECT id, kind FROM categories")}
    n = 0
    for t in rows(conn, "SELECT id, description, type FROM transactions WHERE category_id IS NULL"):
        cid = m.match(t["description"])
        if cid is None:
            continue
        kind = kinds[cid]
        if kind == "transfer":
            conn.execute("UPDATE transactions SET category_id=?, type='transfer' WHERE id=?", (cid, t["id"]))
        elif kind == t["type"]:
            conn.execute("UPDATE transactions SET category_id=? WHERE id=?", (cid, t["id"]))
        else:
            continue
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------- monthly summary

def income_ratio(conn, month):
    lo, hi = month_bounds(month)
    inc = {r["person_id"]: r["s"] for r in conn.execute(
        "SELECT person_id, SUM(amount_cents) s FROM transactions WHERE type='income' AND date BETWEEN ? AND ? "
        "AND person_id IS NOT NULL GROUP BY person_id", (lo, hi))}
    a, b = inc.get(1, 0), inc.get(2, 0)
    if a + b == 0:
        # fall back to expected recurring income, otherwise 50/50
        rec = {1: 0, 2: 0}
        for r in rows(conn, "SELECT person_id, amount_cents, frequency FROM recurring "
                            "WHERE type='income' AND active=1 AND person_id IS NOT NULL"):
            rec[r["person_id"]] += r["amount_cents"] * MONTHLY_FACTOR[r["frequency"]]
        a, b = rec[1], rec[2]
    if a + b == 0:
        return 0.5, 0.5
    return a / (a + b), b / (a + b)


def shares(split, ratio):
    return {"equal": (0.5, 0.5), "income": ratio, "p1": (1.0, 0.0), "p2": (0.0, 1.0)}[split]


def settlement(txs, ratio, people):
    """Who owes whom for shared expenses. balance > 0 means that person is owed money."""
    bal = {1: 0.0, 2: 0.0}
    joint_share = {1: 0.0, 2: 0.0}     # what each should put into the joint account
    shared_total = 0
    for t in txs:
        if t["type"] != "expense":
            continue
        s1, s2 = shares(t["split"], ratio)
        if t["split"] in ("equal", "income"):
            shared_total += t["amount_cents"]
        if t["person_id"] in (1, 2):
            bal[t["person_id"]] += t["amount_cents"]
            bal[1] -= t["amount_cents"] * s1
            bal[2] -= t["amount_cents"] * s2
        else:
            joint_share[1] += t["amount_cents"] * s1
            joint_share[2] += t["amount_cents"] * s2
    names = {p["id"]: p["name"] for p in people}
    net = round(bal[1])
    res = {"shared_expense_cents": shared_total, "ratio": {"1": ratio[0], "2": ratio[1]},
           "joint_contribution_cents": {"1": round(joint_share[1]), "2": round(joint_share[2])},
           "from_person": None, "to_person": None, "amount_cents": 0, "text": "You're all square."}
    if abs(net) >= 1:
        debtor, creditor = (2, 1) if net > 0 else (1, 2)
        res.update(from_person=debtor, to_person=creditor, amount_cents=abs(net))
    return res


def month_transactions(conn, month):
    lo, hi = month_bounds(month)
    return rows(conn, "SELECT * FROM transactions WHERE date BETWEEN ? AND ? AND type != 'transfer'", (lo, hi))


def totals(txs):
    inc = sum(t["amount_cents"] for t in txs if t["type"] == "income")
    exp = sum(t["amount_cents"] for t in txs if t["type"] == "expense")
    return inc, exp


def goal_contrib_month(conn, month):
    lo, hi = month_bounds(month)
    return conn.execute("SELECT COALESCE(SUM(amount_cents),0) FROM goal_contributions WHERE date BETWEEN ? AND ?",
                        (lo, hi)).fetchone()[0]


def summary(conn, month, today=None):
    today = today or date.today()
    people = rows(conn, "SELECT * FROM people ORDER BY id")
    cats = {c["id"]: c for c in rows(conn, "SELECT * FROM categories")}
    txs = month_transactions(conn, month)
    income, expenses = totals(txs)
    savings = income - expenses
    prev_month = shift_month(month, -1)
    prev_txs = month_transactions(conn, prev_month)
    p_inc, p_exp = totals(prev_txs)

    by_person_income = {p["id"]: 0 for p in people}
    by_person_paid = {p["id"]: 0 for p in people}
    for t in txs:
        if t["type"] == "income" and t["person_id"] in by_person_income:
            by_person_income[t["person_id"]] += t["amount_cents"]
        if t["type"] == "expense" and t["person_id"] in by_person_paid:
            by_person_paid[t["person_id"]] += t["amount_cents"]

    def cat_spend(items):
        d = defaultdict(int)
        for t in items:
            if t["type"] == "expense":
                d[t["category_id"]] += t["amount_cents"]
        return d
    spend, prev_spend = cat_spend(txs), cat_spend(prev_txs)
    categories = []
    for cid, amt in sorted(spend.items(), key=lambda kv: -kv[1]):
        c = cats.get(cid)
        categories.append({"category_id": cid, "name": c["name"] if c else "Uncategorised",
                           "icon": c["icon"] if c else "❓", "bucket": c["bucket"] if c else "wants",
                           "amount_cents": amt, "prev_cents": prev_spend.get(cid, 0),
                           "budget_cents": c["budget_cents"] if c else None})
    budgets = [{"category_id": c["id"], "name": c["name"], "icon": c["icon"], "budget_cents": c["budget_cents"],
                "spent_cents": spend.get(c["id"], 0)}
               for c in cats.values() if c["budget_cents"]]

    needs = sum(a["amount_cents"] for a in categories if a["bucket"] == "needs")
    wants = expenses - needs
    fixed = sum(t["amount_cents"] for t in txs if t["type"] == "expense" and t["recurring_id"])
    variable = expenses - fixed

    ratio = income_ratio(conn, month)
    settle = settlement(txs, ratio, people)
    contributed = goal_contrib_month(conn, month)

    # forecast (only for the running month)
    forecast = None
    if month == current_month(today):
        _, last = month_bounds(month)
        last_day = date.fromisoformat(last)
        days_in = last_day.day
        elapsed = max(today.day, 1)
        remaining = [u for u in upcoming(conn, (last_day - today).days, today) if u["date"] <= last]
        up_exp = sum(u["amount_cents"] for u in remaining if u["type"] == "expense")
        up_inc = sum(u["amount_cents"] for u in remaining if u["type"] == "income")
        daily_var = variable / elapsed
        proj_exp = expenses + up_exp + round(daily_var * (days_in - elapsed))
        forecast = {"days_left": days_in - elapsed, "upcoming_expense_cents": up_exp,
                    "upcoming_income_cents": up_inc, "projected_expense_cents": proj_exp,
                    "projected_income_cents": income + up_inc,
                    "projected_savings_cents": income + up_inc - proj_exp,
                    "daily_variable_cents": round(daily_var)}

    uncategorised = conn.execute("SELECT COUNT(*) FROM transactions WHERE category_id IS NULL "
                                 "AND type != 'transfer'").fetchone()[0]
    result = {
        "month": month, "people": people,
        "income_cents": income, "expense_cents": expenses, "savings_cents": savings,
        "savings_rate": round(savings / income, 4) if income else None,
        "prev": {"income_cents": p_inc, "expense_cents": p_exp, "savings_cents": p_inc - p_exp},
        "person_income_cents": by_person_income, "person_paid_cents": by_person_paid,
        "categories": categories, "budgets": budgets,
        "split503020": {"needs_cents": needs, "wants_cents": wants, "savings_cents": max(savings, 0)},
        "fixed_cents": fixed, "variable_cents": variable,
        "goal_contributed_cents": contributed, "unallocated_cents": savings - contributed,
        "settlement": settle, "forecast": forecast, "uncategorised_count": uncategorised,
        "tx_count": len(txs),
    }
    result["insights"] = insights(conn, result, today)
    return result


def trends(conn, month, n=6):
    out = []
    for i in range(n - 1, -1, -1):
        m = shift_month(month, -i)
        inc, exp = totals(month_transactions(conn, m))
        out.append({"month": m, "income_cents": inc, "expense_cents": exp, "savings_cents": inc - exp})
    return out


# ---------------------------------------------------------------- goals

def average_monthly_savings(conn, today=None):
    """Average savings of the last 3 full months that have data; else the running month (>= 0)."""
    today = today or date.today()
    cur = current_month(today)
    vals = []
    for i in range(1, 7):
        m = shift_month(cur, -i)
        txs = month_transactions(conn, m)
        if txs:
            inc, exp = totals(txs)
            vals.append(inc - exp)
        if len(vals) == 3:
            break
    if not vals:
        inc, exp = totals(month_transactions(conn, cur))
        vals = [inc - exp]
    return max(round(sum(vals) / len(vals)), 0)


def months_between(d1, d2):
    return (d2.year - d1.year) * 12 + (d2.month - d1.month) + (d2.day - d1.day) / 30.0


def goals_overview(conn, today=None):
    today = today or date.today()
    goals = rows(conn, """SELECT g.*, COALESCE((SELECT SUM(amount_cents) FROM goal_contributions
                          WHERE goal_id = g.id),0) AS saved_cents FROM goals g ORDER BY g.priority, g.deadline, g.id""")
    pool = average_monthly_savings(conn, today)
    active = []
    for g in goals:
        g["remaining_cents"] = max(g["target_cents"] - g["saved_cents"], 0)
        g["pct"] = round(min(g["saved_cents"] / g["target_cents"], 1) * 100, 1)
        g["done"] = g["remaining_cents"] == 0
        g["months_left"] = None
        g["required_monthly_cents"] = None
        if g["deadline"] and not g["done"]:
            ml = months_between(today, date.fromisoformat(g["deadline"]))
            g["months_left"] = round(ml, 1)
            g["required_monthly_cents"] = round(g["remaining_cents"] / max(ml, 1)) if ml > 0 else g["remaining_cents"]
        if not g["done"]:
            active.append(g)
    # Plan: first cover deadline goals (earliest first), then split what is left over by priority weight.
    left = pool
    for g in sorted([g for g in active if g["deadline"]], key=lambda g: g["deadline"]):
        give = min(left, g["required_monthly_cents"])
        g["planned_monthly_cents"] = give
        left -= give
    free = [g for g in active if not g["deadline"]]
    weights = {1: 3, 2: 2, 3: 1}
    total_w = sum(weights[g["priority"]] for g in free) or 1
    for g in free:
        g["planned_monthly_cents"] = min(round(left * weights[g["priority"]] / total_w), g["remaining_cents"])
    for g in goals:
        g.setdefault("planned_monthly_cents", 0)
        pm = g["planned_monthly_cents"]
        g["eta"] = None
        g["on_track"] = True
        if g["done"]:
            continue
        if pm > 0:
            months = g["remaining_cents"] / pm
            g["eta"] = add_months(today, int(months) + (1 if months % 1 else 0)).isoformat()
            if g["deadline"] and g["eta"] > g["deadline"]:
                g["on_track"] = False
        else:
            g["on_track"] = False
        if g["deadline"] and g["required_monthly_cents"] and pm < g["required_monthly_cents"] - 100:
            g["on_track"] = False
    required = sum(g["required_monthly_cents"] or 0 for g in active)
    return {"goals": goals, "avg_monthly_savings_cents": pool, "required_monthly_cents": required,
            "total_target_cents": sum(g["target_cents"] for g in goals),
            "total_saved_cents": sum(min(g["saved_cents"], g["target_cents"]) for g in goals),
            "fits": required <= pool}


def sweep_to_goals(conn, month, today=None):
    """Move the month's unallocated savings into goals according to the plan."""
    today = today or date.today()
    s = summary(conn, month, today)
    available = s["unallocated_cents"]
    if available <= 0:
        return []
    overview = goals_overview(conn, today)
    plan = [g for g in overview["goals"] if g["planned_monthly_cents"] > 0]
    total_plan = sum(g["planned_monthly_cents"] for g in plan)
    if not plan:
        return []
    _, hi = month_bounds(month)
    made = []
    for g in plan:
        amt = min(round(available * g["planned_monthly_cents"] / max(total_plan, available)
                        if total_plan > available else g["planned_monthly_cents"]), g["remaining_cents"])
        if amt <= 0:
            continue
        conn.execute("INSERT INTO goal_contributions (goal_id, date, amount_cents, note) VALUES (?,?,?,?)",
                     (g["id"], min(hi, today.isoformat()), amt, f"Auto from {month} savings"))
        made.append({"goal_id": g["id"], "name": g["name"], "amount_cents": amt})
    conn.commit()
    return made


# ---------------------------------------------------------------- recurring detection

def detect_recurring(conn):
    """Find repeating payments/income in the history that are not yet tracked as recurring items."""
    txs = rows(conn, "SELECT * FROM transactions WHERE type IN ('income','expense') AND recurring_id IS NULL "
                     "ORDER BY date")
    existing = {merchant_key(r["name"]) for r in rows(conn, "SELECT name FROM recurring")}
    variable_cats = {r["id"] for r in conn.execute(
        "SELECT id FROM categories WHERE name IN ('Groceries','Eating out','Shopping','Household','Personal care')")}
    groups = defaultdict(list)
    for t in txs:
        k = merchant_key(t["description"])
        if k and t["category_id"] not in variable_cats:
            groups[(t["type"], k)].append(t)
    out = []
    today = date.today()
    for (ttype, key), items in groups.items():
        if key in existing or len(items) < 2:
            continue
        amounts = [t["amount_cents"] for t in items]
        med = statistics.median(amounts)
        close = [t for t in items if abs(t["amount_cents"] - med) <= 0.1 * med + 100]
        if len(close) < max(2, int(0.75 * len(items))):
            continue
        close.sort(key=lambda t: t["date"])
        dates = [date.fromisoformat(t["date"]) for t in close]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        if not gaps:
            continue
        g = statistics.median(gaps)
        amounts_close = [t["amount_cents"] for t in close]
        exact = max(amounts_close) - min(amounts_close) <= 100
        if 6 <= g <= 8 and len(close) >= 4:
            freq = "weekly"
        elif 13 <= g <= 15 and len(close) >= 4:
            freq = "biweekly"
        elif 26 <= g <= 35:
            freq = "monthly"
        elif 85 <= g <= 95:
            freq = "quarterly"
        elif 355 <= g <= 375:
            freq = "yearly"
        else:
            continue
        needed = 2 if (exact and freq in ("monthly", "quarterly", "yearly")) else 3
        if len(close) < needed or (freq == "monthly" and len({d.strftime("%Y-%m") for d in dates}) < needed):
            continue
        last = dates[-1]
        step = {"weekly": 7, "biweekly": 14, "monthly": 31, "quarterly": 92, "yearly": 366}[freq]
        if (today - last).days > step * 2:
            continue                                   # looks cancelled
        start = date.fromisoformat(close[0]["date"])
        nxt = occurrences({"start_date": start.isoformat(), "frequency": freq, "end_date": None},
                          last + timedelta(days=400), last)[0]
        cat = Counter(t["category_id"] for t in close).most_common(1)[0][0]
        person = Counter(t["person_id"] for t in close).most_common(1)[0][0]
        split = Counter(t["split"] for t in close).most_common(1)[0][0]
        name = Counter(t["description"] for t in close).most_common(1)[0][0]
        out.append({"name": name[:60], "type": ttype, "amount_cents": int(close[-1]["amount_cents"]),
                    "category_id": cat, "person_id": person, "split": split, "frequency": freq,
                    "last_date": last.isoformat(), "next_date": nxt.isoformat(), "start_date": nxt.isoformat(),
                    "occurrences": len(close), "tx_ids": [t["id"] for t in close]})
    return sorted(out, key=lambda x: (x["type"], -x["amount_cents"]))


# ---------------------------------------------------------------- insights

def insights(conn, s, today):
    cur = get_settings(conn).get("currency", "EUR")
    money = lambda c: fmt_money(c, cur)
    tips = []
    if s["tx_count"] == 0:
        return [{"level": "info", "text": "No transactions this month yet. Import a bank CSV or use the quick-add bar."}]
    rate = s["savings_rate"]
    if rate is not None:
        if rate >= 0.2:
            tips.append({"level": "good", "text": f"You're saving {rate:.0%} of your combined income - above the 20% rule of thumb."})
        elif rate >= 0:
            tips.append({"level": "warn", "text": f"You're saving {rate:.0%} of your income. Aiming for 20% would be {money(round(s['income_cents'] * 0.2))} a month."})
        else:
            tips.append({"level": "bad", "text": f"You're spending {money(-s['savings_cents'])} more than you earn this month."})
    fc = s["forecast"]
    if fc and fc["projected_savings_cents"] != s["savings_cents"]:
        lvl = "good" if fc["projected_savings_cents"] >= 0 else "bad"
        tips.append({"level": lvl, "text": f"At this pace you'll end the month with about {money(fc['projected_savings_cents'])} saved "
                                           f"({money(fc['upcoming_expense_cents'])} of bills still due)."})
    for c in s["categories"]:
        if c["prev_cents"] and c["amount_cents"] > c["prev_cents"] * 1.25 and c["amount_cents"] - c["prev_cents"] >= 3000:
            tips.append({"level": "warn", "text": f"{c['icon']} {c['name']} is {money(c['amount_cents'] - c['prev_cents'])} higher than last month."})
    for b in s["budgets"]:
        pct = b["spent_cents"] / b["budget_cents"]
        if pct > 1:
            tips.append({"level": "bad", "text": f"{b['icon']} {b['name']} is over budget by {money(b['spent_cents'] - b['budget_cents'])}."})
        elif pct > 0.85:
            tips.append({"level": "warn", "text": f"{b['icon']} {b['name']} has used {pct:.0%} of its budget."})
    soon = [u for u in upcoming(conn, 7, today) if u["type"] == "expense"]
    if soon:
        tips.append({"level": "info", "text": f"{len(soon)} bill(s) due in the next 7 days, together {money(sum(u['amount_cents'] for u in soon))}."})
    if s["uncategorised_count"]:
        tips.append({"level": "info", "text": f"{s['uncategorised_count']} transaction(s) need a category - set one once and the app remembers it."})
    st = s["settlement"]
    if st["amount_cents"] > 0:
        names = {p["id"]: p["name"] for p in s["people"]}
        tips.append({"level": "info", "text": f"{names[st['from_person']]} owes {names[st['to_person']]} {money(st['amount_cents'])} for shared costs."})
    if s["unallocated_cents"] > 0 and conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]:
        tips.append({"level": "info", "text": f"{money(s['unallocated_cents'])} of this month's savings isn't assigned to a goal yet."})
    return tips


# ---------------------------------------------------------------- bank import

def _find_recurring_match(conn, row_date, ttype, amount_cents, claimed):
    """A bank line that corresponds to an auto-generated recurring transaction (same type, ~same amount, +-6 days)."""
    d = date.fromisoformat(row_date)
    lo, hi = (d - timedelta(days=6)).isoformat(), (d + timedelta(days=6)).isoformat()
    tol = max(100, int(amount_cents * 0.03))
    for t in conn.execute(
            "SELECT id, amount_cents FROM transactions WHERE recurring_id IS NOT NULL AND import_hash IS NULL "
            "AND type = ? AND date BETWEEN ? AND ? AND ABS(amount_cents - ?) <= ? ORDER BY ABS(amount_cents - ?)",
            (ttype, lo, hi, amount_cents, tol, amount_cents)):
        if t["id"] not in claimed:
            return t["id"]
    return None


def _find_manual_twin(conn, row_date, ttype, amount_cents, claimed):
    """An entry that was typed in / imported from CSV earlier: same amount, +-1 day, not from bank sync."""
    d = date.fromisoformat(row_date)
    lo, hi = (d - timedelta(days=1)).isoformat(), (d + timedelta(days=1)).isoformat()
    for t in conn.execute(
            "SELECT id FROM transactions WHERE recurring_id IS NULL AND type = ? AND amount_cents = ? "
            "AND date BETWEEN ? AND ? AND (import_hash IS NULL OR import_hash NOT LIKE 'eb:%')", (ttype, amount_cents, lo, hi)):
        if t["id"] not in claimed:
            return t["id"]
    return None


def classify_import_rows(conn, parsed_rows, person_id, fuzzy=False, scope=None):
    """Adds hash, suggested category/type and status (new / duplicate / matches_bill) to parsed bank rows.

    fuzzy=True (bank sync) also treats a same-amount entry from +-1 day that you typed in or imported from CSV
    as already present, so mixing quick-add / CSV / automatic sync never double counts."""
    from .parsing import row_hashes
    m = matcher(conn)
    cats = {c["id"]: c for c in rows(conn, "SELECT * FROM categories")}
    hashes = row_hashes(parsed_rows, scope=scope or str(person_id))
    hashes = [r.get("hash") or h for r, h in zip(parsed_rows, hashes)]
    known = {r[0] for r in conn.execute("SELECT import_hash FROM transactions WHERE import_hash IS NOT NULL")}
    claimed, out = set(), []
    for r, h in zip(parsed_rows, hashes):
        signed = r["amount_cents"]
        ttype = "income" if signed > 0 else "expense"
        cid = m.match(r["description"])
        if cid is not None:
            kind = cats[cid]["kind"]
            if kind == "transfer":
                ttype = "transfer"
            elif kind != ttype:
                cid = None
        item = {**r, "hash": h, "type": ttype, "category_id": cid, "amount_cents": abs(signed),
                "signed_cents": signed, "status": "new", "recurring_match_id": None}
        if h in known:
            item["status"] = "duplicate"
        elif fuzzy and (twin := _find_manual_twin(conn, r["date"], ttype, abs(signed), claimed)):
            claimed.add(twin)
            item["status"] = "duplicate"
        elif ttype != "transfer":
            mid = _find_recurring_match(conn, r["date"], ttype, abs(signed), claimed)
            if mid:
                claimed.add(mid)
                item["status"], item["recurring_match_id"] = "matches_bill", mid
        out.append(item)
    return out


def commit_import(conn, items, person_id, default_split):
    """items: rows from classify_import_rows (possibly edited by the user: category_id, type, skip)."""
    added = dup = matched = 0
    for it in items:
        if it.get("skip") or it.get("status") == "duplicate":
            dup += 1 if it.get("status") == "duplicate" else 0
            continue
        cid = it.get("category_id")
        ttype = type_for_category(conn, cid, it["type"]) if cid else it["type"]
        if it.get("status") == "matches_bill" and it.get("recurring_match_id"):
            cur = conn.execute("UPDATE transactions SET import_hash=?, amount_cents=?, description=?, date=?, "
                               "category_id=COALESCE(?, category_id) WHERE id=? AND import_hash IS NULL",
                               (it["hash"], it["amount_cents"], it["description"], it["date"], cid,
                                it["recurring_match_id"]))
            if cur.rowcount:
                matched += 1
                continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO transactions (date, type, amount_cents, description, category_id, person_id,"
            " split, import_hash) VALUES (?,?,?,?,?,?,?,?)",
            (it["date"], ttype, it["amount_cents"], it["description"], cid, person_id, default_split, it["hash"]))
        added += cur.rowcount
        dup += 0 if cur.rowcount else 1
    conn.commit()
    return {"added": added, "duplicates": dup, "matched_bills": matched}
