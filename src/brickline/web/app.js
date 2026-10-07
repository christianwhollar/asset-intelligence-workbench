"use strict";
const $ = (q) => document.querySelector(q);
const escapeHTML = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const esc = escapeHTML;
const money = (c, compact = false) =>
  c == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: compact ? 1 : 0,
        notation: compact ? "compact" : "standard",
      }).format(c / 100);
const pct = (n) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);
const number = (n) => (n == null ? "—" : Number(n).toLocaleString("en-US"));
const ratio = (n) => (n == null ? "No debt" : `${n.toFixed(2)}×`);
const stamp = (s) =>
  new Date(s).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const state = {
  key: sessionStorage.getItem("brickline-key") || "demo-analyst",
  page: "portfolio",
  asset: null,
  tab: "imports",
  documentAsset: "HAR",
  query: "renewal notice capital works",
  brief: null,
  serial: 0,
  filter: "",
  sector: "all",
};
let toastTimer;
function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 5500);
}
async function api(path, options = {}) {
  const key = state.key;
  const headers = { "X-API-Key": key, ...options.headers };
  if (options.body && !(options.body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (key !== state.key) throw new Error("Identity changed. Please retry.");
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: `Request failed (${response.status})` }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Check the form values and try again.",
    );
  }
  return response.json();
}
const post = (url, body) =>
  api(url, { method: "POST", body: JSON.stringify(body) });
