/* Couple Finance front-end (vanilla JS, no build step) */
"use strict";

const S = { boot: null, month: null, me: Number(localStorage.getItem("cf_me")) || 1, page: "overview",
            txFilters: { q: "", category_id: "", person_id: "", uncategorised: "" }, importState: null };

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, path, body) {
  const res = await fetch("/api" + path, { method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  let data = {};
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) { toast(data.error || "Something went wrong", { error: true }); throw new Error(data.error || res.status); }
  return data;
}

function money(cents, opts = {}) {
  const { settings } = S.boot;
  const f = new Intl.NumberFormat(settings.locale || "en", { style: "currency", currency: settings.currency || "EUR",
    maximumFractionDigits: opts.round ? 0 : 2, minimumFractionDigits: opts.round ? 0 : 2 });
  return f.format((cents || 0) / 100);
}
const pct = (x) => (x == null ? "–" : Math.round(x * 100) + "%");

function parseMoney(text) {
  let s = String(text ?? "").trim().replace(/[^\d.,-]/g, "");
  if (!s) return NaN;
  const d = s.lastIndexOf("."), c = s.lastIndexOf(",");
  if (d > -1 && c > -1) s = d > c ? s.replace(/,/g, "") : s.replace(/\./g, "").replace(",", ".");
  else if (c > -1) s = /,\d{3}$/.test(s) && s.split(",").length > 2 ? s.replace(/,/g, "") : s.replace(",", ".");
  return Math.round(parseFloat(s) * 100);
}
const centsToInput = (c) => (c / 100).toFixed(2);

const people = () => S.boot.people;
const person = (id) => people().find((p) => p.id === id);
const personName = (id) => (id == null ? "Joint" : (person(id) || {}).name || "?");
const cats = (kind) => S.boot.categories.filter((c) => !kind || c.kind === kind);
const catById = (id) => S.boot.categories.find((c) => c.id === id);
const chip = (id) => id == null ? `<span class="chip"><span class="dot" style="background:var(--muted)"></span>Joint</span>`
  : `<span class="chip"><span class="dot" style="background:${esc(person(id).color)}"></span>${esc(person(id).name)}</span>`;
const splitLabel = (s) => ({ equal: "50 / 50", income: "By income", p1: "Only " + people()[0].name, p2: "Only " + people()[1].name }[s]);

function monthLabel(m) {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleDateString(S.boot.settings.locale || "en", { month: "long", year: "numeric" });
}
function shiftMonth(m, d) { const [y, mo] = m.split("-").map(Number); const i = y * 12 + mo - 1 + d; return `${Math.floor(i / 12)}-${String(i % 12 + 1).padStart(2, "0")}`; }
function shortMonth(m) { const [y, mo] = m.split("-").map(Number); return new Date(y, mo - 1, 1).toLocaleDateString(S.boot.settings.locale || "en", { month: "short" }); }
function fmtDate(iso) { const d = new Date(iso + "T00:00:00"); return d.toLocaleDateString(S.boot.settings.locale || "en", { day: "numeric", month: "short" }); }
function fmtDateLong(iso) { const d = new Date(iso + "T00:00:00"); return d.toLocaleDateString(S.boot.settings.locale || "en", { day: "numeric", month: "short", year: "numeric" }); }

function toast(msg, { undo, error } = {}) {
  const el = document.createElement("div");
  el.className = "toast" + (error ? " err" : "");
  el.innerHTML = `<span>${esc(msg)}</span>`;
  if (undo) { const b = document.createElement("button"); b.textContent = "Undo"; b.onclick = async () => { el.remove(); await undo(); }; el.appendChild(b); }
  $("#toast-host").appendChild(el);
  setTimeout(() => el.remove(), undo ? 8000 : 4000);
}

function modal(title, body, { onSubmit, submitLabel = "Save", wide = false, hideActions = false } = {}) {
  const host = $("#modal-host");
  host.innerHTML = `<div class="overlay"><form class="modal ${wide ? "wide" : ""}"><h2>${esc(title)}</h2>${body}
    ${hideActions ? "" : `<div class="actions"><button type="button" class="btn" data-close>Cancel</button><button class="btn primary">${esc(submitLabel)}</button></div>`}</form></div>`;
  const close = () => (host.innerHTML = "");
  host.querySelector(".overlay").addEventListener("mousedown", (e) => { if (e.target.classList.contains("overlay")) close(); });
  host.querySelectorAll("[data-close]").forEach((b) => (b.onclick = close));
  const form = host.querySelector("form");
  form.onsubmit = async (e) => {
    e.preventDefault();
    if (!onSubmit) return;
    try { const r = await onSubmit(Object.fromEntries(new FormData(form).entries()), form); if (r !== false) close(); } catch (err) { /* toast shown */ }
  };
  const first = form.querySelector("input:not([type=hidden]),select"); if (first) first.focus();
  return { close, form };
}
const closeModal = () => ($("#modal-host").innerHTML = "");

const opt = (value, label, sel) => `<option value="${esc(value)}" ${String(sel) === String(value) ? "selected" : ""}>${esc(label)}</option>`;
const catOptions = (kind, sel, blank = "Uncategorised") =>
  (blank ? opt("", blank, sel ?? "") : "") + cats(kind).map((c) => opt(c.id, `${c.icon} ${c.name}`, sel)).join("");
const personOptions = (sel, joint = true) =>
  (joint ? opt("", "Joint account", sel ?? "") : "") + people().map((p) => opt(p.id, p.name, sel)).join("");
const splitOptions = (sel) => ["equal", "income", "p1", "p2"].map((s) => opt(s, splitLabel(s), sel)).join("");

// ------------------------------------------------------------------ charts (inline SVG)
function donut(items, size = 170) {
  const total = items.reduce((a, i) => a + i.value, 0);
  if (!total) return "";
  const r = 60, C = 2 * Math.PI * r; let off = 0;
  const arcs = items.map((i) => {
    const len = (i.value / total) * C;
    const s = `<circle r="${r}" cx="80" cy="80" fill="none" stroke="${i.color}" stroke-width="26" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}" transform="rotate(-90 80 80)"><title>${esc(i.label)}: ${money(i.value)}</title></circle>`;
    off += len; return s;
  }).join("");
  return `<svg viewBox="0 0 160 160" width="${size}" height="${size}">${arcs}<text x="80" y="76" text-anchor="middle" style="font-size:11px">Spent</text><text x="80" y="94" text-anchor="middle" style="font-size:15px;font-weight:700;fill:var(--ink)">${money(total, { round: true })}</text></svg>`;
}
const PALETTE = ["#4f46e5", "#e11d74", "#12a150", "#f59e0b", "#0ea5e9", "#8b5cf6", "#ef4444", "#14b8a6", "#84cc16", "#f97316", "#64748b"];

function trendChart(data) {
  const W = 620, H = 210, pad = 28, bw = 26;
  const max = Math.max(1, ...data.map((d) => Math.max(d.income_cents, d.expense_cents)));
  const step = (W - pad * 2) / data.length;
  const y = (v) => H - 40 - (v / max) * (H - 70);
  let svg = "";
  data.forEach((d, i) => {
    const cx = pad + step * i + step / 2;
    svg += `<rect x="${cx - bw - 2}" y="${y(d.income_cents)}" width="${bw}" height="${H - 40 - y(d.income_cents)}" rx="5" fill="var(--good)" opacity=".85"><title>Income ${money(d.income_cents)}</title></rect>`;
    svg += `<rect x="${cx + 2}" y="${y(d.expense_cents)}" width="${bw}" height="${H - 40 - y(d.expense_cents)}" rx="5" fill="var(--accent)" opacity=".85"><title>Spent ${money(d.expense_cents)}</title></rect>`;
    svg += `<text x="${cx}" y="${H - 22}" text-anchor="middle">${shortMonth(d.month)}</text>`;
    svg += `<text x="${cx}" y="${H - 8}" text-anchor="middle" style="font-weight:700;fill:${d.savings_cents >= 0 ? "var(--good)" : "var(--bad)"}">${d.income_cents || d.expense_cents ? money(d.savings_cents, { round: true }) : ""}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Income and spending by month">${svg}</svg>
    <div class="legend"><span><span class="dot" style="background:var(--good)"></span> Income</span><span><span class="dot" style="background:var(--accent)"></span> Spent</span><span>Number below = saved</span></div>`;
}

// ------------------------------------------------------------------ shell
const PAGES = [["overview", "Overview"], ["transactions", "Transactions"], ["bills", "Bills & income"], ["goals", "Goals"], ["import", "Import"], ["settings", "Settings"]];

function renderShell() {
  $("#nav").innerHTML = PAGES.map(([id, label]) => `<a href="#${id}" class="${S.page === id ? "active" : ""}">${label}</a>`).join("");
  $("#m-label").textContent = monthLabel(S.month);
  $("#monthsw").style.visibility = ["overview", "transactions"].includes(S.page) ? "visible" : "hidden";
  $("#whoami").innerHTML = people().map((p) => `<button class="who-btn ${S.me === p.id ? "on" : ""}" style="${S.me === p.id ? `background:${p.color}` : ""}" data-who="${p.id}">${esc(p.name)}</button>`).join("");
  document.querySelectorAll("[data-who]").forEach((b) => (b.onclick = () => { S.me = Number(b.dataset.who); localStorage.setItem("cf_me", S.me); renderShell(); quickPreview(); }));
}

async function route() {
  S.page = (location.hash || "#overview").slice(1).split("?")[0];
  if (!PAGES.some(([id]) => id === S.page)) S.page = "overview";
  renderShell();
  const v = $("#view");
  v.innerHTML = `<div class="empty muted">Loading…</div>`;
  try { await VIEWS[S.page](v); } catch (e) { console.error(e); v.innerHTML = `<div class="empty"><div class="emoji">⚠️</div>${esc(e.message)}</div>`; }
}
const refresh = () => route();

// ------------------------------------------------------------------ OVERVIEW
async function viewOverview(v) {
  const [s, trend, goals, rec] = await Promise.all([api("GET", `/summary?month=${S.month}`), api("GET", `/trends?month=${S.month}&n=6`),
    api("GET", "/goals"), api("GET", "/recurring?days=14")]);
  if (!S.boot.has_data && s.tx_count === 0 && !S.boot.settings.setup_done) return welcome(v);
  const d = (cur, prev, goodUp = true) => {
    if (!prev) return `<span class="delta muted">no data last month</span>`;
    const diff = cur - prev; const up = diff >= 0; const good = up === goodUp;
    return `<span class="delta ${good ? "good" : "bad"}">${up ? "▲" : "▼"} ${money(Math.abs(diff), { round: true })} vs last month</span>`;
  };
  const max = Math.max(s.income_cents, s.expense_cents, 1);
  const saved = Math.max(s.savings_cents, 0);
  const flow = `<div class="flow">
    <div style="width:${s.fixed_cents / max * 100}%;background:#6366f1" title="Fixed bills">${s.fixed_cents / max > .12 ? "Bills" : ""}</div>
    <div style="width:${s.variable_cents / max * 100}%;background:#f59e0b" title="Everyday spending">${s.variable_cents / max > .12 ? "Everyday" : ""}</div>
    <div style="width:${saved / max * 100}%;background:var(--good)" title="Saved">${saved / max > .1 ? "Saved" : ""}</div></div>
    <div class="legend"><span><span class="dot" style="background:#6366f1"></span> Rent & bills ${money(s.fixed_cents, { round: true })}</span>
    <span><span class="dot" style="background:#f59e0b"></span> Everyday ${money(s.variable_cents, { round: true })}</span>
    <span><span class="dot" style="background:var(--good)"></span> Saved ${money(saved, { round: true })}</span></div>`;

  const catTotal = s.categories.reduce((a, c) => a + c.amount_cents, 0);
  const top = s.categories.slice(0, 9).map((c, i) => ({ ...c, color: PALETTE[i % PALETTE.length] }));
  const rest = s.categories.slice(9).reduce((a, c) => a + c.amount_cents, 0);
  if (rest) top.push({ name: "Other categories", icon: "•", amount_cents: rest, color: PALETTE[10] });
  const catRows = top.map((c) => {
    const p = c.amount_cents / Math.max(catTotal, 1);
    const over = c.budget_cents && c.amount_cents > c.budget_cents;
    return `<div class="row"><span class="dot" style="background:${c.color}"></span><div class="grow"><div style="display:flex;justify-content:space-between;gap:8px"><span class="title">${c.icon} ${esc(c.name)}</span><b>${money(c.amount_cents)}</b></div>
      ${c.budget_cents ? `<div class="bar ${over ? "bad" : c.amount_cents > c.budget_cents * .85 ? "warn" : "good"}" style="margin-top:5px"><i style="width:${Math.min(c.amount_cents / c.budget_cents, 1) * 100}%"></i></div><div class="small muted">Budget ${money(c.budget_cents, { round: true })} · ${over ? "over by " + money(c.amount_cents - c.budget_cents) : money(c.budget_cents - c.amount_cents) + " left"}</div>`
        : `<div class="small muted">${pct(p)} of spending${c.prev_cents ? " · last month " + money(c.prev_cents, { round: true }) : ""}</div>`}</div></div>`;
  }).join("");

  const st = s.settlement; const [p1, p2] = s.people;
  const settleHtml = st.amount_cents > 0
    ? `<div style="font-size:1.05rem"><b style="color:${person(st.from_person).color}">${esc(personName(st.from_person))}</b> owes <b style="color:${person(st.to_person).color}">${esc(personName(st.to_person))}</b> <b>${money(st.amount_cents)}</b></div>`
    : `<div class="good"><b>All square 🎉</b></div>`;
  const jc = st.joint_contribution_cents;
  const personCards = `<div class="card"><div class="card-head"><h3>Who brought what</h3></div>
    ${s.people.map((p) => `<div class="row"><span class="dot" style="background:${p.color}"></span><div class="grow"><div class="title">${esc(p.name)}</div>
      <div class="small muted">Income ${money(s.person_income_cents[p.id], { round: true })} · paid ${money(s.person_paid_cents[p.id], { round: true })}</div></div>
      <div class="right small"><div class="muted">share of income</div><b>${pct(st.ratio[p.id])}</b></div></div>`).join("")}
    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--line)"><div class="small muted" style="margin-bottom:4px">Settle-up for shared costs</div>${settleHtml}
    ${(jc["1"] || jc["2"]) ? `<div class="small muted" style="margin-top:6px">Paid from the joint account: ${esc(p1.name)}'s fair share ${money(jc["1"], { round: true })}, ${esc(p2.name)}'s ${money(jc["2"], { round: true })}</div>` : ""}</div></div>`;

  const fc = s.forecast;
  const forecastHtml = fc ? `<div class="card"><div class="card-head"><h3>📈 Rest of the month</h3><span class="badge">${fc.days_left} days left</span></div>
    <dl class="kv"><dt>Bills still to come</dt><dd>${money(fc.upcoming_expense_cents)}</dd><dt>Everyday spending pace</dt><dd>${money(fc.daily_variable_cents)} / day</dd>
    <dt>Expected income still to arrive</dt><dd>${money(fc.upcoming_income_cents)}</dd><dt>Projected total spend</dt><dd>${money(fc.projected_expense_cents)}</dd>
    <dt>Projected savings</dt><dd class="${fc.projected_savings_cents >= 0 ? "good" : "bad"}">${money(fc.projected_savings_cents)}</dd></dl></div>` : "";

  const need = s.split503020, inc = s.income_cents || 1;
  const rule = (label, val, target, color) => `<div style="margin-bottom:10px"><div style="display:flex;justify-content:space-between"><span>${label}</span><span><b>${pct(val / inc)}</b> <span class="muted small">target ${target}%</span></span></div><div class="bar"><i style="width:${Math.min(val / inc, 1) * 100}%;background:${color}"></i></div></div>`;

  const upcomingHtml = rec.upcoming.length ? rec.upcoming.slice(0, 6).map((u) => `<div class="row"><div class="ico">${u.type === "income" ? "💶" : "🧾"}</div><div class="grow"><div class="title">${esc(u.name)}</div><div class="small muted">${fmtDate(u.date)} · ${personName(u.person_id)}</div></div><b class="${u.type === "income" ? "good" : ""}">${u.type === "income" ? "+" : ""}${money(u.amount_cents)}</b></div>`).join("")
    : `<div class="muted small">Nothing due in the next 2 weeks. Add your recurring bills in “Bills & income”.</div>`;

  const goalsHtml = goals.goals.filter((g) => !g.done).slice(0, 4).map((g) => `<div style="margin-bottom:12px"><div style="display:flex;justify-content:space-between"><span>${esc(g.icon)} <b>${esc(g.name)}</b></span><span class="small muted">${money(g.saved_cents, { round: true })} / ${money(g.target_cents, { round: true })}</span></div><div class="bar ${g.on_track ? "good" : "warn"}" style="margin-top:4px"><i style="width:${g.pct}%"></i></div></div>`).join("") || `<div class="muted small">No goals yet — add one in the Goals tab.</div>`;

  v.innerHTML = `<div class="stack">
    ${s.uncategorised_count ? `<div class="insight warn"><span>🏷️</span><span>${s.uncategorised_count} transactions need a category. <a href="#transactions" id="go-uncat">Review them</a> — every answer teaches the app for next time.</span></div>` : ""}
    <div class="grid g3">
      <div class="card stat"><div class="label">Combined income</div><div class="value good">${money(s.income_cents)}</div>${d(s.income_cents, s.prev.income_cents)}</div>
      <div class="card stat"><div class="label">Spent</div><div class="value">${money(s.expense_cents)}</div>${d(s.expense_cents, s.prev.expense_cents, false)}</div>
      <div class="card stat"><div class="label">Saved together</div><div class="value ${s.savings_cents >= 0 ? "good" : "bad"}">${money(s.savings_cents)}</div><span class="delta muted">${s.savings_rate == null ? "" : pct(s.savings_rate) + " of income · "}${s.goal_contributed_cents ? money(s.goal_contributed_cents, { round: true }) + " moved to goals" : "not yet moved to goals"}</span></div>
    </div>
    <div class="card"><div class="card-head"><h3>Where the income went</h3></div>${flow}</div>
    <div class="grid g-main"><div class="stack">
      <div class="card"><div class="card-head"><h3>Spending by category</h3></div>
        ${s.categories.length ? `<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap"><div>${donut(top.map((c) => ({ label: c.name, value: c.amount_cents, color: c.color })))}</div><div style="flex:1;min-width:260px">${catRows}</div></div>` : `<div class="muted">No spending recorded in ${monthLabel(S.month)}.</div>`}</div>
      <div class="card"><div class="card-head"><h3>Last 6 months</h3></div>${trendChart(trend)}</div></div>
    <div class="stack">
      <div class="card"><div class="card-head"><h3>💡 Insights</h3></div>${s.insights.map((i) => `<div class="insight ${i.level === "info" ? "" : i.level}"><span>${{ good: "✅", warn: "⚠️", bad: "🚨", info: "ℹ️" }[i.level]}</span><span>${esc(i.text)}</span></div>`).join("")}</div>
      ${personCards}${forecastHtml}
      <div class="card"><div class="card-head"><h3>Budget rule 50/30/20</h3></div>${rule("Needs", need.needs_cents, 50, "#6366f1")}${rule("Wants", need.wants_cents, 30, "#f59e0b")}${rule("Savings", need.savings_cents, 20, "var(--good)")}</div>
      <div class="card"><div class="card-head"><h3>Coming up</h3><a href="#bills" class="small">All bills</a></div>${upcomingHtml}</div>
      <div class="card"><div class="card-head"><h3>🎯 Goals</h3><a href="#goals" class="small">Open</a></div>${goalsHtml}
        ${s.unallocated_cents > 0 && goals.goals.some((g) => g.planned_monthly_cents > 0) ? `<button class="btn primary sm" id="sweep" style="margin-top:6px">Move ${money(s.unallocated_cents, { round: true })} savings into goals</button>` : ""}</div>
    </div></div></div>`;
  const sw = $("#sweep"); if (sw) sw.onclick = async () => { const r = await api("POST", "/goals/sweep", { month: S.month }); toast(`Moved savings into ${r.moved.length} goal(s)`); refresh(); };
  const gu = $("#go-uncat"); if (gu) gu.onclick = () => { S.txFilters.uncategorised = "1"; };
}

function welcome(v) {
  v.innerHTML = `<div class="card" style="max-width:680px;margin:30px auto"><h2>Welcome 👋 Let's set this up in a minute</h2>
    <p class="muted">Two people, one money picture. The fastest way to start is to let the app read your bank export instead of typing things in.</p>
    <form id="wform"><div class="fields2"><div class="field"><label>Your name</label><input type="text" name="n1" value="${esc(people()[0].name === "Me" ? "" : people()[0].name)}" placeholder="e.g. Hammad" required></div>
      <div class="field"><label>Partner's name</label><input type="text" name="n2" value="${esc(people()[1].name === "Partner" ? "" : people()[1].name)}" placeholder="e.g. Sara" required></div></div>
      <div class="field"><label>How should shared costs (rent, bills) be split?</label><select name="split">${opt("income", "In proportion to income (fair when incomes differ)", S.boot.settings.default_split)}${opt("equal", "50 / 50", S.boot.settings.default_split)}</select></div>
      <button class="btn primary">Save & continue</button></form>
    <hr style="border:0;border-top:1px solid var(--line);margin:22px 0">
    <h3>Then pick a starting point</h3>
    <div class="grid g3" style="margin-top:10px">
      <a class="card" href="#import" style="text-decoration:none"><div style="font-size:1.6rem">🏦</div><b>Import bank CSV</b><div class="small muted">Best option: hundreds of transactions in seconds, auto-categorised.</div></a>
      <a class="card" href="#bills" style="text-decoration:none"><div style="font-size:1.6rem">🔁</div><b>Add salaries & rent</b><div class="small muted">Set once, then it books itself every month.</div></a>
      <a class="card" href="#" id="demo" style="text-decoration:none"><div style="font-size:1.6rem">🧪</div><b>Explore with demo data</b><div class="small muted">See every feature filled in. Can be wiped anytime.</div></a></div></div>`;
  $("#wform").onsubmit = async (e) => {
    e.preventDefault(); const f = Object.fromEntries(new FormData(e.target).entries());
    const ps = people().map((p, i) => ({ id: p.id, name: f["n" + (i + 1)], color: p.color }));
    S.boot = await api("PUT", "/settings", { people: ps, default_split: f.split, setup_done: "1" }); S.month = S.boot.month; toast("Saved. Now import your bank file or add your salaries."); renderShell();
  };
  $("#demo").onclick = async (e) => { e.preventDefault(); await api("POST", "/demo", {}); S.boot = await api("GET", "/bootstrap"); toast("Demo data loaded"); route(); };
}

// ------------------------------------------------------------------ TRANSACTIONS
async function viewTransactions(v) {
  const f = S.txFilters;
  const params = new URLSearchParams({ limit: 1000 });
  if (!f.uncategorised && !f.q) params.set("month", S.month);
  else if (f.q || f.uncategorised) { /* search across all time */ }
  ["q", "category_id", "person_id", "uncategorised"].forEach((k) => f[k] && params.set(k, f[k]));
  const txs = await api("GET", "/transactions?" + params);
  const sumIn = txs.filter((t) => t.type === "income").reduce((a, t) => a + t.amount_cents, 0);
  const sumOut = txs.filter((t) => t.type === "expense").reduce((a, t) => a + t.amount_cents, 0);
  v.innerHTML = `<div class="page-head"><div><h2>Transactions</h2><div class="muted small">${f.uncategorised || f.q ? "Across all months" : monthLabel(S.month)} · ${txs.length} entries · in ${money(sumIn)} · out ${money(sumOut)}</div></div>
    <button class="btn primary" id="add-tx">+ Add transaction</button></div>
    <div class="card"><div class="filters"><input type="search" id="f-q" placeholder="Search description…" value="${esc(f.q)}">
    <select id="f-cat">${opt("", "All categories", f.category_id)}${cats().map((c) => opt(c.id, `${c.icon} ${c.name}`, f.category_id)).join("")}</select>
    <select id="f-person">${opt("", "Everyone", f.person_id)}${opt("joint", "Joint", f.person_id)}${people().map((p) => opt(p.id, p.name, f.person_id)).join("")}</select>
    <label class="check"><input type="checkbox" id="f-unc" ${f.uncategorised ? "checked" : ""}> Needs category</label></div>
    ${txs.length ? `<div class="tx-row head"><div>Date</div><div>Description</div><div>Category</div><div>Who · split</div><div class="right">Amount</div><div></div></div>` +
      txs.map((t) => `<div class="tx-row" data-id="${t.id}"><div class="c-date small muted">${fmtDateLong(t.date)}</div>
        <div class="c-desc desc" title="${esc(t.description)}">${t.recurring_id ? "🔁 " : ""}${esc(t.description || "(no description)")}</div>
        <div class="c-cat">${t.type === "transfer" ? `<span class="badge">🔄 Transfer</span>` : `<select class="inline cat-sel" data-id="${t.id}">${catOptions(t.type, t.category_id ?? "", t.category_id ? null : "❓ Choose category…")}</select>`}</div>
        <div class="c-who">${chip(t.person_id)}${t.type === "expense" ? `<div class="small muted">${splitLabel(t.split)}</div>` : ""}</div>
        <div class="c-amt right"><b class="${t.type === "income" ? "good" : ""}">${t.type === "income" ? "+" : t.type === "expense" ? "−" : ""}${money(t.amount_cents)}</b></div>
        <div class="c-act right nowrap"><button class="btn ghost sm" data-edit="${t.id}" title="Edit">✏️</button></div></div>`).join("")
      : `<div class="empty"><div class="emoji">🗒️</div>Nothing here yet. Use the quick-add bar above or import a bank file.</div>`}</div>`;
  let timer; $("#f-q").oninput = (e) => { clearTimeout(timer); timer = setTimeout(() => { f.q = e.target.value; refresh(); }, 350); };
  $("#f-q").onkeydown = (e) => e.key === "Enter" && e.stopPropagation();
  $("#f-cat").onchange = (e) => { f.category_id = e.target.value; refresh(); };
  $("#f-person").onchange = (e) => { f.person_id = e.target.value; refresh(); };
  $("#f-unc").onchange = (e) => { f.uncategorised = e.target.checked ? "1" : ""; refresh(); };
  $("#add-tx").onclick = () => txModal();
  v.querySelectorAll(".cat-sel").forEach((sel) => (sel.onchange = async () => {
    if (!sel.value) return;
    const r = await api("PATCH", `/transactions/${sel.dataset.id}`, { category_id: Number(sel.value), learn: true });
    toast(r.auto_categorised_others ? `Saved — and categorised ${r.auto_categorised_others} other similar transaction(s) too` : "Saved — I'll remember this merchant");
    refresh();
  }));
  v.querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => txModal(txs.find((t) => t.id === Number(b.dataset.edit)))));
}

function txModal(t) {
  const isNew = !t; t = t || { date: S.boot.today, type: "expense", amount_cents: "", description: "", category_id: null, person_id: S.me, split: S.boot.settings.default_split, note: "" };
  const { form } = modal(isNew ? "Add transaction" : "Edit transaction", `
    <div class="field"><label>Type</label><select name="type" id="t-type">${opt("expense", "Expense", t.type)}${opt("income", "Income", t.type)}${opt("transfer", "Transfer between own accounts (ignored in totals)", t.type)}</select></div>
    <div class="fields2"><div class="field"><label>Amount</label><input type="text" inputmode="decimal" name="amount" value="${t.amount_cents === "" ? "" : centsToInput(t.amount_cents)}" required></div>
      <div class="field"><label>Date</label><input type="date" name="date" value="${t.date}" required></div></div>
    <div class="field"><label>Description</label><input type="text" name="description" value="${esc(t.description)}" placeholder="e.g. Jumbo" ></div>
    <div class="field"><label>Category</label><select name="category_id" id="t-cat"></select></div>
    <div class="fields2"><div class="field"><label id="t-who-l">Paid by</label><select name="person_id">${personOptions(t.person_id ?? "")}</select></div>
      <div class="field" id="t-split-f"><label>Split</label><select name="split">${splitOptions(t.split)}</select></div></div>
    <div class="field"><label>Note</label><input type="text" name="note" value="${esc(t.note || "")}"></div>
    <label class="check"><input type="checkbox" name="learn" checked> Remember this description → category for next time</label>
    ${isNew ? "" : `<div style="margin-top:12px"><button type="button" class="btn danger sm" id="t-del">Delete transaction</button></div>`}`, {
    submitLabel: isNew ? "Add" : "Save",
    onSubmit: async (f) => {
      const cents = parseMoney(f.amount); if (!(cents >= 0)) { toast("Enter a valid amount", { error: true }); return false; }
      const body = { type: f.type, amount_cents: cents, date: f.date, description: f.description, category_id: f.category_id || null, person_id: f.person_id === "" ? null : Number(f.person_id), split: f.split, note: f.note, learn: !!f.learn && !!f.category_id };
      await api(isNew ? "POST" : "PATCH", isNew ? "/transactions" : `/transactions/${t.id}`, body); refresh();
    } });
  const sync = () => {
    const type = form.type.value; const cat = form.category_id;
    const cur = cat.value || (t.category_id ?? "");
    cat.innerHTML = type === "transfer" ? catOptions("transfer", cur, null) : catOptions(type, cur); if (type === "transfer" && !cat.value) cat.selectedIndex = 0;
    $("#t-split-f").style.display = type === "expense" ? "" : "none"; $("#t-who-l").textContent = type === "income" ? "Received by" : "Paid by";
  };
  form.type.onchange = () => { form.category_id.value = ""; sync(); }; sync();
  const del = $("#t-del"); if (del) del.onclick = async () => { if (!confirm("Delete this transaction?")) return; await api("DELETE", `/transactions/${t.id}`); closeModal(); toast("Deleted"); refresh(); };
}

// ------------------------------------------------------------------ BILLS & INCOME (recurring)
const FREQ = { weekly: "Weekly", biweekly: "Every 2 weeks", monthly: "Monthly", quarterly: "Every 3 months", yearly: "Yearly" };

async function viewBills(v) {
  const [r, sug] = await Promise.all([api("GET", "/recurring?days=45"), api("GET", "/recurring/suggestions")]);
  const active = r.items.filter((i) => i.active), paused = r.items.filter((i) => !i.active);
  const item = (i) => `<div class="row"><div class="ico">${i.category_icon || (i.type === "income" ? "💶" : "🧾")}</div><div class="grow"><div class="title">${esc(i.name)}</div>
    <div class="small muted">${FREQ[i.frequency]} · from ${fmtDateLong(i.start_date)} · ${personName(i.person_id)}${i.type === "expense" ? " · " + splitLabel(i.split) : ""}${i.frequency !== "monthly" ? " · ≈ " + money(i.monthly_cents, { round: true }) + "/mo" : ""}</div></div>
    <b class="${i.type === "income" ? "good" : ""}">${money(i.amount_cents)}</b>
    <button class="btn ghost sm" data-redit="${i.id}">✏️</button></div>`;
  const suggHtml = sug.length ? `<div class="card" style="border-color:var(--accent)"><div class="card-head"><div><h3>✨ Found ${sug.length} repeating item${sug.length > 1 ? "s" : ""} in your history</h3><div class="small muted">Track them as recurring and they'll be booked automatically (and matched to your bank lines when you import).</div></div><button class="btn primary sm" id="sug-all">Add all</button></div>
    ${sug.map((s, i) => `<div class="row"><div class="ico">${(catById(s.category_id) || {}).icon || "🔁"}</div><div class="grow"><div class="title">${esc(s.name)}</div><div class="small muted">${FREQ[s.frequency]} · seen ${s.occurrences}× · next ≈ ${fmtDate(s.next_date)} · ${personName(s.person_id)}</div></div><b class="${s.type === "income" ? "good" : ""}">${money(s.amount_cents)}</b><button class="btn sm" data-sug="${i}">Track</button></div>`).join("")}</div>` : "";
  v.innerHTML = `<div class="page-head"><div><h2>Bills & recurring income</h2><div class="muted small">Set once — the app books these for you every period.</div></div><button class="btn primary" id="add-rec">+ Add recurring item</button></div>
    <div class="stack">${suggHtml}
    <div class="grid g3"><div class="card stat"><div class="label">Expected income / month</div><div class="value good">${money(r.monthly_income_cents)}</div></div>
      <div class="card stat"><div class="label">Fixed costs / month</div><div class="value">${money(r.monthly_expense_cents)}</div></div>
      <div class="card stat"><div class="label">Left after fixed costs</div><div class="value ${r.monthly_income_cents - r.monthly_expense_cents >= 0 ? "good" : "bad"}">${money(r.monthly_income_cents - r.monthly_expense_cents)}</div>
      <span class="delta muted">before groceries & everyday spending</span></div></div>
    <div class="grid g2"><div class="card"><div class="card-head"><h3>💶 Income</h3></div>${active.filter((i) => i.type === "income").map(item).join("") || `<div class="muted small">No recurring income yet — add both salaries.</div>`}</div>
      <div class="card"><div class="card-head"><h3>🧾 Rent, bills & subscriptions</h3></div>${active.filter((i) => i.type === "expense").map(item).join("") || `<div class="muted small">No recurring bills yet — add rent first.</div>`}</div></div>
    ${r.upcoming.length ? `<div class="card"><div class="card-head"><h3>Next 45 days</h3></div>${r.upcoming.map((u) => `<div class="row"><div class="small muted" style="width:70px">${fmtDate(u.date)}</div><div class="grow title">${esc(u.name)}</div><span class="small muted">${personName(u.person_id)}</span><b class="${u.type === "income" ? "good" : ""}">${u.type === "income" ? "+" : ""}${money(u.amount_cents)}</b></div>`).join("")}</div>` : ""}
    ${paused.length ? `<div class="card"><div class="card-head"><h3>Paused</h3></div>${paused.map(item).join("")}</div>` : ""}</div>`;
  $("#add-rec").onclick = () => recModal();
  v.querySelectorAll("[data-redit]").forEach((b) => (b.onclick = () => recModal(r.items.find((i) => i.id === Number(b.dataset.redit)))));
  const addSug = async (s) => api("POST", "/recurring", { name: s.name, type: s.type, amount_cents: s.amount_cents, category_id: s.category_id, person_id: s.person_id, split: s.split, frequency: s.frequency, start_date: s.start_date, mark_generated_until: s.last_date, link_tx_ids: s.tx_ids });
  v.querySelectorAll("[data-sug]").forEach((b) => (b.onclick = async () => { await addSug(sug[Number(b.dataset.sug)]); toast("Now tracked as recurring"); refresh(); }));
  const all = $("#sug-all"); if (all) all.onclick = async () => { for (const s of sug) await addSug(s); toast(`Tracking ${sug.length} recurring items`); refresh(); };
}

function recModal(r) {
  const isNew = !r; r = r || { name: "", type: "expense", amount_cents: "", category_id: null, person_id: S.me, split: S.boot.settings.default_split, frequency: "monthly", start_date: S.boot.today, end_date: "", active: 1 };
  const { form } = modal(isNew ? "Add recurring item" : "Edit recurring item", `
    <div class="field"><label>Type</label><select name="type" id="r-type">${opt("expense", "Bill / expense", r.type)}${opt("income", "Income (salary etc.)", r.type)}</select></div>
    <div class="field"><label>Name</label><input type="text" name="name" value="${esc(r.name)}" placeholder="e.g. Rent, Salary Sam, Netflix" required></div>
    <div class="fields2"><div class="field"><label>Amount</label><input type="text" inputmode="decimal" name="amount" value="${r.amount_cents === "" ? "" : centsToInput(r.amount_cents)}" required></div>
      <div class="field"><label>Repeats</label><select name="frequency">${Object.entries(FREQ).map(([k, l]) => opt(k, l, r.frequency)).join("")}</select></div></div>
    <div class="fields2"><div class="field"><label>First / next date</label><input type="date" name="start_date" value="${r.start_date}" required></div>
      <div class="field"><label>Ends (optional)</label><input type="date" name="end_date" value="${r.end_date || ""}"></div></div>
    <div class="field"><label>Category</label><select name="category_id" id="r-cat"></select></div>
    <div class="fields2"><div class="field"><label id="r-who-l">Paid by</label><select name="person_id">${personOptions(r.person_id ?? "")}</select></div>
      <div class="field" id="r-split-f"><label>Split</label><select name="split">${splitOptions(r.split)}</select></div></div>
    ${isNew ? `<p class="small muted">If the start date is in the past, earlier entries are created too — handy for back-filling.</p>` : `<label class="check"><input type="checkbox" name="active" ${r.active ? "checked" : ""}> Active</label><div style="margin-top:12px"><button type="button" class="btn danger sm" id="r-del">Delete (keeps past transactions)</button></div>`}`, {
    onSubmit: async (f) => {
      const cents = parseMoney(f.amount); if (!(cents >= 0)) { toast("Enter a valid amount", { error: true }); return false; }
      const body = { name: f.name, type: f.type, amount_cents: cents, frequency: f.frequency, start_date: f.start_date, end_date: f.end_date || null, category_id: f.category_id || null, person_id: f.person_id === "" ? null : Number(f.person_id), split: f.split };
      if (!isNew) body.active = !!f.active;
      await api(isNew ? "POST" : "PATCH", isNew ? "/recurring" : `/recurring/${r.id}`, body); refresh();
    } });
  const sync = () => { const t = form.type.value; form.category_id.innerHTML = catOptions(t, r.category_id ?? ""); $("#r-split-f").style.display = t === "expense" ? "" : "none"; $("#r-who-l").textContent = t === "income" ? "Received by" : "Paid by"; };
  form.type.onchange = () => { r.category_id = null; sync(); }; sync();
  const del = $("#r-del"); if (del) del.onclick = async () => { if (!confirm("Delete this recurring item?")) return; await api("DELETE", `/recurring/${r.id}`); closeModal(); refresh(); };
}

// ------------------------------------------------------------------ GOALS
async function viewGoals(v) {
  const o = await api("GET", "/goals");
  const goalCard = (g) => `<div class="card goal"><div class="top"><div class="ico big">${esc(g.icon)}</div><div class="grow" style="flex:1"><div style="font-weight:700;font-size:1.05rem">${esc(g.name)}</div>
    <div class="small muted">${g.deadline ? "Target date " + fmtDateLong(g.deadline) : "No deadline"} · ${["", "High", "Normal", "Low"][g.priority]} priority</div></div>
    ${g.done ? `<span class="badge good">Achieved 🎉</span>` : g.on_track ? `<span class="badge good">On track</span>` : `<span class="badge warn">Needs attention</span>`}</div>
    <div><div style="display:flex;justify-content:space-between;margin-bottom:4px"><b>${money(g.saved_cents)}</b><span class="muted">of ${money(g.target_cents)}</span></div><div class="bar ${g.done || g.on_track ? "good" : "warn"}"><i style="width:${g.pct}%"></i></div></div>
    ${g.done ? "" : `<dl class="kv"><dt>Still needed</dt><dd>${money(g.remaining_cents)}</dd>
      ${g.required_monthly_cents != null ? `<dt>Needed per month to hit the date</dt><dd>${money(g.required_monthly_cents)}</dd>` : ""}
      <dt>Suggested per month</dt><dd>${money(g.planned_monthly_cents)}</dd>
      <dt>Estimated finish</dt><dd class="${g.on_track ? "" : "warn"}">${g.eta ? fmtDateLong(g.eta) : "Not with current savings"}</dd></dl>`}
    <div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm primary" data-add="${g.id}">+ Add money</button><button class="btn sm" data-hist="${g.id}">History</button><button class="btn sm" data-gedit="${g.id}">Edit</button></div></div>`;
  v.innerHTML = `<div class="page-head"><div><h2>Goals</h2><div class="muted small">What you want together, what it costs, and when you'll get there.</div></div><button class="btn primary" id="add-goal">+ New goal</button></div>
    <div class="stack"><div class="grid g3">
      <div class="card stat"><div class="label">Saved toward goals</div><div class="value good">${money(o.total_saved_cents)}</div><span class="delta muted">of ${money(o.total_target_cents)} total</span></div>
      <div class="card stat"><div class="label">You typically save</div><div class="value">${money(o.avg_monthly_savings_cents)}<span class="small muted"> /mo</span></div><span class="delta muted">average of the last full months</span></div>
      <div class="card stat"><div class="label">Deadlines need</div><div class="value ${o.fits ? "good" : "bad"}">${money(o.required_monthly_cents)}<span class="small muted"> /mo</span></div><span class="delta ${o.fits ? "good" : "bad"}">${o.fits ? "✔ fits in your savings" : "✖ more than you save — extend a date or trim spending"}</span></div></div>
    ${o.goals.length ? `<div class="grid g2">${o.goals.map(goalCard).join("")}</div>` : `<div class="card empty"><div class="emoji">🎯</div><b>No goals yet</b><p>Add things like “Holiday in Japan — €4,500 by next August” and the app works out what to set aside each month.</p></div>`}
    ${o.goals.length ? `<div class="card"><b>How the plan works:</b> <span class="muted">goals with a deadline are funded first (earliest first), the remaining monthly savings are shared among the other goals by priority. Use “Move savings into goals” on the Overview each month and contributions are booked for you.</span></div>` : ""}</div>`;
  $("#add-goal").onclick = () => goalModal();
  v.querySelectorAll("[data-gedit]").forEach((b) => (b.onclick = () => goalModal(o.goals.find((g) => g.id === Number(b.dataset.gedit)))));
  v.querySelectorAll("[data-add]").forEach((b) => (b.onclick = () => contribModal(o.goals.find((g) => g.id === Number(b.dataset.add)))));
  v.querySelectorAll("[data-hist]").forEach((b) => (b.onclick = () => historyModal(o.goals.find((g) => g.id === Number(b.dataset.hist)))));
}
const ICONS = ["🎯", "🏖️", "🗾", "✈️", "🏡", "🚗", "💍", "👶", "💻", "📱", "🛟", "🎓", "🛋️", "🎸", "🐶", "🎁"];
function goalModal(g) {
  const isNew = !g; g = g || { name: "", icon: "🎯", target_cents: "", deadline: "", priority: 2, note: "" };
  modal(isNew ? "New goal" : "Edit goal", `
    <div class="field"><label>What do you want?</label><input type="text" name="name" value="${esc(g.name)}" placeholder="e.g. Holiday in Japan" required></div>
    <div class="fields2"><div class="field"><label>How much does it cost?</label><input type="text" inputmode="decimal" name="target" value="${g.target_cents === "" ? "" : centsToInput(g.target_cents)}" required></div>
      <div class="field"><label>By when? (optional)</label><input type="date" name="deadline" value="${g.deadline || ""}"></div></div>
    <div class="fields2"><div class="field"><label>Icon</label><select name="icon">${ICONS.map((i) => opt(i, i, g.icon)).join("")}</select></div>
      <div class="field"><label>Priority</label><select name="priority">${opt(1, "High", g.priority)}${opt(2, "Normal", g.priority)}${opt(3, "Low", g.priority)}</select></div></div>
    ${isNew ? `<div class="field"><label>Already saved for it (optional)</label><input type="text" inputmode="decimal" name="saved" placeholder="0,00"></div>` : `<div style="margin-top:8px"><button type="button" class="btn danger sm" id="g-del">Delete goal</button></div>`}`, {
    onSubmit: async (f) => {
      const target = parseMoney(f.target); if (!(target > 0)) { toast("Enter the target amount", { error: true }); return false; }
      const body = { name: f.name, target_cents: target, deadline: f.deadline || null, icon: f.icon, priority: Number(f.priority) };
      if (isNew && f.saved) body.saved_cents = parseMoney(f.saved) || 0;
      await api(isNew ? "POST" : "PATCH", isNew ? "/goals" : `/goals/${g.id}`, body); refresh();
    } });
  const del = $("#g-del"); if (del) del.onclick = async () => { if (!confirm("Delete this goal and its history?")) return; await api("DELETE", `/goals/${g.id}`); closeModal(); refresh(); };
}
function contribModal(g) {
  modal(`Add to “${g.name}”`, `<div class="fields2"><div class="field"><label>Amount</label><input type="text" inputmode="decimal" name="amount" required placeholder="e.g. 150"></div><div class="field"><label>Date</label><input type="date" name="date" value="${S.boot.today}"></div></div>
    <div class="field"><label>From</label><select name="person_id">${personOptions("")}</select></div><div class="field"><label>Note</label><input type="text" name="note"></div>
    <p class="small muted">Tip: enter a negative amount to withdraw money from the goal.</p>`, {
    submitLabel: "Add", onSubmit: async (f) => { const c = parseMoney(f.amount); if (!c) { toast("Enter an amount", { error: true }); return false; }
      await api("POST", `/goals/${g.id}/contributions`, { amount_cents: c, date: f.date, person_id: f.person_id === "" ? null : Number(f.person_id), note: f.note }); refresh(); } });
}
async function historyModal(g) {
  const list = await api("GET", `/goals/${g.id}/contributions`);
  modal(`${g.icon} ${g.name} — history`, list.length ? list.map((c) => `<div class="row"><div class="grow"><div class="title">${fmtDateLong(c.date)}</div><div class="small muted">${personName(c.person_id)}${c.note ? " · " + esc(c.note) : ""}</div></div><b class="${c.amount_cents < 0 ? "bad" : "good"}">${money(c.amount_cents)}</b><button class="btn ghost sm" data-cdel="${c.id}">🗑️</button></div>`).join("") : `<div class="muted">Nothing added yet.</div>`, { hideActions: true });
  $("#modal-host").querySelectorAll("[data-cdel]").forEach((b) => (b.onclick = async () => { await api("DELETE", `/contributions/${b.dataset.cdel}`); closeModal(); refresh(); }));
  const form = $("#modal-host form"); const cl = document.createElement("div"); cl.className = "actions"; cl.innerHTML = `<button type="button" class="btn" data-close>Close</button>`; form.appendChild(cl); cl.firstChild.onclick = closeModal;
}

// ------------------------------------------------------------------ IMPORT
async function viewImport(v) {
  const st = S.importState;
  if (st && st.preview) return importPreview(v);
  v.innerHTML = `<div class="page-head"><div><h2>Import from your bank</h2><div class="muted small">The quickest way to fill the app. Download a CSV export from your banking app/website (ING, ABN AMRO, Rabobank, bunq, Revolut, Wise and most others work) and drop it here.</div></div></div>
    <div class="grid g-main"><div class="card stack">
      <div class="field"><label>Whose account is this?</label><select id="imp-person">${personOptions(S.me, true)}</select></div>
      <div class="drop" id="drop"><div style="font-size:2rem">📥</div><b>Drop CSV file here</b><div class="small">or click to choose a file</div><input type="file" id="file" accept=".csv,.txt,text/csv" hidden></div>
      <div class="field"><label>…or paste the file contents</label><textarea id="imp-text" rows="5" placeholder="Datum;Omschrijving;Bedrag…"></textarea><div style="margin-top:8px;display:flex;gap:8px"><button class="btn primary" id="imp-go">Preview</button><button class="btn" id="imp-sample">Try with sample file</button></div></div></div>
    <div class="card"><h3>What happens automatically</h3><ul class="small" style="padding-left:18px;line-height:1.7"><li><b>Columns are detected</b> — Dutch & English headers, ; or , separators, 1.234,56 amounts, Af/Bij columns.</li><li><b>Categories are guessed</b> from merchant names (Albert Heijn, Jumbo, Ziggo, NS…) and from your past corrections.</li><li><b>Duplicates are skipped</b> — re-importing an overlapping export is safe.</li><li><b>Bills are matched</b> — a bank line for your rent replaces the auto-booked rent instead of counting twice.</li><li><b>Own-account transfers</b> (e.g. to savings) are kept out of your spending.</li><li>Repeating payments are then <b>suggested as recurring bills</b>.</li></ul>
    <p class="small muted">Your file is processed on this machine only.</p></div></div>`;
  const run = async (text) => {
    if (!text.trim()) return toast("Choose a file or paste some text first", { error: true });
    const pid = $("#imp-person").value === "" ? null : Number($("#imp-person").value);
    const p = await api("POST", "/import/preview", { text, person_id: pid });
    if (!p.rows.length) return toast((p.warnings[0] || "No rows found in that file."), { error: true });
    S.importState = { preview: p, person_id: pid }; route();
  };
  const readFile = (f) => { const r = new FileReader(); r.onload = () => run(r.result); r.readAsText(f); };
  const drop = $("#drop"), file = $("#file");
  drop.onclick = () => file.click(); file.onchange = () => file.files[0] && readFile(file.files[0]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); }; drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]); };
  $("#imp-go").onclick = () => run($("#imp-text").value);
  $("#imp-sample").onclick = async () => run((await api("GET", "/sample-csv")).text);
}

