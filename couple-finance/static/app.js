/* Couple Finance front-end — vanilla JS, no build step */
"use strict";

const S = { boot: null, month: null, me: Number(localStorage.getItem("cf_me")) || 1, page: "home", tab: "bank",
            txFilters: { q: "", category_id: "", person_id: "", uncategorised: "" }, importState: null, allCats: false };

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, path, body) {
  const res = await fetch("/api" + path, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  let data = {};
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) { toast(data.error || "Something went wrong", { error: true }); throw new Error(data.error || res.status); }
  return data;
}

const loc = () => S.boot.settings.locale || "en";
const fmt = (opts) => new Intl.NumberFormat(loc(), { style: "currency", currency: S.boot.settings.currency || "EUR", ...opts });
function money(cents, o = {}) { return fmt(o.round ? { maximumFractionDigits: 0, minimumFractionDigits: 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format((cents || 0) / 100); }
function bigMoney(cents) {
  let main = "", frac = "";
  for (const p of fmt({ minimumFractionDigits: 2, maximumFractionDigits: 2 }).formatToParts((cents || 0) / 100)) (p.type === "decimal" || p.type === "fraction" ? (frac += p.value) : (main += p.value));
  return `${esc(main.trim())}<small>${esc(frac)}</small>`;
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
const CAT_COLORS = ["#6366f1", "#ec4899", "#10b981", "#f59e0b", "#0ea5e9", "#8b5cf6", "#ef4444", "#14b8a6", "#84cc16", "#f97316", "#64748b", "#a855f7"];
const catColor = (id) => (id == null ? "#a1a1aa" : CAT_COLORS[id % CAT_COLORS.length]);
const dotFor = (id) => (id == null ? `<span class="dot" style="background:var(--faint)"></span>` : `<span class="dot" style="background:${esc(person(id).color)}"></span>`);
const splitLabel = (s) => ({ equal: "50/50", income: "By income", p1: "Only " + people()[0].name, p2: "Only " + people()[1].name }[s]);
const avatar = (name, color) => `<span class="avatar" style="background:${color}22;color:${color}">${esc((name || "?").trim().charAt(0).toUpperCase())}</span>`;

const loc2 = () => S.boot.settings.locale || "en";
const monthLabel = (m) => { const [y, mo] = m.split("-").map(Number); const t = new Date(y, mo - 1, 1).toLocaleDateString(loc2(), { month: "long", year: "numeric" }); return t.charAt(0).toUpperCase() + t.slice(1); };
const shiftMonth = (m, d) => { const [y, mo] = m.split("-").map(Number); const i = y * 12 + mo - 1 + d; return `${Math.floor(i / 12)}-${String(i % 12 + 1).padStart(2, "0")}`; };
const shortMonth = (m) => { const [y, mo] = m.split("-").map(Number); return new Date(y, mo - 1, 1).toLocaleDateString(loc2(), { month: "short" }); };
const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString(loc2(), { day: "numeric", month: "short" });
const fmtDateLong = (iso) => new Date(iso + "T00:00:00").toLocaleDateString(loc2(), { day: "numeric", month: "short", year: "numeric" });
function dayLabel(iso) {
  const t = S.boot.today; if (iso === t) return "Today";
  const y = new Date(t + "T00:00:00"); y.setDate(y.getDate() - 1);
  if (iso === y.toISOString().slice(0, 10)) return "Yesterday";
  return new Date(iso + "T00:00:00").toLocaleDateString(loc2(), { weekday: "long", day: "numeric", month: "short" });
}

// icons (stroke, 20px)
const ICONS = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>', list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  repeat: '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 013-3h15M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 01-3 3H3"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  link: '<path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  left: '<path d="M15 18l-6-6 6-6"/>', right: '<path d="M9 18l6-6-6-6"/>',
};
const ic = (n) => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n]}</svg>`;

function toast(msg, { undo, error } = {}) {
  const el = document.createElement("div");
  el.className = "toast" + (error ? " err" : "");
  el.innerHTML = `<span>${esc(msg)}</span>`;
  if (undo) { const b = document.createElement("button"); b.textContent = "Undo"; b.onclick = async () => { el.remove(); await undo(); }; el.appendChild(b); }
  $("#toast-host").appendChild(el);
  setTimeout(() => el.remove(), undo ? 8000 : 4200);
}

// segmented control inside forms
const seg = (name, opts, val, cls = "") => `<div class="seg ${cls}" data-seg="${name}"><input type="hidden" name="${name}" value="${esc(val)}">${opts.map(([v, l]) => `<button type="button" data-v="${esc(v)}" class="${String(val) === String(v) ? "on" : ""}">${esc(l)}</button>`).join("")}</div>`;
function bindSegs(root) {
  $$("[data-seg]", root).forEach((g) => $$("button", g).forEach((b) => (b.onclick = () => {
    $$("button", g).forEach((x) => x.classList.toggle("on", x === b));
    const h = $("input", g); h.value = b.dataset.v; h.dispatchEvent(new Event("change", { bubbles: true }));
  })));
}

function modal(title, body, { onSubmit, submitLabel = "Save", wide = false, hideActions = false, extraActions = "" } = {}) {
  const host = $("#modal-host");
  host.innerHTML = `<div class="overlay"><form class="sheet ${wide ? "wide" : ""}"><h2>${esc(title)}</h2>${body}
    ${hideActions ? "" : `<div class="actions">${extraActions}<button type="button" class="btn" data-close>Cancel</button><button class="btn primary">${esc(submitLabel)}</button></div>`}</form></div>`;
  const close = () => (host.innerHTML = "");
  $(".overlay", host).addEventListener("mousedown", (e) => { if (e.target.classList.contains("overlay")) close(); });
  $$("[data-close]", host).forEach((b) => (b.onclick = close));
  const form = $("form", host);
  bindSegs(form);
  form.onsubmit = async (e) => {
    e.preventDefault();
    if (!onSubmit) return;
    try { const r = await onSubmit(Object.fromEntries(new FormData(form).entries()), form); if (r !== false) close(); } catch (err) { /* toast shown */ }
  };
  const first = $("input:not([type=hidden]):not([type=file]),select", form); if (first) first.focus();
  return { close, form };
}
const closeModal = () => ($("#modal-host").innerHTML = "");

const opt = (value, label, sel) => `<option value="${esc(value)}" ${String(sel) === String(value) ? "selected" : ""}>${esc(label)}</option>`;
const catOptions = (kind, sel, blank = "No category") => (blank ? opt("", blank, sel ?? "") : "") + cats(kind).map((c) => opt(c.id, c.name, sel)).join("");
const personOptions = (sel, joint = true) => (joint ? opt("", "Joint account", sel ?? "") : "") + people().map((p) => opt(p.id, p.name, sel)).join("");
const splitOptions = (sel) => ["equal", "income", "p1", "p2"].map((s) => opt(s, splitLabel(s), sel)).join("");

// ------------------------------------------------------------------ shell
const NAV = [["home", "Home", "home"], ["activity", "Activity", "list"], ["bills", "Bills", "repeat"], ["goals", "Goals", "target"], ["connect", "Connect", "link"]];
const ALIAS = { overview: "home", transactions: "activity", bank: "connect", import: "connect" };

function whoHtml() {
  return `<div class="who" role="group" aria-label="Who is adding entries on this device?">${people().map((p) =>
    `<button class="${S.me === p.id ? "on" : ""}" data-who="${p.id}" title="Entries you add are attributed to ${esc(p.name)}"><span class="dot" style="background:${esc(p.color)}"></span><span class="nm">${esc(p.name)}</span></button>`).join("")}</div>`;
}
function renderShell() {
  $("#side").innerHTML = `<div class="brand"><i></i>Money</div>
    <nav class="nav">${NAV.map(([id, label, icon]) => `<a href="#${id}" class="${S.page === id ? "on" : ""}">${ic(icon)}${label}</a>`).join("")}</nav>
    <div class="side-foot"><div><div class="xs muted" style="margin:0 4px 6px">Adding as</div>${whoHtml()}</div>
    <nav class="nav"><a href="#settings" class="${S.page === "settings" ? "on" : ""}">${ic("gear")}Settings</a></nav></div>`;
  $("#topm").innerHTML = `<div class="brand"><i></i>Money</div><div class="tools">${whoHtml()}<a class="iconbtn" href="#settings" aria-label="Settings">${ic("gear")}</a></div>`;
  $("#bottom").innerHTML = NAV.map(([id, label, icon]) => `<a href="#${id}" class="${S.page === id ? "on" : ""}">${ic(icon)}${label}</a>`).join("");
  $("#fab").innerHTML = ic("plus");
  $$("[data-who]").forEach((b) => (b.onclick = () => { S.me = Number(b.dataset.who); localStorage.setItem("cf_me", S.me); renderShell(); }));
}

async function route() {
  let h = (location.hash || "#home").slice(1).split("?")[0];
  if (h === "bank") S.tab = "bank"; if (h === "import") S.tab = "csv";
  h = ALIAS[h] || h;
  S.page = VIEWS[h] ? h : "home";
  renderShell();
  const v = $("#view");
  v.innerHTML = `<div class="empty">Loading…</div>`;
  window.scrollTo(0, 0);
  try { await VIEWS[S.page](v); } catch (e) { console.error(e); v.innerHTML = `<div class="empty"><h3>Something went wrong</h3>${esc(e.message)}</div>`; }
}
const refresh = async () => { const y = window.scrollY; await route(); window.scrollTo(0, y); };

function monthHead(extra = "") {
  return `<header class="ph"><div class="month"><button id="m-prev" aria-label="Previous month">${ic("left")}</button><h1>${esc(monthLabel(S.month))}</h1><button id="m-next" aria-label="Next month">${ic("right")}</button></div>${extra}</header>`;
}
function bindMonth() {
  $("#m-prev").onclick = () => { S.month = shiftMonth(S.month, -1); refresh(); };
  $("#m-next").onclick = () => { S.month = shiftMonth(S.month, 1); refresh(); };
}
const block = (title, right, inner) => `<section class="block"><div class="bt"><h2>${title}</h2>${right || ""}</div>${inner}</section>`;

// ------------------------------------------------------------------ HOME
async function viewHome(v) {
  const [s, trend, goals, rec] = await Promise.all([api("GET", `/summary?month=${S.month}`), api("GET", `/trends?month=${S.month}&n=6`), api("GET", "/goals"), api("GET", "/recurring?days=21")]);
  if (S.boot.settings.setup_done !== "1" && !S.boot.has_data && s.tx_count === 0) return welcome(v);
  if (!S.boot.has_data && s.tx_count === 0) return gettingStarted(v);

  if (s.tx_count === 0) {
    v.innerHTML = monthHead() + `<div class="empty"><h3>Nothing recorded in ${esc(monthLabel(S.month))}</h3>Use the + button to add a payment, or go to another month.</div>`;
    return bindMonth();
  }
  const delta = (cur, prev) => !prev ? "no data last month" : `${cur >= prev ? "↑" : "↓"} ${money(Math.abs(cur - prev), { round: true })} vs last month`;
  const max = Math.max(s.income_cents, s.expense_cents, 1), saved = Math.max(s.savings_cents, 0), fc = s.forecast;
  const flow = `<div class="flow"><i style="width:${s.fixed_cents / max * 100}%;background:var(--ink)"></i><i style="width:${s.variable_cents / max * 100}%;background:var(--faint)"></i><i style="width:${saved / max * 100}%;background:var(--pos)"></i></div>
    <div class="legend"><span><span class="dot" style="background:var(--ink)"></span>Rent & bills ${money(s.fixed_cents, { round: true })}</span><span><span class="dot" style="background:var(--faint)"></span>Everyday ${money(s.variable_cents, { round: true })}</span><span><span class="dot" style="background:var(--pos)"></span>Saved ${money(saved, { round: true })}</span></div>`;
  const hero = `<section class="hero"><div class="label">Saved together</div>
    <div class="big ${s.savings_cents < 0 ? "neg" : ""}">${bigMoney(s.savings_cents)}</div>
    <div class="muted">${s.savings_rate == null ? "" : pct(s.savings_rate) + " of " + money(s.income_cents, { round: true }) + " income"}${fc && fc.upcoming_expense_cents ? ` · on track for <b style="color:var(--ink)">${money(fc.projected_savings_cents, { round: true })}</b> by month end` : ""}</div>
    ${flow}
    <div class="pair"><div><div class="k">Income</div><div class="v">${money(s.income_cents, { round: true })}</div><div class="d">${delta(s.income_cents, s.prev.income_cents)}</div></div>
    <div><div class="k">Spent</div><div class="v">${money(s.expense_cents, { round: true })}</div><div class="d">${delta(s.expense_cents, s.prev.expense_cents)}</div></div></div></section>`;

  // heads-up: only what needs action
  const notes = [];
  if (s.uncategorised_count) notes.push(`<div class="note"><span class="dot" style="background:var(--warn)"></span><span><a href="#activity" data-uncat>${s.uncategorised_count} payment${s.uncategorised_count > 1 ? "s" : ""} need a category</a> — set it once and I'll remember the shop.</span></div>`);
  s.insights.filter((i) => i.level === "warn" || i.level === "bad" || /due in the next/.test(i.text)).slice(0, 3)
    .forEach((i) => notes.push(`<div class="note"><span class="dot" style="background:${i.level === "bad" ? "var(--neg)" : i.level === "warn" ? "var(--warn)" : "var(--faint)"}"></span><span>${esc(i.text.replace(/\s*[\u{1F300}-\u{1FAFF}\u2600-\u27BF\uFE0F]/gu, ""))}</span></div>`));
  const heads = notes.length ? block("Heads up", "", notes.join("")) : "";

  // spending
  const list = S.allCats ? s.categories : s.categories.slice(0, 6), top = Math.max(...s.categories.map((c) => c.amount_cents), 1);
  const spendRows = list.map((c) => {
    const hasB = !!c.budget_cents, over = hasB && c.amount_cents > c.budget_cents;
    const w = hasB ? Math.min(c.amount_cents / c.budget_cents, 1) * 100 : c.amount_cents / top * 100;
    return `<div class="lrow"><span class="dot" style="background:${catColor(c.category_id)}"></span><div class="grow"><div class="l1"><span class="t1">${esc(c.name)}</span><span class="amt">${money(c.amount_cents, { round: true })}</span></div>
      <div class="bar ${over ? "over" : ""}"><i style="width:${w}%"></i></div>${hasB ? `<div class="t2" style="margin-top:5px">${over ? `<span class="neg">${money(c.amount_cents - c.budget_cents, { round: true })} over</span> budget of ${money(c.budget_cents, { round: true })}` : `${money(c.budget_cents - c.amount_cents, { round: true })} left of ${money(c.budget_cents, { round: true })}`}</div>` : ""}</div></div>`;
  }).join("");
  const spending = block("Spending", s.categories.length > 6 ? `<button class="link" id="toggle-cats">${S.allCats ? "Show less" : `Show all ${s.categories.length}`}</button>` : "", spendRows);

  // coming up
  const up = rec.upcoming.filter((u) => u.type === "expense").slice(0, 4);
  const coming = up.length ? block("Coming up", `<a href="#bills">All bills</a>`, up.map((u) => { const d = new Date(u.date + "T00:00:00");
    return `<div class="lrow"><div class="cal"><b>${d.getDate()}</b><span>${d.toLocaleDateString(loc2(), { month: "short" })}</span></div><div class="grow"><div class="t1">${esc(u.name)}</div><div class="t2">${esc(personName(u.person_id))}</div></div><span class="amt">${money(u.amount_cents, { round: true })}</span></div>`; }).join("")) : "";

  // goals
  const open = goals.goals.filter((g) => !g.done).slice(0, 3);
  const canSweep = s.unallocated_cents > 0 && goals.goals.some((g) => g.planned_monthly_cents > 0);
  const goalsBlock = open.length ? block("Goals", `<a href="#goals">All goals</a>`, open.map((g) => `<div class="lrow"><div class="grow"><div class="l1"><span class="t1">${esc(g.name)}</span><span class="t2">${money(g.saved_cents, { round: true })} of ${money(g.target_cents, { round: true })}</span></div><div class="bar"><i style="width:${g.pct}%"></i></div></div></div>`).join("") +
    (canSweep ? `<div style="margin-top:12px"><button class="btn sm" id="sweep">Move ${money(s.unallocated_cents, { round: true })} of savings into goals</button></div>` : "")) : "";

  // between you two
  const st = s.settlement, [p1, p2] = s.people, inc1 = s.person_income_cents[p1.id], inc2 = s.person_income_cents[p2.id];
  const between = (inc1 + inc2 > 0 || st.amount_cents) ? block("Between you two", "", `
    ${inc1 + inc2 > 0 ? `<div class="split2"><i style="width:${st.ratio["1"] * 100}%;background:${esc(p1.color)}"></i><i style="width:${st.ratio["2"] * 100}%;background:${esc(p2.color)}"></i></div>
    <div class="l1 small"><span>${dotFor(p1.id)} ${esc(p1.name)} <span class="muted">${money(inc1, { round: true })} · ${pct(st.ratio["1"])}</span></span><span>${dotFor(p2.id)} ${esc(p2.name)} <span class="muted">${money(inc2, { round: true })} · ${pct(st.ratio["2"])}</span></span></div>` : ""}
    <p style="margin-top:14px">${st.amount_cents > 0 ? `<b>${esc(personName(st.from_person))}</b> owes <b>${esc(personName(st.to_person))}</b> ${money(st.amount_cents)} for shared costs.` : `<span class="muted">Shared costs are settled.</span>`}</p>
    ${(st.joint_contribution_cents["1"] || st.joint_contribution_cents["2"]) ? `<p class="small muted" style="margin-top:6px">Paid from the joint account — fair share: ${esc(p1.name)} ${money(st.joint_contribution_cents["1"], { round: true })}, ${esc(p2.name)} ${money(st.joint_contribution_cents["2"], { round: true })}.</p>` : ""}`) : "";

  // details (collapsed)
  const n = s.split503020, inc = s.income_cents || 1;
  const details = `<section class="block"><details><summary>Trends, forecast & budget rule</summary><div style="margin-top:18px">${trendChart(trend)}
    <dl class="kv" style="margin-top:22px">
      ${fc ? `<dt>Bills still to come this month</dt><dd>${money(fc.upcoming_expense_cents)}</dd><dt>Everyday spending pace</dt><dd>${money(fc.daily_variable_cents)} / day</dd><dt>Projected savings</dt><dd>${money(fc.projected_savings_cents)}</dd>` : ""}
      <dt>Needs · Wants · Savings <span class="faint">(guide 50 · 30 · 20)</span></dt><dd>${pct(n.needs_cents / inc)} · ${pct(n.wants_cents / inc)} · ${pct(n.savings_cents / inc)}</dd></dl></div></details></section>`;

  v.innerHTML = monthHead() + hero + heads + spending + coming + goalsBlock + between + details;
  bindMonth();
  const t = $("#toggle-cats"); if (t) t.onclick = () => { S.allCats = !S.allCats; refresh(); };
  const sw = $("#sweep"); if (sw) sw.onclick = async () => { const r = await api("POST", "/goals/sweep", { month: S.month }); toast(`Moved savings into ${r.moved.length} goal${r.moved.length === 1 ? "" : "s"}`); refresh(); };
  const un = $("[data-uncat]"); if (un) un.onclick = () => { S.txFilters = { q: "", category_id: "", person_id: "", uncategorised: "1" }; };
}

