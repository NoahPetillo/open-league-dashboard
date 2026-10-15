// Awards tab: the week's award cards and the season trophy case.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, teams, T, $, $$, esc, f1, chip, tipHtml, headshot, onRoute } = A;

  // Icon, tone and unit per award key. Titles come from the data (these are fallbacks).
  //   good: a win to be proud of · shame: your fault · unlucky: not your fault, still stings
  const META = {
    top_dog:       { icon: "🏆", tone: "good",    title: "Top dog",                  unit: "points",                   what: "Highest team score of the week." },
    toilet_bowl:   { icon: "🚽", tone: "shame",   title: "Toilet bowl",              unit: "points",                   what: "Lowest team score of the week." },
    blowout:       { icon: "💥", tone: "good",    title: "Blowout",                  unit: "point margin",             what: "Biggest winning margin." },
    nail_biter:    { icon: "😬", tone: "neutral", title: "Nail-biter",               unit: "point margin",             what: "Smallest winning margin." },
    robbed:        { icon: "💸", tone: "unlucky", title: "Robbed",                   unit: "points in a loss",         what: "Highest score in a loss." },
    stole_one:     { icon: "🦝", tone: "neutral", title: "Stole one",                unit: "points in a win",          what: "Lowest score in a win." },
    bench_warmer:  { icon: "🛋️", tone: "shame",   title: "Points left on the bench", unit: "points left on the bench", what: "Most points left on the bench compared with the best possible lineup." },
    mvp:           { icon: "⭐", tone: "good",    title: "MVP",                      unit: "points",                   what: "Highest-scoring starter." },
    dud:           { icon: "🧨", tone: "shame",   title: "Dud",                      unit: "points",                   what: "Lowest-scoring starter (kickers, defenses and coaches excluded)." },
    bench_blunder: { icon: "🤦", tone: "shame",   title: "Bench blunder",            unit: "points lost on the swap",  what: "Biggest start/sit miss: a benched player outscored a starter he could have replaced." },
  };
  const metaOf = (k) => META[k] || { icon: "🏅", tone: "neutral", title: k, unit: "", what: "" };
  A.awardMeta = META;

  const data = D.awards;
  const weeks = data && Array.isArray(data.weeks) ? [...data.weeks].sort((a, b) => b.week - a.week) : [];

  // Everything one team has won, newest week first (for the manager page).
  const byTeam = new Map();
  for (const wk of weeks) {
    for (const a of wk.awards || []) {
      if (!byTeam.has(a.team)) byTeam.set(a.team, []);
      byTeam.get(a.team).push({ week: wk.week, key: a.key, title: a.title, value: a.value, detail: a.detail, player: a.player || null });
    }
  }
  A.awardsFor = (teamId) => (byTeam.get(+teamId) || []).map((x) => ({ ...x }));

  const root = $("#awards");
  if (!root) return;
  const head = (extra = "") => `<h2>Weekly awards</h2><p class="sub">Every week's best and worst, handed out automatically from the box scores.</p>${extra}`;
  if (!data || !weeks.length) {
    root.innerHTML = head(`<div class="card"><div class="empty">${data ? "No awards yet — they show up once week 1 is in the books." : "Awards aren't available right now. The report builder skipped them; try rebuilding the site."}</div></div>`);
    return;
  }

  // ── helpers ─────────────────────────────────────────────
  const titles = {};
  for (const wk of weeks) for (const a of wk.awards || []) titles[a.key] = a.title;
  const titleOf = (k) => titles[k] || metaOf(k).title;
  const money = (key, v) => (key === "nail_biter" ? Math.abs(v).toFixed(2) : f1(Math.abs(v)));
  const fmt = (key, v) => (v < 0 && Math.abs(v) >= 0.005 ? "−" : "") + money(key, v);
  const initialsOf = (name) => String(name || "?").split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase() || "?";
  const weekLabel = (w) => `Week ${w}${L.regular_season_weeks && w > L.regular_season_weeks ? " (playoffs)" : ""}`;
  const who = (id) => (T[id] ? chip(T[id]) : `<span class="team"><span class="nm">Team ${esc(id)}</span></span>`);

  // ── "Share to the board": each award as one plain-text line (account.js; hidden unless you're signed in) ──
  const share = A.shareBtn || (() => "");
  const mgr = (id) => (T[id] ? T[id].manager || T[id].name : `Team ${id}`);
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
  const low = (s) => s.charAt(0).toLowerCase() + s.slice(1);
  const MATCHUP = ["top_dog", "toilet_bowl", "blowout", "nail_biter", "robbed", "stole_one"]; // awards whose line names the opponent
  function sentence(a, nm) {
    const d = String(a.detail || ""), v = fmt(a.key, a.value);
    switch (a.key) {
      case "top_dog": return `${nm} had the top score of the week: ${d}.`;
      case "toilet_bowl": return `${nm} had the lowest score of the week: ${d}.`;
      case "blowout": return `${nm} had the biggest blowout of the week, by ${v}: ${low(d)}.`;
      case "nail_biter": return `${nm} had the closest win of the week, by ${v}: ${low(d)}.`;
      case "robbed": return `${nm} had the highest score in a loss: ${low(d)}.`;
      case "stole_one": return `${nm} stole one with the lowest score in a win: ${low(d)}.`;
      case "bench_warmer": return `${nm} left ${v} points on the bench. ${d}.`;
      case "mvp": return `${nm}'s ${d} was the top scorer of the week with ${v} points.`;
      case "dud": return `${nm} ${/^Started /.test(d) ? low(d) : `got the week's dud: ${d}`}.`;
      case "bench_blunder": return `${nm} ${/^Benched /.test(d) ? low(d) : `blundered: ${d}`}. That cost ${v} points.`;
      default: return `${nm}: ${d}.`;
    }
  }
  function awardStat(a, week, m) {
    const unit = m.unit ? m.unit.charAt(0).toUpperCase() + m.unit.slice(1) : "Value";
    const facts = [[clip(unit, 30), fmt(a.key, a.value)]];
    if (a.tied > 0) facts.push(["Tied with", `${a.tied} other${a.tied === 1 ? "" : "s"}`]);
    const teams = [a.team, ...(MATCHUP.includes(a.key) && a.opponent != null ? [a.opponent] : [])];
    return { kind: "award", title: clip(`Week ${week} ${a.title || m.title}`, 80), text: clip(sentence(a, mgr(a.team)), 300), facts, teams, link: `#awards/${week}` };
  }

  const seen = new Set(Object.keys(META));
  for (const s of data.season || []) for (const k of Object.keys(s.counts || {})) seen.add(k);
  for (const wk of weeks) for (const a of wk.awards || []) seen.add(a.key);
  const KEYS = [...seen];
  const SHAME = KEYS.filter((k) => metaOf(k).tone === "shame");

  // ── week picker + cards ─────────────────────────────────
  function shot(p) {
    const src = headshot(p);
    const ini = initialsOf(p.name);
    return `<div class="aw-shot" data-ini="${esc(ini)}">${src ? `<img src="${esc(src)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<span class="aw-ph">${esc(ini)}</span>`}</div>`;
  }
  // A headshot that won't load falls back to the player's initials.
  function wireShots(scope) {
    $$(".aw-shot img", scope).forEach((img) => {
      img.addEventListener("error", () => {
        const box = img.parentElement;
        const ph = document.createElement("span");
        ph.className = "aw-ph";
        ph.textContent = box.dataset.ini || "?";
        box.replaceChildren(ph);
      }, { once: true });
    });
  }

  function card(a, week) {
    const m = metaOf(a.key);
    const tag = m.tone === "shame" ? '<span class="aw-tag shame">Shame</span>' : m.tone === "unlucky" ? '<span class="aw-tag unlucky">Unlucky</span>' : "";
    const n = a.tied || 0;
    return `<article class="card aw-card ${m.tone}">
      <div class="aw-hd"><span class="aw-ico" aria-hidden="true">${m.icon}</span><h3 class="aw-title">${esc(a.title || m.title)}</h3>${tag}</div>
      <div class="aw-row">
        <div class="aw-main"><div class="aw-val num">${fmt(a.key, a.value)}</div><div class="aw-unit">${esc(m.unit)}</div></div>
        ${a.player ? shot(a.player) : ""}
      </div>
      <div class="aw-who">${who(a.team)}</div>
      <p class="aw-detail">${esc(a.detail)}</p>
      ${n > 0 ? `<p class="aw-tied">${n} other${n === 1 ? "" : "s"} tied at ${fmt(a.key, a.value)}</p>` : ""}
      ${share(awardStat(a, week, m))}
    </article>`;
  }

  root.innerHTML = head(`
    <div class="controls">
      <label class="aw-pick">Week <select id="awWeek" aria-label="Week">${weeks.map((w) => `<option value="${w.week}">${esc(weekLabel(w.week))}</option>`).join("")}</select></label>
      <span class="count" id="awCount"></span>
    </div>
    <div class="aw-grid" id="awGrid"></div>
    <p class="note">Bench blunder is hindsight: it compares a benched player with a starter whose lineup spot he was eligible for (a TE can take a WR's flex spot) and ignores game-time locks and injuries. If several teams tie on an award's exact number, the card says so.</p>
    <h2 class="aw-trophy" id="trophyCase">Trophy case</h2>
    <p class="sub" id="awCaseSub"></p>
    <div class="card aw-case"><div class="tbl-wrap"><table class="aw-table" id="awTable"></table></div><div class="aw-legend" id="awLegend"></div></div>`);

  const pick = $("#awWeek");
  function setWeek(w) {
    const wk = weeks.find((x) => x.week === w) || weeks[0];
    pick.value = String(wk.week);
    const list = wk.awards || [];
    $("#awGrid").innerHTML = list.map((a) => card(a, wk.week)).join("") || '<div class="card"><div class="empty">No awards this week.</div></div>';
    wireShots($("#awGrid"));
    $("#awCount").textContent = `${list.length} award${list.length === 1 ? "" : "s"}`;
  }
  pick.addEventListener("change", () => setWeek(+pick.value));

  // ── trophy case ─────────────────────────────────────────
  const rows = teams.map((t) => {
    const s = (data.season || []).find((x) => x.team === t.id);
    const counts = Object.fromEntries(KEYS.map((k) => [k, (s && s.counts && s.counts[k]) || 0]));
    return { t, counts, shame: SHAME.reduce((n, k) => n + counts[k], 0) };
  });
  let sort = { k: "shame", dir: "desc" };

  const cmp = (a, b) => {
    if (sort.k === "team") return a.t.name.localeCompare(b.t.name) * (sort.dir === "asc" ? 1 : -1);
    const val = (r) => (sort.k === "shame" ? r.shame : r.counts[sort.k]);
    return (val(b) - val(a)) * (sort.dir === "desc" ? 1 : -1) || b.shame - a.shame || a.t.name.localeCompare(b.t.name);
  };

  function cellTip(r, k) {
    const all = byTeam.get(r.t.id) || [];
    const list = all.filter((x) => (k === "shame" ? SHAME.includes(x.key) : x.key === k));
    const rows2 = list.slice(0, 8).map((x) => [k === "shame" ? `W${x.week} · ${x.title}` : `Week ${x.week}`, fmt(x.key, x.value)]);
    if (list.length > 8) rows2.push(["…", `+${list.length - 8} more`]);
    return tipHtml(`${r.t.name} · ${k === "shame" ? "Shame" : titleOf(k)}`, rows2);
  }

  function drawTable() {
    const sorted = [...rows].sort(cmp);
    const lead = {};
    for (const k of [...KEYS, "shame"]) lead[k] = Math.max(0, ...rows.map((r) => (k === "shame" ? r.shame : r.counts[k])));
    const th = (k, inner, tipText, label, cls = "c") => {
      const on = sort.k === k;
      const arrow = on ? (sort.dir === "desc" ? "▼" : "▲") : "";
      return `<th class="${cls}" aria-sort="${on ? (sort.dir === "desc" ? "descending" : "ascending") : "none"}"><button type="button" class="aw-sort${on ? " on" : ""}" data-k="${k}" data-tip="${tipText}" aria-label="${esc(label)}">${inner}<span class="arr" aria-hidden="true">${arrow}</span></button></th>`;
    };
    const shameTip = tipHtml("Shame", [[SHAME.map(titleOf).join(" + "), ""]]);
    $("#awTable").innerHTML = `<thead><tr>
      ${th("team", "Team", tipHtml("Team", [["Sort by name", ""]]), "Sort by team name", "tm")}
      ${th("shame", "Shame", shameTip, "Sort by total shame awards")}
      ${KEYS.map((k) => th(k, `<span class="ico" aria-hidden="true">${metaOf(k).icon}</span>`, tipHtml(titleOf(k), [[metaOf(k).what || titleOf(k), ""]]), `Sort by ${titleOf(k)}`)).join("")}
    </tr></thead><tbody>${sorted.map((r) => {
      const cell = (k, v) => {
        const tone = k === "shame" || ["shame", "unlucky"].includes(metaOf(k).tone) ? "shame" : "good";
        const cls = v === 0 ? "c dim" : `c has${v === lead[k] ? ` lead ${tone}` : ""}`;
        return `<td class="${cls}"${v ? ` data-tip="${cellTip(r, k)}"` : ""}>${v}</td>`;
      };
      return `<tr><td class="tm">${chip(r.t)}</td>${cell("shame", r.shame)}${KEYS.map((k) => cell(k, r.counts[k])).join("")}</tr>`;
    }).join("")}</tbody>`;
  }
  $("#awTable").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-k]");
    if (!b) return;
    const k = b.dataset.k;
    sort = sort.k === k ? { k, dir: sort.dir === "desc" ? "asc" : "desc" } : { k, dir: k === "team" ? "asc" : "desc" };
    drawTable();
    const again = $(`#awTable button[data-k="${k}"]`);
    if (again) again.focus();
  });

  const through = weeks[0].week;
  $("#awCaseSub").textContent = `Season totals through week ${through}. Tap an icon to sort by that award. Shame adds up ${SHAME.map(titleOf).join(", ").replace(/, ([^,]*)$/, " and $1")}. The highlighted cell is the league leader.`;
  $("#awLegend").innerHTML = KEYS.map((k) => `<span class="aw-key"><span class="ico" aria-hidden="true">${metaOf(k).icon}</span>${esc(titleOf(k))}</span>`).join("");

  setWeek(weeks[0].week);
  drawTable();

  // #awards/3 opens on week 3.
  onRoute("awards", (params) => {
    const w = params && params[0] ? +params[0] : NaN;
    if (weeks.some((x) => x.week === w)) setWeek(w);
  });
})();