function importPreview(v) {
  const { preview: p, person_id } = S.importState;
  const rows = p.rows;
  rows.forEach((r) => { if (r.skip === undefined) r.skip = r.status === "duplicate"; });
  const statusBadge = (r) => r.status === "duplicate" ? `<span class="badge">Already imported</span>` : r.status === "matches_bill" ? `<span class="badge info">Matches a bill</span>` : r.type === "transfer" ? `<span class="badge">Transfer</span>` : r.category_id ? `<span class="badge good">Auto</span>` : `<span class="badge warn">Choose</span>`;
  const draw = () => {
    const todo = rows.filter((r) => !r.skip);
    const need = todo.filter((r) => !r.category_id && r.type !== "transfer").length;
    v.innerHTML = `<div class="page-head"><div><h2>Review import</h2><div class="muted small">Account: <b>${esc(personName(person_id))}</b> · detected columns: date “${esc(p.columns.date)}”, amount “${esc(p.columns.amount || "debit/credit")}” · ${rows.length} rows${p.skipped ? ` (${p.skipped} unreadable skipped)` : ""}</div></div>
      <div style="display:flex;gap:8px"><button class="btn" id="imp-cancel">Cancel</button><button class="btn primary" id="imp-commit">Import ${todo.length} rows</button></div></div>
      <div class="card"><div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px"><span class="badge good">${rows.filter((r) => r.status === "new").length} new</span><span class="badge info">${rows.filter((r) => r.status === "matches_bill").length} match your bills</span><span class="badge">${rows.filter((r) => r.status === "duplicate").length} duplicates</span><span class="badge ${need ? "warn" : "good"}">${need} need a category</span></div>
      <div class="table-scroll"><div class="imp-row head small muted"><b>Date</b><b>Description</b><b>Category</b><b class="right">Amount</b><b class="right">Status</b></div>
      ${rows.map((r, i) => `<div class="imp-row ${r.skip ? "dim" : ""}"><div class="muted">${fmtDate(r.date)}</div><div class="desc" title="${esc(r.description)}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><label class="check" style="gap:6px"><input type="checkbox" data-skip="${i}" ${r.skip ? "" : "checked"} ${r.status === "duplicate" ? "disabled" : ""}><span>${esc(r.description)}</span></label></div>
        <div>${r.type === "transfer" ? `<span class="small muted">🔄 own-account transfer</span>` : `<select class="inline" data-cat="${i}" ${r.skip ? "disabled" : ""}>${catOptions(r.type, r.category_id ?? "", "❓ Choose…")}</select>`}</div>
        <div class="right"><b class="${r.type === "income" ? "good" : ""}">${r.type === "income" ? "+" : "−"}${money(r.amount_cents)}</b></div><div class="right">${statusBadge(r)}</div></div>`).join("")}</div></div>`;
    $("#imp-cancel").onclick = () => { S.importState = null; route(); };
    v.querySelectorAll("[data-skip]").forEach((c) => (c.onchange = () => { rows[c.dataset.skip].skip = !c.checked; draw(); }));
    v.querySelectorAll("[data-cat]").forEach((c) => (c.onchange = () => { const r = rows[c.dataset.cat]; r.category_id = c.value ? Number(c.value) : null; r.learn = !!c.value;
      // propagate to other rows of the same merchant that have no category yet
      const key = (r.description || "").toLowerCase().split(/\s+/)[0];
      rows.forEach((o) => { if (o !== r && !o.category_id && o.type === r.type && key && (o.description || "").toLowerCase().startsWith(key)) o.category_id = r.category_id; });
      draw(); }));
    $("#imp-commit").onclick = async () => {
      if (need && !confirm(`${need} rows have no category. Import anyway? You can categorise them later.`)) return;
      const res = await api("POST", "/import/commit", { rows, person_id });
      S.importState = null; S.boot = await api("GET", "/bootstrap");
      toast(`Imported ${res.added} new${res.matched_bills ? `, matched ${res.matched_bills} bills` : ""}${res.duplicates ? `, skipped ${res.duplicates} duplicates` : ""}`);
      const target = res.suggestions ? "#bills" : "#overview";
      if (location.hash === target) route(); else location.hash = target;
    };
  };
  draw();
}

