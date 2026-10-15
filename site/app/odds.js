// Odds tab: the race section, with a picker for which race: avoiding last place (the default:
// nobody wants last place), making the playoffs, or getting a first-round bye. Each race
// comes from the same simulations (D.punishment.races, league/punishment.py).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, T, $, esc, chip, tipHtml } = A;

  const P = D.punishment;
  if (!P) { $("#race").hidden = true; return; }
  const pct = (x) => (x == null ? "–" : x === 0 ? "~0%" : x < 0.005 ? "<1%" : x > 0.995 ? ">99%" : Math.round(x * 100) + "%");
  const rec = (id) => `${T[id].wins}-${T[id].losses}${T[id].ties ? `-${T[id].ties}` : ""}`;
  const nameList = (ids) => ids.map((id) => esc(T[id].name)).join(", ");
  const byId = Object.fromEntries(P.teams.map((t) => [t.id, t]));
  const nTeams = P.teams.length;

  // Data written before the picker existed has only the last-place race, at the top level.
  const races = P.races || { last: {
    magic_number: P.magic_number, safe_odds: P.safe_odds, cutoff_wins: P.last_place_wins, next_week_games: P.next_week_games,
    teams: P.teams.map((t) => ({ id: t.id, p: t.p_last, need: t.need, p_reach_magic: t.p_reach_magic, next_if_win: t.next_if_win, next_if_loss: t.next_if_loss })),
  } };
  const spots = P.playoff_spots, byes = P.byes;
  const weeksText = () => {
    const wl = P.weeks_left;
    return `We simulated the rest of the regular season (week${wl.length === 1 ? ` ${wl[0]}` : `s ${wl[0]}–${wl[wl.length - 1]}`}) ${P.sims.toLocaleString()} times, using each team's scoring so far and the real schedule. ${A.tiebreakText(P)}`;
  };
  const safe = (r) => Math.round(r.safe_odds * 100);

  // How each race is worded. bad: the race is about avoiding it (red); otherwise getting it (blue).
  const RACES = {
    last: {
      bad: true,
      title: "The race to avoid last place",
      sub: () => `Nobody wants to finish last. ${weeksText()}`,
      lead: "Most likely to finish last",
      magic: (r) => `Get there and you finish last less than ${safe(r)}% of the time`,
      typical: "Last place usually finishes with",
      bars: ["Odds of finishing last", "Teams with at least a 0.5% chance"],
      hist: ["What last place ends up with", "Final win total of the last-place team, across all simulations"],
      histTip: "Last place finishes here",
      games: "toilet bowl games",
      gamesSub: "Odds of finishing last with a win vs. a loss",
      col: "Odds of last",
      none: "No game this week really moves the race.",
    },
    playoffs: {
      title: "The race for the playoffs",
      sub: () => `${spots} of ${nTeams} teams make the playoffs: every division winner, then the best records. ${weeksText()}`,
      lead: "On the bubble",
      magic: (r) => `Get there and you make the playoffs at least ${100 - safe(r)}% of the time`,
      typical: "The last team in usually has",
      bars: ["Odds of making the playoffs", "Teams that aren't locked in or out yet"],
      hist: ["What the last team in ends up with", "Fewest wins of any playoff team, across all simulations"],
      histTip: "The last team in has this many",
      games: "playoff race games",
      gamesSub: "Odds of making the playoffs with a win vs. a loss",
      col: "Odds of playoffs",
      none: "No game this week really moves the playoff race.",
    },
    bye: {
      title: "The race for a first-round bye",
      sub: () => `The top ${byes === 1 ? "seed skips" : `${byes} seeds skip`} the first round of the playoffs${P.division_winners === false ? "" : ", and division winners get the top seeds"}. ${weeksText()}`,
      lead: "On the bubble",
      magic: (r) => `Get there and you get a bye at least ${100 - safe(r)}% of the time`,
      typical: "The last bye usually goes to a team with",
      bars: ["Odds of a first-round bye", "Teams that aren't locked in or out yet"],
      hist: ["What the last bye team ends up with", "Fewest wins of a team with a bye, across all simulations"],
      histTip: "The last bye team has this many",
      games: "bye race games",
      gamesSub: "Odds of a bye with a win vs. a loss",
      col: "Odds of a bye",
      none: "No game this week really moves the bye race.",
    },
  };

  const sel = $("#raceSel");
  for (const o of sel.options) o.hidden = !races[o.value];
  sel.hidden = Object.keys(races).length < 2;

  function draw(key) {
    const r = races[key], C = RACES[key];
    const rows = [...r.teams].sort((a, b) => b.p - a.p);
    const R = Object.fromEntries(r.teams.map((t) => [t.id, t]));
    $("#raceTitle").textContent = C.title;
    $("#raceSub").textContent = C.sub();

    // the lead tile: the likeliest to finish last, or (playoffs, bye) the team closest to a coin flip
    const open = rows.filter((t) => t.p >= 0.02 && t.p <= 0.98);
    const lead = C.bad ? rows[0] : open.sort((a, b) => Math.abs(a.p - 0.5) - Math.abs(b.p - 0.5))[0];
    const typical = Object.entries(r.cutoff_wins).sort((a, b) => b[1] - a[1])[0];
    const big = r.next_week_games[0];
    const tile = (label, value, who, cls = "") => `<div class="card tile"><div class="label">${label}</div><div class="value ${cls}">${value}</div><div class="who">${who}</div></div>`;
    $("#raceTiles").innerHTML = [
      lead ? tile(C.lead, pct(lead.p), `<b>${esc(T[lead.id].name)}</b> · ${esc(T[lead.id].manager)} · ${rec(lead.id)}`, C.bad ? "danger" : "") : "",
      r.magic_number != null ? tile("Magic number", `${r.magic_number} wins`, C.magic(r)) : "",
      typical ? tile(C.typical, `${typical[0]} wins`, `${pct(typical[1])} of simulations`) : "",
      big && big.swing >= 0.01 ? tile("Biggest game for the race", `Wk ${big.week}`, `<b>${esc(T[big.a].name)}</b> vs <b>${esc(T[big.b].name)}</b>`) : "",
    ].join("");

    // the bars: every team the race is still live for
    $("#raceBarsTitle").textContent = C.bars[0];
    $("#raceBarsCap").textContent = C.bars[1];
    const live = rows.filter((t) => t.p >= 0.005 && (C.bad || t.p <= 0.995));
    const max = Math.max(...live.map((t) => t.p), 0.01);
    const notes = C.bad
      ? [rows.filter((t) => t.p < 0.005).length ? `Basically safe: ${nameList(rows.filter((t) => t.p < 0.005).map((t) => t.id))}.` : ""]
      : [rows.filter((t) => t.p > 0.995).length ? `Basically in: ${nameList(rows.filter((t) => t.p > 0.995).map((t) => t.id))}.` : "",
        rows.filter((t) => t.p < 0.005).length ? `Basically out: ${nameList(rows.filter((t) => t.p < 0.005).map((t) => t.id))}.` : ""];
    $("#raceBars").innerHTML = (live.length ? live.map((t) => `<div class="bar-row" data-tip="${tipHtml(T[t.id].name, [[C.col, pct(t.p)], ["Projected wins", byId[t.id].exp_wins.toFixed(1)], ["Record", rec(t.id)]])}">${chip(T[t.id])}<div class="bar-track"><span class="zero" style="left:0"></span><span class="b ${C.bad ? "m" : "s"}" style="left:0;width:${(t.p / max) * 100}%;border-radius:0 4px 4px 0"></span></div><div class="v">${pct(t.p)}</div></div>`).join("")
      : '<p class="note">Nobody\'s in the balance any more.</p>')
      + notes.filter(Boolean).map((n) => `<p class="note">${n}</p>`).join("");

    // what the cutoff team ends up with
    $("#raceHistTitle").textContent = C.hist[0];
    $("#raceHistCap").textContent = C.hist[1];
    const hist = Object.entries(r.cutoff_wins).filter(([, v]) => v >= 0.001);
    const hmax = Math.max(...hist.map(([, v]) => v), 0.001);
    $("#raceHist").innerHTML = hist.map(([w, v]) => `<div class="col" data-tip="${tipHtml(`${w} wins`, [[C.histTip, pct(v)]])}"><span class="pct">${pct(v)}</span><span class="bar${C.bad ? "" : " good"}" style="height:${(v / hmax) * 100}%"></span></div>`).join("");
    $("#raceHistX").innerHTML = hist.map(([w]) => `<span>${w} W</span>`).join("");

    // next week's games that swing it most
    const games = r.next_week_games.filter((g) => g.swing >= 0.01).slice(0, 4);
    const gw = r.next_week_games[0]?.week;
    $("#gamesTitle").textContent = gw ? `Week ${gw} ${C.games}` : C.games[0].toUpperCase() + C.games.slice(1);
    $("#gamesSub").textContent = gw && gw <= L.through_week + 1 && L.current_week > L.through_week
      ? `The games that swing the race most. ${C.gamesSub} (week ${gw} counts as unplayed until it's final).`
      : `The games that swing the race most. ${C.gamesSub}.`;
    const side = (id, right) => `<div class="gs ${right ? "r" : ""}">${chip(T[id])}<div class="odds">Win: <b>${pct(R[id].next_if_win)}</b> · Lose: <b>${pct(R[id].next_if_loss)}</b></div></div>`;
    $("#raceGames").innerHTML = games.length
      ? games.map((g) => `<div class="card game">${side(g.a, false)}<div class="vs">VS<small>${Math.round(g.swing * 100)} pt swing</small></div>${side(g.b, true)}</div>`).join("")
      : `<div class="card empty">${C.none}</div>`;

    // every team's path
    const magic = r.magic_number;
    const sosVals = P.teams.map((t) => t.sos).filter((x) => x != null);
    const sosAvg = sosVals.reduce((x, y) => x + y, 0) / Math.max(1, sosVals.length);
    const needText = (t) => {
      const g = byId[t.id].games_left;
      return t.need === 0 ? (C.bad ? "Safe" : "There") : t.need > g ? "Out of reach" : `${t.need} of ${g}`;
    };
    const hot = (p) => (C.bad ? (p >= 0.1 ? "neg" : "") : p >= 0.9 ? "pos" : p < 0.1 ? "neg" : "");
    $("#raceTbl").innerHTML = `<thead><tr><th>Team</th><th class="n">Record</th><th class="n">Proj. wins</th><th class="n">${C.col}</th>${magic != null ? `<th class="n">Wins to ${magic}</th><th>Chance to get there</th>` : ""}<th class="n">Schedule left</th></tr></thead><tbody>${rows.map((t) => {
      const o = byId[t.id];
      const sos = o.sos == null ? "–" : o.sos > sosAvg + 0.8 ? '<span class="neg">Tough</span>' : o.sos < sosAvg - 0.8 ? '<span class="pos">Easy</span>' : "Average";
      return `<tr><td>${chip(T[t.id])}</td><td class="n">${rec(t.id)}</td><td class="n">${o.exp_wins.toFixed(1)}</td><td class="n ${hot(t.p)}">${pct(t.p)}</td>${magic != null ? `<td class="n">${needText(t)}</td><td>${pct(t.p_reach_magic)}<span class="reach"><i style="width:${(t.p_reach_magic || 0) * 100}%"></i></span></td>` : ""}<td class="n" title="Average weekly score of remaining opponents: ${o.sos}">${sos}</td></tr>`;
    }).join("")}</tbody>`;
  }

  sel.addEventListener("change", () => draw(sel.value));
  draw("last");
})();
