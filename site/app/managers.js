// Managers tab: a card per manager (#managers) and one page per manager (#manager/<id>)
// that pulls together what the other tabs compute: odds, power rank, results, head-to-head,
// trades, pickups and awards. Anything another feature couldn't build is simply left out.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, teams, T, ranked, $, esc, f1, sgn, cls, pct, fmtDate, chip, logo, lineChart, onRoute } = A;
  const root = $("#managers");
  if (!root) return;

  const N = teams.length;
  const PAGE_TITLE = `${L.name} · Dashboard`;
  const P = D.punishment && Array.isArray(D.punishment.teams) ? D.punishment : null;
  const FAAB = D.faab && Array.isArray(D.faab.teams) ? D.faab : null;

  // ── small helpers ───────────────────────────────────────
  const ord = (n) => { const v = n % 100, s = ["th", "st", "nd", "rd"]; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const record = (t) => `${t.wins}-${t.losses}${t.ties ? "-" + t.ties : ""}`;
  const pc = (x) => (x == null ? null : x >= 0.995 ? ">99%" : pct(x)); // a simulation never says 100%
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
  const usd = (n) => `$${Math.round(n)}`;
  const divName = (t) => String((L.divisions || {})[t.division] || "");
  const multiDiv = Object.keys(L.divisions || {}).length > 1;
  const power = (id) => (typeof A.powerFor === "function" ? A.powerFor(id) : null);
  const oddsRow = (id) => (P ? P.teams.find((r) => r.id === id) || null : null);
  const fmtScore = (a, b) => `${f1(a)}–${f1(b)}`;
  const tipTitle = (rows) => esc(rows.join(" · "));

  // How a team ranks on a stat, in words. `r` is 1 for the biggest value of the stat.
  function rankLine(r, [top, bottom, mid]) {
    if (N < 3) return "";
    return r === 1 ? `${top} in the league` : r === N ? `${bottom} in the league` : `${ord(r)} ${mid} of ${N}`;
  }
  const rankDesc = (t, key) => 1 + teams.filter((o) => o[key] > t[key]).length;

  // Power-rank movement: ▲2 / ▼1 / – (nothing when we don't know last week).
  function move(c) {
    if (c == null) return "";
    if (c === 0) return '<span class="mg-mv dim" role="img" aria-label="Same as last week">–</span>';
    const up = c > 0;
    return `<span class="mg-mv ${up ? "pos" : "neg"}" role="img" aria-label="${up ? "Up" : "Down"} ${Math.abs(c)} since last week">${up ? "▲" : "▼"}${Math.abs(c)}</span>`;
  }

  // ── what happened on the field, from the box scores ─────
  // gamesOf[id] → [{week, opp, my, their}] and scoreIn[id][week] → score, completed weeks only.
  const gamesOf = {}, scoreIn = {}, weekScores = {};
  for (const t of teams) { gamesOf[t.id] = []; scoreIn[t.id] = {}; }
  for (const m of D.matchups || []) {
    weekScores[m.week] = [];
    for (const g of m.games) {
      if (g.home_score == null || g.away_score == null || !T[g.home] || !T[g.away]) continue;
      gamesOf[g.home].push({ week: m.week, opp: g.away, my: g.home_score, their: g.away_score });
      gamesOf[g.away].push({ week: m.week, opp: g.home, my: g.away_score, their: g.home_score });
      scoreIn[g.home][m.week] = g.home_score; scoreIn[g.away][m.week] = g.away_score;
      weekScores[m.week].push(g.home_score, g.away_score);
    }
  }
  for (const id in gamesOf) gamesOf[id].sort((a, b) => a.week - b.week);
  const played = new Set((D.matchups || []).map((m) => m.week));
  // The games still to play: [{week, opp}] from the full schedule.
  const upcomingOf = (id) => (D.schedule || []).filter((w) => !played.has(w.week)).flatMap((w) => {
    const g = (w.games || []).find((x) => x[0] === id || x[1] === id);
    const opp = g ? (g[0] === id ? g[1] : g[0]) : null;
    return T[opp] ? [{ week: w.week, opp }] : [];
  }).sort((a, b) => a.week - b.week);

  // ── the list ────────────────────────────────────────────
  function listCard(t) {
    const p = power(t.id), o = oddsRow(t.id);
    const stats = [
      ["Record", record(t), ""],
      p ? ["Power", `#${p.rank}${move(p.change)}`, ""] : null,
      o && o.p_playoffs != null ? ["Playoffs", pc(o.p_playoffs), ""] : null,
      o && o.p_last != null ? ["Last place", pc(o.p_last), o.p_last >= 0.1 ? "neg" : ""] : null,
    ].filter(Boolean);
    return `<a class="card mg-card" href="#manager/${t.id}" aria-label="${esc(t.name)}, ${esc(t.manager)}. Open their page.">
      <div class="mg-top">${logo(t)}
        <span class="mg-id"><b class="mg-nm">${esc(t.name)}</b><span class="mg-mgr">${esc(t.manager)}${multiDiv && divName(t) ? ` · ${esc(divName(t).replace(/ Division$/i, ""))}` : ""}</span></span>
        <span class="mg-rk r${Math.min(t.rank, 4)}" title="${ord(t.rank)} in the standings"><b>#${t.rank}</b><small>Standing</small></span>
      </div>
      <dl class="mg-stats">${stats.map(([k, v, c]) => `<div><dt>${k}</dt><dd class="${c}">${v}</dd></div>`).join("")}</dl>
    </a>`;
  }

  function renderList() {
    document.title = PAGE_TITLE;
    root.innerHTML = `<h2>Managers</h2>
      <p class="sub">Everyone in the league, in standings order. Tap a manager for their whole season on one page: results, odds, trades, pickups and awards.</p>
      <div class="mg-grid">${ranked.map(listCard).join("")}</div>`;
  }

  // ── one manager: top bar, header, tiles ─────────────────
  function topBar(t) {
    const i = ranked.indexOf(t), prev = ranked[i - 1], next = ranked[i + 1];
    return `<nav class="mg-bar" aria-label="Managers">
      <a class="mg-back" href="#managers">← All managers</a>
      <span class="mg-pn">
        ${prev ? `<a class="mg-prev" href="#manager/${prev.id}" rel="prev" aria-label="Previous in the standings: ${esc(prev.name)}"><span aria-hidden="true">‹</span><span class="mg-pn-t">#${prev.rank} ${esc(prev.name)}</span></a>` : ""}
        ${next ? `<a class="mg-next" href="#manager/${next.id}" rel="next" aria-label="Next in the standings: ${esc(next.name)}"><span class="mg-pn-t">#${next.rank} ${esc(next.name)}</span><span aria-hidden="true">›</span></a>` : ""}
      </span>
    </nav>`;
  }

  function header(t) {
    const p = power(t.id);
    const fact = (k, v) => `<div><dt>${k}</dt><dd>${v}</dd></div>`;
    const streak = String(t.streak || "");
    const facts = [
      fact("Record", esc(record(t))),
      fact("Standing", `#${t.rank}<span class="of"> of ${N}</span>`),
      streak ? fact("Streak", `<span class="${/^W/i.test(streak) ? "pos" : /^L/i.test(streak) ? "neg" : ""}">${esc(streak)}</span>`) : "",
      p ? fact("Power rank", `#${p.rank}${move(p.change)}`) : "",
    ].join("");
    const sub = [t.manager, multiDiv ? divName(t) : ""].filter(Boolean).map(esc).join(" · ");
    const tags = A.managerTags.map((fn) => safely(() => fn(t))).filter(Boolean).join("");
    return `<div class="card mg-head">
      <div class="mg-who">${logo(t)}
        <div><h2 class="mg-title">${esc(t.name)}</h2><p class="mg-sub">${sub}</p>${tags ? `<p class="mg-tags">${tags}</p>` : ""}</div>
      </div>
      <dl class="mg-facts">${facts}</dl>
      ${p && p.blurb ? `<p class="mg-blurb">${esc(p.blurb)}</p>` : ""}
    </div>`;
  }

  const myTrades = (id) => D.trades.filter((tr) => tr.sides.some((s) => s.team === id));
  const faabOf = (id) => (FAAB ? FAAB.teams.find((r) => r.team === id) || null : null);

  function tiles(t) {
    const out = [];
    const tile = (label, value, sub, vcls, tip) =>
      out.push(`<div class="card tile mg-tile"${tip ? ` title="${esc(tip)}"` : ""}><div class="label">${label}</div><div class="value ${vcls || ""}">${value}</div><div class="who">${sub}</div></div>`);
    const gp = t.wins + t.losses + t.ties;
    tile("Points for", f1(t.points_for), esc(rankLine(rankDesc(t, "points_for"), ["Most", "Fewest", "most"])));
    tile("Points against", f1(t.points_against), esc(rankLine(rankDesc(t, "points_against"), ["Most", "Fewest", "most"])));
    const ap = t.allplay_w + t.allplay_l;
    if (gp > 0 && ap > 0) {
      tile("All-play record", `${t.allplay_w}-${t.allplay_l}`,
        `${Math.round((t.allplay_w / ap) * 100)}% vs everyone`, "", "How this team would do if it played all 11 other teams every week.");
      const w = t.wins + t.ties / 2;
      tile("Luck", sgn(t.luck), `${plural(w, "win")} vs ${f1(t.exp_wins)} expected`, cls(t.luck),
        "Actual wins minus the wins the all-play record predicts. Positive means a kind schedule.");
    }
    if (t.efficiency != null) {
      tile("Lineup efficiency", `${(t.efficiency * 100).toFixed(1)}%`,
        esc(rankLine(rankDesc(t, "efficiency"), ["Best", "Worst", "best"])), "", "Points scored divided by the best lineup the roster could have set.");
    }
    if (t.bench_left != null) {
      tile("Left on the bench", f1(t.bench_left), esc(rankLine(rankDesc(t, "bench_left"), ["Most", "Fewest", "most"])), "",
        "Points the best possible lineups would have scored over what was started.");
    }
    const mine = myTrades(t.id), pend = mine.filter((tr) => tr.status !== "graded").length;
    if (!mine.length) tile("Trades", "0", "Hasn't made a deal yet");
    else if (pend === mine.length) tile("Trade net pts", "–", `${plural(mine.length, "trade")}, not graded yet`);
    else tile("Trade net pts", sgn(t.trade_net), `from ${plural(mine.length - pend, "graded trade")}${pend ? `, ${pend} not graded yet` : ""}`, cls(t.trade_net),
      "Lineup points gained or lost across this team's graded trades.");
    const f = faabOf(t.id);
    if (f && f.left != null) {
      const bonus = f.commish ? ` · ${f.commish > 0 ? "+" : "−"}${usd(Math.abs(f.commish))} from the commish` : "";
      tile("FAAB left", usd(f.left), (FAAB.budget ? `of ${usd(FAAB.budget)} budget` : "to spend") + bonus);
    }
    return `<div class="mg-tiles">${out.join("")}</div>`;
  }

  // ── odds and power rank ─────────────────────────────────
  function oddsBlock(t) {
    const o = oddsRow(t.id);
    const hist = typeof A.oddsChart === "function" && typeof A.oddsHistory === "function" ? A.oddsHistory(t.id) : null;
    const cells = [];
    if (o) {
      const add = (k, v, c) => { if (pc(v)) cells.push(`<div><dt>${k}</dt><dd class="${c || ""}">${pc(v)}</dd></div>`); };
      add("Make playoffs", o.p_playoffs);
      if (multiDiv) add("Win division", o.p_division);
      if (P.byes > 0) add("Get a bye", o.p_bye);
      add("Finish last", o.p_last, o.p_last >= 0.1 ? "neg" : "");
    }
    if (!hist && !cells.length) return "";
    const cap = hist
      ? (P ? "Re-simulated after every week. The last point is today's number." : "The regular season is over, so the last point is how it ended.")
      : "Simulated from here to the end of the regular season.";
    return `<div class="card mg-blk"><h3>Season odds</h3><p class="cap">${cap}</p>
      ${cells.length ? `<dl class="mg-odds">${cells.join("")}</dl>` : ""}
      ${hist ? '<div class="mg-chart" id="mgOdds"></div>' : ""}
    </div>`;
  }

  function powerBlock(t) {
    const p = power(t.id);
    if (!p || !p.history.length) return "";
    const hist = p.history;
    if (hist.length < 2) {
      return `<div class="card mg-blk"><h3>Power rank by week</h3><p class="cap">The line starts once there are two weeks of rankings.</p><div class="empty">Week ${hist[0].week}: #${hist[0].rank}</div></div>`;
    }
    return `<div class="card mg-blk"><h3>Power rank by week</h3><p class="cap">Up is better. #1 is the top line.</p><div class="mg-chart"><div id="mgPower"></div></div></div>`;
  }

  function drawPower(t) {
    const el = $("#mgPower", root), p = power(t.id);
    if (!el || !p || p.history.length < 2) return;
    const hist = p.history, flip = (r) => N + 1 - r; // plot N+1-rank so #1 is the top of the chart
    lineChart(el, {
      x: hist.map((h) => "Wk " + h.week), height: 190, yMin: 1, yMax: N, yTicks: [1, Math.round((N + 1) / 2), N],
      yFmt: (v) => "#" + flip(v), xFmt: (i) => `After week ${hist[i].week}`,
      label: `${t.name}: power rank after each week`,
      series: [{ name: "Power rank", values: hist.map((h) => flip(h.rank)), color: "var(--accent)" }],
      tipRows: (i) => [["Power rank", "#" + hist[i].rank], ["Score", f1(hist[i].score)]],
    });
  }

  // ── results ─────────────────────────────────────────────
  function weekBlock(t) {
    const games = gamesOf[t.id], next = upcomingOf(t.id);
    if (!games.length && !next.length) return "";
    const rows = games.map((g) => {
      const res = g.my > g.their ? "W" : g.my < g.their ? "L" : "T";
      const opp = T[g.opp], scores = weekScores[g.week] || [];
      const r = 1 + scores.filter((s) => s > g.my).length;
      const rcls = r === 1 ? "top" : r === scores.length ? "last" : "";
      const tip = `Scored the ${r === 1 ? "most" : r === scores.length ? "fewest" : ord(r) + "-most"} of the ${scores.length} teams that week`;
      return `<tr><td class="c-wk">${g.week}</td>
        <td class="c-res"><span class="mg-wl ${res}" aria-label="${res === "W" ? "Win" : res === "L" ? "Loss" : "Tie"}">${res}</span></td>
        <td class="c-opp">${chip(opp)}</td>
        <td class="n c-sc">${fmtScore(g.my, g.their)}</td>
        <td class="n c-rk"><span class="mg-rank ${rcls}" title="${esc(tip)}">#${r}</span></td></tr>`;
    }).join("");
    const table = games.length
      ? `<div class="tbl-wrap"><table class="mg-tbl mg-weeks"><thead><tr><th class="c-wk">Wk</th><th class="c-res"><span class="sr">Result</span></th><th class="c-opp">Opponent</th><th class="n c-sc">Score</th><th class="n c-rk" title="Where this score ranked among every team's score that week">Rank</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : '<div class="empty">No games played yet.</div>';
    const upcoming = next.length
      ? `<div class="mg-next-head">Still to play</div><ul class="mg-up">${next.map((n) => `<li><span class="w">Wk ${n.week}</span>${chip(T[n.opp])}</li>`).join("")}</ul>`
      : "";
    return `<div class="card mg-blk"><h3>Week by week</h3><p class="cap">Rank is where the score landed among all ${N} teams that week.</p>${table}${upcoming}</div>`;
  }

  // vs every other team: what happened when they met, and the record if they'd played every week.
  function h2hBlock(t) {
    const rows = ranked.filter((o) => o !== t).map((o) => {
      const met = gamesOf[t.id].filter((g) => g.opp === o.id);
      const later = upcomingOf(t.id).filter((n) => n.opp === o.id);
      let w = 0, l = 0, tie = 0;
      for (const wk in scoreIn[t.id]) {
        const a = scoreIn[t.id][wk], b = scoreIn[o.id][wk];
        if (b == null) continue;
        if (a > b) w++; else if (a < b) l++; else tie++;
      }
      const rec = w + l + tie ? `${w}-${l}${tie ? "-" + tie : ""}` : "–";
      const rc = w > l ? "pos" : w < l ? "neg" : "dim";
      const res = met.map((g) => {
        const r = g.my > g.their ? "W" : g.my < g.their ? "L" : "T";
        return `<span class="mg-r"><b class="${r === "W" ? "pos" : r === "L" ? "neg" : "dim"}">${r}</b> ${fmtScore(g.my, g.their)}<span class="dim">, wk ${g.week}</span></span>`;
      }).join("");
      const again = later.length ? `<span class="mg-r dim">${met.length ? "Again" : "Plays"} wk ${later.map((n) => n.week).join(", ")}</span>` : "";
      const none = met.length || later.length ? "" : '<span class="mg-r dim">Haven\'t met</span>';
      const href = `#rivalry/${t.id}/${o.id}`;
      return `<li><span class="c-opp"><a class="mg-rl" href="${href}" aria-label="Head-to-head with ${esc(o.name)}">${chip(o, { link: false })}</a></span>
        <span class="c-hr">${res}${again}${none}</span>
        <span class="c-ew ${rc}">${rec}<small>every week</small></span>
        <span class="c-go" aria-hidden="true">›</span></li>`;
    }).join("");
    if (!rows) return "";
    return `<div class="card mg-blk"><h3>Head-to-head</h3><p class="cap">What happened when they met this season, and the record if they'd played that team every week. Tap a row for the full rivalry.</p>
      <div class="mg-hh-head"><span>Opponent</span><span>This season</span><span class="n" title="Weeks this team outscored them, no matter who either one played">Every week</span><span></span></div>
      <ul class="mg-hh">${rows}</ul></div>`;
  }

  // ── trades, pickups, awards ─────────────────────────────
  function tradesBlock(t) {
    const mine = myTrades(t.id).sort((a, b) => b.date - a.date);
    const names = (list, faab) => {
      const items = list.map((p) => `<span class="mg-pl">${esc(p.name)}${p.pos && p.pos !== "?" ? `<small>${esc(p.pos)}</small>` : ""}</span>`);
      if (+faab > 0) items.push(`<span class="mg-pl">${usd(faab)} FAAB</span>`);
      return items.join("") || '<span class="dim">nothing</span>';
    };
    const body = mine.length ? `<ul class="mg-trades">${mine.map((tr) => {
      const s = tr.sides.find((x) => x.team === t.id);
      const partners = tr.sides.filter((x) => x !== s && T[x.team]).map((x) => chip(T[x.team])).join("");
      const net = tr.status === "graded"
        ? `<span class="mg-net ${cls(s.net)}">${sgn(s.net)}<small>lineup pts</small></span>`
        : '<span class="mg-net"><small>Not graded yet</small></span>';
      return `<li class="mg-trade">
        <div class="mg-th"><span><a class="mg-tl" href="#trade/${tr.id}"><b>Trade #${tr.id}</b></a> · ${fmtDate(tr.date)}</span>${net}</div>
        <div class="mg-gg">${partners ? `<span class="k">With</span><div class="v">${partners}</div>` : ""}<span class="k">Got</span><div class="v">${names(s.received, s.faab_received)}</div><span class="k">Gave</span><div class="v">${names(s.sent, s.faab_sent)}</div></div>
      </li>`;
    }).join("")}</ul><p class="mg-foot"><a href="#ledger">See the full trade ledger ›</a></p>`
      : '<div class="empty">No trades yet. Playing it safe.</div>';
    return `<div class="card mg-blk"><h3>Trades</h3><p class="cap">${mine.length ? `${plural(mine.length, "trade")}, newest first. Lineup points compare the roster with and without the deal.` : "Nothing on the books."}</p>${body}</div>`;
  }

  function pickupsBlock(t) {
    const f = faabOf(t.id);
    if (!f) return "";
    const best = (f.pickup_list || []).filter((p) => p.started_points > 0)
      .sort((a, b) => b.started_points - a.started_points || b.points - a.points).slice(0, 5);
    const cells = [
      f.left != null ? ["FAAB left", usd(f.left)] : null,
      f.bids_won != null ? ["Bids won", String(f.bids_won)] : null,
      f.spent_on_bids != null ? ["Spent on bids", usd(f.spent_on_bids)] : null,
      f.pickup_started_points != null ? ["Started pts", f1(f.pickup_started_points)] : null,
    ].filter(Boolean);
    const list = best.length
      ? `<div class="tbl-wrap"><table class="mg-tbl mg-pick"><thead><tr><th>Player</th><th class="n">Paid</th><th class="n" title="Weeks on this roster">Wks</th><th class="n" title="Points scored in this team's starting lineup, only in weeks he was on its roster">Started</th></tr></thead><tbody>${best.map((p) =>
        `<tr><td class="c-pn"><span class="ell">${esc(p.name)}</span>${p.pos && p.pos !== "?" ? `<small>${esc(p.pos)}</small>` : ""}</td><td class="n">${p.kind === "waiver" ? usd(p.bid) : "Free"}</td><td class="n">${p.weeks}</td><td class="n"><b>${f1(p.started_points)}</b></td></tr>`).join("")}</tbody></table></div>`
      : '<div class="empty">No pickup has scored in a starting lineup yet.</div>';
    return `<div class="card mg-blk"><h3>Pickups</h3><p class="cap">Best five by points in the starting lineup.</p>
      ${cells.length ? `<dl class="mg-odds">${cells.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>` : ""}
      ${list}</div>`;
  }

  // How this team answers trade offers (D.offers, from league/offers.py).
  function offersBlock(t) {
    const O = D.offers;
    const r = O && Array.isArray(O.teams) ? O.teams.find((x) => x.team === t.id) : null;
    if (!r || (!r.answered && !r.started)) return "";
    const rated = O.teams.filter((x) => x.answered >= 5);
    const yes = r.accept_rate == null ? "–" : `${Math.round(r.accept_rate * 100)}%`;
    let cap = "Offers this team has accepted or turned down, and deals it started.";
    if (r.answered >= 5 && rated.length > 1) {
      const rank = 1 + rated.filter((x) => x.accept_rate > r.accept_rate).length;
      cap = rank === 1 ? "The easiest yes in the league." : rank === rated.length ? "The hardest sell in the league." : `${ord(rank)} most likely to say yes, of ${rated.length}.`;
    }
    const sent = r.sent == null ? null : ["Offers sent", `${r.sent}${r.sent_exact ? "" : "+"}`];
    const cells = [["Answered", String(r.answered)], ["Said yes", String(r.accepted)], ["Said no", String(r.declined)], ["Yes rate", yes], sent, ["Deals started", String(r.started)]].filter(Boolean);
    return `<div class="card mg-blk"><h3>Trade offers</h3><p class="cap">${esc(cap)}</p>
      <dl class="mg-odds">${cells.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>
      ${sent && !r.sent_exact ? '<p class="mg-foot dim">Offers sent is a floor: ESPN hides who sent most declined offers.</p>' : ""}
      <p class="mg-foot"><a href="#offers">Everyone's offers ›</a></p></div>`;
  }

  const SHOW_AWARDS = 8;
  function awardsBlock(t) {
    if (typeof A.awardsFor !== "function" || !D.awards || !Array.isArray(D.awards.weeks)) return "";
    const list = A.awardsFor(t.id), META = A.awardMeta || {};
    const meta = (k) => META[k] || { icon: "🏅", tone: "neutral" };
    if (!list.length) return `<div class="card mg-blk"><h3>Awards</h3><p class="cap">Weekly awards this team has won.</p><div class="empty">No awards yet. Quiet season so far.</div></div>`;
    const counts = {}, titles = {};
    for (const a of list) { counts[a.key] = (counts[a.key] || 0) + 1; titles[a.key] = titles[a.key] || a.title || (META[a.key] && META[a.key].title) || a.key; }
    const keys = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
    const chips = keys.map((k) => `<span class="mg-aw ${esc(meta(k).tone)}" title="${esc(meta(k).what || "")}"><span aria-hidden="true">${meta(k).icon}</span>${esc(titles[k])}<b>×${counts[k]}</b></span>`).join("");
    const items = list.map((a, i) => `<li${i >= SHOW_AWARDS ? ' class="x" hidden' : ""}><span class="w">Wk ${a.week}</span><span class="ic" aria-hidden="true">${meta(a.key).icon}</span><span class="tx"><b>${esc(a.title || titles[a.key])}</b>${a.detail ? `<span class="dim"> · ${esc(a.detail)}</span>` : ""}</span></li>`).join("");
    const more = list.length > SHOW_AWARDS ? `<button type="button" class="mg-more" data-more="awards" aria-expanded="false">Show all ${list.length}</button>` : "";
    return `<div class="card mg-blk"><h3>Awards</h3><p class="cap">${plural(list.length, "award")} won, newest first.</p>
      <div class="mg-awards">${chips}</div><ul class="mg-awlist" id="mgAwards">${items}</ul>${more}</div>`;
  }

  // ── the page ────────────────────────────────────────────
  const row = (...blocks) => {
    const b = blocks.filter(Boolean);
    return b.length ? `<div class="mg-two${b.length === 1 ? " one" : ""}">${b.join("")}</div>` : "";
  };

  // Blocks other tabs add to this page (A.managerBlocks, see core.js). One that throws is
  // logged and left out, so a broken feature never takes the page down.
  function safely(fn) {
    try { return fn() || ""; } catch (e) { console.error(e); return ""; }
  }
  const extraBlocks = (t, place) => A.managerBlocks
    .filter((b) => (b.place || "bottom") === place)
    .sort((a, b) => (a.order || 0) - (b.order || 0))
    .map((b) => safely(() => b.render(t)))
    .filter(Boolean);

  function renderPage(t) {
    document.title = `${t.name} · ${L.name}`;
    const side = [offersBlock(t), pickupsBlock(t), awardsBlock(t)].filter(Boolean);
    const top = extraBlocks(t, "top"), bottom = extraBlocks(t, "bottom");
    root.innerHTML = `${topBar(t)}${header(t)}${tiles(t)}
      ${top.map((b) => `<div class="mg-wide">${b}</div>`).join("")}
      ${row(oddsBlock(t), powerBlock(t))}
      ${row(weekBlock(t), h2hBlock(t))}
      ${row(tradesBlock(t), side.length ? `<div class="mg-col">${side.join("")}</div>` : "")}
      ${bottom.length ? `<div class="mg-extra">${bottom.join("")}</div>` : ""}`;
    const od = $("#mgOdds", root);
    if (od && typeof A.oddsChart === "function") A.oddsChart(od, t.id);
    drawPower(t);
    for (const b of A.managerBlocks) if (typeof b.after === "function") safely(() => b.after(t, root));
  }

  function renderMissing() {
    document.title = PAGE_TITLE;
    root.innerHTML = `<div class="card empty mg-missing"><p>No manager by that name here.</p><p><a class="mg-back" href="#managers">← All managers</a></p></div>`;
  }

  root.addEventListener("click", (e) => {
    const b = e.target.closest("[data-more]");
    if (!b || !root.contains(b)) return;
    const open = b.getAttribute("aria-expanded") !== "true";
    root.querySelectorAll("#mgAwards .x").forEach((li) => (li.hidden = !open));
    b.setAttribute("aria-expanded", String(open));
    b.textContent = open ? "Show fewer" : `Show all ${root.querySelectorAll("#mgAwards li").length}`;
  });

  // Leaving the managers tab: put the plain page title back.
  addEventListener("hashchange", () => { if (!/^#\/?managers?(\/|$)/.test(location.hash)) document.title = PAGE_TITLE; });

  onRoute("managers", (params) => {
    const id = params[0];
    if (id == null || id === "") return renderList();
    const t = T[+id];
    return t ? renderPage(t) : renderMissing();
  });
})();