function trendChart(data) {
  const from = data.findIndex((d) => d.income_cents || d.expense_cents); const d2 = from < 0 ? data : data.slice(from);
  const W = 640, H = 170, top = 10, base = 122, bw = 22;
  const max = Math.max(1, ...d2.map((d) => Math.max(d.income_cents, d.expense_cents))), step = W / d2.length;
  const y = (v) => base - (v / max) * (base - top);
  const bars = d2.map((d, i) => { const cx = step * i + step / 2;
    return `<rect x="${cx - bw - 2}" y="${y(d.income_cents)}" width="${bw}" height="${Math.max(base - y(d.income_cents), 1)}" rx="5" style="fill:var(--fill-2)"><title>Income ${money(d.income_cents)}</title></rect>
    <rect x="${cx + 2}" y="${y(d.expense_cents)}" width="${bw}" height="${Math.max(base - y(d.expense_cents), 1)}" rx="5" style="fill:var(--ink)"><title>Spent ${money(d.expense_cents)}</title></rect>
    <text x="${cx}" y="${base + 20}" text-anchor="middle" style="fill:var(--muted);font-size:12px">${esc(shortMonth(d.month))}</text>
    <text x="${cx}" y="${base + 38}" text-anchor="middle" style="fill:${d.savings_cents >= 0 ? "var(--pos)" : "var(--neg)"};font-size:11px;font-weight:600">${money(d.savings_cents, { round: true })}</text>`; }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Income and spending per month">${bars}</svg>
    <div class="legend" style="margin-top:6px"><span><span class="dot" style="background:var(--fill-2)"></span>Income</span><span><span class="dot" style="background:var(--ink)"></span>Spent</span><span>Saved shown below each month</span></div>`;
}

function welcome(v) {
  v.innerHTML = `<div style="max-width:440px;margin:6vh auto 0"><h1 style="font-size:1.9rem;font-weight:650;letter-spacing:-.03em">Welcome.</h1>
    <p class="muted" style="margin:8px 0 28px">One shared picture of your money. Two quick questions and you're set.</p>
    <form id="wform"><div class="fields2"><div class="field"><label>Your name</label><input type="text" name="n1" placeholder="Your name" value="${esc(people()[0].name === "Me" ? "" : people()[0].name)}" required></div>
      <div class="field"><label>Partner's name</label><input type="text" name="n2" placeholder="Partner's name" value="${esc(people()[1].name === "Partner" ? "" : people()[1].name)}" required></div></div>
      <div class="field"><label>Split shared costs (rent, bills)</label>${seg("split", [["income", "By income"], ["equal", "50 / 50"]], S.boot.settings.default_split)}
      <div class="xs muted" style="margin-top:6px">“By income” is fair when one of you earns more. You can change it per item later.</div></div>
      <button class="btn primary" style="width:100%;padding:11px;margin-top:8px">Continue</button></form></div>`;
  bindSegs(v);
  $("#wform").onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target).entries());
    S.boot = await api("PUT", "/settings", { people: people().map((p, i) => ({ id: p.id, name: f["n" + (i + 1)], color: p.color })), default_split: f.split, setup_done: "1" });
    S.month = S.boot.month; route(); };
}

function gettingStarted(v) {
  const step = (href, title, text, id) => `<a class="lrow click" ${href ? `href="${href}"` : `id="${id}"`} style="text-decoration:none;padding:18px 0"><div class="grow"><div class="t1" style="font-size:1.02rem">${title}</div><div class="t2" style="white-space:normal">${text}</div></div>${ic("right")}</a>`;
  v.innerHTML = `<header class="ph"><div><h1>Let's get your money in</h1><div class="sub">Pick whichever is easiest — you can do all of them.</div></div></header>
    ${step("#bank", "Connect your bank", "Free automatic sync: new payments arrive by themselves.")}
    ${step("#import", "Import a bank file", "Drop a CSV export from your banking app. Shops are categorised for you.")}
    ${step("#bills", "Add salaries and rent", "Set once, and they book themselves every month.")}
    ${step("#goals", "Add something you're saving for", "Holiday, deposit, laptop — with a price and a date.")}
    ${step("", "Look around with sample data", "Fills the app with an example couple. You can wipe it in Settings.", "demo")}`;
  $("#demo").onclick = async (e) => { e.preventDefault(); await api("POST", "/demo", {}); S.boot = await api("GET", "/bootstrap"); toast("Sample data loaded — wipe it any time in Settings"); route(); };
}

// ------------------------------------------------------------------ ACTIVITY
async function viewActivity(v) {
  const f = S.txFilters, search = f.q || f.uncategorised;
  const params = new URLSearchParams({ limit: 1000 });
  if (!search) params.set("month", S.month);
  ["q", "category_id", "person_id", "uncategorised"].forEach((k) => f[k] && params.set(k, f[k]));
  const [txs, sum] = await Promise.all([api("GET", "/transactions?" + params), api("GET", `/summary?month=${S.month}`)]);
  const need = sum.uncategorised_count;
  const chip = (label, on, attr) => `<button class="chip ${on ? "on" : ""}" ${attr}>${label}</button>`;
  let body = "";
  if (!txs.length) body = `<div class="empty"><h3>${search || f.category_id || f.person_id ? "No matches" : "No payments this month"}</h3>${search || f.category_id || f.person_id ? "Try clearing a filter." : "Tap + to add one, or connect your bank."}</div>`;
  else {
    let last = "";
    body = txs.map((t) => { const head = t.date !== last ? `<div class="dayh">${esc(dayLabel(t.date))}</div>` : ""; last = t.date;
      const col = t.type === "transfer" ? "#a1a1aa" : catColor(t.category_id);
      const needsCat = !t.category_id && t.type !== "transfer";
      const sub = needsCat ? `<select class="pick" data-cat="${t.id}" data-type="${t.type}">${catOptions(t.type, "", "Choose category…")}</select>`
        : `<div class="t2">${esc(t.type === "transfer" ? "Transfer" : t.category_name || "")} · ${esc(personName(t.person_id))}${t.type === "expense" && t.split !== "equal" ? " · " + esc(splitLabel(t.split)) : ""}</div>`;
      return head + `<div class="lrow click" data-id="${t.id}">${avatar(t.type === "transfer" ? "⇄" : t.category_name || "?", col)}<div class="grow"><div class="t1">${t.recurring_id ? `<span class="faint" title="Recurring">↻ </span>` : ""}${esc(t.description || "(no description)")}</div>${sub}</div>
        <span class="amt ${t.type === "income" ? "pos" : t.type === "transfer" ? "muted" : ""}">${t.type === "income" ? "+" : ""}${money(t.amount_cents)}</span></div>`; }).join("");
  }
  v.innerHTML = (search ? `<header class="ph"><div><h1>Activity</h1><div class="sub">Searching all months</div></div></header>` : monthHead()) +
    `<div class="search" style="margin-bottom:12px">${ic("search")}<input type="search" id="f-q" placeholder="Search payments" value="${esc(f.q)}"></div>
    <div class="chips" style="margin-bottom:22px">${chip("All", !f.uncategorised && !f.person_id && !f.category_id, 'data-f="all"')}
    ${need ? chip(`Needs category · ${need}`, !!f.uncategorised, 'data-f="unc"') : ""}
    ${people().map((p) => chip(`${dotFor(p.id)}${esc(p.name)}`, f.person_id === String(p.id), `data-f="p${p.id}"`)).join("")}${chip("Joint", f.person_id === "joint", 'data-f="joint"')}
    <select class="pick" id="f-cat" style="color:var(--ink-2)">${opt("", "All categories", f.category_id)}${cats().map((c) => opt(c.id, c.name, f.category_id)).join("")}</select></div>
    ${body}`;
  if (!search) bindMonth();
  let timer; const q = $("#f-q"); q.oninput = () => { clearTimeout(timer); timer = setTimeout(() => { f.q = q.value; refresh(); }, 350); };
  $("#f-cat").onchange = (e) => { f.category_id = e.target.value; refresh(); };
  $$("[data-f]").forEach((b) => (b.onclick = () => { const k = b.dataset.f; f.uncategorised = k === "unc" ? "1" : ""; f.person_id = k === "joint" ? "joint" : k.startsWith("p") ? k.slice(1) : ""; if (k === "all") { f.category_id = ""; f.q = ""; } refresh(); }));
  $$(".lrow[data-id]").forEach((r) => (r.onclick = (e) => { if (e.target.closest("select")) return; txModal(txs.find((t) => t.id === Number(r.dataset.id))); }));
  $$("select[data-cat]").forEach((sel) => (sel.onchange = async () => { if (!sel.value) return;
    const r = await api("PATCH", `/transactions/${sel.dataset.cat}`, { category_id: Number(sel.value), learn: true });
    toast(r.auto_categorised_others ? `Saved — and ${r.auto_categorised_others} similar payment${r.auto_categorised_others > 1 ? "s" : ""} too` : "Saved — I'll remember this shop"); refresh(); }));
}

function txModal(t) {
  const isNew = !t; t = t || { date: S.boot.today, type: "expense", amount_cents: "", description: "", category_id: null, person_id: S.me, split: S.boot.settings.default_split, note: "" };
  const { form } = modal(isNew ? "Add payment" : "Edit payment", `
    ${seg("type", [["expense", "Expense"], ["income", "Income"], ["transfer", "Transfer"]], t.type)}<div style="height:16px"></div>
    <div class="fields2"><div class="field"><label>Amount</label><input type="text" inputmode="decimal" name="amount" value="${t.amount_cents === "" ? "" : centsToInput(t.amount_cents)}" placeholder="0,00" required></div>
      <div class="field"><label>Date</label><input type="date" name="date" value="${t.date}" required></div></div>
    <div class="field"><label>Description</label><input type="text" name="description" value="${esc(t.description)}" placeholder="e.g. Jumbo"></div>
    <div class="field"><label>Category</label><select name="category_id"></select></div>
    <div class="fields2"><div class="field"><label id="t-who-l">Paid by</label><select name="person_id">${personOptions(t.person_id ?? "")}</select></div>
      <div class="field" id="t-split-f"><label>Split</label><select name="split">${splitOptions(t.split)}</select></div></div>
    <div class="field"><label>Note</label><input type="text" name="note" value="${esc(t.note || "")}"></div>
    <label class="check"><input type="checkbox" name="learn" checked> Remember this description → category</label>`, {
    submitLabel: isNew ? "Add" : "Save", extraActions: isNew ? "" : `<button type="button" class="btn danger" id="t-del" style="margin-right:auto">Delete</button>`,
    onSubmit: async (f) => {
      const cents = parseMoney(f.amount); if (!(cents >= 0)) { toast("Enter a valid amount", { error: true }); return false; }
      await api(isNew ? "POST" : "PATCH", isNew ? "/transactions" : `/transactions/${t.id}`, { type: f.type, amount_cents: cents, date: f.date, description: f.description, category_id: f.category_id || null, person_id: f.person_id === "" ? null : Number(f.person_id), split: f.split, note: f.note, learn: !!f.learn && !!f.category_id });
      refresh(); } });
  const sync = (reset) => { const type = form.elements.type.value, cat = form.elements.category_id; const cur = reset ? "" : (cat.value || (t.category_id ?? ""));
    cat.innerHTML = type === "transfer" ? catOptions("transfer", cur, null) : catOptions(type, cur);
    $("#t-split-f").style.display = type === "expense" ? "" : "none"; $("#t-who-l").textContent = type === "income" ? "Received by" : "Paid by"; };
  form.elements.type.onchange = () => sync(true); sync(false);
  const del = $("#t-del"); if (del) del.onclick = async () => { if (!confirm("Delete this payment?")) return; await api("DELETE", `/transactions/${t.id}`); closeModal(); toast("Deleted"); refresh(); };
}

// ------------------------------------------------------------------ quick add (floating button / press N)
function openQuick() {
  const { form } = modal("Add a payment", `
    <input class="quick-in" type="text" name="text" autocomplete="off" spellcheck="false" placeholder="jumbo 23,50" aria-label="Describe the payment">
    <div class="qprev" id="qprev">Type it the way you'd say it.</div>
    <div class="hints"><button type="button" class="chip" data-ex="jumbo 23,50 yesterday">jumbo 23,50 yesterday</button><button type="button" class="chip" data-ex="+2400 salary ${esc(people()[1].name.toLowerCase())}">+2400 salary ${esc(people()[1].name.toLowerCase())}</button><button type="button" class="chip" data-ex="rent 950 joint 01-${String(new Date().getMonth() + 1).padStart(2, "0")}">rent 950 joint</button></div>`, {
    submitLabel: "Add", extraActions: `<button type="button" class="btn ghost" id="q-full" style="margin-right:auto">Full form</button>`,
    onSubmit: async (f) => { const text = (f.text || "").trim(); if (!text) return false;
      const res = await api("POST", "/quick", { text, default_person_id: S.me }); if (!res.ok) { toast(res.error, { error: true }); return false; }
      const t = res.transaction; toast(`Added ${money(t.amount_cents)}${t.category_name ? " · " + t.category_name : ""}`, { undo: async () => { await api("DELETE", `/transactions/${t.id}`); refresh(); } }); refresh(); } });
  const input = form.elements.text; let timer;
  const preview = async () => { const text = input.value.trim(); const box = $("#qprev"); if (!text) { box.textContent = "Type it the way you'd say it."; return; }
    try { const d = await (await fetch("/api/quick", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, default_person_id: S.me, dry_run: true }) })).json();
      if (!d.ok) { box.textContent = d.error || ""; return; } const c = catById(d.category_id);
      box.innerHTML = `<b>${d.type === "income" ? "Income" : d.type === "transfer" ? "Transfer" : "Expense"} ${money(d.amount_cents)}</b> · ${esc(d.description)}<br>${c ? esc(c.name) : "<span class='warn'>No category yet</span>"} · ${esc(personName(d.person_id))} · ${fmtDate(d.date)}`; } catch (e) { /* ignore */ } };
  input.oninput = () => { clearTimeout(timer); timer = setTimeout(preview, 180); };
  $$("[data-ex]", form).forEach((b) => (b.onclick = () => { input.value = b.dataset.ex; input.focus(); preview(); }));
  $("#q-full").onclick = () => { closeModal(); txModal(); };
}

// ------------------------------------------------------------------ BILLS
const FREQ = { weekly: "Weekly", biweekly: "Every 2 weeks", monthly: "Monthly", quarterly: "Quarterly", yearly: "Yearly" };

async function viewBills(v) {
  const [r, sug] = await Promise.all([api("GET", "/recurring?days=45"), api("GET", "/recurring/suggestions")]);
  const active = r.items.filter((i) => i.active), paused = r.items.filter((i) => !i.active);
  const left = r.monthly_income_cents - r.monthly_expense_cents;
  const item = (i) => `<div class="lrow click" data-redit="${i.id}"><div class="grow"><div class="t1">${esc(i.name)}</div><div class="t2">${FREQ[i.frequency]} · ${esc(personName(i.person_id))}${i.type === "expense" ? " · " + esc(splitLabel(i.split)) : ""}${i.frequency !== "monthly" ? ` · ≈ ${money(i.monthly_cents, { round: true })}/mo` : ""}</div></div><span class="amt ${i.type === "income" ? "pos" : ""}">${i.type === "income" ? "+" : ""}${money(i.amount_cents)}</span></div>`;
  const inc = active.filter((i) => i.type === "income"), exp = active.filter((i) => i.type === "expense");
  v.innerHTML = `<header class="ph"><div><h1>Bills</h1><div class="sub">Set once — they book themselves.</div></div><button class="btn primary" id="add-rec">Add</button></header>
    <section class="hero"><div class="label">Left after fixed costs, every month</div><div class="big ${left < 0 ? "neg" : ""}">${bigMoney(left)}</div>
    <div class="muted">${money(r.monthly_income_cents, { round: true })} income − ${money(r.monthly_expense_cents, { round: true })} fixed costs</div></section>
    ${sug.length ? `<section class="block"><div class="panel"><div class="l1"><div><b>${sug.length} repeating payment${sug.length > 1 ? "s" : ""} found</b><div class="small muted">Track them and they'll be booked automatically.</div></div><button class="btn sm primary" id="sug-toggle" style="align-self:center">Review</button></div>
      <div id="sug-list" style="display:none;margin-top:14px">${sug.map((s, i) => `<div class="lrow"><div class="grow"><div class="t1">${esc(s.name)}</div><div class="t2">${FREQ[s.frequency]} · seen ${s.occurrences}× · next ${fmtDate(s.next_date)}</div></div><span class="amt ${s.type === "income" ? "pos" : ""}">${money(s.amount_cents)}</span><button class="btn sm" data-sug="${i}">Track</button></div>`).join("")}<div style="margin-top:12px"><button class="btn sm primary" id="sug-all">Track all</button></div></div></div></section>` : ""}
    ${block("Income", "", inc.map(item).join("") || `<div class="muted small">No recurring income yet. Add both salaries.</div>`)}
    ${block("Rent, bills & subscriptions", "", exp.map(item).join("") || `<div class="muted small">No bills yet. Start with the rent.</div>`)}
    ${paused.length ? block("Paused", "", paused.map(item).join("")) : ""}`;
  $("#add-rec").onclick = () => recModal();
  $$("[data-redit]").forEach((b) => (b.onclick = () => recModal(r.items.find((i) => i.id === Number(b.dataset.redit)))));
  const tg = $("#sug-toggle"); if (tg) tg.onclick = () => { const l = $("#sug-list"); const show = l.style.display === "none"; l.style.display = show ? "" : "none"; tg.textContent = show ? "Hide" : "Review"; };
  const addSug = (s) => api("POST", "/recurring", { name: s.name, type: s.type, amount_cents: s.amount_cents, category_id: s.category_id, person_id: s.person_id, split: s.split, frequency: s.frequency, start_date: s.start_date, mark_generated_until: s.last_date, link_tx_ids: s.tx_ids });
  $$("[data-sug]").forEach((b) => (b.onclick = async () => { await addSug(sug[Number(b.dataset.sug)]); toast("Now tracked"); refresh(); }));
  const all = $("#sug-all"); if (all) all.onclick = async () => { for (const s of sug) await addSug(s); toast(`Tracking ${sug.length} recurring items`); refresh(); };
}

function recModal(r) {
  const isNew = !r; r = r || { name: "", type: "expense", amount_cents: "", category_id: null, person_id: S.me, split: S.boot.settings.default_split, frequency: "monthly", start_date: S.boot.today, end_date: "", active: 1 };
  const { form } = modal(isNew ? "Add recurring item" : "Edit recurring item", `
    ${seg("type", [["expense", "Bill"], ["income", "Income"]], r.type)}<div style="height:16px"></div>
    <div class="field"><label>Name</label><input type="text" name="name" value="${esc(r.name)}" placeholder="Rent, Salary, Netflix…" required></div>
    <div class="fields2"><div class="field"><label>Amount</label><input type="text" inputmode="decimal" name="amount" value="${r.amount_cents === "" ? "" : centsToInput(r.amount_cents)}" placeholder="0,00" required></div>
      <div class="field"><label>Repeats</label><select name="frequency">${Object.entries(FREQ).map(([k, l]) => opt(k, l, r.frequency)).join("")}</select></div></div>
    <div class="fields2"><div class="field"><label>Next / first date</label><input type="date" name="start_date" value="${r.start_date}" required></div>
      <div class="field"><label>Ends (optional)</label><input type="date" name="end_date" value="${r.end_date || ""}"></div></div>
    <div class="field"><label>Category</label><select name="category_id"></select></div>
    <div class="fields2"><div class="field"><label id="r-who-l">Paid by</label><select name="person_id">${personOptions(r.person_id ?? "")}</select></div>
      <div class="field" id="r-split-f"><label>Split</label><select name="split">${splitOptions(r.split)}</select></div></div>
    ${isNew ? `<p class="xs muted">A start date in the past also creates the earlier entries.</p>` : `<label class="check"><input type="checkbox" name="active" ${r.active ? "checked" : ""}> Active</label>`}`, {
    extraActions: isNew ? "" : `<button type="button" class="btn danger" id="r-del" style="margin-right:auto">Delete</button>`,
    onSubmit: async (f) => { const cents = parseMoney(f.amount); if (!(cents >= 0)) { toast("Enter a valid amount", { error: true }); return false; }
      const body = { name: f.name, type: f.type, amount_cents: cents, frequency: f.frequency, start_date: f.start_date, end_date: f.end_date || null, category_id: f.category_id || null, person_id: f.person_id === "" ? null : Number(f.person_id), split: f.split };
      if (!isNew) body.active = !!f.active; await api(isNew ? "POST" : "PATCH", isNew ? "/recurring" : `/recurring/${r.id}`, body); refresh(); } });
  const sync = (reset) => { const t = form.elements.type.value; form.elements.category_id.innerHTML = catOptions(t, reset ? "" : (r.category_id ?? "")); $("#r-split-f").style.display = t === "expense" ? "" : "none"; $("#r-who-l").textContent = t === "income" ? "Received by" : "Paid by"; };
  form.elements.type.onchange = () => sync(true); sync(false);
  const del = $("#r-del"); if (del) del.onclick = async () => { if (!confirm("Delete this recurring item? Past payments are kept.")) return; await api("DELETE", `/recurring/${r.id}`); closeModal(); refresh(); };
}

// ------------------------------------------------------------------ GOALS
async function viewGoals(v) {
  const o = await api("GET", "/goals");
  const row = (g) => `<div class="goal"><div class="l1"><span class="name">${esc(g.name)}</span>${g.done ? `<span class="tag pos">Achieved</span>` : g.on_track ? `<span class="tag pos">On track</span>` : `<span class="tag warn">Behind</span>`}</div>
    <div class="bar"><i style="width:${g.pct}%"></i></div><div class="nums"><b>${money(g.saved_cents, { round: true })}</b><span class="muted">of ${money(g.target_cents, { round: true })}</span></div>
    ${g.done ? "" : `<div class="t2" style="white-space:normal;margin-top:8px">${money(g.remaining_cents, { round: true })} to go${g.deadline ? ` · by ${fmtDateLong(g.deadline)}` : ""}${g.required_monthly_cents != null ? ` · needs ${money(g.required_monthly_cents, { round: true })}/month` : ""}<br>At your pace: ${g.planned_monthly_cents ? `${money(g.planned_monthly_cents, { round: true })}/month` : "nothing set aside"}${g.eta ? ` → ${fmtDateLong(g.eta)}` : ""}</div>`}
    <div class="acts"><button class="btn sm" data-add="${g.id}">Add money</button><button class="btn sm ghost" data-hist="${g.id}">History</button><button class="btn sm ghost" data-gedit="${g.id}">Edit</button></div></div>`;
  v.innerHTML = `<header class="ph"><div><h1>Goals</h1><div class="sub">What you want together — and when you'll get there.</div></div><button class="btn primary" id="add-goal">New goal</button></header>
    ${o.goals.length ? `<section class="hero"><div class="label">Saved toward goals</div><div class="big">${bigMoney(o.total_saved_cents)}</div><div class="muted">of ${money(o.total_target_cents, { round: true })} across ${o.goals.length} goal${o.goals.length > 1 ? "s" : ""}</div>
      <div class="pair"><div><div class="k">You usually save</div><div class="v">${money(o.avg_monthly_savings_cents, { round: true })}<span class="faint" style="font-size:.6em"> /mo</span></div></div>
      <div><div class="k">Deadlines need</div><div class="v ${o.fits ? "" : "neg"}">${money(o.required_monthly_cents, { round: true })}<span class="faint" style="font-size:.6em"> /mo</span></div><div class="d">${o.fits ? "Fits within your savings" : "More than you save — move a date or trim spending"}</div></div></div></section>
      <section class="block">${o.goals.map(row).join("")}</section>`
    : `<div class="empty"><h3>No goals yet</h3>Add something like “Holiday in Japan — €4,500 by next August” and I'll work out what to put aside each month.<br><button class="btn primary" id="add-goal2">Add your first goal</button></div>`}`;
  $("#add-goal").onclick = () => goalModal(); const g2 = $("#add-goal2"); if (g2) g2.onclick = () => goalModal();
  $$("[data-gedit]").forEach((b) => (b.onclick = () => goalModal(o.goals.find((g) => g.id === Number(b.dataset.gedit)))));
  $$("[data-add]").forEach((b) => (b.onclick = () => contribModal(o.goals.find((g) => g.id === Number(b.dataset.add)))));
  $$("[data-hist]").forEach((b) => (b.onclick = () => historyModal(o.goals.find((g) => g.id === Number(b.dataset.hist)))));
}
function goalModal(g) {
  const isNew = !g; g = g || { name: "", target_cents: "", deadline: "", priority: 2 };
  modal(isNew ? "New goal" : "Edit goal", `
    <div class="field"><label>What do you want?</label><input type="text" name="name" value="${esc(g.name)}" placeholder="Holiday in Japan" required></div>
    <div class="fields2"><div class="field"><label>How much does it cost?</label><input type="text" inputmode="decimal" name="target" value="${g.target_cents === "" ? "" : centsToInput(g.target_cents)}" placeholder="0,00" required></div>
      <div class="field"><label>By when? (optional)</label><input type="date" name="deadline" value="${g.deadline || ""}"></div></div>
    <div class="field"><label>Priority</label>${seg("priority", [[1, "High"], [2, "Normal"], [3, "Low"]], g.priority)}</div>
    ${isNew ? `<div class="field"><label>Already saved (optional)</label><input type="text" inputmode="decimal" name="saved" placeholder="0,00"></div>` : ""}`, {
    extraActions: isNew ? "" : `<button type="button" class="btn danger" id="g-del" style="margin-right:auto">Delete</button>`,
    onSubmit: async (f) => { const target = parseMoney(f.target); if (!(target > 0)) { toast("Enter the target amount", { error: true }); return false; }
      const body = { name: f.name, target_cents: target, deadline: f.deadline || null, priority: Number(f.priority) }; if (isNew && f.saved) body.saved_cents = parseMoney(f.saved) || 0;
      await api(isNew ? "POST" : "PATCH", isNew ? "/goals" : `/goals/${g.id}`, body); refresh(); } });
  const del = $("#g-del"); if (del) del.onclick = async () => { if (!confirm("Delete this goal and its history?")) return; await api("DELETE", `/goals/${g.id}`); closeModal(); refresh(); };
}
function contribModal(g) {
  modal(`Add to ${g.name}`, `<div class="fields2"><div class="field"><label>Amount</label><input type="text" inputmode="decimal" name="amount" required placeholder="150"></div><div class="field"><label>Date</label><input type="date" name="date" value="${S.boot.today}"></div></div>
    <div class="field"><label>From</label><select name="person_id">${personOptions("")}</select></div><div class="field"><label>Note</label><input type="text" name="note"></div>
    <p class="xs muted">Use a negative amount to take money out.</p>`, { submitLabel: "Add", onSubmit: async (f) => { const c = parseMoney(f.amount); if (!c) { toast("Enter an amount", { error: true }); return false; }
      await api("POST", `/goals/${g.id}/contributions`, { amount_cents: c, date: f.date, person_id: f.person_id === "" ? null : Number(f.person_id), note: f.note }); refresh(); } });
}
async function historyModal(g) {
  const list = await api("GET", `/goals/${g.id}/contributions`);
  modal(`${g.name} — history`, list.length ? list.map((c) => `<div class="lrow"><div class="grow"><div class="t1">${fmtDateLong(c.date)}</div><div class="t2">${esc(personName(c.person_id))}${c.note ? " · " + esc(c.note) : ""}</div></div><span class="amt ${c.amount_cents < 0 ? "neg" : ""}">${money(c.amount_cents)}</span><button type="button" class="btn sm ghost" data-cdel="${c.id}">Remove</button></div>`).join("") : `<div class="muted">Nothing added yet.</div>`,
    { hideActions: true });
  $$("#modal-host [data-cdel]").forEach((b) => (b.onclick = async () => { await api("DELETE", `/contributions/${b.dataset.cdel}`); closeModal(); refresh(); }));
  const form = $("#modal-host form"); form.insertAdjacentHTML("beforeend", `<div class="actions"><button type="button" class="btn" data-close>Close</button></div>`); $("[data-close]", form).onclick = closeModal;
}

// ------------------------------------------------------------------ CONNECT (bank sync · CSV · phone)
async function viewConnect(v) {
  const tabs = seg("tab", [["bank", "Bank sync"], ["csv", "CSV file"], ["phone", "Phone payments"]], S.tab, "auto");
  v.innerHTML = `<header class="ph"><div><h1>Connect</h1><div class="sub">Get payments in without typing them. All free.</div></div></header><div style="margin-bottom:28px">${tabs}</div><div id="tab-body"></div>`;
  bindSegs(v); $("input[name=tab]", v).onchange = (e) => { S.tab = e.target.value; S.importState = null; route(); };
  const body = $("#tab-body"); ({ bank: connectBank, csv: connectCsv, phone: connectPhone })[S.tab](body);
}

async function connectBank(el) {
  const st = await api("GET", "/bank/status"), cfg = st.config, ready = cfg.app_id && cfg.has_key;
  const defaultRedirect = S.boot.settings.eb_redirect_url || (location.protocol === "https:" ? location.origin + "/callback" : `https://localhost:${location.port || 8765}/callback`);
  const ago = (iso) => { if (!iso) return "never"; const m = Math.round((Date.now() - new Date(iso)) / 60000); return m < 1 ? "just now" : m < 60 ? m + " min ago" : m < 1440 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " days ago"; };
  const conns = st.connections.map((c) => { const exp = c.status === "expired" || (c.days_left != null && c.days_left < 0), soon = !exp && c.days_left != null && c.days_left <= 7;
    return `<div class="lrow" style="align-items:flex-start"><div class="grow"><div class="t1">${esc(c.aspsp_name)} <span class="muted">· ${esc(personName(c.person_id))}</span></div>${c.accounts.map((a) => `<div class="t2" style="white-space:normal">${esc(a.name)} ···· ${esc(a.iban_tail)} · synced ${a.last_sync ? fmtDateLong(a.last_sync) : "never"}${a.last_error ? ` · <span class="neg">${esc(a.last_error)}</span>` : ""}</div>`).join("")}</div>
      <div class="right">${exp ? `<span class="tag neg">Expired</span>` : soon ? `<span class="tag warn">Renew in ${c.days_left} days</span>` : `<span class="tag pos">Connected${c.days_left != null ? " · " + c.days_left + "d left" : ""}</span>`}
      <div style="margin-top:8px;display:flex;gap:6px;justify-content:flex-end"><button class="btn sm" data-sync="${c.id}" ${exp ? "disabled" : ""}>Sync</button><button class="btn sm ghost" data-disc="${c.id}">Remove</button></div></div></div>`; }).join("");
  el.innerHTML = `
    <p class="muted" style="margin-bottom:28px">Uses <b style="color:var(--ink)">Enable Banking</b>'s free <i>Restricted Production</i> mode: real data from accounts <i>you</i> link yourselves (EU/UK, official PSD2). Payments are pulled every few hours, categorised, and never counted twice. Banks ask you to renew every 90–180 days.</p>
    ${st.connections.length ? block("Connected accounts", `<span class="xs muted">Last sync ${ago(st.last_sync)}</span>`, conns + `<div style="margin-top:14px"><button class="btn primary sm" id="sync-all">Sync now</button></div>`) : ""}
    ${block(ready ? "Step 1 · Enable Banking" : "Step 1 · One-time setup", ready ? `<button class="link" id="edit-cfg">Change</button>` : "", `
      ${ready ? `<div class="small"><span class="tag pos">Set up</span> <span class="muted">Application ${esc(cfg.app_id.slice(0, 8))}…</span></div>` : ""}
      <div id="cfg-wrap" style="${ready ? "display:none" : ""}"><ol class="steps">
        <li>Sign in at <a href="https://enablebanking.com/sign-in/" target="_blank" rel="noopener"><b>enablebanking.com</b></a> with your email (no card), then open <b>API applications → Add</b>.</li>
        <li>Choose <b>Production</b>, keep “Generate in the browser and export private key” (a <code>.pem</code> file downloads), and set the <b>Redirect URL</b> to <code>${esc(defaultRedirect)}</code>. Other fields can be anything.</li>
        <li>Click <b>Activate by linking accounts</b> and log in to your bank. <b>Your partner does the same</b> with her bank login.</li>
        <li>Paste the <b>Application ID</b> and the <code>.pem</code> contents here.</li></ol>
      <form id="cfg-form"><div class="fields2"><div class="field"><label>Application ID</label><input type="text" name="app_id" value="${esc(cfg.app_id)}" required></div>
        <div class="field"><label>Redirect URL</label><input type="text" name="redirect_url" value="${esc(defaultRedirect)}"></div></div>
        <div class="field"><label>Private key ${cfg.has_key ? "(saved — leave empty to keep)" : ""}</label><input type="file" id="pem-file" accept=".pem,.key,.txt"><textarea name="private_key" rows="3" placeholder="-----BEGIN PRIVATE KEY-----" style="margin-top:8px"></textarea></div>
        <div class="field" style="max-width:200px"><label>Sync every (hours, min 4)</label><input type="number" name="sync_hours" min="4" max="48" value="${cfg.sync_hours}"></div>
        <button class="btn primary">Save</button></form></div>`)}
    ${ready ? block("Step 2 · Connect an account", "", `
      <div class="fields3"><div class="field"><label>Whose account?</label><select id="b-person">${personOptions(S.me, true)}</select></div>
        <div class="field"><label>Country</label><select id="b-country">${["NL", "BE", "DE", "FR", "GB", "ES", "IT", "IE", "PT", "AT", "FI", "SE", "DK", "NO", "PL"].map((c) => opt(c, c, "NL")).join("")}</select></div>
        <div class="field"><label>Bank</label><select id="b-bank"><option>Loading…</option></select></div></div>
      <button class="btn primary" id="b-connect" disabled>Connect</button>
      <div id="b-paste" style="display:none;margin-top:22px"><p class="small" style="margin-bottom:10px"><b>Approve in your bank.</b> You'll land on a page that may look like an error — that's expected. <b>Copy the full address from the address bar</b> (it contains <code>?code=</code>) and paste it here:</p>
        <div style="display:flex;gap:8px"><input type="text" id="b-redirect" placeholder="https://localhost:8765/callback?code=…"><button class="btn primary" id="b-finish">Finish</button></div>
        <p class="xs muted" style="margin-top:8px"><a id="b-open" href="#" target="_blank" rel="noopener">Bank page didn't open? Click here.</a></p></div>`) : ""}`;
  const doSync = async (btn) => { btn.disabled = true; btn.textContent = "Syncing…"; try { const r = await api("POST", "/bank/sync", {}); const errs = r.results.filter((x) => x.error);
    toast(errs.length ? errs[0].error : `Synced — ${r.added} new payment${r.added === 1 ? "" : "s"}`, { error: !!errs.length }); S.boot = await api("GET", "/bootstrap"); } finally { refresh(); } };
  const sa = $("#sync-all"); if (sa) sa.onclick = () => doSync(sa);
  $$("[data-sync]", el).forEach((b) => (b.onclick = () => doSync(b)));
  $$("[data-disc]", el).forEach((b) => (b.onclick = async () => { if (!confirm("Remove this connection? Payments already imported are kept.")) return; await api("DELETE", `/bank/connections/${b.dataset.disc}`); refresh(); }));
  const ec = $("#edit-cfg"); if (ec) ec.onclick = () => { $("#cfg-wrap").style.display = ""; ec.remove(); };
  const pf = $("#pem-file"); if (pf) pf.onchange = () => { const r = new FileReader(); r.onload = () => { $("#cfg-form").elements.private_key.value = r.result; }; r.readAsText(pf.files[0]); };
  $("#cfg-form").onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target).entries());
    await api("PUT", "/bank/config", { app_id: f.app_id, redirect_url: f.redirect_url, private_key: f.private_key || null, sync_hours: f.sync_hours }); S.boot = await api("GET", "/bootstrap"); toast("Saved"); refresh(); };
  if (ready) {
    const sel = $("#b-bank"), btn = $("#b-connect"); let banks = [];
    const load = async () => { sel.innerHTML = "<option>Loading…</option>"; btn.disabled = true;
      try { banks = await api("GET", `/bank/banks?country=${$("#b-country").value}`); sel.innerHTML = banks.map((b, i) => opt(i, b.name, "")).join(""); btn.disabled = !banks.length; } catch (e) { sel.innerHTML = "<option>Couldn't load banks</option>"; } };
    $("#b-country").onchange = load; load();
    btn.onclick = async () => { const b = banks[Number(sel.value)]; if (!b) return; btn.disabled = true;
      try { const pid = $("#b-person").value; const r = await api("POST", "/bank/connect", { person_id: pid === "" ? null : Number(pid), bank: b.name, country: b.country, max_days: b.max_days });
        $("#b-paste").style.display = ""; $("#b-open").href = r.url; window.open(r.url, "_blank", "noopener"); } finally { btn.disabled = false; } };
    $("#b-finish").onclick = async (e) => { const val = $("#b-redirect").value.trim(); if (!val) return toast("Paste the address first", { error: true }); e.target.disabled = true; e.target.textContent = "Connecting…";
      try { const r = await api("POST", "/bank/finish", { redirect: val }); const added = (r.sync || []).reduce((a, x) => a + (x.added || 0), 0), err = (r.sync || []).find((x) => x.error);
        toast(err ? "Connected, but the first sync failed: " + err.error : `Connected — imported ${added} payments`, { error: !!err }); S.boot = await api("GET", "/bootstrap"); refresh(); } catch (err) { e.target.disabled = false; e.target.textContent = "Finish"; } };
  }
}