// ------------------------------------------------------------------ SETTINGS
async function viewSettings(v) {
  const [rules, boot] = await Promise.all([api("GET", "/rules"), api("GET", "/bootstrap")]); S.boot = boot;
  const st = boot.settings;
  v.innerHTML = `<div class="page-head"><h2>Settings</h2></div><div class="stack">
    <div class="card"><div class="card-head"><h3>You two</h3></div><form id="set-form"><div class="fields2">${people().map((p, i) => `<div class="field"><label>Person ${i + 1}</label><div style="display:flex;gap:8px"><input type="text" name="n${p.id}" value="${esc(p.name)}" required><input type="color" name="c${p.id}" value="${esc(p.color)}" style="width:52px;padding:2px"></div></div>`).join("")}</div>
      <div class="fields2"><div class="field"><label>Default split for shared costs</label><select name="split">${opt("income", "By income", st.default_split)}${opt("equal", "50 / 50", st.default_split)}</select></div>
      <div class="field"><label>Currency</label><select name="currency">${["EUR", "USD", "GBP"].map((c) => opt(c, c, st.currency)).join("")}</select></div></div><button class="btn primary">Save</button></form></div>
    <div class="card"><div class="card-head"><div><h3>Categories & monthly budgets</h3><div class="small muted">Set a budget and the overview warns you before you overspend. “Needs/Wants” drives the 50/30/20 view.</div></div></div>
      ${cats("expense").map((c) => `<div class="row"><div class="ico">${c.icon}</div><div class="grow title">${esc(c.name)}</div><select class="inline" data-bucket="${c.id}" style="width:110px">${opt("needs", "Need", c.bucket)}${opt("wants", "Want", c.bucket)}</select>
      <input type="text" inputmode="decimal" data-budget="${c.id}" value="${c.budget_cents ? centsToInput(c.budget_cents) : ""}" placeholder="Budget / month" style="width:140px"></div>`).join("")}
      <div style="margin-top:12px"><button class="btn sm" id="add-cat">+ New category</button></div></div>
    <div class="card"><div class="card-head"><div><h3>Auto-categorisation rules (${rules.length})</h3><div class="small muted">If a description contains the text, it gets that category. New rules appear here as you categorise.</div></div></div>
      <form id="rule-form" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px"><input type="text" name="pattern" placeholder="e.g. bakker" required style="flex:1;min-width:140px"><select name="category_id" style="flex:1;min-width:160px">${catOptions(null, "", null)}</select><button class="btn">Add rule</button></form>
      <details><summary class="small muted" style="cursor:pointer">Show all rules</summary><div style="max-height:320px;overflow:auto;margin-top:8px">${rules.map((r) => `<div class="row" style="padding:5px 0"><code class="grow">${esc(r.pattern)}</code><span class="small muted">${esc(r.category_name)}</span><button class="btn ghost sm" data-rdel="${r.id}">✕</button></div>`).join("")}</div></details></div>
    <div class="card"><div class="card-head"><h3>Your data</h3></div><p class="small muted">Everything is stored in a single file on this computer (<code>couple-finance/data/finance.db</code>). Nothing is sent anywhere.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn" href="/api/export" download>⬇️ Download backup (JSON)</a><button class="btn" id="demo">Load demo data</button><button class="btn danger" id="wipe">Delete all transactions, bills & goals</button></div></div></div>`;
  $("#set-form").onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target).entries());
    S.boot = await api("PUT", "/settings", { people: people().map((p) => ({ id: p.id, name: f["n" + p.id], color: f["c" + p.id] })), default_split: f.split, currency: f.currency, setup_done: "1" }); renderShell(); toast("Saved"); };
  v.querySelectorAll("[data-budget]").forEach((i) => (i.onchange = async () => { const c = parseMoney(i.value); await api("PATCH", `/categories/${i.dataset.budget}`, { budget_cents: c > 0 ? c : null }); toast("Budget saved"); }));
  v.querySelectorAll("[data-bucket]").forEach((i) => (i.onchange = async () => { await api("PATCH", `/categories/${i.dataset.bucket}`, { bucket: i.value }); toast("Saved"); }));
  $("#add-cat").onclick = () => modal("New category", `<div class="field"><label>Name</label><input type="text" name="name" required></div><div class="fields2"><div class="field"><label>Icon (emoji)</label><input type="text" name="icon" value="📦" maxlength="2"></div><div class="field"><label>Kind</label><select name="kind">${opt("expense", "Expense", "expense")}${opt("income", "Income", "income")}</select></div></div>`,
    { onSubmit: async (f) => { await api("POST", "/categories", f); S.boot = await api("GET", "/bootstrap"); refresh(); } });
  $("#rule-form").onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target).entries()); const r = await api("POST", "/rules", { pattern: f.pattern, category_id: Number(f.category_id) }); toast(r.applied ? `Rule added; categorised ${r.applied} existing transactions` : "Rule added"); refresh(); };
  v.querySelectorAll("[data-rdel]").forEach((b) => (b.onclick = async () => { await api("DELETE", `/rules/${b.dataset.rdel}`); refresh(); }));
  $("#demo").onclick = async () => { try { await api("POST", "/demo", {}); } catch (e) { return; } S.boot = await api("GET", "/bootstrap"); toast("Demo data loaded"); location.hash = "#overview"; };
  $("#wipe").onclick = async () => { if (prompt("This deletes every transaction, bill and goal. Type DELETE to confirm.") !== "DELETE") return; await api("POST", "/reset", { confirm: "DELETE" }); S.boot = await api("GET", "/bootstrap"); toast("All cleared"); location.hash = "#overview"; route(); };
}

