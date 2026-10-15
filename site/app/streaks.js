// Awards tab: shame streaks. A counter card for every embarrassing run still going, the
// season's longest run of each kind, and a block on every manager's page. The rules live in
// league/streaks.py; this file only lays them out.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, $, esc, f1, chip } = A;

  const S = D.streaks;
  const ok = S && Array.isArray(S.kinds) && Array.isArray(S.active);
  const root = $("#streaks");
  if (!ok || !root) return;
  const records = Array.isArray(S.records) ? S.records : [];
  // Teams the report covers (every team that has played). Without that list, treat all as covered.
  const covered = Array.isArray(S.teams) ? new Set(S.teams.map((x) => x.team)) : null;

  // Icon and wording per kind. Titles and minimum lengths come from the data; these are the
  // fallbacks for a kind this page doesn't know yet.
  const wk = (n) => (n === 1 ? "week" : "weeks");
  const META = {
    loss:       { icon: "📉", unit: (n) => (n === 1 ? "loss" : "straight losses"),
                  best: "Longest losing streak" },
    under120:   { icon: "🥶", unit: (n) => (n === 1 ? "week under 120" : "weeks in a row under 120"),
                  best: "Most weeks in a row under 120" },
    sub100:     { icon: "🤮", unit: (n) => (n === 1 ? "week under 100" : "weeks in a row under 100"),
                  best: "Most weeks in a row under 100" },
    blunder:    { icon: "🤦", unit: (n) => (n === 1 ? "week with a bench blunder" : "weeks in a row with a bench blunder"),
                  best: "Most bench blunders in a row" },
    under_proj: { icon: "🔻", unit: (n) => (n === 1 ? "week under ESPN's projection" : "weeks in a row under ESPN's projection"),
                  best: "Most weeks in a row under ESPN's projection" },
    dud:        { icon: "🧨", unit: (n) => (n === 1 ? "week starting a dud" : "weeks in a row starting a dud"),
                  best: "Most weeks in a row starting a dud" },
  };
  const kindOf = (key) => S.kinds.find((k) => k.key === key) || { key, title: key, what: "", min: 1 };
  const metaOf = (key) => META[key] || {
    icon: "💩", unit: (n) => `${wk(n)} in a row`, best: `Longest run: ${kindOf(key).title}`,
  };
  // sub100 is the loud tier, under120 the milder "Shameful"; everything else is a plain shame card.
  const tierOf = (key) => (key === "sub100" ? "disgust" : key === "under120" ? "shameful" : "plain");

  const nm = (id) => (T[id] ? T[id].manager || T[id].name : `Team ${id}`);
  const link = (id) => (T[id] ? `<a class="sh-name" href="#manager/${T[id].id}">${esc(nm(id))}</a>` : esc(nm(id)));
  const span = (a, b) => (a === b ? `week ${a}` : `weeks ${a}–${b}`);
  const names = (ids, max = 3) => {
    const shown = ids.slice(0, max).map(link);
    const more = ids.length - shown.length;
    if (more > 0) shown.push(`${more} more`);
    return shown.length < 2 ? shown.join("") : `${shown.slice(0, -1).join(", ")} and ${shown[shown.length - 1]}`;
  };

  // ── "Share to the board" (account.js): one active streak as a plain-text stat ──
  const share = A.shareBtn || (() => "");
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  function streakStat(a) {
    const unit = metaOf(a.key).unit(a.length), d = String(a.detail || "").trim();
    return {
      kind: "streak", title: clip(kindOf(a.key).title, 80),
      text: clip(`${nm(a.team)}: ${a.length} ${unit}.${d ? ` ${d}${/[.!?]$/.test(d) ? "" : "."}` : ""}`, 300),
      facts: [["Length", clip(`${a.length} ${unit}`, 40)], ["Since", `Week ${a.since_week}`]],
      teams: T[a.team] ? [a.team] : [], link: "#streaks",
    };
  }

  // ── counter cards ───────────────────────────────────────
  const order =Object.fromEntries(S.kinds.map((k, i) => [k.key, i]));
  const active = [...S.active].sort((a, b) =>
    (b.key === "sub100") - (a.key === "sub100") || b.length - a.length
    || (order[a.key] ?? 99) - (order[b.key] ?? 99) || nm(a.team).localeCompare(nm(b.team)));

  function card(a) {
    const m = metaOf(a.key), unit = m.unit(a.length);
    return `<article class="card sh-card ${tierOf(a.key)}" aria-label="${esc(`${nm(a.team)}: ${a.length} ${unit}`)}">
      <div class="sh-hd"><span class="sh-ico" aria-hidden="true">${m.icon}</span><h3 class="sh-title">${esc(kindOf(a.key).title)}</h3></div>
      <div class="sh-count"><span class="sh-num num">${a.length}</span><span class="sh-unit">${esc(unit)}</span></div>
      <div class="sh-who">${T[a.team] ? chip(T[a.team]) : esc(nm(a.team))}</div>
      <p class="sh-detail">${esc(a.detail)}</p>
      <div class="sh-foot"><p class="sh-since">Since week ${esc(a.since_week)}</p>${share(streakStat(a))}</div>
    </article>`;
  }

  // ── season records ──────────────────────────────────────
  // "Casey, 4 (weeks 1–4, still going)"; holders with the same weeks share one phrase: "Casey and Riley, 4 each (...)".
  function holders(list) {
    const groups = new Map();
    for (const r of list) {
      const k = `${r.from_week}-${r.to_week}-${!!r.active}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(r);
    }
    return [...groups.values()].map((g) => {
      const r = g[0];
      return `${names(g.map((x) => x.team))}, ${esc(r.length)}${g.length > 1 ? " each" : ""} <span class="dim">(${esc(span(r.from_week, r.to_week))}${r.active ? ", still going" : ""})</span>`;
    }).join("; ");
  }

  function recordRows() {
    const rows = [];
    for (const k of S.kinds) {
      const mine = records.filter((r) => r.key === k.key);
      if (mine.length) {
        rows.push(`<li><b>${esc(metaOf(k.key).best)}:</b> ${holders(mine)}</li>`);
      } else if (k.key === "sub100") {
        const low = S.lowest_score;
        const lowText = low && T[low.team] ? ` Low score so far: ${link(low.team)}, ${f1(low.score)} in week ${esc(low.week)}.` : "";
        rows.push(`<li class="sh-none"><b>${esc(k.title)}</b> (under 100): nobody yet.${lowText}</li>`);
      }
    }
    return rows;
  }

  const rules = `<details class="sh-rules"><summary>How streaks are counted</summary>
    <ul>${S.kinds.map((k) => `<li><b>${esc(k.title)}</b> <span class="dim">(counts from ${esc(k.min)})</span>: ${esc(k.what)}</li>`).join("")}</ul>
    <p>Regular season only. Blunders and duds are judged on final scores, so it's hindsight, and a bench player picked up after his game can't be a blunder. "Under the projection" uses ESPN's pregame projection for the starting lineup. A week without projection data doesn't count.</p>
  </details>`;

  // ── the section ─────────────────────────────────────────
  const recs = recordRows();
  const LIMIT = 6; // the longest few; the rest wait behind a button so the awards aren't buried
  let showAll = false;
  function draw() {
    const shown = showAll ? active : active.slice(0, LIMIT);
    root.innerHTML = `<h2>Shame streaks</h2><p class="sub">Embarrassing runs still going after week ${esc(S.through)}.</p>
      ${active.length
        ? `<div class="sh-grid">${shown.map(card).join("")}</div>`
        : `<div class="card"><div class="empty">Nobody's on a shame streak right now. Give it a week.</div></div>`}
      ${active.length > LIMIT ? `<button type="button" class="sh-more" aria-expanded="${showAll}">${showAll ? "Show just the longest" : `Show all ${active.length} streaks`}</button>` : ""}
      ${recs.length ? `<div class="card sh-records"><h3>Season records</h3><ul class="sh-rec">${recs.join("")}</ul></div>` : ""}
      ${rules}`;
  }
  draw();
  root.addEventListener("click", (e) => { if (e.target.closest(".sh-more")) { showAll = !showAll; draw(); } });
  root.hidden = false;

  // ── manager page ────────────────────────────────────────
  function chipHtml(a) {
    const m = metaOf(a.key);
    return `<li class="sh-row ${tierOf(a.key)}">
      <div class="sh-chip"><b class="num">${esc(a.length)}</b><span>${esc(m.unit(a.length))}</span></div>${share(streakStat(a))}
      <div class="sh-rsub">${esc(kindOf(a.key).title)}, since week ${esc(a.since_week)}. ${esc(a.detail)}</div>
    </li>`;
  }

  A.managerBlocks.push({
    order: 30,
    place: "bottom",
    render(t) {
      if (covered && !covered.has(t.id)) return "";
      const mine = active.filter((a) => a.team === t.id);
      const held = records.filter((r) => r.team === t.id);
      const head = '<h3>Shame streaks</h3><p class="cap">Embarrassing runs still going, and any season record this team holds.</p>';
      if (!mine.length && !held.length) {
        return `<div class="card mg-blk">${head}<div class="empty">Clean sheet. No active shame streaks.</div></div>`;
      }
      const list = mine.length
        ? `<ul class="sh-mine">${mine.map(chipHtml).join("")}</ul>`
        : '<p class="sh-clean">No active shame streaks right now.</p>';
      const rec = held.length ? `<div class="sh-sub-h">Season records</div><ul class="sh-held">${held.map((r) => {
        const others = records.filter((x) => x.key === r.key && x.team !== t.id).map((x) => x.team);
        return `<li><span aria-hidden="true">🏅</span><span><b>${esc(metaOf(r.key).best)}:</b> ${esc(r.length)} <span class="dim">(${esc(span(r.from_week, r.to_week))}${r.active ? ", still going" : ""})</span>${others.length ? `. Shared with ${names(others)}.` : ""}</span></li>`;
      }).join("")}</ul>` : "";
      return `<div class="card mg-blk">${head}${list}${rec}</div>`;
    },
  });
})();
