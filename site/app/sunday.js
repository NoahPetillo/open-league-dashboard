// Home tab: the Sunday recap. How every matchup's win chance moved as the week's games finished
// (D.recap for completed weeks, LIVE_DATA.winprob for the week in progress; both from league/winprob.py).
// There's no in-game data, so a "step" is a whole slate of games finishing: Thursday night, the early games...
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, $, $$, esc, f1, pct, chip } = A;
  const root = $("#sunday");
  if (!root) return;

  const MIN_GAMES = 8; // fewer finished games than this and a favorites' record means little
  const nm = (id) => (T[id] ? T[id].manager || T[id].name : `Team ${id}`);
  const tn = (id) => (T[id] ? T[id].name : `Team ${id}`);
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const lc = (s) => s.charAt(0).toLowerCase() + s.slice(1);
  const p1 = (a) => (a === 1 ? "100%" : a === 0 ? "0%" : pct(a)); // only a finished game is exactly 0% or 100%

  // "Share to the board" needs plain text: the tiles' sentences, minus their <b> tags.
  const share = A.shareBtn || (() => "");
  const ENT = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'" };
  const plain = (html) => String(html).replace(/<[^>]*>/g, "").replace(/&(?:amp|lt|gt|quot|#39);/g, (m) => ENT[m]);
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

  // Both teams' chances as strings that always add to 100: [home, away].
  function pair(p) {
    if (p === 1 || p === 0) return [p * 100 + "%", (1 - p) * 100 + "%"];
    const d = Math.round(p * 100);
    const s = (x) => (x < 1 ? "<1%" : x > 99 ? ">99%" : x + "%");
    return [s(d), s(100 - d)];
  }

  // ESPN's favorites' record, from the recap data.
  function record() {
    const f = D.recap && D.recap.favorites;
    if (!f || !(f.won + f.lost)) return "";
    const n = f.won + f.lost;
    const line = `ESPN's favorites are ${f.won}–${f.lost} this season`;
    if (n < MIN_GAMES) return `${line} so far.`;
    return f.won / n < 0.6 ? `${line}, so don't bet the house.` : `${line}, so they've held up, but it's still fantasy football.`;
  }

  // ── what to show ─────────────────────────────────────────
  const usable = (w) => w && Array.isArray(w.checkpoints) && w.checkpoints.length >= 2 && Array.isArray(w.games) && w.games.length;
  function views() {
    const out = [];
    const done = D.recap && Array.isArray(D.recap.weeks) ? D.recap.weeks.filter(usable) : [];
    const LV = window.LIVE_DATA, W = LV && LV.winprob;
    const lastDone = done.reduce((m, w) => Math.max(m, w.week), 0);
    // the week in progress, once a slate of games has finished (unless the recap already has it)
    if (usable(W) && W.week > lastDone) out.push({ key: "live", week: W.week, live: true, done: !!W.done, src: W, LV });
    for (const w of [...done].sort((a, b) => b.week - a.week)) out.push({ key: "w" + w.week, week: w.week, live: false, done: true, src: w });
    for (const v of out) {
      v.cps = v.src.checkpoints;
      v.heads = v.src.headlines || {};
      v.games = v.src.games.filter((g) => T[g.home] && T[g.away] && Array.isArray(g.p_home) && g.p_home.length === v.cps.length);
    }
    return out.filter((v) => v.games.length);
  }

  // Each team's score: official for a finished week, the live score for the week in progress.
  function scores(v, g) {
    const last = (a) => (a && a.length ? a[a.length - 1] : 0);
    if (v.live) {
      const m = (v.LV.matchups || []).find((x) => x.home.team === g.home && x.away.team === g.away);
      if (m) return { home: m.home.score, away: m.away.score };
    }
    return { home: last(g.home_pts), away: last(g.away_pts) };
  }
  const drama = (g) => g.p_home.reduce((m, p, k) => (k ? Math.max(m, Math.abs(p - g.p_home[k - 1])) : 0), 0);
  const slateAt = (v, k) => (v.cps[k].slate || String(v.cps[k].label).replace(/^After /, ""));
  const when = (v, k) => lc(v.cps[k].label); // "after the early games", "before kickoff"
  const same = (a, b) => (a.team === b.team && a.opp === b.opp) || (a.team === b.opp && a.opp === b.team);

  // ── headline tiles (the sentences are the content) ───────
  // Each: {tag (on that matchup's card), label, line (html), sub (html), team, opp}
  function headlines(v) {
    const H = v.heads, out = [];
    const vs = (h) => `${esc(tn(h.team))} vs ${esc(tn(h.opp))}`;
    const fin = (h) => [[nm(h.team), f1(h.score)], [nm(h.opp), f1(h.opp_score)]]; // the final score, for the Share card
    const swing = (h, label) => ({ tag: "Biggest swing", label, team: h.team, opp: h.opp, sub: vs(h),
      line: `${esc(cap(slateAt(v, h.at)))} took <b>${esc(nm(h.team))}</b> from ${p1(h.from)} to ${p1(h.to)}.` });
    if (v.live && !v.done) {
      if (H.swing) out.push(swing(H.swing, "Biggest swing so far"));
      const u = H.upset_watch;
      if (u) out.push({ tag: "Upset watch", label: "Upset watch", team: u.team, opp: u.opp, sub: vs(u),
        line: `<b>${esc(nm(u.team))}</b> was a ${p1(u.pregame)} underdog and is now ${p1(u.now)} to win.` });
      return fold(out);
    }
    if (v.live) { // the week is over, ESPN hasn't started the next one
      if (H.swing) out.push(swing(H.swing, "Biggest swing"));
      const u = H.upset_watch;
      if (u) out.push({ tag: "Upset", label: "Biggest upset", team: u.team, opp: u.opp, sub: vs(u),
        line: `<b>${esc(nm(u.team))}</b> was a ${p1(u.pregame)} underdog and won.`,
        short: `<b>${esc(nm(u.team))}</b> was a ${p1(u.pregame)} underdog before kickoff.` });
      return fold(out);
    }
    const c = H.comeback, u = H.upset, d = H.collapse;
    // a comeback from "before kickoff" is just the pregame underdog winning: the upset tile says it
    if (c && !(c.at === 0 && u && same(c, u))) {
      out.push({ tag: "Comeback", label: "Biggest comeback", team: c.team, opp: c.opp, sub: `${esc(tn(c.team))} over ${esc(tn(c.opp))}`,
        line: `<b>${esc(nm(c.team))}</b> was ${p1(c.low)} to win ${esc(when(v, c.at))}. Won ${f1(c.score)}–${f1(c.opp_score)}.`,
        short: `<b>${esc(nm(c.team))}</b> was ${p1(c.low)} to win ${esc(when(v, c.at))}.`, result: `Won ${f1(c.score)}–${f1(c.opp_score)}.`, final: fin(c) });
    }
    if (H.swing) out.push(swing(H.swing, "Biggest swing"));
    if (u) {
      out.push({ tag: "Upset", label: "Biggest pregame upset", team: u.team, opp: u.opp, sub: `${esc(tn(u.team))} over ${esc(tn(u.opp))}, ${f1(u.score)}–${f1(u.opp_score)}`,
        line: `<b>${esc(nm(u.team))}</b> was a ${p1(u.pregame)} underdog and won.`,
        short: `<b>${esc(nm(u.team))}</b> was a ${p1(u.pregame)} underdog before kickoff.`,
        result: `${esc(nm(u.team))} won ${f1(u.score)}–${f1(u.opp_score)}.`, final: fin(u) });
    }
    // the mirror of the comeback is the same game; only worth its own tile when it's a different one
    if (d && !(c && same(c, d))) {
      out.push({ tag: "Collapse", label: "Biggest collapse", team: d.team, opp: d.opp, sub: `${esc(tn(d.opp))} over ${esc(tn(d.team))}`,
        line: `<b>${esc(nm(d.team))}</b> was ${p1(d.high)} to win ${esc(when(v, d.at))}. Lost ${f1(d.score)}–${f1(d.opp_score)}.`, final: fin(d) });
    }
    return fold(out);
  }
  // One game can top several lists (the comeback, the swing and the upset can all be the same game).
  // Later tiles about a game fold into its first tile, so the row never repeats a matchup; the
  // game's card still gets every tag. Folded sentences run in order: the pregame odds first, the
  // final score last.
  function fold(list) {
    const out = [];
    for (const h of list) {
      const first = out.find((o) => same(o, h));
      if (!first) { out.push({ ...h, tags: [h.tag], parts: [h.short || h.line] }); continue; }
      first.tags.push(h.tag);
      first.label += " + " + h.label.replace(/^Biggest /, "");
      first.parts[/upset/i.test(h.tag) ? "unshift" : "push"](h.short || h.line);
      first.result = first.result || h.result;
      first.final = first.final || h.final;
      first.folded = true;
    }
    for (const o of out) if (o.folded) o.line = [...o.parts, o.result].filter(Boolean).join(" ");
    return out;
  }
  // The tile's sentence, as the stat for "Share to the board" (a folded tile shares its combined sentence).
  const tileStat = (h, title) => ({
    kind: "recap", title, text: clip(plain(h.line), 300), teams: [h.team, h.opp], link: "#sunday",
    ...(h.final ? { facts: h.final.map(([k, x]) => [clip(k, 30), clip(x, 40)]) } : {}),
  });
  const tile = (h, title) => `<div class="card tile sun-tile"><div class="label">${esc(h.label)}</div><p class="line">${h.line}</p><div class="who">${h.sub}</div>${share(tileStat(h, title))}</div>`;

  // ── one matchup ──────────────────────────────────────────
  function caption(v, g) {
    const n = g.p_home.length, last = v.cps[n - 1];
    const who = `<b>${esc(nm(g.home))}</b>`;
    const start = pair(g.p_home[0])[0];
    if (last.label === "Final") return `${who}'s chance to win started at ${start}.`;
    return `${who}'s chance to win: ${start} before kickoff, ${pair(g.p_home[n - 1])[0]} ${esc(when(v, n - 1))}.`;
  }

  function card(v, g, i, tags) {
    const sc = scores(v, g);
    const lead = sc.home === sc.away ? "" : sc.home > sc.away ? "home" : "away";
    const line = (side) => `<div class="sun-line${lead === side ? " lead" : ""}">${chip(T[g[side]])}<span class="sc num">${f1(sc[side])}</span></div>`;
    return `<article class="card sun-card">
      ${tags.length ? `<div class="sun-tags">${tags.map((t) => `<span class="sun-tag">${esc(t)}</span>`).join("")}</div>` : ""}
      ${line("home")}${line("away")}
      <div class="sun-chart" data-i="${i}"></div>
      <p class="sun-cap">${caption(v, g)}</p>
    </article>`;
  }

  // ── the chart ────────────────────────────────────────────
  // A short x-axis label (6 characters at most) for each checkpoint: "Pre", "Thu", "Early", "Late", "SNF", "Mon", "Final".
  const DAYS = { monday: "Mon", tuesday: "Tue", wednesday: "Wed", thursday: "Thu", friday: "Fri", saturday: "Sat", sunday: "Sun" };
  function short(cp) {
    const label = String(cp.label || ""), slate = String(cp.slate || label.replace(/^After /, "")).toLowerCase().replace(/^the /, "");
    if (/^before/i.test(label)) return "Pre";
    if (label === "Final") return "Final";
    if (slate.startsWith("early")) return "Early";
    if (slate.startsWith("late")) return "Late";
    if (slate === "sunday night") return "SNF";
    if (slate.startsWith("sunday morning")) return "Sun AM";
    const day = (slate.match(/^[a-z]+/) || [""])[0];
    const clock = (slate.match(/\((\d{1,2}:\d{2})/) || [])[1]; // two slates with one name carry their kickoff time
    if (clock) return clock;
    if (DAYS[day]) return slate.includes("afternoon") ? `${DAYS[day]} PM` : DAYS[day];
    return (day || label).slice(0, 6);
  }
  function xLabels(v) {
    const seen = new Map();
    return v.cps.map((cp) => {
      const s = short(cp), n = (seen.get(s) || 0) + 1;
      seen.set(s, n);
      return n > 1 ? `${s.slice(0, 4).trim()} ${n}` : s;
    });
  }

  // One line per matchup: the home team's chance to win after each set of games. lineChart measures its
  // element and redraws when its width changes, so a chart drawn while Home was hidden fills in once it's shown.
  function charts(v, games) {
    const x = xLabels(v);
    $$(".sun-chart", root).forEach((el) => {
      const g = games[+el.dataset.i];
      if (!g) return;
      const pts = (a, k) => (a && a[k] != null ? ` · ${f1(a[k])} pts` : "");
      A.lineChart(el, {
        x, height: 120, yMin: 0, yMax: 1, yTicks: [0, 0.5, 1],
        yFmt: (p) => Math.round(p * 100) + "%",
        series: [{ name: tn(g.home), values: g.p_home, color: "var(--accent)" }],
        xFmt: (k) => v.cps[k].label,
        tipRows: (k) => {
          const [h, a] = pair(g.p_home[k]);
          return [[tn(g.home), h + pts(g.home_pts, k)], [tn(g.away), a + pts(g.away_pts, k)]];
        },
        label: `${tn(g.home)}'s chance to beat ${tn(g.away)} after each set of games: ${x.map((l, k) => `${l} ${pair(g.p_home[k])[0]}`).join(", ")}`,
      });
    });
  }

  let picked = null; // the week the reader chose; null follows the newest
  let showAll = false; // Home stays short: just the games in the headlines until the reader asks for all
  function draw() {
    const vs = views();
    if (!vs.length) { root.hidden = true; return; }
    const v = vs.find((x) => x.key === picked) || vs[0];
    const heads = headlines(v);
    const tagsOf = (g) => heads.filter((h) => (h.team === g.home && h.opp === g.away) || (h.team === g.away && h.opp === g.home)).flatMap((h) => h.tags);
    const games = [...v.games].sort((a, b) => drama(b) - drama(a));
    const featured = games.filter((g) => tagsOf(g).length).length;
    const all = showAll || !featured; // no headline games: show them all
    const hidden = featured && featured < games.length;
    const weekName = (x) => `Week ${x.week}${x.live && !x.done ? " (so far)" : ""}`;
    const title = `Week ${v.week} ${v.live && !v.done ? "so far" : "recap"}`;
    const shareTitle = `Week ${v.week} recap${v.live && !v.done ? " so far" : ""}`;
    const rec = record();
    const method = (D.recap && D.recap.model && D.recap.model.method) || "Each starter still to play counts as his ESPN projection, give or take a typical miss for his position. Points already scored are banked.";
    root.hidden = false;
    root.innerHTML = `<div class="sun-head">
        <div><h2>${esc(title)}</h2>
        <p class="sub">${v.live && !v.done ? "Win chances after each set of games finished so far. " : "Win chances after each set of games finished. "}There's no in-game data, so swings are measured between sets of games (Thursday night, the early games and so on), not at halftime.${rec ? ` Odds come from ESPN's projections, which have been close to a coin flip. ${esc(rec)}` : ""}${v.live && !v.done ? " ESPN sends no game clock, so a game counts as over 3½ hours after kickoff, and games still going aren't counted yet." : ""}</p></div>
        ${vs.length > 1 ? `<select id="sunWeek" aria-label="Choose week">${vs.map((x) => `<option value="${esc(x.key)}"${x.key === v.key ? " selected" : ""}>${esc(weekName(x))}</option>`).join("")}</select>` : ""}
      </div>
      ${heads.length ? `<div class="tiles sun-tiles">${heads.map((h) => tile(h, shareTitle)).join("")}</div>` : ""}
      <div class="sun-grid">${games.map((g, i) => (all || tagsOf(g).length ? card(v, g, i, tagsOf(g)) : "")).join("")}</div>
      ${hidden ? `<button type="button" class="sun-more" aria-expanded="${all}">${all ? "Show just the headline games" : `Show all ${games.length} matchups`}</button>` : ""}
      <p class="method"><b>How the odds work.</b> ${esc(method)}</p>`;
    charts(v, games);
    const sel = $("#sunWeek", root);
    if (sel) sel.addEventListener("change", () => { picked = sel.value; draw(); });
    const more = $(".sun-more", root);
    if (more) more.addEventListener("click", () => { showAll = !showAll; draw(); });
  }

  draw();
  document.addEventListener("live:update", draw);
})();