function connectPhone(el) {
  const token = S.boot.settings.ingest_token || "", hook = `${location.origin}/api/ingest`, me = personName(S.me);
  el.innerHTML = `<p class="muted" style="margin-bottom:24px">Every card or Apple Pay payment you make with your phone becomes an entry the moment you pay. No bank login and no third party.</p>
    <ol class="steps"><li>On iPhone open <b>Shortcuts → Automation → New → Transaction</b> and pick your cards.</li>
    <li>Add <b>Get contents of URL</b>: method <b>POST</b>, request body <b>JSON</b> with these fields. <span class="muted">(Android: same URL from Tasker, MacroDroid or HTTP Shortcuts.)</span></li></ol>
    <pre>URL   ${esc(hook)}
{ "token":    "${esc(token)}",
  "amount":   Shortcut Input → Amount,
  "merchant": Shortcut Input → Merchant,
  "person":   "${esc(me)}" }</pre>
    <p class="small muted" style="margin:18px 0 6px">Try it from a terminal:</p>
    <pre>curl -X POST ${esc(hook)} -H 'Content-Type: application/json' \\
  -d '{"token":"${esc(token)}","amount":"4,50","merchant":"Coffee","person":"${esc(me)}"}'</pre>
    <p class="small muted">Your phone must be able to reach this app: same Wi-Fi with <code>HOST=0.0.0.0</code> and a <code>CF_PASSWORD</code> set, or a free private tunnel like Tailscale. Keep the token secret.</p>`;
}

