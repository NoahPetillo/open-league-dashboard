// Home tab: headline tiles and the most-traded players podium.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, MY_TEAM, teams, T, ranked, $, $$, esc, f1, sgn, cls, pct, fmtDate, chip, tipHtml, divergingBars, onRoute } = A;

  const graded = D.trades.filter((t) => t.status === "graded");
  const sides = graded.flatMap((tr) => tr.sides.map((s) => ({ ...s, trade: tr })));

  // ── tiles ───────────────────────────────────────────────
  const by = (arr, k, dir = -1) => [...arr].sort((a, b) => dir * (a[k] - b[k]))[0];
  const mostTrades = by(teams, "trades");
  const bestSide = by(sides, "net");
  const worstSide = by(sides, "net", 1);
  const bestMarket = by(teams, "trade_net");
  const benchKing = by(teams, "bench_left");
  const luckiest = by(teams, "luck");
  const pl = (s) => s.received.map((p) => p.name).slice(0, 2).join(", ") + (s.received.length > 2 ? "…" : "");
  const tiles = [
    { label: "Trades this season", value: D.trades.length, who: `Across ${new Set(D.trades.flatMap((t) => t.sides.map((s) => s.team))).size} of ${teams.length} teams` },
    mostTrades && { label: "Most trades", value: mostTrades.trades, who: `<b>${esc(mostTrades.name)}</b> · ${esc(mostTrades.manager)}` },
    bestMarket && { label: "Best trader overall", value: sgn(bestMarket.trade_net), who: `<b>${esc(bestMarket.name)}</b> · lineup pts from trades` },
    bestSide && { label: "Best single trade", value: sgn(bestSide.net), who: `<b>${esc(T[bestSide.team].name)}</b> got ${esc(pl(bestSide))}` },
    worstSide && worstSide.net < 0 && { label: "Worst single trade", value: sgn(worstSide.net), who: `<b>${esc(T[worstSide.team].name)}</b> got ${esc(pl(worstSide))}` },
    benchKing && { label: "Most points benched", value: f1(benchKing.bench_left), who: `<b>${esc(benchKing.name)}</b> · ${esc(benchKing.manager)}` },
    luckiest && { label: "Luckiest team", value: sgn(luckiest.luck) + " W", who: `<b>${esc(luckiest.name)}</b> · ${luckiest.wins}-${luckiest.losses}, all-play ${luckiest.allplay_w}-${luckiest.allplay_l}` },
  ].filter(Boolean);
  $("#tiles").innerHTML = tiles.map((t) => `<div class="card tile"><div class="label">${t.label}</div><div class="value num">${t.value}</div><div class="who">${t.who}</div></div>`).join("");

  // ── most-traded players (R-rated mode, Settings tab, gives it its old name) ──
  function drawTraded() {
    const M = D.most_traded || [];
    if (M.length < 1) return;
    const R = A.rRated();
    $("#traded h2").textContent = R ? "Biggest league slut" : "Most traded players";
    $("#traded").hidden = false;
    const top = M.slice(0, 3);
    const headshot = A.headshot;
    const ini = (p) => esc(p.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join(""));
    const crown = `<svg class="crown" viewBox="0 0 40 28" aria-hidden="true"><path fill="currentColor" d="M3 8l9 7 8-13 8 13 9-7-3 18H6z"/><circle cx="3" cy="7" r="3" fill="currentColor"/><circle cx="20" cy="3" r="3" fill="currentColor"/><circle cx="37" cy="7" r="3" fill="currentColor"/></svg>`;
    const meta = (p) => [p.pos, p.pro_team].filter((x) => x && x !== "?").join(" · ");
    const mgr = (id) => (T[id] ? T[id].manager || T[id].name : "?");
    const trades = (n) => `${n} trade${n === 1 ? "" : "s"}`;

    $("#podium").innerHTML = top.map((p, i) => {
      const src = headshot(p);
      const img = src ? `<img src="${esc(src)}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=&quot;ph&quot;>${ini(p)}</span>'">` : `<span class="ph">${ini(p)}</span>`;
      return `<div class="pod r${i + 1}">
        ${i === 0 ? crown : ""}
        <div class="head">${img}</div>
        <div class="pname">${esc(p.name)}</div>
        <div class="pmeta">${esc(meta(p))}</div>
        ${i === 0 ? `<span class="tag">${R ? "League Slutt" : "Most traded"}</span>` : ""}
        <div class="plinth"><div class="rk">${i + 1}</div><div class="ct">${trades(p.trades)}</div></div>
      </div>`;
    }).join("");

    $("#tradedCards").innerHTML = top.map((p, i) => {
      const path = p.path.map((id) => `<b data-tip="${tipHtml(T[id] ? T[id].name : "?", [["Manager", mgr(id)]])}">${esc(mgr(id))}</b>`).join('<span class="arr">→</span>');
      return `<div class="card traded-card">
        <div class="hd"><span class="medal">#${i + 1}</span>${esc(p.name)}</div>
        <dl>
          <dt>Trades</dt><dd>${p.trades}</dd>
          <dt>Fantasy teams</dt><dd>${p.teams}</dd>
          <dt>Season points</dt><dd>${f1(p.season_points)} <span class="dim">(${f1(p.avg)}/gm)</span></dd>
          <dt>Last traded</dt><dd>${fmtDate(p.last_date)}</dd>
          <dt>Now with</dt><dd>${T[p.owner] ? esc(T[p.owner].name) : "?"}</dd>
        </dl>
        <div class="path">${path}</div>
      </div>`;
    }).join("");

    const n = top[0].trades;
    const tied = M.filter((p) => p.trades === n).length;
    const rest = M.slice(3, 8);
    $("#tradedSub").textContent = `The players who've been passed around the most this season. Ranked by trades, then by how many fantasy teams have had them, then season points.` +
      (tied > 1 ? ` ${tied} players are tied at ${trades(n)}${tied > 3 ? ", so the tiebreakers decide the podium" : ""}.` : "");
    $("#tradedAlso").innerHTML = rest.length ? `${R ? "Also getting around" : "Also on the move"}: ${rest.map((p) => `<b>${esc(p.name)}</b> (${p.trades})`).join(", ")}` : "";
  }
  drawTraded();
  document.addEventListener("open:rated", drawTraded);
})();
