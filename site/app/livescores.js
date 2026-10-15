// Live tab: this week's lineups, re-read from ESPN every 5 minutes.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, MY_TEAM, teams, T, ranked, $, $$, esc, f1, sgn, cls, pct, fmtDate, chip, tipHtml, divergingBars, onRoute } = A;

  let liveSel = null, showBench = false;
  try { liveSel = localStorage.getItem("liveMatchup"); } catch (e) {}
  const SLOT_LABEL = { "RB/WR/TE": "FLX", "D/ST": "DST", "OP": "SFX" };
  const DAY = (iso) => new Date(iso).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
  const INJ = { OUT: "O", QUESTIONABLE: "Q", DOUBTFUL: "D", DAY_TO_DAY: "DTD", INJURY_RESERVE: "IR", SUSPENSION: "SSPD" };
  const ago = (iso) => {
    const m = Math.round((Date.now() - new Date(iso)) / 60000);
    return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} hr ago` : `${Math.round(m / 1440)} days ago`;
  };
  const shortName = (p) => {
    const parts = p.name.split(" ");
    return p.pos === "HC" || parts.length < 2 ? p.name : `${parts[0][0]}. ${parts.slice(1).join(" ")}`;
  };
  function playerCell(p, right) {
    if (!p) return `<div class="pl empty ${right ? "r" : ""}"><div class="who"><div class="nm">Empty</div></div></div>`;
    const status = p.status === "live" ? '<span class="lv">● Live</span>'
      : p.status === "upcoming" ? (p.kickoff ? DAY(p.kickoff) : "Not played")
      : p.status === "bye" ? "Bye" : "Final";
    const inj = p.injury ? `<span class="inj" title="${esc(p.injury.replace(/_/g, " ").toLowerCase())}">${esc(INJ[p.injury] || p.injury.slice(0, 3))}</span>` : "";
    const pts = p.status === "upcoming" || p.status === "bye" ? '<b class="dim">–</b>' : `<b>${f1(p.points)}</b>`;
    const tp = tipHtml(p.name, [["Position", `${p.pos} · ${p.team || "FA"}`], ["Points", f1(p.points)], ["ESPN projection", f1(p.projected)], ["Game", p.status === "upcoming" && p.kickoff ? DAY(p.kickoff) : p.status]]);
    return `<div class="pl ${right ? "r" : ""}" data-tip="${tp}"><div class="who"><div class="nm"><span class="full">${esc(p.name)}</span><span class="short">${esc(shortName(p))}</span>${inj}</div><div class="st"><span class="posx">${esc(p.pos)} · </span>${esc(p.team || "FA")} · ${status}</div></div><div class="pts">${pts}<small>proj ${f1(p.projected)}</small></div></div>`;
  }
  function pairRows(a, b, labelOf) {
    // Align the two lineups slot by slot (same slot → same row).
    const groups = [];
    const idx = {};
    for (const [side, list] of [["a", a], ["b", b]]) for (const p of list) {
      const k = labelOf(p);
      if (!(k in idx)) { idx[k] = groups.length; groups.push({ k, a: [], b: [] }); }
      groups[idx[k]][side].push(p);
    }
    return groups.flatMap((g) => Array.from({ length: Math.max(g.a.length, g.b.length) }, (_, i) =>
      `<div class="lrow">${playerCell(g.a[i], false)}<div class="slot">${esc(SLOT_LABEL[g.k] || g.k)}</div>${playerCell(g.b[i], true)}</div>`)).join("");
  }
  function drawLive() {
    const LV = window.LIVE_DATA;
    if (!LV || !LV.matchups || !LV.matchups.length) {
      $("#liveMeta").textContent = "No live data yet. Run: uv run python scripts/build_site.py --live";
      $("#matchups").innerHTML = ""; $("#h2h").innerHTML = "";
      return;
    }
    const anyLive = LV.matchups.some((m) => m.home.playing + m.away.playing > 0);
    const left = LV.matchups.reduce((n, m) => n + m.home.yet_to_play + m.away.yet_to_play, 0);
    $("#liveTitle").textContent = `Week ${LV.week} lineups`;
    $("#liveMeta").innerHTML = `<span class="dot ${anyLive ? "on" : ""}"></span><span>${anyLive ? "Games in progress" : left ? `${left} starters yet to play` : "All games final"} · updated ${esc(ago(LV.generated_at))}</span>`;
    const key = (m) => `${m.home.team}-${m.away.team}`;
    let sel = LV.matchups.find((m) => key(m) === liveSel) || (MY_TEAM && LV.matchups.find((m) => m.home.team === MY_TEAM || m.away.team === MY_TEAM)) || LV.matchups[0];
    $("#matchups").innerHTML = LV.matchups.map((m) => {
      const lead = m.home.score === m.away.score ? null : m.home.score > m.away.score ? "home" : "away";
      const ln = (s, w) => `<div class="ln ${lead === w ? "lead" : ""}"><span>${esc(T[s.team]?.name || s.team)}</span><b>${f1(s.score)}</b></div>`;
      return `<button class="mu" data-key="${key(m)}" aria-pressed="${m === sel}">${ln(m.home, "home")}${ln(m.away, "away")}</button>`;
    }).join("");
    const H = sel.home, A = sel.away;
    const side = (s, right) => `<div class="tm ${right ? "r" : ""}">${chip(T[s.team])}<div class="score">${f1(s.score)}</div><div class="score-sub">proj ${f1(s.projected)} · ${s.yet_to_play ? `${s.yet_to_play} yet to play` : s.playing ? `${s.playing} playing` : "done"}</div></div>`;
    const benchLabel = (p) => (p.slot === "IR" ? "IR" : "BN");
    $("#h2h").innerHTML = `<div class="h2h-top">${side(H, false)}<span class="vs">VS</span>${side(A, true)}</div>
      ${pairRows(H.starters, A.starters, (p) => p.slot)}
      ${showBench ? `<div class="bench-head">Bench</div>${pairRows(H.bench, A.bench, benchLabel)}` : ""}
      <button class="bench-toggle" aria-expanded="${showBench}">${showBench ? "Hide bench" : `Show bench (${H.bench.length} · ${A.bench.length})`}</button>`;
  }
  $("#matchups").addEventListener("click", (e) => {
    const b = e.target.closest(".mu"); if (!b) return;
    liveSel = b.dataset.key;
    try { localStorage.setItem("liveMatchup", liveSel); } catch (err) {}
    drawLive();
  });
  $("#h2h").addEventListener("click", (e) => {
    if (e.target.closest(".bench-toggle")) { showBench = !showBench; drawLive(); }
  });
  drawLive();
  // Every 5 minutes, re-read this week's lineups from ESPN (in the page's Python worker, see
  // start.js), then tell anything else built on window.LIVE_DATA (upset alert, Sunday recap)
  // to redraw. Skipped while the tab is in the background.
  setInterval(async () => {
    if (document.hidden || !window.OpenLeague) return;
    try {
      window.LIVE_DATA = await window.OpenLeague.refreshLive();
      drawLive();
      document.dispatchEvent(new CustomEvent("live:update"));
    } catch (err) { console.warn("Live refresh failed:", err.message); }
  }, 5 * 60 * 1000);
})();