function connectCsv(el) {
  if (S.importState && S.importState.preview) return importPreview(el);
  el.innerHTML = `<p class="muted" style="margin-bottom:24px">Download a CSV export from your banking app or website (ING, ABN AMRO, Rabobank, bunq, Revolut, Wise…) and drop it here. Columns, Dutch number formats and duplicates are handled for you.</p>
    <div class="field" style="max-width:260px"><label>Whose account is this?</label><select id="imp-person">${personOptions(S.me, true)}</select></div>
    <div class="drop" id="drop"><b style="color:var(--ink)">Drop your CSV here</b><div class="small">or click to choose a file</div><input type="file" id="file" accept=".csv,.txt,text/csv" hidden></div>
    <details style="margin-top:18px"><summary>Or paste the text</summary><textarea id="imp-text" rows="5" style="margin-top:8px" placeholder="Datum;Omschrijving;Bedrag…"></textarea><button class="btn primary sm" id="imp-go" style="margin-top:8px">Preview</button></details>
    <p class="small" style="margin-top:22px"><button class="link" id="imp-sample" style="text-decoration:underline">Try with a sample file</button></p>`;
  const run = async (text) => { if (!text.trim()) return toast("Choose a file or paste some text first", { error: true });
    const pid = $("#imp-person").value === "" ? null : Number($("#imp-person").value);
    const p = await api("POST", "/import/preview", { text, person_id: pid });
    if (!p.rows.length) return toast(p.warnings[0] || "No rows found in that file.", { error: true });
    S.importState = { preview: p, person_id: pid }; route(); };
  const readFile = (f) => { const r = new FileReader(); r.onload = () => run(r.result); r.readAsText(f); };
  const drop = $("#drop"), file = $("#file");
  drop.onclick = () => file.click(); file.onchange = () => file.files[0] && readFile(file.files[0]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); }; drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]); };
  $("#imp-go").onclick = () => run($("#imp-text").value);
  $("#imp-sample").onclick = async () => run((await api("GET", "/sample-csv")).text);
}

