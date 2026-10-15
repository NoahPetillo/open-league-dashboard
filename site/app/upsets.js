// Live tab: the upset alert. Pregame win odds for every matchup this week (LIVE_DATA.winprob.pregame,
// from league/winprob.py), closest first. Redraws whenever livescores.js re-reads live.js.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, $, esc, f1, chip } = A;
  const root = $("#upsets");
  if (!root) return;

  const share = A.shareBtn || (() => ""); // "Share to the board" (account.js; hidden unless you're signed in)
  const nm = (id) => (T[id] ? T[id].manager || T[id].name : `Team ${id}`);
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

  const COIN = 0.45;   // the underdog is at least this likely: a coin flip
  const ALERT = 0.35;  // ... at least this likely: worth watching. Below it, nobody's tagged "upset alert".
  const MIN_GAMES = 8; // fewer finished games than this and a favorites' record means little

  // "38%" and "62%" that always add to 100, however the halves round.
  function pair(dog) {
    const d = Math.round(dog * 100);
    return d < 1 ? ["<1%", ">99%"] : [d + "%", 100 - d + "%"];
  }

  // The season's record for ESPN's favorites, from the recap data (not typed in here).
  function record() {
    const f = D.recap && D.recap.favorites;
    if (!f || !(f.won + f.lost)) return "";
    const n = f.won + f.lost;
    const line = `ESPN's favorites are ${f.won}–${f.lost} this season`;
    if (n < MIN_GAMES) return ` ${line} so far.`;
    return f.won / n < 0.6 ? ` ${line}, so don't bet the house.` : ` ${line}, so they've held up, but it's still fantasy football.`;
  }

  const started = (LV) => LV.matchups.some((m) => [m.home, m.away].some((s) => (s.starters || []).some((p) => p.status === "live" || p.status === "final")));
  const scoreOf = (LV, g) => {
    const m = LV.matchups.find((x) => x.home.team === g.home && x.away.team === g.away);
    return m ? { [g.home]: m.home.score, [g.away]: m.away.score } : null;
  };

  // The row as a plain-text stat for the board: an upset alert, or (the biggest-gap row) a blowout.
  function stat(r, now, done, week, dp) {
    const { dog, fav } = r, d = nm(dog.id), f = nm(fav.id);
    const proj = `${f1(dog.proj)} to ${f1(fav.proj)} projected`;
    const won = done && now ? (now[dog.id] > now[fav.id] ? " and won" : " and lost") : "";
    const text = r.blowout
      ? `${f} ${done ? "was" : "is"} projected to beat ${d} ${f1(fav.proj)} to ${f1(dog.proj)}, the biggest gap of the week. ${d} ${done ? "had" : "has"} a ${dp} chance.`
      : `${d} ${done ? "had" : "has"} a ${dp} chance to beat ${f} (${proj})${won}.`;
    const facts = [[clip(`${d} chance`, 30), dp], ["Projected", `${f1(dog.proj)}–${f1(fav.proj)}`]];
    if (done && now) facts.push(["Final", `${f1(now[dog.id])}–${f1(now[fav.id])}`]);
    return { kind: "upset", title: `Week ${week} ${r.blowout ? "projected blowout" : "upset alert"}`, text: clip(text, 300), facts, teams: [dog.id, fav.id], link: "#upsets" };
  }

  function row(r, now, done, week) {
    const { dog, fav } = r;
    const [dp, fp] = pair(dog.p);
    const tags = [];
    if (done && now && now[dog.id] > now[fav.id]) tags.push(["won", "Upset!"]);
    if (dog.p >= COIN) tags.push(["coin", "Coin flip"]);
    else if (dog.p >= ALERT) tags.push(["alert", "Upset alert"]);
    if (r.blowout) tags.push(["blow", "Biggest projected blowout"]);
    const sc = (side) => (now ? `<b>${f1(now[side.id])}</b><small>proj ${f1(side.proj)}</small>` : `<b>${f1(side.proj)}</b><small>proj</small>`);
    const label = `${T[dog.id].name} has a ${dp} chance to beat ${T[fav.id].name}`;
    return `<li class="ua-row${done && now && now[dog.id] > now[fav.id] ? " won" : ""}">
      <div class="ua-team dog">${chip(T[dog.id])}</div>
      <div class="ua-sc dog">${sc(dog)}</div>
      <div class="ua-pct dog"><b>${dp}</b></div>
      <div class="ua-mid">
        ${tags.length ? `<div class="ua-tags">${tags.map(([k, t]) => `<span class="ua-tag ${k}">${esc(t)}</span>`).join("")}</div>` : ""}
        <div class="ua-bar" role="img" aria-label="${esc(label)}"><i style="width:${(dog.p * 100).toFixed(1)}%"></i></div>
        ${now ? '<div class="ua-note">Pregame odds</div>' : ""}
        ${share(stat(r, now, done, week, dp))}
      </div>
      <div class="ua-pct fav"><b>${fp}</b></div>
      <div class="ua-sc fav">${sc(fav)}</div>
      <div class="ua-team fav">${chip(T[fav.id])}</div>
    </li>`;
  }

  function draw() {
    const LV = window.LIVE_DATA;
    const W = LV && LV.winprob;
    const pre = W && Array.isArray(W.pregame) ? W.pregame.filter((g) => T[g.home] && T[g.away] && Number.isFinite(g.p_home)) : [];
    if (!LV || !Array.isArray(LV.matchups) || !pre.length) { root.hidden = true; root.innerHTML = ""; return; }

    const rows = pre.map((g) => {
      const homeDog = g.p_home < 0.5;
      const side = (home) => ({ id: home ? g.home : g.away, p: home ? g.p_home : 1 - g.p_home, proj: home ? g.proj_home : g.proj_away });
      const dog = homeDog ? side(true) : side(false);
      return { g, dog, fav: homeDog ? side(false) : side(true), gap: Math.abs(g.proj_home - g.proj_away) };
    }).sort((a, b) => b.dog.p - a.dog.p || b.gap - a.gap);
    const big = rows.reduce((best, r) => (r.gap > best.gap ? r : best), rows[0]);
    if (big.dog.p < ALERT) big.blowout = true; // a close game isn't a blowout, whatever the biggest gap is

    const live = started(LV);
    const done = !!W.done;
    root.hidden = false;
    root.innerHTML = `<h2>Upset alert</h2>
      <p class="sub">Win odds for each matchup, from ESPN's projections for the lineups as they're set right now, give or take a typical miss for each position (measured on this league's games).${esc(record())}${live ? " They use each starter's pregame projection, so the scores coming in don't move them. A lineup change still can." : " Lineups can still change before kickoff."}</p>
      <div class="card ua-card"><ol class="ua-list" aria-label="Matchups, closest odds first">${rows.map((r) => row(r, live ? scoreOf(LV, r.g) : null, done, W.week ?? LV.week)).join("")}</ol></div>`;
  }

  draw();
  document.addEventListener("live:update", draw);
})();
