"""Parsing helpers: numbers, dates, bank CSV files, merchant rules and quick-add text."""
import csv
import hashlib
import io
import re
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- numbers / dates


def parse_amount(text):
    """'1.234,56' / '1,234.56' / '-12,50' / '€ 12.5' / '12' -> float (None if not a number)."""
    if text is None:
        return None
    s = str(text).strip().replace("\u00a0", " ")
    if not s:
        return None
    neg = s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not re.search(r"\d", s):
        return None
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot != -1 and last_comma != -1:
        dec = "." if last_dot > last_comma else ","
        thou = "," if dec == "." else "."
        s = s.replace(thou, "").replace(dec, ".")
    elif last_comma != -1 or last_dot != -1:
        sep = "," if last_comma != -1 else "."
        parts = s.split(sep)
        if len(parts) > 2:                      # 1,234,567 -> thousands
            s = "".join(parts)
        elif len(parts[-1]) == 3 and len(parts[0]) >= 1 and parts[0] != "0":
            s = "".join(parts)                  # 1.234 -> thousands separator
        else:
            s = parts[0] + "." + parts[1]
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def to_cents(value):
    return int(round(value * 100))


DATE_FORMATS = ["%Y-%m-%d", "%Y%m%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y",
                "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y"]


def parse_date(text):
    """Day-first (European) date parsing. Returns 'YYYY-MM-DD' or None."""
    if not text:
        return None
    s = str(text).strip().split("T")[0]
    if re.match(r"^\d{4}-\d{2}-\d{2} ", s):
        s = s.split(" ")[0]
    s = re.split(r"\s+\d{1,2}:\d{2}", s)[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- merchant helpers

NOISE = {"betaalautomaat", "pas", "nr", "apple", "pay", "ideal", "sepa", "incasso", "overboeking", "term",
         "transactie", "kaart", "google", "bv", "b.v.", "nv", "n.v.", "the", "de", "het", "pos", "card",
         "payment", "purchase", "to", "from", "via", "eur"}


def merchant_key(description):
    """Stable short key for a merchant, e.g. 'Albert Heijn 1234 Naaldwijk' -> 'albert'."""
    words = re.findall(r"[a-zà-ÿ][a-zà-ÿ'&.\-]*", (description or "").lower())
    words = [w.strip(".-'") for w in words]
    words = [w for w in words if w and w not in NOISE]
    if not words:
        return ""
    if len(words[0]) >= 5 or len(words) == 1:
        return words[0]
    return " ".join(words[:2])


def _pattern_regex(pattern):
    p = pattern.strip().lower()
    core = re.escape(p)
    if re.match(r"^[a-z0-9]", p):
        core = r"\b" + core
    if pattern.endswith(" ") or (re.fullmatch(r"[a-z0-9 ]+", p) and len(p) <= 4):
        core += r"(?![a-z0-9])"
    return re.compile(core)


class RuleMatcher:
    """Matches a description against learnt/seeded rules (longest pattern wins)."""

    def __init__(self, rules):
        # rules: list of dicts with pattern, category_id
        ordered = sorted(rules, key=lambda r: -len(r["pattern"].strip()))
        self._compiled = [(_pattern_regex(r["pattern"]), r["category_id"]) for r in ordered]

    def match(self, description, allowed_category_ids=None):
        d = (description or "").lower()
        for rx, cid in self._compiled:
            if allowed_category_ids is not None and cid not in allowed_category_ids:
                continue
            if rx.search(d):
                return cid
        return None


# ---------------------------------------------------------------- bank CSV import

DATE_HEADERS = ["datum", "date", "boekingsdatum", "transactiedatum", "transaction date", "booking date",
                "posted date", "buchungstag", "valutadatum", "rentedatum", "started date", "completed date"]
DESC_HEADERS = ["naam / omschrijving", "omschrijving", "description", "naam", "name", "payee", "merchant",
                "mededelingen", "details", "reference", "counterparty", "tegenpartij", "verwendungszweck",
                "narrative", "memo"]
AMOUNT_HEADERS = ["bedrag (eur)", "bedrag", "amount", "transactiebedrag", "transaction amount", "value",
                  "betrag", "waarde"]
DEBIT_HEADERS = ["debit", "debet", "af", "withdrawal", "paid out", "money out"]
CREDIT_HEADERS = ["credit", "bij", "deposit", "paid in", "money in"]
DIRECTION_HEADERS = ["af bij", "af/bij", "debit/credit", "dc", "type"]


def _norm(h):
    return re.sub(r"\s+", " ", (h or "").strip().lower().lstrip("\ufeff"))


def _pick(headers, candidates):
    normed = [_norm(h) for h in headers]
    for cand in candidates:                   # priority by candidate order
        if cand in normed:
            return normed.index(cand)
    return None


_NOISE_RX = re.compile(r"(pasvolgnr|transactie|term|kaartvolgnr|valutadatum|iban|machtiging|kenmerk|"
                       r"incassant id)\s*:?\s*[\w\-/]*(\s+\d[\d:.\-/ ]*)?", re.I)


def clean_description(text):
    v = _NOISE_RX.sub(" ", text)
    v = re.sub(r"NL\d{2}[A-Z]{4}\d{10}", " ", v)
    return re.sub(r"\s+", " ", v).strip(" -:")


def detect_delimiter(text):
    sample = "\n".join(text.splitlines()[:5])
    counts = {d: sample.count(d) for d in [";", ",", "\t", "|"]}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def parse_bank_csv(text, joint_desc_columns=True):
    """Parse a bank CSV export into normalised rows.

    Returns {"columns": {...detected mapping...}, "rows": [{date, description, amount_cents (signed)}],
             "skipped": n, "warnings": [...]}.
    """
    text = text.lstrip("\ufeff")
    delim = detect_delimiter(text)
    reader = list(csv.reader(io.StringIO(text), delimiter=delim))
    reader = [r for r in reader if any(c.strip() for c in r)]
    if not reader:
        return {"columns": {}, "rows": [], "skipped": 0, "warnings": ["The file looks empty."]}

    # The header row is the first row where we can find a date column.
    header_idx = 0
    for i, r in enumerate(reader[:10]):
        if _pick(r, DATE_HEADERS) is not None and (
                _pick(r, AMOUNT_HEADERS) is not None or _pick(r, DEBIT_HEADERS) is not None):
            header_idx = i
            break
    headers = reader[header_idx]
    body = reader[header_idx + 1:]
    warnings = []

    i_date = _pick(headers, DATE_HEADERS)
    i_amt = _pick(headers, AMOUNT_HEADERS)
    i_dir = _pick(headers, DIRECTION_HEADERS)
    i_deb = _pick(headers, DEBIT_HEADERS) if i_amt is None else None
    i_cred = _pick(headers, CREDIT_HEADERS) if i_amt is None else None
    desc_idx = [headers.index(h) for h in headers if _norm(h) in DESC_HEADERS]
    # prefer "naam / omschrijving" (+ mededelingen) style columns, keep order as in file
    if not desc_idx:
        desc_idx = [i for i in range(len(headers)) if i not in (i_date, i_amt, i_dir, i_deb, i_cred)][:1]

    # Headerless file fallback: guess columns from content
    if i_date is None or (i_amt is None and i_deb is None):
        guess = _guess_columns(reader)
        if guess:
            body = reader
            i_date, i_amt, desc_idx = guess["date"], guess["amount"], guess["desc"]
            i_dir = i_deb = i_cred = None
            headers = [f"col{i}" for i in range(len(reader[0]))]
            warnings.append("No header row found - columns were guessed from the content.")
        else:
            return {"columns": {}, "rows": [], "skipped": len(reader), "warnings": [
                "Could not find date and amount columns. Expected headers like Date/Datum and Amount/Bedrag."]}

    out, skipped = [], 0
    for r in body:
        if len(r) <= max([x for x in [i_date, i_amt, i_dir, i_deb, i_cred] if x is not None] + [0]):
            skipped += 1
            continue
        d = parse_date(r[i_date])
        if i_amt is not None:
            amt = parse_amount(r[i_amt])
        else:
            deb = parse_amount(r[i_deb]) if i_deb is not None else None
            cred = parse_amount(r[i_cred]) if i_cred is not None else None
            amt = (cred or 0) - abs(deb or 0) if (deb is not None or cred is not None) else None
        if d is None or amt is None:
            skipped += 1
            continue
        if i_dir is not None:
            direction = _norm(r[i_dir])
            if direction in ("af", "debit", "d", "db", "dr"):
                amt = -abs(amt)
            elif direction in ("bij", "credit", "c", "cr"):
                amt = abs(amt)
        parts = []
        for i in desc_idx:
            if i < len(r) and r[i].strip():
                v = clean_description(r[i])
                if v and v not in parts:
                    parts.append(v)
        desc = " - ".join(parts) if joint_desc_columns else (parts[0] if parts else "")
        out.append({"date": d, "description": desc[:300], "amount_cents": to_cents(amt)})

    cols = {"date": headers[i_date], "amount": headers[i_amt] if i_amt is not None else None,
            "description": [headers[i] for i in desc_idx], "delimiter": delim}
    return {"columns": cols, "rows": out, "skipped": skipped, "warnings": warnings}


def _guess_columns(rows):
    sample = rows[:20]
    width = max(len(r) for r in sample)
    date_col = amt_col = None
    for c in range(width):
        vals = [r[c] for r in sample if c < len(r)]
        if vals and sum(parse_date(v) is not None for v in vals) >= 0.8 * len(vals):
            date_col = c
            break
    for c in range(width):
        if c == date_col:
            continue
        vals = [r[c] for r in sample if c < len(r)]
        if vals and sum(parse_amount(v) is not None and re.search(r"[.,]\d{2}$|^-?\d+$", v.strip())
                        is not None for v in vals) >= 0.8 * len(vals):
            amt_col = c
            break
    if date_col is None or amt_col is None:
        return None
    text_cols = [c for c in range(width) if c not in (date_col, amt_col)
                 and any(re.search(r"[A-Za-z]{3}", r[c]) for r in sample if c < len(r))]
    return {"date": date_col, "amount": amt_col, "desc": text_cols[:2] or [0]}


def row_hashes(rows, scope=""):
    """Deterministic hash per row, with an occurrence counter so two identical same-day
    purchases in one file are both kept, but re-importing the same file adds nothing."""
    seen, out = {}, []
    for r in rows:
        base = f"{scope}|{r['date']}|{r['amount_cents']}|{re.sub(r'[^a-z0-9]', '', r['description'].lower())}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append(hashlib.sha1(f"{base}|{n}".encode()).hexdigest())
    return out


# ---------------------------------------------------------------- quick add ("jumbo 23,50 yesterday")

INCOME_WORDS = {"salary", "salaris", "loon", "income", "refund", "payout", "bonus", "received", "+"}
JOINT_WORDS = {"joint", "shared", "samen", "together", "both"}
TODAY_WORDS = {"today", "vandaag"}
YESTERDAY_WORDS = {"yesterday", "gisteren"}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_quick(text, people, categories, matcher, today=None, default_person=None):
    """Turn a free-text line into a draft transaction dict.

    people: [{id, name}], categories: [{id, name, kind}], matcher: RuleMatcher.
    """
    today = today or date.today()
    raw = text.strip()
    tokens = raw.split()
    amount = None
    amount_i = None
    for i, t in enumerate(tokens):
        clean = t.replace("€", "").replace("$", "").replace("£", "")
        if re.fullmatch(r"[+-]?\d[\d.,]*", clean) and not re.fullmatch(r"\d{1,2}[-/.]\d{1,2}([-/.]\d{2,4})?", clean):
            amount = parse_amount(clean)
            amount_i = i
            if t.startswith("+") or t.startswith("-"):
                pass
            break
    if amount is None:
        return {"ok": False, "error": "I couldn't find an amount. Try e.g. 'jumbo 23,50' or '+2400 salary anna'."}

    sign_income = tokens[amount_i].startswith("+")
    used = {amount_i}
    d = today
    person_id, joint = default_person, False
    lower_people = {p["name"].lower(): p["id"] for p in people}
    for i, t in enumerate(tokens):
        tl = t.lower().strip(",.")
        if i in used:
            continue
        if tl in TODAY_WORDS:
            used.add(i)
        elif tl in YESTERDAY_WORDS:
            d = today - timedelta(days=1)
            used.add(i)
        elif tl in WEEKDAYS:
            delta = (today.weekday() - WEEKDAYS.index(tl)) % 7 or 7
            d = today - timedelta(days=delta)
            used.add(i)
        elif re.fullmatch(r"\d{1,2}[-/.]\d{1,2}([-/.]\d{2,4})?", tl):
            parts = re.split(r"[-/.]", tl)
            day, month = int(parts[0]), int(parts[1])
            year = int(parts[2]) if len(parts) > 2 else today.year
            year += 2000 if year < 100 else 0
            try:
                d = date(year, month, day)
                if len(parts) == 2 and d > today:
                    d = date(year - 1, month, day)
                used.add(i)
            except ValueError:
                pass
        elif tl in lower_people:
            person_id = lower_people[tl]
            used.add(i)
        elif tl in JOINT_WORDS:
            joint, person_id = True, None
            used.add(i)
        elif tl in INCOME_WORDS and tl != "+":
            sign_income = True

    desc_words = [t for i, t in enumerate(tokens) if i not in used and t.replace("€", "").strip()]
    desc = " ".join(desc_words).strip() or "Unnamed"
    cat_by_name = {c["name"].lower(): c for c in categories}
    by_id = {c["id"]: c for c in categories}
    explicit_income = sign_income
    cat_id = matcher.match(desc)
    if cat_id is not None and explicit_income and by_id[cat_id]["kind"] == "expense":
        cat_id = None                          # "+50 jumbo" is a refund, not a grocery purchase
    if cat_id is None:                         # a category name typed directly, e.g. "groceries"
        want = "income" if explicit_income else "expense"
        for w in desc_words:
            for name, c in cat_by_name.items():
                if c["kind"] == want and (w.lower() == name or (len(w) >= 4 and name.startswith(w.lower()))):
                    cat_id = c["id"]
                    break
            if cat_id:
                break
    if cat_id is not None and by_id[cat_id]["kind"] == "income":
        kind = "income"
    else:
        kind = "income" if explicit_income else "expense"
    cat = next((c for c in categories if c["id"] == cat_id), None)
    ttype = "transfer" if cat and cat["kind"] == "transfer" else kind
    return {"ok": True, "date": d.isoformat(), "type": ttype, "amount_cents": to_cents(abs(amount)),
            "description": desc, "category_id": cat_id, "person_id": None if joint else person_id}