function importPreview(el) {
  const { preview: p, person_id } = S.importState, rows = p.rows;
  rows.forEach((r) => { if (r.skip === undefined) r.skip = r.status === "duplicate"; });
  const draw = () => {
    const todo = rows.filter((r) => !r.skip), need = todo.filter((r) => !r.category_id && r.type !== "transfer").length;
    const stat = (r) => r.status === "duplicate" ? "already imported" : r.status === "matches_bill" ? "matches a bill" : r.type === "transfer" ? "own-account transfer" : "";
    el.innerHTML = `<div class="l1" style="align-items:center;margin-bottom:6px"><div><b>${rows.length} rows</b> <span class="muted">from ${esc(personName(person_id))}'s account</span></div><div style="display:flex;gap:8px"><button class="btn" id="imp-cancel">Cancel</button><button class="btn primary" id="imp-commit">Import ${todo.length}</button></div></div>
      <div class="small muted" style="margin-bottom:16px">${rows.filter((r) => r.status === "new").length} new · ${rows.filter((r) => r.status === "matches_bill").length} match your bills · ${rows.filter((r) => r.status === "duplicate").length} duplicates · <span class="${need ? "warn" : ""}">${need} need a category</span>${p.skipped ? ` · ${p.skipped} unreadable rows skipped` : ""}</div>
      ${rows.map((r, i) => `<div class="imp ${r.skip ? "dim" : ""}"><span class="muted">${fmtDate(r.date)}</span>
        <label class="check" style="min-width:0;gap:8px"><input type="checkbox" data-skip="${i}" ${r.skip ? "" : "checked"} ${r.status === "duplicate" ? "disabled" : ""}><span style="min-width:0"><span class="t1" style="display:block">${esc(r.description)}</span>${stat(r) ? `<span class="t2" style="display:block">${stat(r)}</span>` : ""}</span></label>
        <div>${r.type === "transfer" ? "" : `<select class="pick" style="color:${r.category_id ? "var(--ink-2)" : "var(--warn)"}" data-cat="${i}" ${r.skip ? "disabled" : ""}>${catOptions(r.type, r.category_id ?? "", "Choose category…")}</select>`}</div>
        <span class="amt right ${r.type === "income" ? "pos" : ""}">${r.type === "income" ? "+" : "−"}${money(r.amount_cents)}</span></div>`).join("")}`;
    $("#imp-cancel").onclick = () => { S.importState = null; route(); };
    $$("[data-skip]", el).forEach((c) => (c.onchange = () => { rows[c.dataset.skip].skip = !c.checked; draw(); }));
    $$("[data-cat]", el).forEach((c) => (c.onchange = () => { const r = rows[c.dataset.cat]; r.category_id = c.value ? Number(c.value) : null; r.learn = !!c.value;
      const key = (r.description || "").toLowerCase().split(/\s+/)[0];
      rows.forEach((o) => { if (o !== r && !o.category_id && o.type === r.type && key && (o.description || "").toLowerCase().startsWith(key)) o.category_id = r.category_id; }); draw(); }));
    $("#imp-commit").onclick = async () => { if (need && !confirm(`${need} rows have no category. Import anyway? You can categorise them later.`)) return;
      const res = await api("POST", "/import/commit", { rows, person_id }); S.importState = null; S.boot = await api("GET", "/bootstrap");
      toast(`Imported ${res.added} new${res.matched_bills ? `, matched ${res.matched_bills} bills` : ""}${res.duplicates ? `, skipped ${res.duplicates} duplicates` : ""}`);
      const target = res.suggestions ? "#bills" : "#home"; if (location.hash === target) route(); else location.hash = target; };
  };
  draw();
}

