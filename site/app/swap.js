// Standings tab: schedule swap. Row team R plays column team C's schedule: in each
// completed regular-season week R faces whoever C actually faced (if that was R itself,
// R faces C), and the result is decided by the real scores that week.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, teams, T, ranked, $, esc, f1, tipHtml } = A;
  const root = $("#swap");
  if (!root) return;

  const REG = L.regular_season_weeks || Infinity;
  const mgr = (t) => t.manager || t.abbrev || t.name;
  const taken = {};
  for (const t of teams) taken[mgr(t)] = (taken[mgr(t)] || 0) + 1;
  const short = (t) => (taken[mgr(t)] > 1 ? `${mgr(t)} ${t.abbrev || t.id}` : mgr(t));
  const bold = (t) => `<b>${esc(short(t))}</b>`;

  // Who played whom, and the real scores, for each completed regular-season week.
  const opp = {}, pts = {};
  for (const m of D.matchups || []) {
    if (m.week > REG || !m.games.length) continue;
    opp[m.week] = {}; pts[m.week] = {};
    for (const g of m.games) {
      opp[m.week][g.home] = g.away; opp[m.week][g.away] = g.home;
      pts[m.week][g.home] = g.home_score; pts[m.week][g.away] = g.away_score;
    }
  }
  const weeks = Object.keys(opp).map(Number).sort((x, y) => x - y);

  root.innerHTML = `<h2>Schedule swap</h2><p class="sub">Your record if you'd played someone else's schedule.</p>`;
  if (!weeks.length || ranked.length < 2) {
    root.insertAdjacentHTML("beforeend", '<div class="card empty">Nothing to swap until week 1 is done.</div>');
    return;
  }

  // Row team r playing column team c's schedule.
  function play(r, c) {
    const rows = [];
    for (const w of weeks) {
      let o = opp[w][c];
      if (o == null) continue;
      if (o === r) o = c; // c's opponent was r itself: r plays c instead
      const mine = pts[w][r], theirs = pts[w][o];
      if (mine == null || theirs == null) continue;
      rows.push({ week: w, opp: o, mine, theirs, res: mine > theirs ? "W" : mine < theirs ? "L" : "T" });
    }
    return rows;
  }
  const cells = {};
  for (const r of ranked) {
    cells[r.id] = {};
    for (const c of ranked) {
      const rows = play(r.id, c.id);
      cells[r.id][c.id] = { rows, w: rows.filter((x) => x.res === "W").length, l: rows.filter((x) => x.res === "L").length, t: rows.filter((x) => x.res === "T").length };
    }
  }
  const val = (x) => x.w + x.t / 2; // wins, with a tie as half
  const anyTie = ranked.some((r) => ranked.some((c) => cells[r.id][c.id].t > 0));
  const rec = (x) => `${x.w}-${x.l}${anyTie ? "-" + x.t : ""}`;
  const num = (x) => (Number.isInteger(x) ? String(x) : f1(x));
  const winsText = (d) => `${d > 0 ? "+" : "−"}${num(Math.abs(d))} win${Math.abs(d) === 1 ? "" : "s"}`;
  const diffOf = (r, c) => val(cells[r.id][c.id]) - val(cells[r.id][r.id]);
  let maxAbs = 1;
  for (const r of ranked) for (const c of ranked) maxAbs = Math.max(maxAbs, Math.abs(diffOf(r, c)));

  function tint(d) {
    if (Math.abs(d) < 1e-9) return "background:var(--surface-2)";
    return `background:color-mix(in srgb, var(${d > 0 ? "--pos-soft" : "--neg-soft"}) ${Math.round(30 + 70 * Math.min(1, Math.abs(d) / maxAbs))}%, var(--surface))`;
  }
  function tipFor(r, c) {
    const x = cells[r.id][c.id], real = cells[r.id][r.id];
    if (r.id === c.id) return tipHtml(`${short(r)}'s real schedule`, [["Record", rec(x)]]);
    const d = diffOf(r, c);
    return tipHtml(`${short(r)} with ${short(c)}'s schedule: ${rec(x)}`, [["Real record", rec(real)], ["Difference", Math.abs(d) < 1e-9 ? "same" : winsText(d)]]);
  }

  const n = ranked.length;
  const head = `<thead><tr><th class="sw-corner" rowspan="2" scope="col">Team</th><th class="sw-axis" colspan="${n}" scope="colgroup">Playing whose schedule →</th></tr>
    <tr>${ranked.map((c) => `<th class="sw-colh" scope="col" data-tip="${tipHtml(`${short(c)}'s schedule`, [["Team", c.name]])}">${esc(short(c))}</th>`).join("")}</tr></thead>`;
  const body = `<tbody>${ranked.map((r) => `<tr><th class="sw-rowh" scope="row" data-tip="${tipHtml(r.name, [["Manager", r.manager || "–"]])}">${esc(short(r))}</th>${ranked.map((c) => {
    const x = cells[r.id][c.id], d = diffOf(r, c), self = r.id === c.id;
    const label = self ? `${short(r)} real schedule: ${rec(x)}` : `${short(r)} with ${short(c)}'s schedule: ${rec(x)}, ${Math.abs(d) < 1e-9 ? "same as real" : d > 0 ? "better than real" : "worse than real"}`;
    return `<td><button type="button" class="sw-cell${self ? " self" : ""}" data-r="${r.id}" data-c="${c.id}" style="${tint(d)}" data-tip="${tipFor(r, c)}" aria-label="${esc(label)}">${rec(x)}</button></td>`;
  }).join("")}</tr>`).join("")}</tbody>`;
  root.insertAdjacentHTML("beforeend", `<div class="card tbl-wrap"><table class="sw-grid" id="swGrid">${head}${body}</table></div>
    <div class="card sw-detail" id="swDetail" hidden aria-live="polite"></div>
    <ul class="sw-calls" id="swCalls"></ul>
    <p class="note">Each cell is the row team's record against the column team's opponents, using the real scores from ${weeks.length === 1 ? "week " + weeks[0] : `weeks ${weeks[0]}–${weeks[weeks.length - 1]}`}. If the column team's opponent was the row team itself, it plays the column team instead. The outlined diagonal is the real record. Blue is better than reality, red is worse.</p>`);

  // A score pair to one decimal, or two when one decimal would show a W or L as a tie (123.61 vs 123.57).
  const score = (a, b) => (f1(a) === f1(b) && a !== b ? `${a.toFixed(2)}–${b.toFixed(2)}` : `${f1(a)}–${f1(b)}`);

  // "Share to the board" (account.js): one swapped schedule as a plain-text stat.
  const share = A.shareBtn || (() => "");
  function swapStat(r, c) {
    const x = cells[r.id][c.id], real = cells[r.id][r.id], d = diffOf(r, c);
    const text = Math.abs(d) < 1e-9
      ? `${short(r)} would be ${rec(x)} with ${short(c)}'s schedule too. Same as reality.`
      : `If ${short(r)} had ${short(c)}'s schedule, they'd be ${rec(x)}. Instead, they're ${rec(real)}.`;
    return {
      kind: "swap", title: "Schedule swap", text,
      facts: [[`With ${short(c)}'s schedule`.slice(0, 30), rec(x)], ["Real record", rec(real)], ["Difference", Math.abs(d) < 1e-9 ? "Same" : winsText(d)]],
      teams: [r.id, c.id], link: "#swap",
    };
  }

  // Tap or click a cell for the week-by-week behind it (hover tooltips don't exist on a phone).
  const detail = $("#swDetail");
  $("#swGrid").addEventListener("click", (e) => {
    const el = e.target.closest(".sw-cell");
    if (!el) return;
    const r = T[+el.dataset.r], c = T[+el.dataset.c], x = cells[r.id][c.id];
    document.querySelectorAll("#swGrid .sw-cell.sel").forEach((b) => b.classList.remove("sel"));
    el.classList.add("sel");
    const self = r.id === c.id, d = diffOf(r, c);
    detail.innerHTML = `<div class="sw-dh"><b>${self ? `${esc(short(r))}'s real schedule` : `${esc(short(r))} with ${esc(short(c))}'s schedule`}</b><span class="sw-dr">${rec(x)}</span></div>
      <div class="sw-dl">${x.rows.map((g) => `<div><span class="dim">Wk ${g.week}</span><span>vs ${esc(short(T[g.opp]))}</span><span class="${g.res === "W" ? "pos" : g.res === "L" ? "neg" : "dim"}">${g.res} ${score(g.mine, g.theirs)}</span></div>`).join("")}</div>
      ${self ? "" : `<div class="sw-df"><span>Real record ${rec(cells[r.id][r.id])}. ${Math.abs(d) < 1e-9 ? "No difference." : `${winsText(d)} ${d > 0 ? "better" : "worse"} than reality.`}</span>${share(swapStat(r, c))}</div>`}`;
    detail.hidden = false;
    detail.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  });

  // Callouts, all read straight off the grid. Two completed weeks minimum: after one
  // week every record is 1-0 or 0-1 and "luck" means nothing.
  if (weeks.length >= 2) {
    const rowStats = ranked.map((r) => {
      const real = val(cells[r.id][r.id]);
      const alts = ranked.filter((c) => c.id !== r.id).map((c) => ({ c, x: cells[r.id][c.id], v: val(cells[r.id][c.id]) }));
      const avg = alts.reduce((s, a) => s + a.v, 0) / alts.length;
      return { r, real, avg, luck: real - avg, alts, worse: alts.filter((a) => a.v < real).length, better: alts.filter((a) => a.v > real).length };
    });
    const out = [];
    const lucky = rowStats.reduce((m, s) => (s.luck > m.luck ? s : m));
    if (lucky.luck >= 0.25) {
      out.push(`<b>Luckiest team:</b> ${bold(lucky.r)} (${rec(cells[lucky.r.id][lucky.r.id])}). On the other ${lucky.alts.length} schedules they'd average ${f1(lucky.avg)} wins, and do worse on ${lucky.worse} of them.`);
    }
    const unlucky = rowStats.reduce((m, s) => (s.luck < m.luck ? s : m));
    if (unlucky.luck <= -0.25) {
      const best = unlucky.alts.reduce((m, a) => (a.v > m.v ? a : m));
      out.push(`<b>Unluckiest team:</b> ${bold(unlucky.r)} (${rec(cells[unlucky.r.id][unlucky.r.id])}). They'd average ${f1(unlucky.avg)} wins on the other schedules and do better on ${unlucky.better} of ${unlucky.alts.length}. Best case: ${rec(best.x)} with ${esc(short(best.c))}'s.`);
    }
    const cols = ranked.map((c) => {
      const others = ranked.filter((r) => r.id !== c.id).map((r) => val(cells[r.id][c.id]));
      return { c, avg: others.reduce((s, v) => s + v, 0) / others.length };
    });
    const soft = cols.reduce((m, s) => (s.avg > m.avg ? s : m)), tough = cols.reduce((m, s) => (s.avg < m.avg ? s : m));
    if (soft.avg - tough.avg >= 0.25) {
      out.push(`<b>Softest schedule:</b> ${bold(soft.c)}'s. Everyone else averages ${f1(soft.avg)} wins from it in ${weeks.length} games. <b>Toughest:</b> ${bold(tough.c)}'s, at ${f1(tough.avg)}.`);
    }
    $("#swCalls").innerHTML = out.map((h) => `<li>${h}</li>`).join("");
  }
})();