const VIEWS = { overview: viewOverview, transactions: viewTransactions, bills: viewBills, goals: viewGoals, import: viewImport, settings: viewSettings };

// ------------------------------------------------------------------ quick add
let qTimer;
async function quickPreview() {
  const text = $("#quick").value.trim(); const box = $("#quick-preview");
  if (!text) { box.innerHTML = ""; return; }
  try {
    const res = await fetch("/api/quick", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, default_person_id: S.me, dry_run: true }) });
    const d = await res.json();
    if (!d.ok) { box.textContent = d.error || ""; return; }
    const c = catById(d.category_id);
    box.innerHTML = `→ <b>${d.type === "income" ? "Income" : d.type === "transfer" ? "Transfer" : "Expense"} ${money(d.amount_cents)}</b> · ${esc(d.description)} · ${c ? c.icon + " " + esc(c.name) : "<span class='warn'>no category yet</span>"} · ${esc(personName(d.person_id))} · ${fmtDate(d.date)} <span class="muted">— press Enter</span>`;
  } catch (e) { /* ignore */ }
}
async function quickAdd() {
  const input = $("#quick"); const text = input.value.trim(); if (!text) return;
  const res = await api("POST", "/quick", { text, default_person_id: S.me });
  if (!res.ok) return toast(res.error, { error: true });
  const t = res.transaction; input.value = ""; $("#quick-preview").innerHTML = "";
  toast(`Added ${money(t.amount_cents)} · ${t.category_name || "no category"}`, { undo: async () => { await api("DELETE", `/transactions/${t.id}`); refresh(); } });
  refresh();
}

// ------------------------------------------------------------------ boot
async function start() {
  S.boot = await api("GET", "/bootstrap"); S.month = S.boot.month;
  if (!people().some((p) => p.id === S.me)) S.me = 1;
  $("#m-prev").onclick = () => { S.month = shiftMonth(S.month, -1); route(); };
  $("#m-next").onclick = () => { S.month = shiftMonth(S.month, 1); route(); };
  $("#quick").oninput = () => { clearTimeout(qTimer); qTimer = setTimeout(quickPreview, 200); };
  $("#quick").onkeydown = (e) => { if (e.key === "Enter") quickAdd(); };
  $("#quick-go").onclick = quickAdd;
  window.addEventListener("hashchange", route);
  route();
}
start();