// ------------------------------------------------------------------ SETTINGS
async function viewSettings(v) {
  const [rules, boot] = await Promise.all([api("GET", "/rules"), api("GET", "/bootstrap")]); S.boot = boot;
  const st = boot.settings;
  v.innerHTML = `<header class="ph"><div><h1>Settings</h1></div></header>
    ${block("You two", "", `<form id="set-form"><div class="fields2">${people().map((p, i) => `<div class="field"><label>Person ${i + 1}</label><div style="display:flex;gap:8px"><input type="text" name="n${p.id}" value="${esc(p.name)}" required><input type="color" name="c${p.id}" value="${esc(p.color)}" aria-label="Colour"></div></div>`).join("")}</div>
      <div class="fields2"><div class="field"><label>Split shared costs</label><select name="split">${opt("income", "By income", st.default_split)}${opt("equal", "50 / 50", st.default_split)}</select></div>
      <div class="field"><label>Currency</label><select name="currency">${["EUR", "USD", "GBP"].map((c) => opt(c, c, st.currency)).join("")}</select></div></div><button class="btn primary">Save</button></form>`)}
    ${block("Monthly budgets", "", `<p class="small muted" style="margin-bottom:6px">Optional. Set a limit and Home shows how much is left. “Need / Want” feeds the 50/30/20 guide.</p>${cats("expense").map((c) => `<div class="lrow"><span class="dot" style="background:${catColor(c.id)}"></span><div class="grow t1">${esc(c.name)}</div><select data-bucket="${c.id}" style="width:96px;padding:6px 28px 6px 10px">${opt("needs", "Need", c.bucket)}${opt("wants", "Want", c.bucket)}</select><input type="text" inputmode="decimal" data-budget="${c.id}" value="${c.budget_cents ? centsToInput(c.budget_cents) : ""}" placeholder="No limit" style="width:110px;padding:6px 10px;text-align:right"></div>`).join("")}<div style="margin-top:14px"><button class="btn sm" id="add-cat">Add category</button></div>`)}
    ${block(`Auto-categorisation (${rules.length} rules)`, "", `<p class="small muted" style="margin-bottom:12px">If a description contains the text, it gets that category. New rules appear as you categorise.</p>
      <form id="rule-form" style="display:flex;gap:8px;flex-wrap:wrap"><input type="text" name="pattern" placeholder="e.g. bakker" required style="flex:1;min-width:140px"><select name="category_id" style="flex:1;min-width:160px">${catOptions(null, "", null)}</select><button class="btn">Add</button></form>
      <details style="margin-top:12px"><summary>Show all rules</summary><div style="max-height:320px;overflow:auto;margin-top:6px">${rules.map((r) => `<div class="lrow" style="padding:7px 0"><code class="grow" style="background:none;padding:0">${esc(r.pattern)}</code><span class="small muted">${esc(r.category_name)}</span><button class="btn sm ghost" data-rdel="${r.id}" aria-label="Delete rule">✕</button></div>`).join("")}</div></details>`)}
    ${block("Your data", "", `<p class="small muted" style="margin-bottom:14px">Everything lives in one file on this computer (<code>couple-finance/data/finance.db</code>). Nothing is sent anywhere except to your bank via Enable Banking, if you connect it.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn" href="/api/export" download>Download backup</a><button class="btn" id="demo">Load sample data</button><button class="btn danger" id="wipe">Delete all data…</button></div>`)}`;
  $("#set-form").onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target).entries());
    S.boot = await api("PUT", "/settings", { people: people().map((p) => ({ id: p.id, name: f["n" + p.id], color: f["c" + p.id] })), default_split: f.split, currency: f.currency, setup_done: "1" }); renderShell(); toast("Saved"); };
  $$("[data-budget]").forEach((i) => (i.onchange = async () => { const c = parseMoney(i.value); await api("PATCH", `/categories/${i.dataset.budget}`, { budget_cents: c > 0 ? c : null }); toast("Saved"); }));
  $$("[data-bucket]").forEach((i) => (i.onchange = async () => { await api("PATCH", `/categories/${i.dataset.bucket}`, { bucket: i.value }); toast("Saved"); }));
  $("#add-cat").onclick = () => modal("New category", `<div class="fields2"><div class="field"><label>Name</label><input type="text" name="name" required></div><div class="field"><label>Kind</label><select name="kind">${opt("expense", "Expense", "expense")}${opt("income", "Income", "income")}</select></div></div>`,
    { onSubmit: async (f) => { await api("POST", "/categories", { name: f.name, kind: f.kind, icon: "•" }); S.boot = await api("GET", "/bootstrap"); refresh(); } });
  $("#rule-form").onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target).entries()); const r = await api("POST", "/rules", { pattern: f.pattern, category_id: Number(f.category_id) }); toast(r.applied ? `Rule added — categorised ${r.applied} payments` : "Rule added"); refresh(); };
  $$("[data-rdel]").forEach((b) => (b.onclick = async () => { await api("DELETE", `/rules/${b.dataset.rdel}`); refresh(); }));
  $("#demo").onclick = async () => { try { await api("POST", "/demo", {}); } catch (e) { return; } S.boot = await api("GET", "/bootstrap"); toast("Sample data loaded"); location.hash = "#home"; };
  $("#wipe").onclick = async () => { if (prompt("This deletes every payment, bill and goal. Type DELETE to confirm.") !== "DELETE") return; await api("POST", "/reset", { confirm: "DELETE" }); S.boot = await api("GET", "/bootstrap"); toast("All cleared"); location.hash = "#home"; route(); };
}

const VIEWS = { home: viewHome, activity: viewActivity, bills: viewBills, goals: viewGoals, connect: viewConnect, settings: viewSettings };

// ------------------------------------------------------------------ boot
async function start() {
  S.boot = await api("GET", "/bootstrap"); S.month = S.boot.month;
  if (!people().some((p) => p.id === S.me)) S.me = 1;
  $("#fab").onclick = openQuick;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
    const tag = (e.target.tagName || "").toLowerCase();
    if ((e.key === "n" || e.key === "+") && !e.metaKey && !e.ctrlKey && !["input", "textarea", "select"].includes(tag) && !$("#modal-host .overlay")) { e.preventDefault(); openQuick(); }
  });
  window.addEventListener("hashchange", route);
  route();
}
start();
