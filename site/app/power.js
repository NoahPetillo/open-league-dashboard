// Home tab: power rankings, plus App.powerFor(teamId) for the manager page.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, $, esc, f1, chip, tipHtml } = A;

  const P = D.power;
  const weeks = P && Array.isArray(P.weeks) ? P.weeks.filter((w) => w.teams && w.teams.length) : [];
  const latest = weeks[weeks.length - 1];
  const blurbOf = Object.fromEntries(((P && P.blurbs) || []).map((b) => [b.team, b.text]));
  const rowOf = (w, id) => w.teams.find((r) => r.team === id);

  // Everything the manager page needs about one team, or null when we have no rankings for it.
  A.powerFor = (teamId) => {
    const r = latest && rowOf(latest, +teamId);
    if (!r) return null;
    const history = weeks.flatMap((w) => {
      const x = rowOf(w, r.team);
      return x ? [{ week: w.week, rank: x.rank, score: x.score }] : [];
    });
    return { rank: r.rank, change: r.change, score: r.score, blurb: blurbOf[r.team] || "", history };
  };

  const sec = $("#power");
  if (!sec) return;
  if (!latest) { sec.hidden = true; return; }

  const TOP = 6; // phones show this many until "Show all"
  const n = latest.teams.length;
  const prevWeek = weeks.length > 1 ? weeks[weeks.length - 2].week : null;
  const pc = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
  const formLabel = weeks.length >= 3 ? "Last 3 weeks" : `Last ${weeks.length} week${weeks.length === 1 ? "" : "s"}`;

  function move(r) {
    const c = r.change;
    if (!c) {
      const why = c === 0 ? `No change from week ${prevWeek}` : "First week of rankings";
      return `<span class="p-mv" role="img" aria-label="${esc(why)}" data-tip="${tipHtml(why, [])}">–</span>`;
    }
    const up = c > 0, k = Math.abs(c);
    const why = `${up ? "Up" : "Down"} ${k} from week ${prevWeek}`;
    return `<span class="p-mv ${up ? "up" : "down"}" role="img" aria-label="${esc(why)}" data-tip="${tipHtml(why, [["Last week", "#" + (r.rank + c)]])}">${up ? "▲" : "▼"}${k}</span>`;
  }

  // Tiny rank-by-week line: rank 1 at the top, same scale for every team.
  function spark(id) {
    const hist = A.powerFor(id).history;
    if (hist.length < 2) return "";
    const W = 84, H = 24, pad = 4;
    const x = (i) => pad + (i / (hist.length - 1)) * (W - 2 * pad);
    const y = (rank) => pad + ((rank - 1) / Math.max(1, n - 1)) * (H - 2 * pad);
    const pts = hist.map((h, i) => `${x(i).toFixed(1)},${y(h.rank).toFixed(1)}`);
    const last = hist[hist.length - 1];
    const tip = tipHtml("Power rank by week", hist.map((h) => [`Week ${h.week}`, "#" + h.rank]));
    return `<svg class="p-spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Rank by week: ${esc(hist.map((h) => "#" + h.rank).join(", "))}" data-tip="${tip}"><polyline points="${pts.join(" ")}" fill="none" stroke="var(--axis)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${x(hist.length - 1).toFixed(1)}" cy="${y(last.rank).toFixed(1)}" r="3" fill="var(--accent)"/></svg>`;
  }

  function scoreTip(r, t) {
    return tipHtml(t.name, [
      ["Power score", f1(r.score)],
      ["All-play record", r.allplay ? `${r.allplay} (${pc(r.allplay_pct)})` : "–"],
      [formLabel, r.form_avg == null ? "–" : `${f1(r.form_avg)} a game`],
      ["Actual record", `${r.record} (${pc(r.win_pct)})`],
    ]);
  }

  // The row as a plain-text stat for "Share to the board" (account.js; the button is hidden unless you're signed in).
  const share = A.shareBtn || (() => "");
  function stat(r, t) {
    const blurb = blurbOf[r.team] || "";
    const sentence = `#${r.rank} in the power rankings: ${t.manager || t.name}.${blurb ? ` ${/[.!?]$/.test(blurb) ? blurb : blurb + "."}` : ""}`;
    const facts = [["Power score", f1(r.score)], ["Record", String(r.record)]];
    if (r.allplay) facts.push(["All-play", String(r.allplay)]);
    if (r.change != null) facts.push(["Move", r.change ? `${r.change > 0 ? "Up" : "Down"} ${Math.abs(r.change)}` : "No change"]);
    return { kind: "power", title: `Week ${latest.week} power rankings`, text: sentence.slice(0, 300), facts, teams: [r.team], link: "#power" };
  }

  function row(r, i) {
    const t = T[r.team];
    if (!t) return "";
    const width = Math.max(0, Math.min(100, r.score));
    const cls = ["prow", i >= TOP ? "more" : "", i === TOP - 1 ? "tail" : ""].filter(Boolean).join(" ");
    return `<li class="${cls}">
      <span class="p-rk num r${Math.min(r.rank, 4)}">${r.rank}</span>
      ${move(r)}
      <span class="p-team">${chip(t)}</span>
      <span class="p-why">${esc(blurbOf[r.team] || "")}${share(stat(r, t))}</span>
      <span class="p-rec num">${esc(r.record)}</span>
      <span class="p-score" data-tip="${scoreTip(r, t)}"><b class="num">${f1(r.score)}</b><span class="p-bar"><i style="width:${width}%"></i></span></span>
      <span class="p-trend">${spark(r.team)}</span>
    </li>`;
  }

  sec.innerHTML = `<h2>Power rankings</h2>
    <p class="sub">Week ${latest.week}. ${esc(P.method)}.</p>
    <div class="card power-card">
      <ol class="power-list${n > TOP ? " collapsed" : ""}" id="powerList">${latest.teams.map(row).join("")}</ol>
      ${n > TOP ? `<button type="button" class="power-more" id="powerMore" aria-expanded="false" aria-controls="powerList">Show all ${n}</button>` : ""}
    </div>`;

  const more = $("#powerMore");
  if (more) more.addEventListener("click", () => {
    const list = $("#powerList");
    const open = list.classList.toggle("collapsed") === false;
    more.setAttribute("aria-expanded", String(open));
    more.textContent = open ? `Show top ${TOP}` : `Show all ${n}`;
  });
})();
