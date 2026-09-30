# 💞 Couple Finance

A small, private money app for two people. Track both incomes, rent & bills, groceries and everyday spending,
see what you save together, and plan the things you want (holiday, deposit, laptop…) with a clear monthly plan.

Everything runs on your own computer. **No accounts, no cloud, no dependencies** – just Python 3.9+.

```bash
cd couple-finance
python3 run.py            # then open http://127.0.0.1:8765
```
…or double-click `start.command` (macOS) / `start.bat` (Windows). On a phone, open the address and use
“Add to Home Screen” – it installs like an app.

Options (environment variables): `PORT=8765`, `HOST=127.0.0.1` (use `HOST=0.0.0.0` so your partner can open it from
her phone on the same Wi-Fi), `CF_PASSWORD=...` (asks for a password – **set this whenever HOST is not 127.0.0.1**),
`COUPLE_FINANCE_DB=/path/to/finance.db` (default `couple-finance/data/finance.db`, git-ignored).

Run the tests: `python3 -m unittest discover -s tests`

## Getting transactions in without typing (all free)

**1. Automatic bank sync – Auto-sync tab.** Uses [Enable Banking](https://enablebanking.com)'s free *Restricted
Production* mode (EU/UK, official PSD2 APIs, 2,500+ banks incl. the big Dutch ones). It is free for accounts you link
yourselves – exactly this use case – but it is *not* a public service: each of you links your own bank login to your own
application. One-time setup of ~15 minutes (the tab walks you through it), then the app pulls new transactions every
few hours (banks allow ~4 pulls/day), categorises them and skips anything you already typed or imported.
Banks require you to renew the consent every 90–180 days; the app shows a countdown and a *Reconnect* button.
GoCardless Bank Account Data (ex-Nordigen), the old free option, no longer accepts new sign-ups.

**2. Phone payment webhook.** `POST /api/ingest` with `{token, amount, merchant, person}` creates an entry instantly.
With an iPhone Shortcut automation on *Wallet → Transaction* every Apple Pay / card payment is booked the moment you pay.
Needs no bank API at all. Token and copy-paste instructions are on the Auto-sync tab.

**3. Quick-add bar / CSV import** as fallbacks (below).

> Privacy: the private key stays in `data/enablebanking.pem` (permissions 600, git-ignored); bank data goes
> bank → Enable Banking → your computer. Nothing is stored anywhere else. Bank sync needs `openssl` on the PATH
> (present on macOS/Linux and Git-for-Windows) or `pip install cryptography`.

## Other automation

| Feature | What it does |
|---|---|
| **Bank CSV import** (Import tab) | Drop the export from your bank. Detects delimiter, date/amount/description columns, Dutch (`1.234,56`, `Af/Bij`, `yyyymmdd`) and English formats. Works for ING, ABN AMRO, Rabobank, bunq, Revolut, Wise… |
| **Auto-categorisation** | ~150 built-in merchant rules (Albert Heijn, Jumbo, Ziggo, Vattenfall, NS, Netflix…). When you categorise something once, the app remembers the merchant and fixes every similar uncategorised transaction. |
| **Duplicate protection** | Every row gets a fingerprint – importing overlapping exports never double counts. |
| **Recurring detection** | After an import, repeating payments/salaries are proposed as recurring items ("Track" / "Add all"). |
| **Recurring items auto-book** | Salaries, rent, insurance, subscriptions are created automatically on their due dates (weekly → yearly). |
| **Bill ↔ bank matching** | When the bank line for your rent arrives, it *replaces* the auto-booked rent instead of counting twice. |
| **Own-account transfers** | Moves to your savings account are recognised and kept out of spending. |
| **Quick-add bar** | One line: `jumbo 23,50 yesterday`, `+2400 salary sam`, `rent 950 shared 01-09`. Live preview, Undo. |
| **Sweep savings to goals** | One click moves the month's leftover savings into your goals following the plan. |

## What you get

* **Overview** – combined income, spending, savings + savings rate, vs last month; income → bills → everyday → saved flow;
  category breakdown with budgets; 6-month trend; 50/30/20 check; end-of-month forecast; upcoming bills; plain-language insights.
* **Fair sharing** – each expense is split 50/50, by income share, or belongs to one person. The app shows who owes whom
  (settle-up) and what each of you should put in a joint account.
* **Bills & income** – recurring items with monthly equivalents ("left after fixed costs").
* **Goals** – target amount, optional deadline, priority. Shows what is needed per month, what you can afford from your
  average savings, estimated finish date and whether all deadlines fit.
* **Settings** – names/colours, default split, per-category budgets, rules, JSON backup, demo data.

## Layout

```
couple-finance/
  run.py                      entry point
  couplefinance/
    db.py                     schema + seed categories/rules
    parsing.py                numbers, dates, bank CSV, rule matching, quick-add parser
    bank.py                   Enable Banking client (JWT), connect flow, background sync, webhook helpers
    service.py                recurring, summary, settlement, goals, detection, import
    server.py                 stdlib HTTP server + JSON API (/api/...)
    demo.py                   demo data + sample bank export
  static/                     index.html, app.js, style.css (no build step)
  tests/test_app.py
```

## Ideas for later

* Receipt photo → transaction, PDF statement import, monthly e-mail summary, sinking funds for yearly bills.
