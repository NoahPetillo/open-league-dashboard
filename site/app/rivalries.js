// Rivalries tab: head-to-head grid, a rivalry card for any pair of teams, and a few
// rivalries to watch. Real games come from D.matchups (this season) plus D.history
// (past seasons, once ESPN has any); "every week" uses this season's weekly scores.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, teams, T, ranked, $, $$, esc, f1, pct, chip, tipHtml, onRoute } = A;
  const root = $("#rivalries");
  if (!root) return;

  const SD_FLOOR = 24; // a team's weekly swing is never treated as less than this (same as league/punishment.py)
  const REG = L.regular_season_weeks || Infinity;
  const through = L.through_week || 0;
  const hist = D.history && D.history.games && D.history.games.length ? D.history : null;
  const scope = hist ? "all-time" : "this season";

  // ── names ───────────────────────────────────────────────
  const mgr = (t) => t.manager || t.abbrev || t.name;
  const taken = {};
  for (const t of teams) taken[mgr(t)] = (taken[mgr(t)] || 0) + 1;
  const short = (t) => (taken[mgr(t)] > 1 ? `${mgr(t)} ${t.abbrev || t.id}` : mgr(t));
  const bold = (t) => `<b>${esc(short(t))}</b>`;
  const ord = (k) => { const s = ["th", "st", "nd", "rd"], v = k % 100; return k + (s[(v - 20) % 10] || s[v] || s[0]); };

  // ── records ─────────────────────────────────────────────
  const recStr = (r) => `${r.w}-${r.l}${r.t ? "-" + r.t : ""}`;
  const flip = (r) => ({ w: r.l, l: r.w, t: r.t });
  const games = (r) => r.w + r.l + r.t;
  const share = (r) => (games(r) ? (r.w + r.t / 2) / games(r) : null);
  const mf = (x) => (x < 1 ? (Math.round(x * 100) / 100).toFixed(2) : f1(x)); // margins under a point keep 2 decimals
  const leadOf = (sh) => (sh == null || Math.abs(sh - 0.5) < 1e-9 ? null : sh > 0.5 ? "a" : "b");

  // Every game two teams have played, this season and (when present) past seasons.
  const all = [];
  for (const m of D.matchups || []) {
    for (const g of m.games) all.push({ season: L.season, week: m.week, a: g.home, b: g.away, as: g.home_score, bs: g.away_score, playoff: m.week > REG });
  }
  if (hist) {
    const team = {};
    for (const m of hist.managers || []) if (m.team != null && T[m.team]) team[m.key] = m.team;
    for (const g of hist.games) {
      if (g.season === L.season) continue;
      const a = team[g.a], b = team[g.b];
      if (a == null || b == null || a === b) continue; // someone who's no longer in the league
      all.push({ season: g.season, week: g.week, a, b, as: g.a_score, bs: g.b_score, playoff: !!g.playoff });
    }
  }
  all.sort((x, y) => x.season - y.season || x.week - y.week);
  const pk = (a, b) => (a < b ? a + "-" + b : b + "-" + a);
  const byPair = {};
  for (const g of all) (byPair[pk(g.a, g.b)] = byPair[pk(g.a, g.b)] || []).push(g);
  // Meetings from a's point of view (a = first team).
  const meetings = (a, b) => (byPair[pk(a, b)] || []).map((g) => (g.a === a ? g : { ...g, a: g.b, b: g.a, as: g.bs, bs: g.as }));
  function recOf(ms) {
    const r = { w: 0, l: 0, t: 0 };
    for (const g of ms) { if (g.as > g.bs) r.w++; else if (g.as < g.bs) r.l++; else r.t++; }
    return r;
  }
  const realRec = (a, b) => recOf(meetings(a, b));

  // This season's weekly scores → "every week" record and scoring averages.
  const score = {};
  for (const t of teams) { score[t.id] = {}; for (const w of t.weekly || []) score[t.id][w.week] = w.score; }
  const doneWeeks = [...new Set((D.matchups || []).map((m) => m.week))].filter((w) => w <= REG).sort((x, y) => x - y);
  function everyRec(a, b) {
    const r = { w: 0, l: 0, t: 0 };
    for (const k of doneWeeks) {
      const x = score[a][k], y = score[b][k];
      if (x == null || y == null) continue;
      if (x > y) r.w++; else if (x < y) r.l++; else r.t++;
    }
    return r;
  }
  const scoresOf = (id) => Object.values(score[id]);
  const mean = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;
  function sd(xs) {
    if (xs.length < 2) return null;
    const m = mean(xs);
    return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / (xs.length - 1));
  }
  function erf(x) { // Abramowitz & Stegun 7.1.26
    const s = Math.sign(x), v = Math.abs(x), t = 1 / (1 + 0.3275911 * v);
    const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-v * v);
    return s * y;
  }
  // P(a outscores b in a future week): normal approximation on this season's scores.
  // Needs two completed weeks from each side, otherwise there's nothing to go on.
  function winProb(a, b) {
    const xa = scoresOf(a), xb = scoresOf(b);
    if (xa.length < 2 || xb.length < 2) return null;
    const spread = Math.hypot(Math.max(SD_FLOOR, sd(xa)), Math.max(SD_FLOOR, sd(xb)));
    return 0.5 * (1 + erf((mean(xa) - mean(xb)) / spread / Math.SQRT2));
  }

  // Upcoming regular-season games, from the schedule.
  const upcoming = [];
  for (const s of D.schedule || []) if (s.week > through) for (const g of s.games) upcoming.push({ week: s.week, a: g[0], b: g[1] });
  const nextWeek = upcoming.length ? Math.min(...upcoming.map((g) => g.week)) : null;
  const meetAgain = (a, b) => upcoming.filter((g) => pk(g.a, g.b) === pk(a, b)).map((g) => g.week);

  // ── page shell ──────────────────────────────────────────
  root.innerHTML = `
    <h2>Head-to-head</h2>
    <p class="sub">Every team against every other, ${hist ? "all-time" : "this season"}. Real games are the matchups that actually happened. Every week asks who outscored whom in each completed week, as if they'd played each other all year${hist ? " (this season only)" : ""}.</p>
    <div class="card rv-watch" id="rvWatch" hidden><h3>Rivalries to watch</h3><ul id="rvWatchList"></ul></div>
    <div class="rv-bar"><h3>The grid</h3>
      <div class="seg" role="group" aria-label="What the grid shows">
        <button type="button" data-mode="real" aria-pressed="true">Real games</button>
        <button type="button" data-mode="every" aria-pressed="false">Every week</button>
      </div>
    </div>
    <div class="card tbl-wrap"><table class="rv-grid" id="rvGrid"></table></div>
    <p class="note" id="rvGridNote"></p>
    <div class="card rv-card" id="rivalryCard">
      <div class="rv-pick">
        <select id="rvA" aria-label="First team"></select>
        <button type="button" class="rv-swap" id="rvSwap" aria-label="Swap the two teams" title="Swap sides">⇄</button>
        <select id="rvB" aria-label="Second team"></select>
      </div>
      <div id="rvBody"></div>
    </div>`;

  const selA = $("#rvA"), selB = $("#rvB");
  const byName = [...teams].sort((x, y) => mgr(x).localeCompare(mgr(y)));
  const opts = byName.map((t) => `<option value="${t.id}">${esc(short(t))} · ${esc(t.name)}</option>`).join("");
  selA.innerHTML = opts; selB.innerHTML = opts;

  // ── the grid ────────────────────────────────────────────
  let mode = "real";
  let pa = null, pb = null;

  function heat(sh) {
    if (sh == null) return "";
    const d = Math.abs(sh - 0.5) * 2;
    if (d < 0.01) return "background:var(--surface-2)";
    return `background:color-mix(in srgb, var(${sh > 0.5 ? "--pos-soft" : "--neg-soft"}) ${Math.round(35 + 65 * d)}%, var(--surface))`;
  }
  function drawGrid() {
    const n = ranked.length;
    const cell = (r, c) => {
      const real = realRec(r.id, c.id), ev = everyRec(r.id, c.id);
      const rec = mode === "real" ? real : ev;
      const txt = games(rec) ? recStr(rec) : "";
      const tip = tipHtml(`${short(r)} vs ${short(c)}`, [[`Real games, ${scope}`, games(real) ? recStr(real) : "haven't met"], ["Every week, this season", games(ev) ? recStr(ev) : "–"]]);
      const on = (r.id === pa && c.id === pb) || (r.id === pb && c.id === pa);
      return `<td><button type="button" class="rv-cell${on ? " sel" : ""}" data-a="${r.id}" data-b="${c.id}" style="${heat(share(rec))}" data-tip="${tip}" aria-label="${esc(`${short(r)} vs ${short(c)}: ${txt || "no games"}. Open the rivalry.`)}">${txt}</button></td>`;
    };
    $("#rvGrid").innerHTML = `<thead>
        <tr><th class="rv-corner" rowspan="2" scope="col">Team</th><th class="rv-axis" colspan="${n}" scope="colgroup">Against →</th></tr>
        <tr>${ranked.map((c) => `<th class="rv-colh" scope="col" data-tip="${tipHtml(c.name, [["Manager", c.manager || "–"], ["Record", `${c.wins}-${c.losses}${c.ties ? "-" + c.ties : ""}`]])}">${esc(short(c))}</th>`).join("")}</tr>
      </thead><tbody>${ranked.map((r) => `<tr><th class="rv-rowh" scope="row" data-tip="${tipHtml(r.name, [["Manager", r.manager || "–"]])}">${esc(short(r))}</th>${ranked.map((c) => (c.id === r.id ? '<td class="rv-diag" aria-hidden="true"></td>' : cell(r, c))).join("")}</tr>`).join("")}</tbody>`;
    $("#rvGridNote").textContent = (mode === "real"
      ? `Real games: the row team's record against the column team, ${scope}. Blank means they haven't met.`
      : `Every week: in how many completed weeks this season the row team outscored the column team, as if they'd played every week.`)
      + " Blue means the row team is ahead, red means behind. Tap a cell for the full story."
      + (doneWeeks.length ? "" : " Nothing to compare until week 1 is done.");
  }
  $$(".seg button[data-mode]", root).forEach((b) => b.addEventListener("click", () => {
    mode = b.dataset.mode;
    $$(".seg button[data-mode]", root).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    drawGrid();
  }));

  // ── the rivalry card ────────────────────────────────────
  function nextHtml(a, b) {
    const up = meetAgain(a.id, b.id);
    if (!up.length) return '<p class="rv-none">No more regular-season meetings scheduled.</p>';
    const first = `<div class="rv-when">Week ${up[0]}${up[0] === L.current_week ? " · this week" : ""}</div>`
      + (up.length > 1 ? `<div class="rv-again">They also meet in week ${up.slice(1).join(" and ")}.</div>` : "");
    const p = winProb(a.id, b.id);
    if (p == null) return first + '<p class="note">Too early for a win chance. It needs two completed weeks from each team.</p>';
    const pctA = Math.round(p * 100);
    return first + `<div class="rv-prob" role="img" aria-label="${esc(`${short(a)} ${pct(p)}, ${short(b)} ${pct(1 - p)}`)}"><span class="a" style="width:${Math.min(99, Math.max(1, pctA))}%"></span><span class="b"></span></div>
      <div class="rv-prob-lab"><span><i class="a"></i>${bold(a)} ${pct(p)}</span><span>${pct(1 - p)} ${bold(b)}<i class="b"></i></span></div>
      <p class="note">A rough guide, not a forecast: it treats each team's scores this season as a bell curve (weekly swing at least ${SD_FLOOR} points).</p>`;
  }
  function meetHtml(a, b, ms) {
    if (!ms.length) return `<p class="rv-none">${esc(short(a))} and ${esc(short(b))} haven't played each other${hist ? "" : " yet this season"}.</p>`;
    const rows = [...ms].reverse().map((g) => {
      const win = g.as > g.bs ? a : g.as < g.bs ? b : null;
      return `<tr><td>${hist ? `${g.season} · ` : ""}Wk ${g.week}${g.playoff ? ' <span class="rv-tag">Playoffs</span>' : ""}</td>
        <td class="n${win === a ? " w" : ""}">${f1(g.as)}</td><td class="n${win === b ? " w" : ""}">${f1(g.bs)}</td>
        <td class="n">${mf(Math.abs(g.as - g.bs))}</td><td>${win ? esc(short(win)) : "Tie"}</td></tr>`;
    }).join("");
    return `<div class="tbl-wrap"><table class="rv-meet"><thead><tr><th>When</th><th class="n">${esc(short(a))}</th><th class="n">${esc(short(b))}</th><th class="n">Margin</th><th>Winner</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function factsHtml(a, b, ms) {
    if (!ms.length) return "";
    const fact = (label, g) => {
      const win = g.as > g.bs ? a : g.as < g.bs ? b : null;
      return `<div class="rv-fact"><div class="label">${label}</div><div class="value">${mf(Math.abs(g.as - g.bs))}</div>
        <div class="who">${win ? `${bold(win)} won` : "Tied"}, ${hist ? `${g.season} ` : ""}week ${g.week} (${f1(g.as)}–${f1(g.bs)})</div></div>`;
    };
    const margin = (g) => Math.abs(g.as - g.bs);
    const big = ms.reduce((m, g) => (margin(g) > margin(m) ? g : m));
    const close = ms.reduce((m, g) => (margin(g) < margin(m) ? g : m));
    return ms.length === 1 ? `<div class="rv-facts">${fact("Their only game", big)}</div>`
      : `<div class="rv-facts">${fact("Biggest blowout", big)}${fact("Closest game", close)}</div>`;
  }
  function drawCard() {
    const a = T[pa], b = T[pb];
    const ms = meetings(pa, pb), real = recOf(ms), ev = everyRec(pa, pb);
    const avgA = scoresOf(pa).length ? mean(scoresOf(pa)) : null, avgB = scoresOf(pb).length ? mean(scoresOf(pb)) : null;
    const season = (t) => { const g = t.wins + t.losses + t.ties; return g ? (t.wins + t.ties / 2) / g : null; };
    const sRec = (t) => `${t.wins}-${t.losses}${t.ties ? "-" + t.ties : ""} · ${ord(t.rank)}`;
    const tape = [
      { lab: `Head-to-head, ${scope}`, a: games(real) ? recStr(real) : "–", b: games(real) ? recStr(flip(real)) : "–", lead: leadOf(share(real)) },
      { lab: "Every week, this season", a: games(ev) ? recStr(ev) : "–", b: games(ev) ? recStr(flip(ev)) : "–", lead: leadOf(share(ev)) },
      { lab: "Average score", a: avgA == null ? "–" : f1(avgA), b: avgB == null ? "–" : f1(avgB), lead: avgA == null || avgB == null || Math.abs(avgA - avgB) < 0.05 ? null : avgA > avgB ? "a" : "b" },
      { lab: "Season record", a: sRec(a), b: sRec(b), lead: season(a) == null || season(b) == null ? null : leadOf(0.5 + (season(a) - season(b)) / 2) },
    ];
    $("#rvBody").innerHTML = `
      <div class="rv-top"><div class="tm">${chip(a)}</div><div class="vs">VS</div><div class="tm r">${chip(b)}</div></div>
      <div class="rv-tape">${tape.map((r) => `<div class="rv-trow"><div class="v${r.lead === "a" ? " lead" : ""}">${esc(r.a)}</div><div class="lab">${r.lab}</div><div class="v r${r.lead === "b" ? " lead" : ""}">${esc(r.b)}</div></div>`).join("")}</div>
      <div class="rv-sec"><h4>Coming up</h4>${nextHtml(a, b)}</div>
      ${ms.length ? `<div class="rv-sec"><h4>Standout games</h4>${factsHtml(a, b, ms)}</div>` : ""}
      <div class="rv-sec"><h4>Every meeting${hist ? "" : " this season"}</h4>${meetHtml(a, b, ms)}</div>`;
  }

  function setPair(a, b, o = {}) {
    pa = a; pb = b;
    selA.value = String(a); selB.value = String(b);
    $$(".rv-cell", root).forEach((el) => {
      const x = +el.dataset.a, y = +el.dataset.b;
      el.classList.toggle("sel", (x === a && y === b) || (x === b && y === a));
    });
    drawCard();
    if (o.url) { // replaceState: no hashchange, so the router doesn't scroll to the top
      try { history.replaceState(null, "", `#rivalry/${a}/${b}`); } catch (e) { /* some sandboxes refuse; the page still works */ }
    }
    if (o.scroll) $("#rivalryCard").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }
  selA.addEventListener("change", () => {
    const a = +selA.value;
    setPair(a, a === pb ? pa : pb, { url: true });
  });
  selB.addEventListener("change", () => {
    const b = +selB.value;
    setPair(b === pa ? pb : pa, b, { url: true });
  });
  $("#rvSwap").addEventListener("click", () => setPair(pb, pa, { url: true }));
  $("#rvGrid").addEventListener("click", (e) => {
    const el = e.target.closest(".rv-cell");
    if (el) setPair(+el.dataset.a, +el.dataset.b, { url: true, scroll: true });
  });

  // ── rivalries to watch ──────────────────────────────────
  function watchItems() {
    const out = [];
    const used = new Set();
    const add = (a, b, html) => { out.push({ a, b, html }); used.add(pk(a, b)); };
    const rec = (t) => `${t.wins}-${t.losses}${t.ties ? "-" + t.ties : ""}`;

    // 1. The closest-in-standings game next week.
    const next = upcoming.filter((g) => g.week === nextWeek);
    if (next.length) {
      const gap = (g) => Math.abs(T[g.a].rank - T[g.b].rank);
      const best = next.reduce((m, g) => (gap(g) < gap(m) || (gap(g) === gap(m) && T[g.a].rank + T[g.b].rank < T[m.a].rank + T[m.b].rank) ? g : m));
      const x = T[best.a], y = T[best.b], hi = Math.max(x.rank, y.rank), lo = Math.min(x.rank, y.rank);
      const flavor = hi <= 3 ? " Top-three collision." : lo >= teams.length - 2 ? " Bottom-three collision." : "";
      add(best.a, best.b, `Week ${nextWeek}: ${bold(x)} (${rec(x)}, ${ord(x.rank)}) vs ${bold(y)} (${rec(y)}, ${ord(y.rank)}).${next.length > 1 ? " The closest pair in the standings meeting that week." : ""}${flavor}`);
    }
    if (doneWeeks.length >= 3) {
      // 2. A lopsided every-week record between teams about to meet.
      let pick = null;
      for (const g of upcoming.filter((u) => nextWeek != null && u.week < nextWeek + 3 && !used.has(pk(u.a, u.b)))) {
        const ev = everyRec(g.a, g.b), sh = share(ev);
        if (sh == null || Math.abs(sh - 0.5) < 0.25) continue;
        const gapPts = Math.abs(mean(scoresOf(g.a)) - mean(scoresOf(g.b)));
        if (!pick || Math.abs(sh - 0.5) > pick.d || (Math.abs(sh - 0.5) === pick.d && gapPts > pick.gapPts)) pick = { g, ev, sh, d: Math.abs(sh - 0.5), gapPts };
      }
      if (pick) {
        const aLead = pick.sh > 0.5, w = aLead ? T[pick.g.a] : T[pick.g.b], l = aLead ? T[pick.g.b] : T[pick.g.a];
        const k = aLead ? pick.ev.w : pick.ev.l, n = games(pick.ev);
        const p = winProb(w.id, l.id);
        add(pick.g.a, pick.g.b, `${bold(w)} has outscored ${bold(l)} in ${k === n ? `all ${n}` : `${k} of ${n}`} weeks, and they meet in week ${pick.g.week}${p == null ? "" : ` (rough odds: ${pct(p)} ${esc(short(w))})`}.`);
      }
      // 3. A real result the scores don't back up.
      let fluke = null;
      for (const g of all.filter((x) => x.season === L.season && !x.playoff && x.as !== x.bs)) {
        const win = g.as > g.bs ? g.a : g.b, lose = win === g.a ? g.b : g.a;
        const ev = everyRec(lose, win), n = games(ev);
        if (n < 3 || ev.w / n < 0.75 || used.has(pk(g.a, g.b))) continue;
        const d = ev.w / n;
        if (!fluke || d > fluke.d) fluke = { win, lose, ev, week: g.week, d };
      }
      if (fluke) {
        const again = meetAgain(fluke.win, fluke.lose);
        add(fluke.win, fluke.lose, `${bold(T[fluke.win])} beat ${bold(T[fluke.lose])} in week ${fluke.week}, but ${esc(short(T[fluke.lose]))} has outscored ${esc(short(T[fluke.win]))} in ${fluke.ev.w} of ${games(fluke.ev)} weeks.${again.length ? ` They meet again in week ${again[0]}.` : ""}`);
      }
    }
    // 4. The longest-running grudge, once there's history to have one.
    if (hist) {
      let grudge = null;
      for (const a of teams) for (const b of teams) {
        if (a.id >= b.id) continue;
        const r = realRec(a.id, b.id), sh = share(r);
        if (games(r) < 3 || sh == null || Math.abs(sh - 0.5) < 0.25) continue;
        if (!grudge || Math.abs(sh - 0.5) > grudge.d || (Math.abs(sh - 0.5) === grudge.d && games(r) > games(grudge.r))) grudge = { a, b, r, sh, d: Math.abs(sh - 0.5) };
      }
      if (grudge) {
        const aLead = grudge.sh > 0.5, w = aLead ? grudge.a : grudge.b, l = aLead ? grudge.b : grudge.a;
        add(w.id, l.id, `${bold(w)} is ${recStr(aLead ? grudge.r : flip(grudge.r))} all-time against ${bold(l)}.`);
      }
    }
    // Filler, only if the above came up short: the season's biggest beating.
    if (out.length < 2) {
      const played = all.filter((g) => g.season === L.season && g.as !== g.bs);
      if (played.length) {
        const g = played.reduce((m, x) => (Math.abs(x.as - x.bs) > Math.abs(m.as - m.bs) ? x : m));
        const win = g.as > g.bs ? g.a : g.b, lose = win === g.a ? g.b : g.a;
        add(win, lose, `Biggest beating this season: ${bold(T[win])} over ${bold(T[lose])} by ${mf(Math.abs(g.as - g.bs))} in week ${g.week}.`);
      }
    }
    return out.slice(0, 4);
  }
  const items = watchItems();
  if (items.length) {
    $("#rvWatch").hidden = false;
    $("#rvWatchList").innerHTML = items.map((it) => `<li><button type="button" data-a="${it.a}" data-b="${it.b}"><span>${it.html}</span><span class="go" aria-hidden="true">→</span></button></li>`).join("");
    $("#rvWatchList").addEventListener("click", (e) => {
      const el = e.target.closest("button[data-a]");
      if (el) setPair(+el.dataset.a, +el.dataset.b, { url: true, scroll: true });
    });
  }

  // ── start ───────────────────────────────────────────────
  function defaultPair() {
    const next = upcoming.filter((g) => g.week === nextWeek && T[g.a] && T[g.b]);
    if (next.length) {
      const key = (g) => [Math.abs(T[g.a].rank - T[g.b].rank), T[g.a].rank + T[g.b].rank];
      const best = next.reduce((m, g) => { const x = key(g), y = key(m); return x[0] < y[0] || (x[0] === y[0] && x[1] < y[1]) ? g : m; });
      return [best.a, best.b];
    }
    return [ranked[0].id, ranked[1].id];
  }
  drawGrid();
  if (ranked.length >= 2) {
    const [da, db] = defaultPair();
    setPair(da, db);
  }
  onRoute("rivalries", (params) => {
    const a = +params[0], b = +params[1];
    if (T[a] && T[b] && a !== b && (a !== pa || b !== pb)) setPair(a, b);
  });
})();
