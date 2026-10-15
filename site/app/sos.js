// Standings tab: schedule ahead. Each team's remaining opponents, colored by how many points
// per game those opponents have scored so far (not projections), toughest schedule on top.
// Everything comes from data the page already has: D.schedule, D.matchups and each team's weekly scores.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, teams, T, $, esc, f1, chip, tipHtml } = A;
  const root = $("#sos");
  if (!root) return;

  const REG = L.regular_season_weeks || Infinity;
  const done = L.through_week || 0;
  const ahead = (D.schedule || [])
    .filter((w) => w.week > done && w.week <= REG && Array.isArray(w.games) && w.games.length)
    .sort((a, b) => a.week - b.week);
  if (!done || !ahead.length) return; // nothing to rank yet, or the regular season is over

  // Opponent strength: points per game so far (mean of the team's completed weekly scores).
  const mean = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);
  const ppg = {};
  for (const t of teams) ppg[t.id] = mean((t.weekly || []).map((w) => w.score).filter((x) => x != null));
  const scored = teams.filter((t) => ppg[t.id] != null);
  if (scored.length < 2) return;
  const N = scored.length;
  const leagueAvg = mean(scored.map((t) => ppg[t.id]));

  // Rank 1 scores the most. The league splits into six equal tiers by rank; tier 5 is the toughest.
  const rank = {};
  for (const t of scored) rank[t.id] = 1 + scored.filter((o) => ppg[o.id] > ppg[t.id]).length;
  const tier = (id) => 5 - Math.floor(((rank[id] - 1) * 6) / N);

  // A cell shows the opponent's manager name (first name + abbreviation if two share one).
  const mgr = (t) => t.manager || t.abbrev || t.name;
  const taken = {};
  for (const t of teams) taken[mgr(t)] = (taken[mgr(t)] || 0) + 1;
  const short = (t) => (taken[mgr(t)] > 1 ? `${mgr(t)} ${t.abbrev || t.id}` : mgr(t));
  const rec = (t) => `${t.wins}-${t.losses}${t.ties ? "-" + t.ties : ""}`;

  // Who each team still plays (by week), and who it has already played.
  const to = {}, faced = {};
  for (const t of teams) { to[t.id] = {}; faced[t.id] = []; }
  for (const w of ahead) {
    for (const [a, b] of w.games) {
      if (!T[a] || !T[b]) continue;
      to[a][w.week] = b;
      to[b][w.week] = a;
    }
  }
  for (const m of D.matchups || []) {
    if (m.week > REG) continue;
    for (const g of m.games) {
      if (!T[g.home] || !T[g.away]) continue;
      faced[g.home].push(g.away);
      faced[g.away].push(g.home);
    }
  }

  const rows = teams.map((t) => {
    const opps = Object.values(to[t.id]);
    return {
      t,
      coming: mean(opps.map((o) => ppg[o]).filter((x) => x != null)),
      played: mean(faced[t.id].map((o) => ppg[o]).filter((x) => x != null)),
      n: opps.length,
    };
  }).filter((r) => r.n);
  if (!rows.length) return;
  rows.sort((a, b) => (b.coming ?? -1) - (a.coming ?? -1) || a.t.name.localeCompare(b.t.name));

  const weeks = ahead.map((w) => w.week);
  const num = (x) => (x == null ? "–" : f1(x));

  function cell(r, w) {
    const oid = to[r.t.id][w], o = T[oid];
    if (!o) return '<td class="c"><div class="sos-cell none">–</div></td>';
    if (ppg[oid] == null) return `<td class="c"><div class="sos-cell none">${esc(short(o))}</div></td>`;
    const tp = tipHtml(`Week ${w}: ${o.name}`, [
      ["Manager", o.manager || "–"],
      ["Points per game", f1(ppg[oid])],
      ["Rank", `#${rank[oid]} of ${N}`],
      ["Record", rec(o)],
    ]);
    return `<td class="c" data-tip="${tp}"><div class="sos-cell t${tier(oid)}"><span class="sos-nm">${esc(short(o))}</span><small>${f1(ppg[oid])}</small></div></td>`;
  }

  const head = `<tr><th class="sos-tm" scope="col">Team</th>${weeks.map((w) => `<th class="c" scope="col">Wk ${esc(w)}</th>`).join("")}
    <th class="n" scope="col" data-tip="${tipHtml("Opp PPG ahead", [["Average points per game of the opponents still to play", ""]])}">Opp PPG ahead</th>
    <th class="n" scope="col" data-tip="${tipHtml("Played so far", [["Average points per game of the opponents already played", ""]])}">Played so far</th></tr>`;
  const body = rows.map((r) => `<tr><th class="sos-tm" scope="row">${chip(r.t)}</th>${weeks.map((w) => cell(r, w)).join("")}<td class="n"><b>${num(r.coming)}</b></td><td class="n dim">${num(r.played)}</td></tr>`).join("");

  root.innerHTML = `<h2>Schedule ahead</h2>
    <p class="sub">Each team's remaining opponents, colored by how much they've been scoring (points per game so far, not projections): red scores the most, blue the least. Toughest schedule on top.</p>
    <div class="card sos-card">
      <div class="tbl-wrap"><table class="sos-tbl"><caption class="sr-only">Remaining opponents for every team, toughest schedule first</caption><thead>${head}</thead><tbody>${body}</tbody></table></div>
      <div class="sos-scale" aria-label="Color scale"><span>Easier: scores least</span>${[0, 1, 2, 3, 4, 5].map((i) => `<i class="t${i}"></i>`).join("")}<span>Tougher: scores most</span></div>
    </div>
    <p class="note">Colors split the league into sixths by points per game through week ${esc(done)}. Points per game are season averages; the league average is ${f1(leagueAvg)}. "Opp PPG ahead" averages the opponents still to come, "Played so far" the ones already faced.</p>`;
  root.hidden = false;
})();
