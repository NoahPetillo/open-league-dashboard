// Trades tab: trade market bars and the trade ledger.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, MY_TEAM, teams, T, ranked, $, $$, esc, f1, sgn, cls, pct, fmtDate, chip, tipHtml, divergingBars, onRoute } = A;

  const tradedTeams = teams.filter((t) => t.trades > 0);
  divergingBars($("#netBars"),
    [...tradedTeams].sort((a, b) => b.trade_net - a.trade_net).map((t) => ({ t, v: t.trade_net })),
    sgn, (r) => tipHtml(r.t.name, [["Net lineup pts", sgn(r.v)], ["Trades", r.t.trades]]), { top: "gold" });
  if (!tradedTeams.length) $("#netBars").innerHTML = '<div class="empty">No trades yet.</div>';
  divergingBars($("#countBars"),
    [...teams].sort((a, b) => b.trades - a.trades || b.trade_net - a.trade_net).map((t) => ({ t, v: t.trades })),
    (v) => v, (r) => tipHtml(r.t.name, [["Trades", r.v], ["Net lineup pts", sgn(r.t.trade_net)]]), { top: "gold" });

  // ── trade ledger ────────────────────────────────────────
  const tf = $("#teamFilter");
  [...teams].sort((a, b) => a.name.localeCompare(b.name)).forEach((t) => tf.insertAdjacentHTML("beforeend", `<option value="${t.id}">${esc(t.name)} (${esc(t.manager)})</option>`));
  let tradeSort = "swing";
  const swing = (tr) => Math.max(...tr.sides.map((s) => Math.abs(s.net)));

  function weekBars(s) {
    if (!s.weekly.length) return "";
    const max = Math.max(10, ...s.weekly.map((w) => Math.abs(w.delta)));
    const bars = s.weekly.map((w) => {
      const h = (Math.abs(w.delta) / max) * 50;
      const t = tipHtml(`Week ${w.week}`, [["With trade", f1(w.with)], ["Without", f1(w.without)], ["Difference", sgn(w.delta)]]);
      return `<div class="wk" data-tip="${t}" aria-label="Week ${w.week}: ${sgn(w.delta)}"><span class="${w.delta >= 0 ? "p" : "m"}" style="height:${Math.max(h, Math.abs(w.delta) > 0.05 ? 3 : 0)}%"></span></div>`;
    }).join("");
    return `<div class="weeks">${bars}</div><div class="wk-lab">${s.weekly.map((w) => `<span>W${w.week}</span>`).join("")}</div>`;
  }
  // faab: FAAB dollars that moved to (Got) or from (Gave) this side in the deal.
  function plist(title, players, kind, faab, pending) {
    const cash = +faab > 0 ? `<li class="faab-li" title="FAAB dollars that changed hands in this deal"><span class="pn">$${+faab}<span class="pp">FAAB</span></span></li>` : "";
    if (!players.length && !cash) return "";
    return `<div class="h">${title}</div>` + players.map((p) => {
      const val = pending
        ? `<span class="pv dim" title="This trade happened after the last finished week">no games yet</span>`
        : kind === "got" && p.weeks_rostered === 0
        ? `<span class="pv dim" title="Traded away again before he played a game for this team">flipped before playing</span>`
        : kind === "got"
        ? `<span class="pv" title="Points while on this roster (points in the starting lineup)">${f1(p.points)} <span class="dim">(${f1(p.started_points)} started)</span></span>`
        : `<span class="pv" title="Points since the trade, wherever he played">${f1(p.points)}</span>`;
      return `<li><span class="pn">${esc(p.name)}<span class="pp">${esc(p.pos)}</span></span>${val}</li>`;
    }).join("") + cash;
  }
  function sideHtml(s, tr) {
    const t = T[s.team];
    const pend = tr.status !== "graded";
    const other = tr.sides.filter((o) => o !== s);
    const higher = tr.sides.length === 2 && s.net - other[0].net > 0.05;
    const best = !pend && higher && s.net > 0.05;
    const worst = !pend && s.net < -0.05;
    const flips = (s.flipped_into || []).length ? `<div class="note">Includes what they flipped these players into (trade ${s.flipped_into.map((i) => "#" + i).join(", ")}).</div>` : "";
    return `<div class="side">
      <div class="side-top"><div>${chip(t)}${best ? '<div><span class="badge win">Won the trade</span></div>' : worst ? '<div><span class="badge loss">Lost the trade</span></div>' : ""}</div>
      ${pend ? "" : `<div class="net ${cls(s.net)}">${sgn(s.net)}<small>lineup pts</small></div>`}</div>
      <ul class="plist">${plist("Got", s.received, "got", s.faab_received, pend)}${plist("Gave", s.sent, "gave", s.faab_sent, pend)}</ul>
      ${weekBars(s)}${flips}
    </div>`;
  }
  function drawTrades() {
    const team = +tf.value || null;
    let list = D.trades.filter((tr) => !team || tr.sides.some((s) => s.team === team));
    list.sort(tradeSort === "new" ? (a, b) => b.date - a.date : tradeSort === "old" ? (a, b) => a.date - b.date
      : (a, b) => (b.status === "graded") - (a.status === "graded") || swing(b) - swing(a));
    $("#tradeCount").textContent = `${list.length} trade${list.length === 1 ? "" : "s"}`;
    $("#tradeList").innerHTML = list.length ? list.map((tr) => {
      const sidesOrdered = team ? [...tr.sides].sort((a, b) => (b.team === team) - (a.team === team)) : tr.sides;
      return `<article class="card trade" id="trade-${tr.id}" tabindex="-1">
        <div class="trade-head"><span><b>Trade #${tr.id}</b> · ${fmtDate(tr.date)}</span><span>${tr.status === "graded" ? `Graded weeks ${tr.first_week}–${L.through_week}` : "Not graded yet"}</span></div>
        <div class="trade-sides">${sidesOrdered.map((s) => sideHtml(s, tr)).join("")}</div>
        ${tr.status === "graded" ? "" : `<div class="pending">Happened after week ${L.through_week} finished. It gets a grade once week ${L.through_week + 1} is done.</div>`}
      </article>`;
    }).join("") : '<div class="card empty">No trades for this team yet.</div>';
  }
  tf.addEventListener("change", drawTrades);

  // #trade/23 → open the Trades tab on that trade (showing all teams if the filter hides it).
  onRoute("trades", (params) => {
    const id = +params[0];
    if (!id || !D.trades.some((tr) => tr.id === id)) return false;
    if (!$("#trade-" + id)) { tf.value = ""; drawTrades(); }
    const el = $("#trade-" + id);
    el.scrollIntoView({ block: "start" });
    el.focus({ preventScroll: true });
    el.classList.remove("flash");
    void el.offsetWidth; // restart the highlight if it's the same trade again
    el.classList.add("flash");
    return true;
  });
  document.querySelectorAll("#ledger .seg button").forEach((b) => b.addEventListener("click", () => {
    tradeSort = b.dataset.sort;
    document.querySelectorAll("#ledger .seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    drawTrades();
  }));
  drawTrades();
})();
