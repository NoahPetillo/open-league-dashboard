// Lineups tab: "If they could set a lineup". Each team's record if it had set its best lineup
// every week (the opponent keeps the real score), and the games that would have flipped.
// Data: D.whatif (league/whatif.py). Records, bench points and the table count the regular season
// only, like the standings; flipped games in playoff weeks are listed but flagged.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, $, esc, f1, chip, tipHtml } = A;
  const root = $("#whatif");
  const W = D.whatif;
  if (!root || !W || !Array.isArray(W.teams) || !Array.isArray(W.weeks)) return;

  // ── small helpers ───────────────────────────────────────
  const rec = (w, l, t) => `${w}-${l}${t ? "-" + t : ""}`;
  const who = (t) => t.manager || t.name;
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
  // Scores to one decimal, or two when two of them would read the same that way (a close game).
  const places = (nums) => (nums.some((a, i) => nums.some((b, j) => j > i && a !== b && f1(a) === f1(b))) ? 2 : 1);
  // "Share to the board" buttons (account.js); no button where accounts aren't loaded.
  const share = A.shareBtn || (() => "");
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

  const rows = W.teams.filter((r) => T[r.team]).map((r) => {
    const flips = (r.flips || []).filter((f) => T[f.opp]);
    return {
      ...r, flips, t: T[r.team],
      actual: rec(r.wins, r.losses, r.ties), best: rec(r.best_wins, r.best_losses, r.best_ties),
      given: flips.filter((f) => !f.playoff).length,   // games given away: the ones the record counts
      better: r.best_wins > r.wins || (r.best_wins === r.wins && r.best_losses < r.losses),
    };
  });
  if (!rows.length) return;
  const byGiven = (a, b) => b.given - a.given || b.points_left - a.points_left;
  const sorted = [...rows].sort(byGiven);
  const worst = sorted[0].given > 0 ? sorted[0] : null;

  // ── headline ────────────────────────────────────────────
  // The shareable version of a team's record with perfect lineups (the headline, and the manager page).
  const recStat = (r) => ({
    kind: "whatif", title: "If they could set a lineup",
    text: `${who(r.t)} would be ${r.best} if they could set a lineup. Right now it's ${r.actual}.`,
    facts: [["Actual record", r.actual], ["With best lineups", r.best], ["Games given away", String(r.given)], ["Left on bench", f1(r.points_left)]],
    teams: [r.team], link: "#whatif",
  });
  const headline = worst
    ? `<p class="wi-hl"><b>${esc(who(worst.t))}</b> would be <b>${esc(worst.best)}</b> if they could set a lineup. Right now it's ${esc(worst.actual)}.${share(recStat(worst))}</p>`
    : "";

  // ── table ───────────────────────────────────────────────
  const body = sorted.map((r) => {
    const tip = tipHtml(r.t.name, [["Actual record", r.actual], ["With best lineups", r.best],
      ["Games given away", r.given], ["Left on the bench", f1(r.points_left)]]);
    return `<tr class="${r.given ? "wi-hit" : ""}" data-tip="${tip}"><td>${chip(r.t)}</td>
      <td class="n">${esc(r.actual)}</td>
      <td class="n${r.better ? " pos" : ""}">${esc(r.best)}</td>
      <td class="n">${r.given ? `<span class="wi-pill">${r.given}</span>` : '<span class="dim">–</span>'}</td>
      <td class="n">${f1(r.points_left)}</td></tr>`;
  }).join("");

  // ── flipped games ───────────────────────────────────────
  // "Should have started A (28.4), B (19.0) over C (3.1), D (4.0) +1 more": two names each side.
  // The starters who cost the most (fewest points) come first; the pickups who'd have scored most.
  const names = (list, n = 2) => {
    const shown = list.slice(0, n).map((p) => `<b>${esc(p.name)}</b> <span class="dim">(${f1(p.points)})</span>`);
    const more = list.length - n;
    return shown.join(", ") + (more > 0 ? ` <span class="dim">+${more} more</span>` : "");
  };
  function swapLine(f) {
    const ins = f.swap_in || [], outs = [...(f.swap_out || [])].sort((a, b) => a.points - b.points);
    const empty = ins.length - outs.length; // more in the best lineup than were started: spots left empty
    const gap = empty > 0 ? ` ${empty === 1 ? "A lineup spot" : `${empty} lineup spots`} sat empty.` : "";
    if (ins.length && outs.length) return `Should have started ${names(ins)} over ${names(outs)}.${gap}`;
    if (ins.length) return `Should have started ${names(ins)}.${gap}`;
    return outs.length ? `Should have sat ${names(outs)}.` : "";
  }
  const flipsOf = (r) => r.flips.map((f) => ({ ...f, team: r.team }));
  const allFlips = rows.flatMap(flipsOf)
    .sort((a, b) => b.week - a.week || (b.best - b.score) - (a.best - a.score) || a.team - b.team);
  const tag = (f) => (f.playoff ? ' <span class="wi-tag" title="After the regular season, so not in the records above">Playoff week</span>' : "");

  // A game lost to lineup calls, as a shareable stat (f needs .team).
  function flipStat(f) {
    const dp = places([f.score, f.opp_score, f.best]), n = (x) => x.toFixed(dp);
    const ins = f.swap_in || [];
    const facts = [["Best lineup", n(f.best)], ["Left on bench", n(f.best - f.score)]];
    if (ins.length) facts.push(["Should have started", clip(ins.slice(0, 2).map((p) => p.name).join(", ") + (ins.length > 2 ? ` +${ins.length - 2}` : ""), 40)]);
    return {
      kind: "whatif", title: "Lost to a lineup call",
      text: `${who(T[f.team])} lost ${n(f.score)}–${n(f.opp_score)} to ${who(T[f.opp])} in week ${f.week}${f.playoff ? " (playoffs)" : ""}. The best lineup scored ${n(f.best)}.`,
      facts, teams: [f.team, f.opp], link: "#whatif",
    };
  }
  function flipCard(f) {
    const dp = places([f.score, f.opp_score, f.best]), n = (x) => x.toFixed(dp);
    const swap = swapLine(f);
    return `<li class="card wi-flip"><div class="wi-line"><span class="wi-wk">Week ${esc(f.week)}${tag(f)}</span>
      ${chip(T[f.team])}<span class="wi-lost">lost <b>${n(f.score)}–${n(f.opp_score)}</b> to</span>${chip(T[f.opp])}</div>
      <div class="wi-best-row"><p class="wi-best">Best lineup: <b>${n(f.best)}</b> <span class="dim">· ${n(f.best - f.score)} left on the bench</span></p>${share(flipStat(f))}</div>
      ${swap ? `<p class="wi-swap">${swap}</p>` : ""}</li>`;
  }
  const flipList = allFlips.length
    ? `<h3 class="wi-h3">Games lost to lineup calls</h3>
      <ul class="wi-list">${allFlips.map(flipCard).join("")}</ul>`
    : `<h3 class="wi-h3">Games lost to lineup calls</h3>
      <div class="card empty">Nobody's lineup calls have cost them a game yet.</div>`;

  const games = W.weeks.flatMap((w) => w.games || []);
  const flipped = games.filter((g) => g.flipped != null).length;
  const afterReg = games.some((g) => g.playoff) ? " Weeks after the regular season are listed below but don't count toward the records or bench points." : "";
  const th = (long, short, title) => `<th class="n" title="${esc(title)}"><span class="lg">${long}</span><span class="sm">${short}</span></th>`;

  root.innerHTML = `<h2>If they could set a lineup</h2>
    <p class="sub">Each team's record with the best possible lineup every week. The best lineup is the highest-scoring legal one from that week's roster, in hindsight, using ESPN's lineup slots. The opponent keeps their actual score. Players picked up after their game kicked off don't count.</p>
    ${headline}
    <div class="card tbl-wrap"><table class="wi-tbl">
      <thead><tr><th>Team</th>${th("Record", "Now", "Actual record")}${th("With best lineups", "Best", "Record with the best lineup every week, every opponent keeping their real score")}${th("Games given away", "Given", "Losses the best lineup would have won")}${th("Left on bench", "Bench", "Points between what was scored and the best lineup, over the season")}</tr></thead>
      <tbody>${body}</tbody>
    </table></div>
    <p class="note wi-key">Best: record with the best lineup every week. Given: losses the best lineup would have won. Bench: points left on the bench.</p>
    <p class="note">${flipped ? `${flipped} of ${plural(games.length, "game")} would have gone the other way with the loser's best lineup.` : `None of the ${plural(games.length, "game")} would have gone the other way.`} Sorted by games given away, then points left on the bench.${afterReg}</p>
    ${flipList}`;
  root.hidden = false;

  // ── a block on every manager's page (A.managerBlocks, see core.js) ──
  const byTeam = Object.fromEntries(rows.map((r) => [r.team, r]));
  A.managerBlocks.push({
    order: 20, place: "bottom",
    render(t) {
      const r = byTeam[t.id];
      if (!r) return "";
      const items = [...r.flips].sort((a, b) => b.week - a.week).map((f) => {
        const dp = places([f.score, f.opp_score, f.best]), n = (x) => x.toFixed(dp);
        const swap = swapLine(f);
        return `<li class="wi-mg-flip"><span class="wi-mg-wk">Wk ${esc(f.week)}</span><span class="wi-mg-opp">${chip(T[f.opp])}</span>
          <span class="wi-mg-sc"><b class="neg">${n(f.score)}</b> vs ${n(f.opp_score)}<small>best ${n(f.best)}${f.playoff ? " · playoff week" : ""}</small></span>
          ${swap ? `<span class="wi-mg-swap">${swap}</span>` : ""}${share(flipStat({ ...f, team: t.id }))}</li>`;
      }).join("");
      const meta = `${plural(r.given, "game")} given away · ${f1(r.points_left)} points left on the bench`;
      return `<div class="card mg-blk"><h3>With perfect lineups</h3>
        <p class="cap">The best lineup from the roster each week, in hindsight. Every opponent keeps their real score.</p>
        <p class="wi-mg-rec">${r.given ? share(recStat(r)) : ""}${esc(r.best)} <small>(actual ${esc(r.actual)})</small></p>
        <p class="wi-mg-meta">${meta}</p>
        ${items ? `<ul class="wi-mg-list">${items}</ul>` : '<div class="empty">Never lost a game to their own lineup calls.</div>'}
      </div>`;
    },
  });
})();
