// Draft tab: every pick graded on points scored vs. where he was taken, team report cards, the
// draft board and a sortable list of all picks. Also adds a "Draft report card" block to every
// manager page. Data: D.draft (league/draft.py).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, teams, $, $$, esc, f1, sgn, chip, tipHtml, headshot } = A;
  const root = $("#draft");
  if (!root) return;

  const heading = (sub) => `<h2>Draft report card</h2><p class="sub">${sub}</p>`;
  const R = D.draft;
  if (!R || !Array.isArray(R.picks) || !R.picks.length || !Array.isArray(R.teams)) {
    root.hidden = false;
    root.innerHTML = heading("How every draft pick has done against where he was taken.")
      + '<div class="card empty">No draft data yet.</div>';
    return;
  }

  // ── small helpers ───────────────────────────────────────
  const ord = (n) => { const v = n % 100, s = ["th", "st", "nd", "rd"]; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const signed = (n) => (n > 0 ? "+" + n : n < 0 ? "−" + Math.abs(n) : "0");
  const meta = (p) => [p.pos, p.pro_team].filter((x) => x && x !== "?").join(" · ");
  const initialsOf = (name) => String(name || "?").split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase() || "?";

  const through = R.through;
  const picks = [...R.picks].sort((a, b) => a.pick - b.pick);
  const byPick = new Map(picks.map((p) => [p.pick, p]));
  const pickOf = (n) => (n == null ? null : byPick.get(n) || null);
  const graded = picks.filter((p) => p.skill);
  const nGraded = graded.length;
  const perTeam = {};
  for (const p of picks) perTeam[p.team] = (perTeam[p.team] || 0) + 1;

  // Players tied on points share a rank; say so wherever a rank is shown.
  const sharing = new Map();
  for (const p of graded) sharing.set(p.points, (sharing.get(p.points) || 0) + 1);
  const isTied = (p) => p.skill && sharing.get(p.points) > 1;
  const rankTxt = (p) => `${isTied(p) ? "tied for " : ""}${ord(p.points_rank)}`;

  // Manager first name, with the team name added when two teams share a manager.
  const mgrCount = {};
  teams.forEach((t) => { if (t.manager) mgrCount[t.manager] = (mgrCount[t.manager] || 0) + 1; });
  const mgr = (id) => {
    const t = T[id];
    if (!t) return "Someone";
    if (!t.manager) return t.name;
    return mgrCount[t.manager] > 1 ? `${t.manager} (${t.name})` : t.manager;
  };

  // "J. Herbert", "A. St. Brown", "Chargers" (head coaches). Suffixes like Jr. and IV are dropped.
  const SUFFIX = /^(jr\.?|sr\.?|ii|iii|iv|v)$/i, PARTICLE = /^(st\.?|van|von|de|del|di|du|la|le)$/i;
  function shortName(p) {
    const name = String(p.name || "?").trim();
    if (p.pos === "HC") return name.replace(/\s+coach$/i, "");
    const w = name.split(/\s+/);
    if (w.length < 2 || p.pos === "D/ST") return name;
    let last = w.length - 1;
    while (last > 1 && SUFFIX.test(w[last])) last--;
    const from = last > 1 && PARTICLE.test(w[last - 1]) ? last - 1 : last;
    return `${w[0][0]}. ${w.slice(from, last + 1).join(" ")}`;
  }

  // What happened to him since the draft. Long form for tooltips and tiles, short form for the list.
  const VERB = { dropped: "Dropped", traded: "Traded" };
  const when = (p, short) => (p.let_go_week
    ? (short ? `wk ${p.let_go_week}` : `in week ${p.let_go_week}`)
    : (short ? `after wk ${through}` : `after week ${through}`));
  function fateLong(p) {
    const now = p.now_team == null ? "now a free agent" : `now with ${mgr(p.now_team)}`;
    if (p.status === "kept") return p.let_go_week ? `Still on the roster. Let go in week ${p.let_go_week}, then got him back` : "Still on the roster";
    if (p.status === "gone") return `Off the roster, ${now}. ESPN's log doesn't say how he left`;
    if (VERB[p.status]) return `${VERB[p.status]} ${when(p)}, ${now}`;
    return "Unknown";
  }
  function fateShort(p) {
    if (p.status === "kept") return "Kept";
    const now = p.now_team == null ? "free agent" : mgr(p.now_team);
    if (p.status === "gone") return `Gone · ${now}`;
    if (VERB[p.status]) return `${VERB[p.status]} ${when(p, true)} · ${now}`;
    return "–";
  }

  // ── headshots (a broken image falls back to initials) ───
  function shot(p) {
    const src = headshot(p);
    const ini = initialsOf(p.name);
    return `<div class="dft-shot" data-ini="${esc(ini)}">${src ? `<img src="${esc(src)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<span class="dft-ph">${esc(ini)}</span>`}</div>`;
  }
  function wireShots(scope) {
    $$(".dft-shot img", scope).forEach((img) => {
      const fallback = () => {
        const box = img.parentElement;
        const ph = document.createElement("span");
        ph.className = "dft-ph";
        ph.textContent = box.dataset.ini || "?";
        box.replaceChildren(ph);
      };
      img.addEventListener("error", fallback, { once: true });
      if (img.complete && img.currentSrc && !img.naturalWidth) fallback();
    });
  }

  // ── "Share to the board" (account.js): plain-text stats for the tiles and report cards ──
  const share = A.shareBtn || (() => "");
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  function pickStat(title, p, text) {
    const facts = [["Pick", `${p.pick} (round ${p.round})`], ["Points", f1(p.points)]];
    if (p.skill) facts.push(["Points rank", `${rankTxt(p)} of ${nGraded}`]);
    facts.push(["Status", clip(fateShort(p), 40)]);
    return { kind: "draft", title, text: clip(text, 300), facts, teams: [p.team], link: "#draft" };
  }

  // ── highlight tiles ─────────────────────────────────────
  const H = R.highlights || {};
  function tile(label, p, line, note, empty, stat) {
    if (!p) return `<div class="card tile dft-tile"><div class="label">${esc(label)}</div><div class="who dim">${esc(empty)}</div></div>`;
    return `<div class="card tile dft-tile">
      <div class="label">${esc(label)}</div>
      <div class="dft-top">${shot(p)}<div class="dft-id">
        <div class="dft-name">${esc(p.name)}</div>
        <div class="dft-meta">${esc(meta(p))}</div>
        <div class="who">Taken by <b>${esc(mgr(p.team))}</b></div>
      </div></div>
      <div class="dft-line">${line}</div>
      ${note ? `<div class="dft-note">${note}</div>` : ""}
      ${stat ? share(stat) : ""}
    </div>`;
  }
  const span = through === 1 ? "week 1" : `weeks 1–${through}`;
  const standing = (p) => `Pick ${p.pick} · ${esc(rankTxt(p))} in points among drafted skill players`;
  const season = (p) => `${f1(p.points)} pts in ${span}, on any roster · ${esc(fateLong(p))}`;

  function tilesHtml() {
    const steal = pickOf(H.steal), bust = pickOf(H.bust), worst = pickOf(H.worst_first_rounder);
    const best = pickOf(H.best_first_rounder), cut = pickOf(H.earliest_cut);
    // The same picks as plain sentences, for the Share buttons.
    const ranked = (p) => `${mgr(p.team)} took ${p.name} at pick ${p.pick}. He's ${rankTxt(p)} in points among drafted skill players (${f1(p.points)} pts).`;
    return [
      tile("Steal of the draft", steal, steal && standing(steal), steal && season(steal), "Needs a finished week.",
        steal && pickStat("Steal of the draft", steal, ranked(steal))),
      tile("Biggest bust", bust, bust && standing(bust), bust && season(bust), "Needs a finished week.",
        bust && pickStat("Biggest bust", bust, ranked(bust))),
      tile("Worst first-rounder", worst,
        worst && `Pick ${worst.pick} · ${f1(worst.points)} pts, the fewest in round 1`,
        worst && `${esc(fateLong(worst))}${best && best !== worst ? `. Best of round 1: ${esc(best.name)}, ${f1(best.points)} pts` : ""}`,
        "No first-round picks.",
        worst && pickStat("Worst first-rounder", worst, `${mgr(worst.team)} took ${worst.name} at pick ${worst.pick}. ${f1(worst.points)} pts so far, the fewest of any first-round pick.`)),
      tile("Earliest cut", cut,
        cut && `Pick ${cut.pick} · cut ${esc(when(cut))}`,
        cut && `${f1(cut.points)} pts in ${span}, on any roster · now ${esc(cut.now_team == null ? "a free agent" : "with " + mgr(cut.now_team))}`,
        "Nobody has dropped a pick yet.",
        cut && pickStat("Earliest cut", cut, `${mgr(cut.team)} took ${cut.name} at pick ${cut.pick} and cut him ${when(cut)}.`)),
    ].join("");
  }

  // Facts straight from the picks, so they stay true as the data changes.
  function factsHtml() {
    const r1 = picks.filter((p) => p.round === 1);
    const qbs = r1.filter((p) => p.pos === "QB").length;
    const off = picks.find((p) => !p.skill && p.pos !== "?");
    return [
      r1.length && qbs * 2 > r1.length ? `${qbs} of the ${r1.length} first-round picks were QBs.` : "",
      off ? `The first kicker, head coach or defensive player went at pick ${off.pick}.` : "",
    ].filter(Boolean).map(esc).join(" ");
  }

  // ── team report cards ───────────────────────────────────
  const rows = R.teams.filter((r) => T[r.team]);
  const rowOf = (id) => R.teams.find((r) => r.team === id) || null;
  const gradeTxt = (g) => (g ? esc(String(g).replace("-", "−")) : "–");
  const gradeTone = (g) => (!g ? "" : g[0] === "A" ? "up" : g[0] === "D" || g[0] === "F" ? "down" : "");
  const pickLine = (p) => (p
    ? `<b>${esc(p.name)}</b> <span class="dim">#${p.pick} · ${esc(rankTxt(p))} in points</span>`
    : '<span class="dim">–</span>');

  // A team's draft as a shareable stat ("Jordan's draft: A+, 1st of 12. Best pick ... Worst pick ..."); none until it has a grade.
  function gradeStat(r) {
    if (!r.grade || !T[r.team]) return null;
    const g = String(r.grade).replace("-", "−"), best = pickOf(r.best_pick), worst = pickOf(r.worst_pick);
    const rank = r.rank ? `${ord(r.rank)} of ${R.teams_n}` : "";
    const facts = [["Grade", g]];
    if (rank) facts.push(["Rank", rank]);
    if (best) facts.push(["Best pick", clip(`${best.name} #${best.pick}`, 40)]);
    if (worst) facts.push(["Worst pick", clip(`${worst.name} #${worst.pick}`, 40)]);
    if (r.kept != null) facts.push(["Kept", `${r.kept} of ${perTeam[r.team] || 0}`]);
    return {
      kind: "draft", title: "Draft report card",
      text: clip(`${mgr(r.team)}'s draft: ${g}${rank ? `, ${rank}` : ""}.${best ? ` Best pick ${best.name} #${best.pick}.` : ""}${worst ? ` Worst pick ${worst.name} #${worst.pick}.` : ""}`, 300),
      facts, teams: [r.team], link: "#draft",
    };
  }
  const gradeBtn = (r) => { const s = gradeStat(r); return s ? share(s) : ""; };

  function cardHtml(r) {
    const t = T[r.team];
    const tip = r.graded ? tipHtml(`${mgr(r.team)}'s draft`, [
      ["Avg spots vs. slot", sgn(r.value_avg)], ["Graded picks", String(r.graded)],
      ["Points, all picks", f1(r.points)],
      ...(r.kept == null ? [] : [[`Points, the ${r.kept} kept`, f1(r.kept_points)]]),
    ]) : "";
    return `<article class="card dft-card">
      <div class="dft-gr"><div class="dft-grade ${gradeTone(r.grade)}"${tip ? ` data-tip="${tip}"` : ""}>${gradeTxt(r.grade)}</div>
        ${r.rank ? `<div class="dft-rk">${ord(r.rank)} of ${R.teams_n}</div>` : ""}</div>
      <div class="dft-bd">
        <div class="dft-who">${chip(t)}</div>
        <dl class="dft-facts">
          <div><dt>Best</dt><dd>${pickLine(pickOf(r.best_pick))}</dd></div>
          <div><dt>Worst</dt><dd>${pickLine(pickOf(r.worst_pick))}</dd></div>
          ${r.kept == null ? "" : `<div><dt>Kept</dt><dd><b>${r.kept}</b> of ${perTeam[r.team] || 0}</dd></div>`}
        </dl>
        ${gradeBtn(r)}
      </div>
    </article>`;
  }

  // Ties for the most picks kept are common; the tiebreak is points from the kept picks.
  function keptLine() {
    const held = rows.filter((r) => r.kept != null);
    if (!held.length) return "";
    const most = Math.max(...held.map((r) => r.kept));
    const tied = held.filter((r) => r.kept === most);
    const top = [...tied].sort((a, b) => b.kept_points - a.kept_points)[0];
    return tied.length === 1
      ? `${esc(mgr(top.team))} kept the most picks: ${most} of ${perTeam[top.team] || 0}.`
      : `${tied.length} teams kept ${most} picks, the most. ${esc(mgr(top.team))}'s kept picks scored the most.`;
  }

  // ── draft board ─────────────────────────────────────────
  // Tint = how far above or below his slot he finished, as a share of the graded picks.
  const MILD = 0.15, STRONG = 0.4;
  const up = (p) => p.skill && p.value > 0 && p.points > 0; // a pick who scored nothing is never a steal
  function tone(p) {
    if (!p.skill) return "na";
    const k = p.value / nGraded;
    if (up(p)) return k >= STRONG ? "s2" : k >= MILD ? "s1" : "";
    return k <= -STRONG ? "b2" : k <= -MILD ? "b1" : "";
  }

  function tipFor(p) {
    const rows2 = [["Pick", `${p.pick} · round ${p.round}`], ["Drafted by", mgr(p.team)], ["Points", f1(p.points)]];
    if (p.skill) rows2.push(["Taken", `${ord(p.order)} skill player`], ["Points rank", `${rankTxt(p)} of ${nGraded}`]);
    else rows2.push(["Graded", "No, different scale"]);
    rows2.push(["Status", fateLong(p)]);
    return tipHtml(`${p.name}${meta(p) ? " · " + meta(p) : ""}`, rows2);
  }

  function cellHtml(p) {
    return `<div class="dft-c ${tone(p)}" data-tip="${tipFor(p)}"><span class="nm">${esc(shortName(p))}</span>`
      + `<span class="ln"><span>${esc(p.pos)} ${f1(p.points)}</span>${p.skill ? `<b>${signed(p.value)}</b>` : ""}</span></div>`;
  }

  // Columns follow the round-1 pick order; each cell is that team's pick in that round.
  const slots = picks.filter((p) => p.round === 1).sort((a, b) => a.round_pick - b.round_pick).map((p) => p.team);
  const cols = [...new Set([...slots, ...picks.map((p) => p.team)])];
  const cells = new Map();
  for (const p of picks) cells.set(p.round + ":" + p.team, [...(cells.get(p.round + ":" + p.team) || []), p]);
  const rounds = Array.from({ length: R.rounds || Math.max(...picks.map((p) => p.round)) }, (_, i) => i + 1);

  const LEGEND = [["s2", "Big steal"], ["s1", "Steal"], ["", "About right"], ["b1", "Bust"], ["b2", "Big bust"], ["na", "Not graded"]];
  function boardHtml() {
    const head = `<tr><th class="rd" scope="col">Rd</th>${cols.map((id, i) => {
      const t = T[id];
      const tip = t ? ` data-tip="${tipHtml(t.name, [["Manager", t.manager || "–"], ["Round 1 slot", `#${i + 1}`]])}"` : "";
      return `<th scope="col"><a class="dft-col" href="#manager/${id}"${tip}><span class="slot">${i + 1}</span>${esc(mgr(id))}</a></th>`;
    }).join("")}</tr>`;
    const body = rounds.map((r) => `<tr><th class="rd" scope="row">${r}</th>${cols.map((id) => `<td>${(cells.get(r + ":" + id) || []).map(cellHtml).join("")}</td>`).join("")}</tr>`).join("");
    return `<div class="card tbl-wrap"><table class="dft-board" aria-label="Draft board: rounds down, teams across"><thead>${head}</thead><tbody>${body}</tbody><tfoot>${head}</tfoot></table></div>
      <div class="dft-legend">${LEGEND.map(([c, label]) => `<span><i class="dft-sw ${c}"></i>${label}</span>`).join("")}</div>
      <p class="note">Rounds run down, teams run across in round-1 pick order. The number in each cell is how many spots above (+) or below (−) his draft slot he finished in points, among skill players. Tap or hover a cell for details.</p>`;
  }

  // ── list of every pick ──────────────────────────────────
  let sort = { k: "pick", dir: 1 };
  const STATUS_RANK = { kept: 0, traded: 1, dropped: 2, gone: 3 };
  const KEYS = {
    pick: (p) => p.pick, name: (p) => p.name.toLowerCase(), pos: (p) => p.pos, team: (p) => mgr(p.team).toLowerCase(),
    points: (p) => p.points, value: (p) => p.value, status: (p) => (p.status in STATUS_RANK ? STATUS_RANK[p.status] : null),
  };
  function sortedPicks() {
    const key = KEYS[sort.k];
    return [...picks].sort((a, b) => {
      const x = key(a), y = key(b);
      if (x == null || y == null) return x == null && y == null ? a.pick - b.pick : x == null ? 1 : -1; // blanks last
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir || a.pick - b.pick;
    });
  }

  function listHtml() {
    const th = (k, label, cls = "") => {
      const on = sort.k === k;
      return `<th class="${cls}" aria-sort="${on ? (sort.dir > 0 ? "ascending" : "descending") : "none"}"><button type="button" class="dft-sort${on ? " on" : ""}" data-k="${k}">${label}<span class="arr" aria-hidden="true">${on ? (sort.dir > 0 ? "▲" : "▼") : ""}</span></button></th>`;
    };
    const back = picks.some((p) => p.status === "kept" && p.let_go_week);
    const body = sortedPicks().map((p) => {
      const val = !p.skill ? '<span class="dim">–</span>' : `<span class="${up(p) ? "pos" : p.value < 0 ? "neg" : "dim"}">${signed(p.value)}</span>`;
      const star = p.status === "kept" && p.let_go_week;
      return `<tr><td class="n">${p.pick}</td>
        <td><b>${esc(p.name)}</b> <span class="dim">${esc(p.pro_team)}</span></td>
        <td>${esc(p.pos)}</td>
        <td><a class="dft-tl" href="#manager/${p.team}"${T[p.team] ? ` title="${esc(T[p.team].name)}"` : ""}>${esc(mgr(p.team))}</a></td>
        <td class="n">${f1(p.points)}</td>
        <td class="n">${val}</td>
        <td${star ? ` title="${esc(fateLong(p))}"` : ""}>${esc(fateShort(p))}${star ? "*" : ""}</td></tr>`;
    }).join("");
    return `<div class="card tbl-wrap"><table class="dft-list"><thead><tr>${th("pick", "#", "n")}${th("name", "Player")}${th("pos", "Pos")}${th("team", "Team")}${th("points", "Pts", "n")}${th("value", "Value", "n")}${th("status", "Status")}</tr></thead><tbody>${body}</tbody></table></div>
      <p class="note">Value is how many spots above (+) or below (−) his draft slot he finished in points, among skill players. Tap a column to sort.${back ? " * Let go earlier, then got him back." : ""}</p>`;
  }

  // ── the page ────────────────────────────────────────────
  const facts = factsHtml();
  const byRank = [...rows].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99) || a.team - b.team);
  root.innerHTML = heading(`Every pick graded on points so far (${span}, wherever he played) against where he was taken, among QBs, RBs, WRs and TEs. Kickers, head coaches and defensive players are listed but not graded because they score on a different scale. Grades are on a curve.`)
    + `<div class="tiles dft-tiles">${tilesHtml()}</div>
    ${facts ? `<p class="note dft-facts-line">${facts}</p>` : ""}
    <p class="note">Steal and bust compare where a player was taken with where he ranks in points, among drafted QBs, RBs, WRs and TEs. Earliest cut is the highest pick dropped by the team that took him.</p>
    <h3 class="dft-h3">Team report cards</h3>
    <p class="sub">Best average pick first. The best draft gets the A+, the worst gets the F, and everyone else lands in between.</p>
    <div class="dft-cards">${byRank.map(cardHtml).join("")}</div>
    ${keptLine() ? `<p class="note">${keptLine()}</p>` : ""}
    <h3 class="dft-h3" id="dftHead">Draft board</h3>
    <div class="controls dft-controls">
      <div class="seg dft-seg" role="group" aria-label="View">
        <button type="button" data-mode="board" aria-pressed="true">Board</button>
        <button type="button" data-mode="list" aria-pressed="false">List</button>
      </div>
      <span class="count">${picks.length} picks · ${nGraded} graded</span>
    </div>
    <div id="dftView"></div>
    <p class="method"><b>How picks are graded.</b> Each QB, RB, WR and TE is ranked twice: by where he was taken among those four positions, and by points scored so far (this league's exact scoring, on any team or in free agency). The gap is his value: positive means he finished above his draft slot, negative means below it. Players tied on points share a rank, so a late pick who scored nothing can still show a small plus. A team's grade comes from the average value of its graded picks, curved across the league: the best average gets the A+, the worst gets the F, and teams with the same average share a grade. Status comes from ESPN's activity log. "Gone" means he's off the roster and the log shows no drop or trade for him.</p>`;
  root.hidden = false;

  let mode = "board";
  const view = $("#dftView", root);
  function drawView() {
    view.innerHTML = mode === "board" ? boardHtml() : listHtml();
    $("#dftHead", root).textContent = mode === "board" ? "Draft board" : "Every pick";
    $$(".dft-seg button", root).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
  }
  drawView();
  wireShots(root);

  root.addEventListener("click", (e) => {
    const m = e.target.closest("button[data-mode]");
    if (m && m.dataset.mode !== mode) {
      mode = m.dataset.mode;
      drawView();
      return;
    }
    const s = e.target.closest("button[data-k]");
    if (!s) return;
    const k = s.dataset.k;
    sort = sort.k === k ? { k, dir: -sort.dir } : { k, dir: k === "points" || k === "value" ? -1 : 1 };
    drawView();
    const again = root.querySelector(`.dft-sort[data-k="${k}"]`);
    if (again) again.focus();
  });

  // ── a block on every manager page ───────────────────────
  if (Array.isArray(A.managerBlocks)) {
    A.managerBlocks.push({
      order: 40,
      place: "bottom",
      render(t) {
        const r = rowOf(t.id);
        if (!r) return "";
        const stats = [
          ["Grade", `<span class="dft-g ${gradeTone(r.grade)}">${gradeTxt(r.grade)}</span>`],
          ["Rank", r.rank ? `${ord(r.rank)}<span class="dft-of"> of ${R.teams_n}</span>` : "–"],
          r.kept == null ? null : ["Kept", `${r.kept}<span class="dft-of"> of ${perTeam[t.id] || 0}</span>`],
        ].filter(Boolean);
        const best = pickOf(r.best_pick), worst = pickOf(r.worst_pick);
        const picksList = best || worst
          ? `<ul class="dft-mg"><li><span class="k">Best pick</span><span class="v">${pickLine(best)}</span></li>
              <li><span class="k">Worst pick</span><span class="v">${pickLine(worst)}</span></li></ul>` : "";
        return `<div class="card mg-blk"><h3>Draft report card</h3><p class="cap">How this team's picks did against where they were taken.</p>
          <dl class="mg-odds">${stats.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>
          ${picksList}
          <p class="mg-foot dft-mg-foot"><a href="#draft">Full draft report ›</a>${gradeBtn(r)}</p></div>`;
      },
    });
  }
})();
