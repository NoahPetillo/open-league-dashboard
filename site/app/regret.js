// Trades tab: trade regret meter. What each side's received players have scored since every
// graded trade, week by week and wherever they played (D.regret, from league/regret.py).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, T, teams, $, esc, f1, fmtDate, chip, tipHtml, lineChart } = A;
  const root = $("#regret");
  const R = D.regret;
  if (!root) return;
  const trades = ((R && R.trades) || []).filter((tr) => tr.sides.length > 1 && tr.sides.every((s) => T[s.team]));
  if (!trades.length) { root.hidden = true; return; }
  const byId = new Map(trades.map((tr) => [tr.id, tr]));

  const n1 = (x) => (x < -0.05 ? "−" : "") + f1(Math.abs(x));
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const pc = (x) => (x > 0 && x < 0.005 ? "<1%" : Math.round(x * 100) + "%");
  const gap = (x) => (x > 0 && x < 0.1 ? x.toFixed(2) : f1(x));
  const weeksOf = (tr) => (tr.weeks.length === 1 ? `Week ${tr.weeks[0]}` : `Weeks ${tr.weeks[0]}–${tr.weeks[tr.weeks.length - 1]}`);

  // A side's name: the manager's first name, with the team's abbreviation when two managers share one.
  const label = {};
  {
    const base = (t) => t.manager || t.abbrev || t.name || "?";
    const seen = {};
    teams.forEach((t) => (seen[base(t)] = (seen[base(t)] || 0) + 1));
    teams.forEach((t) => (label[t.id] = seen[base(t)] > 1 ? `${base(t)} (${t.abbrev || t.name})` : base(t)));
  }
  const names = (ids) => {
    const n = ids.map((id) => `<b>${esc(label[id])}</b>`);
    return n.length > 1 ? `${n.slice(0, -1).join(", ")} and ${n[n.length - 1]}` : n[0];
  };

  // ── "Share to the board" (account.js): one trade as a plain-text stat ──
  const share = A.shareBtn || (() => "");
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  function tradeStat(tr) {
    const byPts = [...tr.sides].sort((a, b) => b.total - a.total);
    const two = tr.sides.length === 2;
    const totals = two ? `${n1(byPts[0].total)} to ${n1(byPts[1].total)}` : byPts.map((s) => `${label[s.team]} ${n1(s.total)}`).join(", ");
    const top = byPts[0].total, tied = tr.sides.filter((s) => s.total === top);
    let text;
    if (tr.sides.every((s) => s.total === 0)) text = `Trade #${tr.id}: no points scored yet by either side since the trade.`;
    else if (tr.leader != null && T[tr.leader]) text = `Trade #${tr.id}: ${label[tr.leader]}'s side is up ${gap(tr.margin)}${tr.sides.length > 2 ? " on second place" : ""} (${totals}) since the trade.`;
    else if (tied.length === tr.sides.length) text = `Trade #${tr.id}: dead even (${totals}) since the trade.`;
    else text = `Trade #${tr.id}: ${tied.map((s) => label[s.team]).join(" and ")} are tied at the top (${totals}) since the trade.`;
    return {
      kind: "traderegret", title: "Trade regret meter", text: clip(text, 300),
      facts: [...byPts.slice(0, 4).map((s) => [clip(`${label[s.team]}'s side`, 30), `${n1(s.total)} pts`]), ["Traded", fmtDate(tr.date)]],
      teams: tr.sides.slice(0, 4).map((s) => s.team), link: `#regret-${tr.id}`,
    };
  }

  // ── one trade ───────────────────────────────────────────
  // Share of the combined points. A side below zero counts as nothing, so the bar can't go negative.
  function shares(tr) {
    const pos = tr.sides.map((s) => Math.max(s.total, 0));
    const sum = pos.reduce((a, b) => a + b, 0);
    return pos.map((v) => (sum > 0 ? v / sum : 0));
  }
  function verdict(tr) {
    const top = Math.max(...tr.sides.map((s) => s.total));
    const tied = tr.sides.filter((s) => s.total === top);
    if (tr.sides.every((s) => s.total === 0)) return "No points yet";
    if (tr.leader != null && T[tr.leader]) return `${names([tr.leader])}'s side is up <b>${gap(tr.margin)}</b>${tr.sides.length > 2 ? " on second place" : ""}`;
    return tied.length === tr.sides.length ? "Dead even" : `${names(tied.map((s) => s.team))} are tied at the top`;
  }
  // Side i's color class (s0 blue, s1 red, s2 gold ...): it matches the bar segment, chart line and table header.
  const sc = (i) => `s${i % 5}`;
  function cardHtml(tr) {
    const sh = shares(tr);
    const split = sh.some((x) => x > 0);
    const sides = tr.sides.map((s, i) => {
      const faab = +s.faab_received > 0 ? `<span class="rg-faab" title="FAAB dollars that came with the deal. They aren't in the points.">+ $${+s.faab_received} FAAB</span>` : "";
      return `<div class="rg-side ${sc(i)}"><div class="rg-who">${chip(T[s.team])}</div><div class="rg-pts"><b>${n1(s.total)}</b><small>pts${split ? ` · ${pc(sh[i])}` : ""}</small>${faab}</div></div>`;
    }).join("");
    const segs = tr.sides.map((s, i) => {
      const text = sh[i] >= 0.3 ? `${esc(label[s.team])} ${pc(sh[i])}` : sh[i] >= 0.1 ? pc(sh[i]) : "";
      const tip = tipHtml(label[s.team], [["Points since the trade", n1(s.total)], ["Share of the combined points", pc(sh[i])]]);
      return sh[i] > 0 ? `<span class="rg-seg ${sc(i)}${sh[i] < 0.03 ? " tiny" : ""}" style="flex-grow:${Math.round(sh[i] * 1000)}" data-tip="${tip}">${text ? `<span class="rg-pill">${text}</span>` : ""}</span>` : "";
    }).join("");
    const said = tr.sides.map((s, i) => `${label[s.team]} ${n1(s.total)} points (${pc(sh[i])})`).join(", ");
    const bar = segs ? `<div class="rg-bar" role="img" aria-label="Share of the combined points: ${esc(said)}">${segs}</div>`
      : '<div class="rg-bar" role="img" aria-label="No points yet"></div>';
    const changes = tr.lead_changes > 0 ? `<span class="dim"> · lead changed ${plural(tr.lead_changes, "time")}</span>` : "";
    return `<article class="card rg" id="regret-${tr.id}" data-id="${tr.id}">
      <div class="rg-head"><span><b>Trade #${tr.id}</b> · ${fmtDate(tr.date)}</span><span>${weeksOf(tr)}</span></div>
      <div class="rg-sides">${sides}</div>
      ${bar}
      <div class="rg-vrow"><p class="rg-verdict">${verdict(tr)}${changes}</p>${share(tradeStat(tr))}</div>
      <div class="rg-foot"><button type="button" class="rg-toggle" aria-expanded="false" aria-controls="rg-more-${tr.id}">Week by week</button><a class="rg-link" href="#trade/${tr.id}">See the grade ›</a></div>
      <div class="rg-more" id="rg-more-${tr.id}" hidden></div>
    </article>`;
  }

  // ── expanded: running totals chart + every player, week by week ──
  // A week that doesn't count for a player (his game kicked off before the trade) comes through as null.
  function tableHtml(tr) {
    const cols = tr.weeks.length + 2;
    const cell = (v) => (v == null ? '<td class="n dim" title="That game kicked off before the trade, so it doesn\'t count">–</td>' : `<td class="n">${n1(v)}</td>`);
    const body = tr.sides.map((s, i) => {
      const head = `<tr class="rg-sh ${sc(i)}"><td colspan="${cols}"><span class="rg-sticky"><i></i>${esc(T[s.team].name)} <span class="dim">· ${esc(label[s.team])} got</span></span></td></tr>`;
      if (!s.players.length) return `${head}<tr><td colspan="${cols}" class="dim">${+s.faab_received > 0 ? "No players, just FAAB." : "No players."}</td></tr>`;
      const rows = s.players.map((p) => `<tr><td class="rg-pl">${esc(p.name)}<span class="pp">${esc(p.pos)}</span></td>${p.weekly.map(cell).join("")}<td class="n"><b>${n1(p.total)}</b></td></tr>`).join("");
      const sum = `<tr class="rg-sum"><td>Side total</td>${s.weekly.map((v) => `<td class="n">${n1(v)}</td>`).join("")}<td class="n"><b>${n1(s.total)}</b></td></tr>`;
      return head + rows + sum;
    }).join("");
    return `<table class="rg-tbl"><caption class="sr-only">Points since trade ${tr.id}, by player and week</caption><thead><tr><th>Player</th>${tr.weeks.map((w) => `<th class="n">Wk ${w}</th>`).join("")}<th class="n">Total</th></tr></thead><tbody>${body}</tbody></table>`;
  }
  function moreHtml(tr) {
    const key = tr.sides.map((s, i) => `<span class="${sc(i)}"><i></i>${esc(label[s.team])}</span>`).join("");
    const dashes = tr.sides.some((s) => s.players.some((p) => p.weekly.some((v) => v == null)));
    return `${tr.weeks.length > 1 ? `<div class="rg-key">${key}</div><div class="rg-chart"></div>` : ""}
      <div class="card tbl-wrap">${tableHtml(tr)}</div>
      ${dashes ? '<p class="note">A dash means that game kicked off before the trade went through, so it doesn\'t count.</p>' : ""}
      ${tr.gaps ? `<p class="note">${esc(`ESPN had no points for ${plural(tr.gaps, "player-week")} on this trade. They count as 0.`)}</p>` : ""}`;
  }
  // Round the y axis out to whole, even steps: 0, 20, 40 ...
  function niceStep(raw) {
    const mag = 10 ** Math.floor(Math.log10(raw));
    const f = raw / mag;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * mag;
  }
  const COLORS = ["var(--pos)", "var(--neg)", "var(--gold)", "var(--ink-2)", "var(--muted)"];
  function drawChart(tr, el) {
    const vals = tr.sides.flatMap((s) => s.cumulative);
    const lo = Math.min(0, ...vals), hi = Math.max(4, ...vals);
    const step = niceStep((hi - lo) / 4);
    const yMin = Math.floor(lo / step) * step, yMax = Math.ceil(hi / step) * step;
    const ticks = [];
    for (let v = yMin; v <= yMax + step / 2; v += step) ticks.push(v);
    lineChart(el, {
      x: tr.weeks.map((w) => "Wk " + w),
      series: tr.sides.map((s, i) => ({ name: label[s.team], values: s.cumulative, color: COLORS[i % COLORS.length] })),
      yMin, yMax, yTicks: ticks, yFmt: (v) => String(Math.round(v)), height: 200,
      xFmt: (i) => `Through week ${tr.weeks[i]}`,
      tipRows: (i) => tr.sides.map((s) => [label[s.team], `${n1(s.cumulative[i])} (${s.weekly[i] < 0 ? "−" : "+"}${f1(Math.abs(s.weekly[i]))})`]),
      label: `Points since trade ${tr.id}, running total: ${tr.sides.map((s) => `${label[s.team]} ${n1(s.total)}`).join(", ")}`,
    });
  }
  // Only the expanded cards have a chart: it needs a visible element to measure.
  const open = new Set();
  function setOpen(card, on) {
    const tr = byId.get(+card.dataset.id);
    const more = $(".rg-more", card);
    $(".rg-toggle", card).setAttribute("aria-expanded", String(on));
    more.hidden = !on;
    if (on) {
      if (!more.dataset.ready) { more.innerHTML = moreHtml(tr); more.dataset.ready = "1"; }
      const chart = $(".rg-chart", more);
      if (chart) drawChart(tr, chart);
      open.add(tr.id);
    } else open.delete(tr.id);
  }

  // ── section ─────────────────────────────────────────────
  const pickable = [...new Map(trades.flatMap((tr) => tr.sides.map((s) => [s.team, T[s.team]]))).values()]
    .sort((a, b) => a.name.localeCompare(b.name));
  const note = [
    R.pending > 0 ? `${plural(R.pending, "more trade")} went through after week ${L.through_week} finished. ${R.pending === 1 ? "It shows" : "They show"} up here once week ${L.through_week + 1} is done.` : "",
    "Points are this league's exact ESPN scoring. A player who sat in free agency still counts, but ESPN gives no game time for him, so in the week a trade lands he counts only if every game that week kicked off after the trade.",
  ].filter(Boolean).map((s) => `<p class="note">${esc(s)}</p>`).join("");
  root.innerHTML = `<h2>Trade regret meter</h2>
    <p class="sub">Raw fantasy points each side's new players have scored since the trade, wherever they played, even after being flipped or cut. A game that kicked off before the trade went through doesn't count. The ledger below grades what each trade did to lineups; this is the who-got-more-points argument.</p>
    <div class="controls">
      <div class="seg" role="group" aria-label="Sort the regret meter">
        <button type="button" data-rsort="gap" aria-pressed="true">Biggest gap</button>
        <button type="button" data-rsort="new" aria-pressed="false">Newest</button>
      </div>
      <select id="regretTeam" aria-label="Filter the regret meter by team"><option value="">All teams</option>${pickable.map((t) => `<option value="${t.id}">${esc(t.name)} (${esc(t.manager)})</option>`).join("")}</select>
      <span class="count" id="regretCount"></span>
    </div>
    <div class="rg-list" id="regretList"></div>
    ${note}`;
  root.hidden = false;

  // Only the top few until asked, so the trade court below doesn't sit under a mile of cards. The
  // rest are rendered but hidden: a shared link to one of them (#regret-12) still finds its tab.
  const LIMIT = 3;
  const list = $("#regretList", root), count = $("#regretCount", root), pick = $("#regretTeam", root);
  let sort = "gap", showAll = false;
  function render() {
    const team = +pick.value || null;
    const rows = trades.filter((tr) => !team || tr.sides.some((s) => s.team === team));
    rows.sort(sort === "new" ? (a, b) => b.date - a.date || b.id - a.id : (a, b) => b.margin - a.margin || b.date - a.date || b.id - a.id);
    count.textContent = plural(rows.length, "trade");
    const more = rows.length > LIMIT
      ? `<button type="button" class="rg-more-btn" aria-expanded="${showAll}">${showAll ? `Show just the top ${LIMIT}` : `Show all ${rows.length} trades`}</button>` : "";
    list.innerHTML = rows.length
      ? rows.map((tr, i) => (i < LIMIT || showAll ? cardHtml(tr) : cardHtml(tr).replace("<article ", "<article hidden "))).join("") + more
      : '<div class="card empty">No trades for this team yet.</div>';
    list.querySelectorAll(".rg").forEach((card) => { if (open.has(+card.dataset.id) && !card.hidden) setOpen(card, true); });
  }
  // A link straight to a trade that's tucked away: show them all, then go to it.
  function reveal() {
    const m = /^#regret-(\d+)$/.exec(location.hash);
    const card = m && $(`#regret-${m[1]}`, list);
    if (!card || !card.hidden) return;
    showAll = true;
    render();
    requestAnimationFrame(() => { const el = $(`#regret-${m[1]}`, list); if (el) el.scrollIntoView(); });
  }
  addEventListener("hashchange", reveal);
  list.addEventListener("click", (e) => {
    if (e.target.closest(".rg-more-btn")) {
      showAll = !showAll;
      render();
      if (!showAll) root.scrollIntoView({ block: "start" }); // collapsing: don't leave them stranded at the court
      return;
    }
    const b = e.target.closest(".rg-toggle");
    if (b) setOpen(b.closest(".rg"), b.getAttribute("aria-expanded") !== "true");
  });
  pick.addEventListener("change", render);
  root.querySelectorAll("[data-rsort]").forEach((b) => b.addEventListener("click", () => {
    sort = b.dataset.rsort;
    root.querySelectorAll("[data-rsort]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    render();
  }));
  render();
  reveal();
})();
