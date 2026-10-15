// Odds tab, top section: playoff odds (tiles + table) and how the odds moved week by week.
// Also hands the manager page a per-team version: App.oddsHistory(teamId), App.oddsChart(el, teamId).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, T, $, $$, esc, pct, chip, logo, lineChart } = A;

  const P = D.punishment;      // null once the regular season is over
  const H = D.odds_history;    // null if the odds module failed
  const spots = L.playoff_teams;
  const hist = H && H.weeks && H.weeks.length && H.teams && H.teams.length ? H : null;
  const HT = hist ? Object.fromEntries(hist.teams.map((t) => [t.team, t])) : {};
  const labels = hist ? hist.weeks.map((w) => (w === 0 ? "Pre" : "Wk " + w)) : [];
  const yFmt = (v) => Math.round(v * 100) + "%";
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const xTitle = (i) => (hist.weeks[i] === 0 ? "Preseason" : "After week " + hist.weeks[i]);
  // Never claim 100%: the odds are a simulation, not a proof.
  const pc = (x) => (x == null ? "–" : x >= 0.995 ? ">99%" : pct(x));
  // Once the regular season is over the last point is the real outcome, not a forecast.
  const pcAt = (x, i) => (!P && hist && i === hist.weeks.length - 1 && (x === 0 || x === 1) ? (x ? "100%" : "0%") : pc(x));
  const last = (a) => a[a.length - 1];

  // ── manager-page API ────────────────────────────────────
  // One team's odds after each week (null if there is no history to draw yet).
  A.oddsHistory = (teamId) => {
    const h = HT[teamId];
    if (!hist || !h || hist.weeks.length < 2) return null;
    return { labels, playoffs: h.p_playoffs, last: h.p_last, division: h.p_division };
  };
  // Draws that team's playoff odds (blue) and last-place odds (red) into `el`, with a legend.
  A.oddsChart = (el, teamId) => {
    const h = A.oddsHistory(teamId);
    if (!h) { el.innerHTML = '<div class="empty">Odds history starts after week 1.</div>'; return; }
    const name = T[teamId] ? T[teamId].name : "Team";
    el.innerHTML = '<div class="po-leg"><span><i style="background:var(--pos)"></i>Make playoffs</span><span><i style="background:var(--neg)"></i>Finish last</span></div><div class="po-mini"></div>';
    lineChart($(".po-mini", el), {
      x: h.labels, height: 190, yMin: 0, yMax: 1, yTicks, yFmt,
      label: `${name}: odds of making the playoffs and of finishing last, after each week`,
      xFmt: (i) => xTitle(i),
      series: [
        { name: "Make playoffs", values: h.playoffs, color: "var(--pos)" },
        { name: "Finish last", values: h.last, color: "var(--neg)" },
      ],
      tipRows: (i) => [["Make playoffs", pcAt(h.playoffs[i], i)], ["Finish last", pcAt(h.last[i], i)]],
    });
  };

  // ── this section ────────────────────────────────────────
  const root = $("#playoffs");
  const hasOdds = !!(P && P.teams && P.teams.length && P.teams[0].p_playoffs != null);
  if (!root) return;
  if (!spots || (!hasOdds && !hist)) { root.hidden = true; return; }

  const divCount = Object.keys(L.divisions || {}).length;
  const divName = (t) => String((L.divisions || {})[t.division] || "").replace(/ Division$/i, "");
  const record = (t) => `${t.wins}-${t.losses}${t.ties ? "-" + t.ties : ""}`;
  const rowsOf = (hasOdds ? P.teams : []).filter((r) => T[r.id]);
  const byOdds = [...rowsOf].sort((a, b) => b.p_playoffs - a.p_playoffs || b.exp_wins - a.exp_wins || T[b.id].points_for - T[a.id].points_for);

  // Odds as the chart's last point has them (identical to the table when both exist).
  const lastOf = (key) => (hist ? hist.teams.filter((h) => T[h.team] && last(h[key]) != null).map((h) => ({ id: h.team, v: last(h[key]) })) : []);
  const moves = () => {
    if (!hist || hist.weeks.length < 2) return [];
    return hist.teams.filter((h) => T[h.team] && h.p_playoffs.length > 1)
      .map((h) => { const n = h.p_playoffs.length; return { id: h.team, from: h.p_playoffs[n - 2], to: h.p_playoffs[n - 1] }; })
      .filter((m) => m.from != null && m.to != null)
      .map((m) => ({ ...m, d: m.to - m.from }));
  };

  // Tiles: only ones that are true right now.
  function tiles() {
    if (!hasOdds) return "";
    const out = [];
    const tile = (label, value, who, vcls) => `<div class="card tile"><div class="label">${esc(label)}</div><div class="value ${vcls || ""}">${value}</div><div class="who">${who}</div></div>`;
    const bubble = [...rowsOf].filter((r) => r.p_playoffs >= 0.2 && r.p_playoffs <= 0.8)
      .sort((a, b) => Math.abs(a.p_playoffs - 0.5) - Math.abs(b.p_playoffs - 0.5))[0];
    if (bubble) {
      const t = T[bubble.id];
      out.push(tile("Bubble team", pc(bubble.p_playoffs), `<b>${esc(t.name)}</b> · ${record(t)} · closest to a coin flip`));
    }
    if (P.byes > 0) {
      const top = [...rowsOf].sort((a, b) => (b.p_bye || 0) - (a.p_bye || 0))[0];
      if (top && top.p_bye >= 0.05) {
        const t = T[top.id];
        out.push(tile("Best shot at a bye", pc(top.p_bye), `<b>${esc(t.name)}</b> · top ${P.byes} seeds skip round one`));
      }
    }
    const mv = moves().sort((a, b) => Math.abs(b.d) - Math.abs(a.d))[0];
    if (mv && Math.abs(mv.d) >= 0.03) {
      const wkNo = last(hist.weeks), t = T[mv.id];
      const pts = Math.round(mv.to * 100) - Math.round(mv.from * 100);  // same rounding as the numbers beside it
      out.push(tile(`Biggest mover, week ${wkNo}`, `${pts > 0 ? "+" : "−"}${Math.abs(pts)} pts`,
        `<b>${esc(t.name)}</b> · ${pc(mv.from)} → ${pc(mv.to)} to make it`, mv.d > 0 ? "pos" : "neg"));
    }
    const locks = rowsOf.filter((r) => r.p_playoffs >= 0.99);
    out.push(tile("Near-locks", String(locks.length),
      locks.length ? locks.map((r) => esc(T[r.id].name)).join(", ") + " · 99%+ to make it" : "Nobody's safe yet"));
    return out.join("");
  }

  function table() {
    if (!hasOdds) return "";
    const showDiv = divCount > 1;
    const hasWinDiv = rowsOf.some((r) => r.p_division != null);
    const hasBye = P.byes > 0 && rowsOf.some((r) => r.p_bye != null);
    const head = `<thead><tr><th>Team</th><th class="n">Record</th>${showDiv ? '<th class="c-div">Division</th>' : ""}<th class="n c-proj" title="Average final wins across the simulations">Proj. wins</th>${hasWinDiv ? '<th class="n" title="Chance to finish first in its division">Win division</th>' : ""}<th class="n">Make playoffs</th>${hasBye ? `<th class="n" title="Top ${P.byes} seeds skip the first round">Bye</th>` : ""}<th class="n">Last place</th></tr></thead>`;
    const body = byOdds.map((r) => {
      const t = T[r.id];
      return `<tr><td>${chip(t)}</td><td class="n">${record(t)}</td>${showDiv ? `<td class="c-div dim">${esc(divName(t))}</td>` : ""}<td class="n c-proj">${r.exp_wins.toFixed(1)}</td>${hasWinDiv ? `<td class="n">${pc(r.p_division)}</td>` : ""}<td class="n po-pl"><span class="po-num">${pc(r.p_playoffs)}</span><span class="po-meter"><i style="width:${(r.p_playoffs * 100).toFixed(1)}%"></i></span></td>${hasBye ? `<td class="n">${pc(r.p_bye)}</td>` : ""}<td class="n ${r.p_last >= 0.1 ? "neg" : ""}">${pc(r.p_last)}</td></tr>`;
    }).join("");
    const byeNote = P.byes > 0 ? ` The top ${P.byes} seeds skip round one.` : "";
    return `<div class="card tbl-wrap"><table class="po-tbl">${head}<tbody>${body}</tbody></table></div><p class="note">Sorted by playoff odds. They add up to ${spots} because that's how many teams get in.${byeNote}</p>`;
  }

  // ── "how the odds moved" chart ─────────────────────────
  // Every team keeps one color for good (by team id, never by rank, so a pick never
  // repaints the others): eight distinct hues, then the same hues dashed for teams 9–12.
  const CAT = 8;
  const colorOrder = [...hist?.teams || []].map((h) => h.team).filter((id) => T[id]).sort((a, b) => a - b);
  const styleOf = (id) => {
    const i = Math.max(0, colorOrder.indexOf(id));
    return { color: `var(--cat-${(i % CAT) + 1})`, dashed: i >= CAT };
  };
  const METRICS = {
    p_playoffs: { btn: "Playoffs", cap: "Chance to make the playoffs" },
    p_last: { btn: "Last place", cap: "Chance to finish in last place" },
    p_division: { btn: "Division", cap: "Chance to win the division" },
  };
  let metric = "p_playoffs";
  let picks = [];   // highlighted team ids

  function drawChartBlock() {
    if (!hist) return "";
    if (hist.weeks.length < 2) return '<h3 class="po-h3">How the odds moved</h3><div class="card empty">Odds history starts after week 1.</div>';
    const avail = Object.keys(METRICS).filter((m) => hist.teams.some((h) => h[m] && h[m].some((v) => v != null)));
    if (!avail.length) return "";
    if (!avail.includes(metric)) metric = avail[0];
    const order = [...hist.teams].filter((h) => T[h.team])
      .sort((a, b) => (last(b.p_playoffs) ?? -1) - (last(a.p_playoffs) ?? -1) || T[a.team].name.localeCompare(T[b.team].name));
    pickDefaults(order);
    const seg = avail.map((m) => `<button type="button" data-m="${m}" aria-pressed="${m === metric}">${METRICS[m].btn}</button>`).join("");
    const pick = order.map((h) => `<button type="button" class="po-pick-btn" data-id="${h.team}" aria-pressed="false">${logo(T[h.team])}<span class="nm">${esc(T[h.team].name)}</span><i class="sw"></i></button>`).join("");
    return `<h3 class="po-h3">How the odds moved</h3>
      <p class="sub" id="poChartSub"></p>
      <div class="card">
        <div class="po-ctl"><div class="seg" role="group" aria-label="Which odds to chart">${seg}</div>
          <div class="po-all"><button type="button" class="po-all-btn" data-all="1">All teams</button><button type="button" class="po-all-btn" data-all="0">Clear</button></div></div>
        <div class="po-chart-wrap"><div class="po-chart" id="poChart"></div></div>
        <div class="po-pick" role="group" aria-label="Teams to highlight">${pick}</div>
        <p class="note po-hint">Tap teams to highlight them, or show all 12 at once (teams past the eighth color get dashed lines); grey lines are everyone else. Each week's odds use only the scores known at that point, so "Pre" is a blank slate.</p>
      </div>`;
  }

  function pickDefaults(order) {
    if (picks.length) return;
    const add = (id) => { if (id != null && T[id] && !picks.includes(id) && picks.length < 4) picks.push(id); };
    const now = lastOf("p_playoffs");
    const near = [...now].sort((a, b) => Math.abs(a.v - 0.5) - Math.abs(b.v - 0.5))[0];
    const mv = moves().sort((a, b) => Math.abs(b.d) - Math.abs(a.d))[0];
    const fav = [...now].sort((a, b) => b.v - a.v)[0];
    const worst = [...lastOf("p_last")].sort((a, b) => b.v - a.v)[0];
    add(near && near.id); add(mv && mv.id); add(fav && fav.id); add(worst && worst.id);
    for (const h of order) if (picks.length < 3) add(h.team);
  }

  function togglePick(id) {
    const i = picks.indexOf(id);
    if (i >= 0) picks.splice(i, 1); else picks.push(id);
  }

  function paintChart() {
    const el = $("#poChart");
    if (!el || !hist || hist.weeks.length < 2) return;
    const m = METRICS[metric];
    $("#poChartSub").textContent = `${m.cap}, re-simulated after every week from the standings at that point. The last point is today's number.`;
    $$("[data-m]", root).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.m === metric)));
    $$(".po-pick-btn", root).forEach((b) => {
      const id = +b.dataset.id, on = picks.includes(id);
      b.setAttribute("aria-pressed", String(on));
      const st = styleOf(id);
      b.style.setProperty("--c", on ? st.color : "var(--axis)");
      b.classList.toggle("dashed", on && st.dashed);
    });
    const allOn = picks.length === colorOrder.length;
    $$(".po-all-btn", root).forEach((b) => (b.disabled = b.dataset.all === "1" ? allOn : !picks.length));
    const series = hist.teams.filter((h) => T[h.team]).map((h) => {
      const on = picks.includes(h.team), st = styleOf(h.team);
      return { name: T[h.team].name, values: h[metric], muted: !on, color: on ? st.color : undefined, dashed: on && st.dashed };
    });
    const shown = picks.map((id) => HT[id]).filter(Boolean);
    lineChart(el, {
      x: labels, series, height: 260, yMin: 0, yMax: 1, yTicks, yFmt, xFmt: xTitle,
      label: `${m.cap}, by week, for all teams`,
      tipRows: (i) => {
        const rows = shown.filter((h) => h[metric][i] != null)
          .sort((a, b) => b[metric][i] - a[metric][i])
          .map((h) => {
            const v = h[metric][i], prev = i > 0 ? h[metric][i - 1] : null;
            const d = prev == null ? null : Math.round(v * 100) - Math.round(prev * 100);
            return [T[h.team].name, pcAt(v, i) + (d == null ? "" : ` (${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(d)})`)];
          });
        return rows.length ? rows : [["Tap a team below", "to compare"]];
      },
    });
  }

  root.innerHTML = `<h2>Playoff odds</h2><p class="sub" id="poSub"></p>${hasOdds ? `<div class="tiles po-tiles">${tiles()}</div>${table()}` : ""}${drawChartBlock()}`;

  const left = P && P.weeks_left && P.weeks_left.length ? P.weeks_left : null;
  const wild = Math.max(0, spots - divCount);
  $("#poSub", root).textContent = hasOdds
    ? `We simulated the rest of the regular season (weeks ${left[0]}–${last(left)}) ${P.sims.toLocaleString()} times, using each team's scoring so far and the real schedule. ${divCount > 1 ? `The ${divCount} division winners get in, then the best records fill the other ${wild} spots` : `The ${spots} best records get in`}. Ties go to division record, then points for.`
    : P ? "How each team's odds have moved after every week."
    : "The regular season is over. Here is how each team's odds moved on the way to the final bracket.";

  root.addEventListener("click", (e) => {
    const m = e.target.closest("[data-m]");
    if (m && root.contains(m)) { metric = m.dataset.m; paintChart(); return; }
    const all = e.target.closest("[data-all]");
    if (all && root.contains(all)) { picks = all.dataset.all === "1" ? [...colorOrder] : []; paintChart(); return; }
    const b = e.target.closest(".po-pick-btn");
    if (b && root.contains(b)) { togglePick(+b.dataset.id); paintChart(); }
  });
  paintChart();
})();
