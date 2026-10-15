// Lineups tab: lineup efficiency, points left on the bench, weekly score heatmap.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, MY_TEAM, teams, T, ranked, $, $$, esc, f1, sgn, cls, pct, fmtDate, chip, tipHtml, divergingBars, onRoute } = A;

  const effRows = teams.filter((t) => t.efficiency != null).sort((a, b) => b.efficiency - a.efficiency);
  const effBest = effRows.length ? effRows[0].efficiency : null;  // the league's best lineup setter shimmers gold
  $("#effBars").innerHTML = effRows.map((t) => {
    const lo = 0.7, w = Math.max(0, (t.efficiency - lo) / (1 - lo)) * 100;
    const gold = t.efficiency === effBest;
    return `<div class="bar-row${gold ? " top-gold" : ""}" data-tip="${tipHtml(t.name, [["Efficiency", (t.efficiency * 100).toFixed(1) + "%"], ["Left on bench", f1(t.bench_left)]])}">${chip(t)}<div class="bar-track"><span class="zero" style="left:0"></span><span class="b s${gold ? " gold" : ""}" style="left:0;width:${w}%"></span></div><div class="v">${(t.efficiency * 100).toFixed(1)}%${gold ? '<span class="sr-only"> (league best)</span>' : ""}</div></div>`;
  }).join("") + '<p class="note">Axis starts at 70%.</p>';
  divergingBars($("#benchBars"),
    [...teams].sort((a, b) => b.bench_left - a.bench_left).map((t) => ({ t, v: t.bench_left })),
    f1, (r) => tipHtml(r.t.name, [["Left on bench", f1(r.v)], ["Per week", f1(r.v / Math.max(1, r.t.weekly.length))]]), { top: "laugh" });

  const weeks = D.matchups.map((m) => m.week);
  const all = teams.flatMap((t) => t.weekly.map((w) => w.score));
  const lo = Math.min(...all), hi = Math.max(...all);
  const step = (v) => Math.min(5, Math.floor(((v - lo) / Math.max(1, hi - lo)) * 6));
  const hiWk = {}, loWk = {};
  for (const w of weeks) {
    const s = teams.map((t) => t.weekly.find((x) => x.week === w)?.score).filter((x) => x != null);
    hiWk[w] = Math.max(...s); loWk[w] = Math.min(...s);
  }
  const opp = {};
  for (const m of D.matchups) for (const g of m.games) {
    opp[`${m.week}-${g.home}`] = { o: g.away, me: g.home_score, them: g.away_score };
    opp[`${m.week}-${g.away}`] = { o: g.home, me: g.away_score, them: g.home_score };
  }
  $("#heatTbl").innerHTML = `<thead><tr><th>Team</th>${weeks.map((w) => `<th class="n" style="text-align:center">Wk ${w}</th>`).join("")}<th class="n">Avg</th></tr></thead><tbody>${ranked.map((t) => `<tr><td>${chip(t)}</td>${weeks.map((w) => {
    const x = t.weekly.find((y) => y.week === w);
    if (!x) return '<td class="c dim">–</td>';
    const st = step(x.score);
    const g = opp[`${w}-${t.id}`];
    const res = g ? (g.me > g.them ? "W" : g.me < g.them ? "L" : "T") : "";
    const tp = tipHtml(`${t.name} · Week ${w}`, [["Score", f1(x.score)], ...(g ? [["vs " + T[g.o].name, `${res} ${f1(g.me)}–${f1(g.them)}`]] : []), ["Best possible", f1(x.optimal)]]);
    const mark = x.score === hiWk[w] ? " ▲" : x.score === loWk[w] ? " ▼" : "";
    return `<td class="c" data-tip="${tp}"><div style="background:var(--seq-${st});color:${st >= 3 ? "#fff" : "var(--ink)"}">${f1(x.score)}${mark}</div></td>`;
  }).join("")}<td class="n">${f1(t.weekly.reduce((a, b) => a + b.score, 0) / Math.max(1, t.weekly.length))}</td></tr>`).join("")}</tbody>`;
  $("#heatScale").innerHTML = `<span>${f1(lo)}</span>${[0, 1, 2, 3, 4, 5].map((i) => `<i style="background:var(--seq-${i})"></i>`).join("")}<span>${f1(hi)}</span>`;
})();