async function download(path, name) {
  const r = await fetch(`/api${path}`, { headers: { "X-API-Key": state.key } });
  if (!r.ok) throw new Error((await r.json()).detail);
  const url = URL.createObjectURL(await r.blob()),
    link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const stat = (label, value, note) =>
  `<div class="stat"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`;
const empty = (text) => `<div class="empty">${esc(text)}</div>`;
const title = (label, heading, sub) =>
  `<div class="page-title"><div class="eyebrow">${esc(label)}</div><h1>${esc(heading)}</h1><p>${esc(sub)}</p></div>`;
function assetOptions(selected) {
  return state.portfolio.assets
    .map(
      (a) =>
        `<option value="${esc(a.id)}" ${a.id === selected ? "selected" : ""}>${esc(a.name)}</option>`,
    )
    .join("");
}
function evidenceHTML(hits) {
  return hits.length
    ? hits
        .map(
          (h) =>
            `<article class="source"><div class="source-title">${esc(h.title)}</div><span class="pill">VERSION ${h.version} · PAGE ${h.page}</span><p>${esc(h.text)}</p><div class="mono">${esc(h.id)}</div></article>`,
        )
        .join("")
    : empty("No matching authorized passages. Try a more specific term.");
}
async function navigate(page = state.page) {
  state.page = page;
  const serial = ++state.serial;
  document
    .querySelectorAll("nav button")
    .forEach((b) =>
      b.setAttribute(
        "aria-current",
        b.dataset.page === page ? "page" : "false",
      ),
    );
  $("#main").innerHTML =
    '<div class="loading" role="status">Loading workspace…</div>';
  try {
    const renderers = {
      portfolio: portfolioPage,
      data: dataPage,
      briefs: briefsPage,
      actions: actionsPage,
      activity: activityPage,
    };
    const html = await renderers[page]();
    if (serial === state.serial) {
      $("#main").innerHTML = html;
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  } catch (error) {
    if (serial === state.serial)
      $("#main").innerHTML =
        `<div class="notice error" role="alert">${esc(error.message)}</div><button data-action="reload">Try again</button>`;
  }
}
function assetRows() {
  const rows = state.portfolio.assets.filter(
    (a) =>
      (state.sector === "all" || a.sector === state.sector) &&
      `${a.name} ${a.market}`
        .toLowerCase()
        .includes(state.filter.toLowerCase()),
  );
  return rows.length
    ? rows
        .map(
          (a) =>
            `<tr><td><button class="asset-link" data-asset="${esc(a.id)}">${esc(a.name)} ↗</button><small>${esc(a.market)}</small></td><td><span class="tag">${esc(a.sector)}</span></td><td class="number">${money(a.noi_cents, true)}<small>T12 operating</small></td><td class="number">${pct(a.occupancy)}<svg class="meter" viewBox="0 0 100 4" aria-hidden="true"><rect width="100" height="4" fill="#e6eade"/><rect width="${a.occupancy * 100}" height="4" fill="#203f34"/></svg></td><td class="number">${pct(a.expiry_share)}<small>Annual base rent</small></td><td class="number">${ratio(a.dscr)}</td><td><span class="pill ${a.attention.length ? "warn" : ""}">${a.attention.length ? `${a.attention.length} REVIEW FLAGS` : "MONITOR"}</span></td></tr>`,
        )
        .join("")
    : `<tr><td colspan="7">${empty("No assets match these filters.")}</td></tr>`;
}
async function portfolioPage() {
  state.portfolio = await api("/portfolio");
  if (state.asset) return assetPage();
  const t = state.portfolio.totals;
  return `<section class="hero"><div><div class="eyebrow">${esc(state.session.tenant.toUpperCase())} / OPERATING REVIEW / ${esc(state.portfolio.snapshot.as_of)}</div><h1>Know what needs<br>attention.</h1><p>One view of operating performance, lease exposure, and the source documents behind your next conversation.</p></div><div class="hero-right"><div class="eyebrow">THE REVIEW QUEUE</div><strong>${t.attention_count} of ${state.portfolio.assets.length}</strong><p>assets cross an illustrative monitoring threshold. Start with the operating facts.</p><svg class="block-art" viewBox="0 0 150 150" aria-hidden="true"><path d="M10 140V75h35V40h35V10h35v65h25v65z" fill="currentColor"/><path d="M20 90h13m-13 15h13m-13 15h13m23-65h13m-13 15h13m-13 15h13m23-55h13m-13 15h13m-13 15h13" stroke="#203f34" stroke-width="5"/></svg></div></section><section class="stats" aria-label="Portfolio metrics">${stat("Trailing 12-month NOI", money(t.noi_cents, true), "Income less recurring operating expenses")}${stat("Area occupancy", pct(t.occupancy), `${number(t.leased_sf)} of ${number(t.area_sf)} sq ft`)}${stat("Rent rolling in 12 months", money(t.expiry_rent_cents, true), `${pct(t.expiry_share)} of active annual base rent`)}${stat("Debt service coverage", ratio(t.dscr), "After declared replacement reserves")}</section><div class="section-head"><h2>The asset book <span class="muted small">/ ${state.portfolio.assets.length} properties</span></h2><div class="filters"><input id="assetFilter" aria-label="Filter assets" placeholder="Find an asset or market" value="${esc(state.filter)}"><select id="sectorFilter" aria-label="Filter by sector"><option value="all">All sectors</option><option ${state.sector === "Industrial" ? "selected" : ""}>Industrial</option><option ${state.sector === "Office" ? "selected" : ""}>Office</option></select></div></div><div class="panel flush table-wrap"><table><thead><tr><th>Asset / market</th><th>Sector</th><th>NOI</th><th>Occupancy</th><th>12-mo expiry</th><th>DSCR</th><th>Focus</th></tr></thead><tbody id="assetRows">${assetRows()}</tbody></table></div><div class="equal"><div class="panel"><div class="eyebrow">FROM DATA TO DECISION</div><h2>Every number has a starting point.</h2><p class="small">Open an asset to inspect its rent roll and monthly statements. Changes arrive as full snapshots, pass validation, and require an independent reviewer before publication.</p><button class="secondary" data-go="data">Open the data room →</button></div><div class="panel"><div class="eyebrow">FOLLOW THROUGH</div><h2>Turn a finding into an action.</h2><p class="small">Build an evidence brief, check the source passages, and assign a follow-up. Review and feedback stay attached to the work.</p><button class="secondary" data-go="briefs">Build a review brief →</button></div></div><p class="definition">Synthetic data as of ${esc(state.portfolio.snapshot.as_of)}. NOI excludes capital expenditures, depreciation, and debt service. Coverage subtracts the declared annual replacement reserve. Monitoring thresholds are illustrative and do not represent loan covenants.</p>`;
}
async function assetPage() {
  const result = await api(`/assets/${state.asset}`),
    m = result.metrics;
  state.assetDetail = result;
  const max = Math.max(...result.monthly.map((r) => r.noi_cents), 1),
    min = Math.min(...result.monthly.map((r) => r.noi_cents), 0);
  const points = result.monthly
    .map(
      (r, i) =>
        `${((i * 560) / 11 + 20).toFixed(1)},${(120 - ((r.noi_cents - min) / (max - min)) * 90).toFixed(1)}`,
    )
    .join(" ");
  return `<button class="quiet back" data-action="back">← Portfolio</button><div class="asset-heading"><div><div class="eyebrow">ASSET ${esc(m.id)} / ${esc(m.as_of)}</div><h1>${esc(m.name)}</h1><p><span class="tag">${esc(m.sector)}</span>${esc(m.market)} · ${number(m.area_sf)} sq ft</p></div><button data-action="asset-brief">Build asset brief ↗</button></div><div class="stats">${stat("T12 net operating income", money(m.noi_cents, true), "Statement-derived; before debt service")}${stat("Area occupancy", pct(m.occupancy), `${number(m.leased_sf)} occupied sq ft`)}${stat("Weighted lease term", m.walt_years == null ? "—" : `${m.walt_years.toFixed(2)} yrs`, "Weighted by active annual base rent")}${stat("Reserve-adjusted DSCR", ratio(m.dscr), `${money(m.debt_cents, true)} annual debt service`)}</div><div class="split"><div><section class="panel"><div class="section-head"><h2>Operating rhythm</h2><span class="small muted">Monthly NOI · USD</span></div><svg class="chart" viewBox="0 0 600 145" role="img" aria-label="Monthly net operating income over twelve months"><line x1="20" y1="120" x2="580" y2="120" stroke="#d7ddd3"/><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="3"/>${result.monthly.map((r, i) => `<circle cx="${(i * 560) / 11 + 20}" cy="${120 - ((r.noi_cents - min) / (max - min)) * 90}" r="4" fill="currentColor"><title>${esc(r.month)}: ${money(r.noi_cents)}</title></circle>`).join("")}</svg><div class="chart-labels"><span>${esc(result.monthly[0].month)}</span><span>${money(max)} peak monthly NOI</span><span>${esc(result.monthly.at(-1).month)}</span></div>${m.attention.map((a) => `<div class="insight">${esc(a)}</div>`).join("")}<details><summary>Inspect monthly statement and source rows</summary><div class="table-wrap"><table><thead><tr><th>Month</th><th>Account</th><th>Amount</th><th>Sheet row</th></tr></thead><tbody>${result.operating.map((r) => `<tr><td>${esc(r.month)}</td><td>${esc(r.account)}</td><td>${money(r.amount_cents)}</td><td>${r.source_row}</td></tr>`).join("")}</tbody></table></div></details></section><section class="panel"><div class="section-head"><h2>Lease exposure</h2><span class="pill">${pct(m.expiry_share)} ROLLING</span></div><div class="table-wrap"><table><thead><tr><th>Occupier</th><th>Area / sq ft</th><th>Annual base rent</th><th>Expiry</th><th>Source row</th></tr></thead><tbody>${result.leases.map((l) => `<tr><td><strong>${esc(l.tenant_name)}</strong><small>${esc(l.id)} · ${l.active ? "Active" : "Outside snapshot date"}</small></td><td>${number(l.area_sf)}</td><td>${money(l.rent_cents)}</td><td>${esc(l.end_date)}</td><td>${l.source_row}</td></tr>`).join("")}</tbody></table></div></section></div><div><section class="panel"><div class="eyebrow">WHAT IF?</div><h2>Operating sensitivity</h2><p class="small">Adjust the trailing income and expense base. Debt service and reserves remain fixed.</p><form id="scenarioForm" class="form"><label>Operating income change <span id="incomeLabel">0%</span><input id="incomeChange" name="income" type="range" min="-30" max="30" value="0" step="1"></label><label>Operating expense change <span id="expenseLabel">0%</span><input id="expenseChange" name="expense" type="range" min="-20" max="50" value="0" step="1"></label><label>Cap rate change <span id="capLabel">0 bps</span><input id="capChange" name="cap" type="range" min="-200" max="300" value="0" step="25"></label><button>Calculate scenario</button></form><div id="scenarioResult"><div class="metric-row"><span>Base NOI</span><strong>${money(m.noi_cents, true)}</strong></div><div class="metric-row"><span>Reference cap rate</span><strong>${pct(m.cap_rate)}</strong></div><div class="metric-row"><span>Capitalized base NOI</span><strong>${money(m.capitalized_noi_cents, true)}</strong></div></div><p class="definition">A sensitivity calculation, not an appraisal or investment recommendation. It does not model stabilized occupancy, leasing costs, rent-free periods, sale costs, or market comparables.</p></section><section class="panel"><div class="eyebrow">SOURCE TRAIL</div><h3>Active reporting snapshot</h3><div class="mono">${esc(m.dataset)}</div><p class="small">Property assumptions: Assets row ${m.source_row}. Lease and statement row numbers appear alongside each source record.</p><button class="secondary" data-action="asset-docs">Inspect source documents →</button></section></div></div>`;
}
async function dataPage() {
  if (state.tab === "documents" && !state.portfolio)
    state.portfolio = await api("/portfolio");
  const head = title(
    "INGEST / NORMALIZE / REVIEW",
    "A data room with a paper trail.",
    "Publish reconciled snapshots, inspect source documents, and control what reaches a review brief.",
  );
  const tabs = `<div class="tabs"><button class="${state.tab === "imports" ? "active" : ""}" data-tab="imports">Portfolio snapshots</button><button class="${state.tab === "documents" ? "active" : ""}" data-tab="documents">Documents & evidence</button></div>`;
  return (
    head +
    tabs +
    (state.tab === "imports" ? await importPage() : await documentsPage())
  );
}
async function importPage() {
  const data = await api("/imports");
  state.imports = data;
  return `<div class="split"><section class="panel"><h2>Bring in the next snapshot</h2><p class="small">One workbook with Assets, Leases, and Operating sheets, or a ZIP containing those three CSV files. Include all twelve reporting months and explicit zeros for empty accounts.</p><form id="importForm" class="form"><label>Reporting month end<input name="as_of" type="date" value="2025-09-30" required></label><label>Workbook or CSV bundle<input name="file" type="file" accept=".xlsx,.zip" required></label><button>Validate & stage</button></form><p class="definition">2 MB upload limit. Formula cells are rejected. Asset aliases must be explicit. Staging never changes the active portfolio.</p><div class="toolbar"><button class="secondary small" data-download="portfolio.xlsx">Example workbook ↓</button><button class="secondary small" data-download="portfolio-csv.zip">CSV bundle ↓</button><button class="secondary small" data-download="needs-review.xlsx">Error example ↓</button></div></section><section class="panel"><h2>Validation desk</h2>${state.staged ? validationHTML(state.staged) : `<div class="notice">Upload a workbook to see row-level checks. An independent reviewer publishes valid snapshots.</div><p class="small">Checks include required accounts, reporting dates, currency precision, lease identifiers, property mappings, and occupied area.</p>`}</section></div><section class="panel"><div class="section-head"><h2>Snapshot history</h2><span class="small muted">${data.imports.length} retained imports</span></div>${data.imports.map((r) => `<div class="history-row"><div><h3>${esc(r.as_of)} <span class="pill ${r.report.valid ? "" : "red"}">${r.id === data.current ? "ACTIVE" : r.report.valid ? r.status.toUpperCase() : "NEEDS CORRECTION"}</span></h3><span class="mono">${esc(r.id)} · ${esc(r.actor)} · ${stamp(r.created)}</span><p class="small">${r.report.counts.assets} assets · ${r.report.counts.leases} leases · ${r.report.counts.operating} statement rows</p></div><div class="toolbar"><button class="secondary small" data-inspect-import="${r.id}">Validation</button>${r.report.valid && r.id !== data.current ? `<button class="small" data-publish="${r.id}" ${state.session.role !== "reviewer" || r.actor === state.session.user ? "disabled" : ""}>${r.status === "published" ? "Restore snapshot" : "Publish snapshot"}</button>` : ""}</div></div>`).join("")}</section>`;
}
function validationHTML(row) {
  const r = row.report;
  return `<div class="notice ${r.valid ? "" : "error"}">${r.valid ? "All checks passed. Ready for independent review." : `${r.error_count} issue${r.error_count === 1 ? "" : "s"} require correction.`}</div><p class="small">${esc(r.normalization)}</p><div class="metric-row"><span>Assets / leases / statement rows</span><strong>${r.counts.assets} / ${r.counts.leases} / ${r.counts.operating}</strong></div>${r.errors.length ? `<ul class="error-list">${r.errors.map((e) => `<li><strong>${esc(e.sheet)}, row ${e.row}</strong><br>${esc(e.message)}</li>`).join("")}</ul>` : '<p class="definition">Switch to a reviewer identity to publish this snapshot. The person who staged it cannot approve it.</p>'}`;
}
async function documentsPage() {
  const docs = await api(`/assets/${state.documentAsset}/documents`);
  const hits = await api(
    `/assets/${state.documentAsset}/search?q=${encodeURIComponent(state.query)}`,
  );
  return `<div class="section-head"><label>Asset<select id="documentAsset">${assetOptions(state.documentAsset)}</select></label><span class="pill">${docs.length} AUTHORIZED DOCUMENTS</span></div><div class="split"><section class="panel"><h2>Search the source material</h2><form id="searchForm" class="inline-input"><label>Question or search terms<input name="query" value="${esc(state.query)}" maxlength="500" required></label><button>Search</button></form><div class="sources">${evidenceHTML(hits)}</div><p class="definition">Lexical BM25 retrieval scores rank relevance; they do not measure answer confidence. Only current, authorized document revisions are searched.</p></section><section class="panel"><h2>Document register</h2>${docs.map((d) => `<div class="source"><h3>${esc(d.title)}</h3><div class="toolbar"><span class="pill">V${d.version} · ${d.restricted ? "REVIEWER ONLY" : "TEAM ACCESS"}</span>${state.session.role === "reviewer" ? `<button class="danger small" data-revoke="${d.id}">Revoke access</button>` : ""}</div></div>`).join("")}<details><summary>Add or revise a document</summary>${state.session.role === "reviewer" ? `<form id="documentForm" class="form"><label>Document title<input name="title" minlength="3" maxlength="150" required placeholder="Use the same title to create a revision"></label><label>Text-bearing PDF, TXT, or Markdown<input name="file" type="file" accept=".pdf,.txt,.md" required></label><label class="check"><input name="restricted" type="checkbox">Reviewer-only evidence</label><button>Save document revision</button><small>New revisions retire the previous title. Revocation or revision invalidates affected briefs.</small></form>` : '<p class="small">Switch to Reviewer to curate documents.</p>'}</details></section></div>`;
}
async function briefsPage() {
  if (!state.portfolio) state.portfolio = await api("/portfolio");
  const history = await api("/briefs");
  let brief = null;
  if (state.brief) {
    brief = await api(`/briefs/${state.brief}`);
    state.openBrief = brief;
  }
  return (
    title(
      "CONTEXT / EVIDENCE / INDEPENDENT REVIEW",
      "Prepare the next conversation.",
      "Combine operating facts and source passages into a reviewable asset brief. Optional local AI drafts stay separate from verified figures.",
    ) +
    `<div class="split"><div><section class="panel"><form id="briefForm" class="form"><label>Asset<select name="asset">${assetOptions(state.briefAsset || "HAR")}</select></label><label>What should the review cover?<textarea name="question" maxlength="500" minlength="3" required>${esc(state.question || "What renewal notice and capital works need attention?")}</textarea></label><label class="check"><input name="live" type="checkbox" ${state.session.model ? "checked" : "disabled"}>Include a local AI draft ${state.session.model ? `(${esc(state.session.model)})` : "(configure a model to enable)"}</label><button>Build source-backed brief</button></form></section>${brief ? briefHTML(brief) : `<section class="panel">${empty("Build a brief or open an earlier review. Verified figures and passages work without an LLM.")}</section>`}</div><aside class="panel"><div class="eyebrow">REVIEW HISTORY</div><h2>Brief register</h2>${history.length ? history.map((b) => `<div class="history-row"><div><h3>${esc(b.asset)} <span class="pill ${b.status === "rejected" ? "red" : ""}">${esc(b.status.toUpperCase())}</span></h3><span class="small muted">${esc(b.actor)} · ${stamp(b.created)}</span></div><button class="secondary small" data-open-brief="${b.id}">Open</button></div>`).join("") : empty("No briefs yet.")}</aside></div>`
  );
}
function briefHTML(b) {
  if (b.stale)
    return '<section class="panel"><div class="notice warn">This brief’s sources changed. Its content is withheld to respect current access. Build a new brief before review or export.</div></section>';
  const data = b.body,
    m = data.metrics,
    n = data.narrative;
  return `<section class="panel"><div class="brief-title"><div><div class="eyebrow">OPERATING BRIEF / ${esc(m.as_of)}</div><h2>${esc(m.name)}</h2></div><span class="pill ${b.status === "rejected" ? "red" : ""}">${esc(b.status.toUpperCase())}</span></div><div class="metric-row"><span>Verified trailing NOI</span><strong>${money(m.noi_cents)}</strong></div><div class="metric-row"><span>Area occupancy / 12-month expiry share</span><strong>${pct(m.occupancy)} / ${pct(m.expiry_share)}</strong></div><div class="metric-row"><span>Reserve-adjusted DSCR</span><strong>${ratio(m.dscr)}</strong></div>${m.attention.map((a) => `<div class="insight">${esc(a)}</div>`).join("")}<div class="trace">${data.trace.map((t) => `<span>${esc(t.tool)} ✓</span>`).join("")}</div><details><summary>Inspect source lineage and tool trace</summary><pre>${esc(JSON.stringify({ lineage: data.lineage, trace: data.trace }, null, 2))}</pre></details><h3>Authorized source passages</h3>${evidenceHTML(data.evidence)}<div class="notice">Public context: ${esc(data.market.title)} — ${data.market.observation ? `${data.market.observation.value.toFixed(2)}% on ${esc(data.market.observation.date)}` : "No observation before this date"}. <a href="${esc(data.market.source_url)}" target="_blank" rel="noopener">FRED source ↗</a><br>${esc(data.market.note)}</div>${n.status === "draft" ? `<h3>AI narrative · unverified draft</h3><p class="brief-summary">${esc(n.response.summary)}</p>${n.response.observations.map((o) => `<p class="small">${esc(o.text)}</p><blockquote class="quote">“${esc(o.quote)}”<br><span class="mono">${esc(o.evidence_id)}</span></blockquote>`).join("")}<p class="definition">${esc(n.validation)} ${esc(n.model)} · ${(n.milliseconds / 1000).toFixed(1)}s · ${number(n.tokens.output)} output tokens</p>` : `<div class="notice ${n.status === "rejected" ? "warn" : ""}">${esc(n.reason)}</div>`}<div class="toolbar"><button class="secondary" data-export-brief="${b.id}">Export ${esc(b.status)} memo ↓</button><button class="secondary" data-action="brief-action">Create follow-up →</button></div>${b.status === "draft" ? `<details open><summary>Independent review</summary>${state.session.role === "reviewer" && b.actor !== state.session.user ? `<form id="reviewForm" class="form"><label>Review note<textarea name="note" minlength="5" maxlength="1000" required placeholder="Record source checks, corrections, or required follow-up"></textarea></label><div class="toolbar"><button name="decision" value="approved">Approve brief</button><button class="danger" name="decision" value="rejected">Return for revision</button></div></form>` : '<p class="small">A different user with the Reviewer role must check this brief.</p>'}</details>` : `<p class="definition">Reviewed by ${esc(b.reviewer)}. ${esc(b.review_note)}</p>`}<details><summary>Was this brief useful?</summary><form id="feedbackForm" class="form"><label>Assessment<select name="helpful"><option value="true">Useful for the review</option><option value="false">Needs improvement</option></select></label><label>Feedback<input name="comment" maxlength="500" placeholder="What would make this more useful?"></label><button class="secondary">Save feedback</button></form></details></section>`;
}
async function actionsPage() {
  if (!state.portfolio) state.portfolio = await api("/portfolio");
  const rows = await api("/actions");
  state.actions = rows;
  return (
    title(
      "OWNERSHIP / FOLLOW-UP",
      "Keep the work moving.",
      "Track the next concrete step. This register records review work; it cannot transact, contact tenants, or authorize spending.",
    ) +
    `<section class="panel"><form id="actionForm" class="form"><div class="equal"><label>Asset<select name="asset">${assetOptions(state.actionAsset || "HAR")}</select></label><label>Owner<input name="owner" required maxlength="100" placeholder="Asset management"></label></div><label>Follow-up<input name="title" minlength="5" maxlength="250" required placeholder="Confirm renewal notice receipt with counsel"></label><div><button>Create action</button></div></form></section><div class="section-head"><h2>Action register</h2><span class="small muted">${rows.filter((a) => a.status !== "closed").length} open or in progress</span></div><div class="action-grid">${rows.length ? rows.map((a) => `<section class="panel action-card"><div class="eyebrow">${esc(a.asset)} / ${esc(a.status.replace("_", " "))}</div><h3>${esc(a.title)}</h3><p class="small">Owner: ${esc(a.owner)}<br>Updated ${stamp(a.updated)} · version ${a.version}</p><div class="toolbar"><button class="secondary small" data-update-action="${a.id}" data-status="${a.status === "open" ? "in_progress" : a.status === "in_progress" ? "closed" : "open"}">${a.status === "open" ? "Start work" : a.status === "in_progress" ? "Mark complete" : "Reopen"}</button></div></section>`).join("") : empty("No follow-ups yet. Create an action above.")}</div>`
  );
}
async function activityPage() {
  const data = await api("/activity"),
    counts = data.brief_counts;
  return (
    title(
      "ADOPTION / GOVERNANCE",
      "A record of how the tool is used.",
      "Recorded activity and explicit user feedback. No simulated time savings or invented business impact.",
    ) +
    `<section class="stats">${stat("Briefs created", number(Object.values(counts).reduce((a, b) => a + b, 0)), "All statuses in this portfolio")}${stat("Approved briefs", number(counts.approved || 0), "Independent reviewer decisions")}${stat("Feedback received", number(data.feedback.n), "One response per user and brief")}${stat("Marked useful", number(data.feedback.helpful || 0), "User-reported assessment")}</section><section class="panel"><h2>Activity ledger</h2><p class="small">Tenant-scoped operational history. These records support review; the local database is not an immutable audit store.</p>${data.events.map((e) => `<div class="activity"><span>${stamp(e.at)}</span><strong>${esc(e.actor)}</strong><span><strong>${esc(e.kind)}</strong><br><span class="mono">${esc(JSON.stringify(e.details))}</span></span></div>`).join("")}</section>`
  );
}
async function run(button, fn) {
  const old = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "Working…";
  }
  try {
    await fn();
  } catch (e) {
    toast(e.message);
  } finally {
    if (button?.isConnected) {
      button.disabled = false;
      button.textContent = old;
    }
  }
}
document.addEventListener("click", (event) => {
  const b = event.target.closest("button");
  if (!b) return;
  if (b.dataset.page) {
    state.asset = null;
    navigate(b.dataset.page);
  }
  if (b.dataset.go) navigate(b.dataset.go);
  if (b.dataset.asset) {
    state.asset = b.dataset.asset;
    navigate("portfolio");
  }
  if (b.dataset.tab) {
    state.tab = b.dataset.tab;
    navigate("data");
  }
  if (b.dataset.download)
    run(b, () =>
      download(`/examples/${b.dataset.download}`, b.dataset.download),
    );
  if (b.dataset.inspectImport) {
    state.staged = state.imports.imports.find(
      (i) => i.id === b.dataset.inspectImport,
    );
    navigate("data");
  }
  if (b.dataset.publish)
    run(b, async () => {
      await post(`/imports/${b.dataset.publish}/publish`, {
        expected_current: state.imports.current,
      });
      state.portfolio = null;
      toast("Snapshot published. Previous versions remain in history.");
      await navigate("data");
    });
  if (b.dataset.revoke)
    run(b, async () => {
      await api(`/documents/${b.dataset.revoke}`, { method: "DELETE" });
      toast("Access revoked. Affected briefs now require rebuilding.");
      await navigate("data");
    });
  if (b.dataset.openBrief) {
    state.brief = b.dataset.openBrief;
    navigate("briefs");
  }
  if (b.dataset.exportBrief)
    run(b, () =>
      download(
        `/briefs/${b.dataset.exportBrief}/memo`,
        `brickline-${b.dataset.exportBrief}.md`,
      ),
    );
  if (b.dataset.updateAction)
    run(b, async () => {
      const row = state.actions.find((a) => a.id === b.dataset.updateAction);
      await api(`/actions/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          version: row.version,
          status: b.dataset.status,
          owner: row.owner,
        }),
      });
      await navigate("actions");
    });
  if (b.dataset.action === "back") {
    state.asset = null;
    navigate("portfolio");
  }
  if (b.dataset.action === "reload") navigate();
  if (b.dataset.action === "asset-brief") {
    state.briefAsset = state.asset;
    navigate("briefs");
  }
  if (b.dataset.action === "asset-docs") {
    state.documentAsset = state.asset;
    state.tab = "documents";
    navigate("data");
  }
  if (b.dataset.action === "brief-action") {
    state.actionAsset = state.openBrief.body.asset;
    navigate("actions");
  }
});
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  event.preventDefault();
  const button = event.submitter,
    f = new FormData(form);
  run(button, async () => {
    if (form.id === "importForm") {
      state.staged = await api("/imports", { method: "POST", body: f });
      await navigate("data");
    }
    if (form.id === "documentForm") {
      if (!f.has("restricted")) f.set("restricted", "false");
      else f.set("restricted", "true");
      await api(`/assets/${state.documentAsset}/documents`, {
        method: "POST",
        body: f,
      });
      toast("Document revision saved.");
      await navigate("data");
    }
    if (form.id === "searchForm") {
      state.query = f.get("query");
      await navigate("data");
    }
    if (form.id === "briefForm") {
      state.briefAsset = f.get("asset");
      state.question = f.get("question");
      const result = await post("/briefs", {
        asset: state.briefAsset,
        question: state.question,
        live: f.has("live"),
      });
      state.brief = result.id;
      await navigate("briefs");
    }
    if (form.id === "reviewForm") {
      await post(`/briefs/${state.brief}/review`, {
        version: state.openBrief.version,
        decision: button.value,
        note: f.get("note"),
      });
      toast("Review recorded.");
      await navigate("briefs");
    }
    if (form.id === "feedbackForm") {
      await post(`/briefs/${state.brief}/feedback`, {
        helpful: f.get("helpful") === "true",
        comment: f.get("comment"),
      });
      toast("Feedback saved.");
    }
    if (form.id === "actionForm") {
      await post("/actions", Object.fromEntries(f));
      toast("Action created.");
      await navigate("actions");
    }
    if (form.id === "scenarioForm") {
      const r = await post(`/assets/${state.asset}/scenario`, {
        income_change_pct: Number(f.get("income")),
        expense_change_pct: Number(f.get("expense")),
        cap_shift_bps: Number(f.get("cap")),
      });
      $("#scenarioResult").innerHTML =
        `<div class="metric-row"><span>Scenario NOI</span><strong>${money(r.noi_cents, true)}</strong></div><div class="metric-row"><span>Change from base</span><strong>${money(r.delta_noi_cents, true)}</strong></div><div class="metric-row"><span>Reserve-adjusted DSCR</span><strong>${ratio(r.dscr)}</strong></div><div class="metric-row"><span>Capitalized scenario NOI</span><strong>${money(r.capitalized_noi_cents, true)}</strong></div><details open><summary>Cap rate sensitivity</summary>${r.sensitivity.map((x) => `<div class="metric-row"><span>${pct(x.cap_rate)}</span><strong>${money(x.capitalized_noi_cents, true)}</strong></div>`).join("")}</details>`;
    }
  });
});
document.addEventListener("input", (event) => {
  const el = event.target;
  if (el.id === "assetFilter") {
    state.filter = el.value;
    $("#assetRows").innerHTML = assetRows();
  }
  for (const [id, label, unit] of [
    ["incomeChange", "incomeLabel", "%"],
    ["expenseChange", "expenseLabel", "%"],
    ["capChange", "capLabel", " bps"],
  ])
    if (el.id === id) $(`#${label}`).textContent = `${el.value}${unit}`;
});
document.addEventListener("change", (event) => {
  if (event.target.id === "sectorFilter") {
    state.sector = event.target.value;
    $("#assetRows").innerHTML = assetRows();
  }
  if (event.target.id === "documentAsset") {
    state.documentAsset = event.target.value;
    navigate("data");
  }
});
async function connectIdentity(key) {
  state.key = key;
  sessionStorage.setItem("brickline-key", key);
  state.serial++;
  state.portfolio = null;
  state.staged = null;
  state.asset = null;
  state.brief = null;
  $("#main").innerHTML = '<div class="loading">Connecting…</div>';
  try {
    state.session = await api("/session");
    $("#session").textContent =
      `${state.session.tenant} / ${state.session.user}`;
    $("#login").hidden = true;
    await navigate();
  } catch (error) {
    $("#main").innerHTML =
      `<div class="notice error">${esc(error.message)} Use Connect to enter a configured API key.</div>`;
  }
}
$("#identity").value = ["demo-analyst", "demo-reviewer", "demo-other"].includes(
  state.key,
)
  ? state.key
  : "custom";
$("#identity").addEventListener("change", (e) => {
  if (e.target.value === "custom") $("#login").hidden = false;
  else connectIdentity(e.target.value);
});
$("#keyButton").addEventListener("click", () => {
  $("#login").hidden = !$("#login").hidden;
});
$("#saveKey").addEventListener("click", () => {
  const key = $("#apiKey").value.trim();
  if (key) {
    $("#identity").value = "custom";
    $("#apiKey").value = "";
    connectIdentity(key);
  }
});
connectIdentity(state.key);
