// Waivers tab, top section: the FAAB report card. FAAB left is ESPN's own number;
// pickup points count only the weeks the player was on the roster of the team that
// added him. Data: D.faab (league/faab.py).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, teams, $, esc, f1, fmtDate, chip, tipHtml } = A;
  const root = $("#faab");
  if (!root) return;

  const F = D.faab;
  const heading = (sub) => `<h2>FAAB report card</h2><p class="sub">${sub}</p>`;
  if (!F || !Array.isArray(F.teams) || !F.teams.length) {
    root.innerHTML = heading("Who has FAAB left, and what the waiver pickups were worth.")
      + '<div class="card empty">No FAAB numbers yet. They show up the next time the site data is rebuilt.</div>';
    return;
  }

  // ── small helpers ───────────────────────────────────────
  const budget = F.budget || 100;
  const num = (x) => Math.round(x * 100) / 100;
  const usd = (n) => (n < 0 ? "−$" : "$") + Math.abs(num(n));
  const perPt = (x) => (x == null ? "–" : "$" + x.toFixed(2));
  const wk = (n) => `${n} wk${n === 1 ? "" : "s"}`;
  const name = (id) => (T[id] ? T[id].name : "Unknown team");
  const meta = (p) => [p.pos, p.pro_team].filter((x) => x && x !== "?").join(" · ");
  const rows = F.teams.filter((r) => T[r.team]);
  const H = F.highlights || {};

  // ── tiles ───────────────────────────────────────────────
  function tile(label, p, line, empty) {
    if (!p) return `<div class="card tile"><div class="label">${label}</div><div class="value dim">–</div><div class="who">${empty}</div></div>`;
    return `<div class="card tile">
      <div class="label">${label}</div>
      <div class="value">${esc(p.name)}</div>
      <div class="who"><b>${esc(name(p.team))}</b>${meta(p) ? ` <span class="dim">· ${esc(meta(p))}</span>` : ""}</div>
      <div class="stat">${line(p)}</div>
    </div>`;
  }
  const started = (p) => `${f1(p.started_points)} started pts`;
  const perDollar = (p) => `${num(p.started_points / p.bid).toFixed(2)} pts per $`;
  const benched = (p) => (p.points - p.started_points > 0.05 ? ` · ${f1(p.points - p.started_points)} pts left on the bench` : "");

  const maxLeft = Math.max(...rows.map((r) => r.left));
  const richest = rows.filter((r) => r.left === maxLeft);
  const richWho = richest.length === 1 ? esc(name(richest[0].team))
    : richest.length === rows.length ? "Nobody has spent a dollar"
    : richest.length <= 3 ? "Tied: " + richest.map((r) => esc(name(r.team))).join(", ") : `${richest.length} teams tied`;

  const med = H.median_pts_per_dollar;
  const bustRule = med ? `the biggest bid that returned no more than the league median of ${med.toFixed(2)} started pts per $`
    : "the biggest bid that put up nothing in a starting lineup";
  const tiles = [
    tile("Best value pickup", H.best_value, (p) => `${usd(p.bid)} bid · ${started(p)} · ${perDollar(p)}`,
      "No paid pickup has made a starting lineup yet."),
    tile("Best free pickup", H.best_free, (p) => `${usd(p.bid)} · ${started(p)} · ${wk(p.weeks)}`,
      "No free pickup has made a starting lineup yet."),
    tile("Most expensive bust", H.bust, (p) => `${usd(p.bid)} bid · ${started(p)}${benched(p)}`,
      "Needs two paid pickups that have been on a roster for a finished week."),
    tile("Biggest bid", H.biggest_bid, (p) => `${usd(p.bid)} bid · ${p.weeks ? started(p) : "no finished week yet"}`,
      "No one has won a bid yet."),
    `<div class="card tile"><div class="label">Most FAAB left</div><div class="value big">${usd(maxLeft)}</div><div class="who">${richWho}</div></div>`,
  ].join("");

  // ── table ───────────────────────────────────────────────
  const open = new Set();
  let sortKey = "left";
  const order = {
    left: (a, b) => b.left - a.left || b.pickup_started_points - a.pickup_started_points,
    pts: (a, b) => b.pickup_started_points - a.pickup_started_points || b.left - a.left,
  };

  // FAAB that came or went outside of bids: trades, and anything the commish handed out.
  const viaTrades = (r) => (!r.faab_in && !r.faab_out && !r.commish ? '<span class="dim">–</span>'
    : [r.faab_in ? `<span class="pos">+${usd(r.faab_in)}</span>` : "", r.faab_out ? `<span class="neg">−${usd(r.faab_out)}</span>` : "",
      r.commish ? `<span class="${r.commish > 0 ? "pos" : "neg"}" title="From the commish">${r.commish > 0 ? "+" : "−"}${usd(Math.abs(r.commish))} commish</span>` : ""].filter(Boolean).join(" "));

  function pickRow(p) {
    const status = [p.kind === "waiver" ? "waiver" : "free agent",
      p.weeks ? wk(p.weeks) : p.let_go ? "let go before a week finished" : "just added",
      p.weeks && p.let_go ? "let go" : ""].filter(Boolean).join(" · ");
    const pts = p.weeks ? `<b>${f1(p.started_points)}</b> started <span class="dim">/ ${f1(p.points)} total</span>` : '<span class="dim">no finished week</span>';
    return `<li class="pk"><span class="pk-n"><b>${esc(p.name)}</b>${meta(p) ? `<span class="pp">${esc(meta(p))}</span>` : ""}</span>
      <span class="pk-bid">${usd(p.bid)}</span><span class="pk-meta">${esc(status)}</span><span class="pk-pts">${pts}</span></li>`;
  }

  function rowHtml(r) {
    const t = T[r.team];
    const isOpen = open.has(r.team);
    const bp = r.best_pickup;
    const left = Math.max(0, Math.min(1, r.left / budget)) * 100;
    const calc = r.left_source === "espn" ? "" : "*";
    const best = bp
      ? `<td class="faab-best hide-sm" data-tip="${tipHtml(bp.name, [["Bid", usd(bp.bid)], ["Weeks on roster", bp.weeks], ["Started pts", f1(bp.started_points)], ["All pts", f1(bp.points)]])}"><span class="ell">${esc(bp.name)} <span class="dim">${f1(bp.started_points)}</span></span></td>`
      : '<td class="faab-best hide-sm dim">–</td>';
    // Phones hide most table columns; this line carries them (shown by CSS at narrow widths only).
    const summary = `<div class="faab-sum">
      <span><b>${r.bids_won}</b> bid${r.bids_won === 1 ? "" : "s"} won</span><span><b>${usd(r.spent_on_bids)}</b> on bids</span>
      <span><b>${r.pickups}</b> pickup${r.pickups === 1 ? "" : "s"}</span>${r.dollars_per_started_point == null ? "" : `<span><b>${perPt(r.dollars_per_started_point)}</b> per started pt</span>`}
      ${r.faab_in || r.faab_out || r.commish ? `<span>Trades &amp; commish: <b>${viaTrades(r)}</b></span>` : ""}${bp ? `<span>Best: <b>${esc(bp.name)}</b> ${f1(bp.started_points)}</span>` : ""}</div>`;
    const list = r.pickup_list || [];
    return `<tr class="faab-row${isOpen ? " open" : ""}" data-team="${r.team}">
      <td><button type="button" class="faab-toggle" aria-expanded="${isOpen}" aria-controls="faab-d-${r.team}"><span class="chev" aria-hidden="true"></span>${chip(t, { link: false })}</button></td>
      <td class="n"><div class="fl"><b>${usd(r.left)}${calc}</b><span class="bar" aria-hidden="true"><i style="width:${left.toFixed(1)}%"></i></span></div></td>
      <td class="n hide-sm">${r.bids_won}</td>
      <td class="n hide-sm">${usd(r.spent_on_bids)}</td>
      <td class="n hide-sm">${r.pickups}</td>
      <td class="n">${f1(r.pickup_started_points)}</td>
      <td class="n hide-xs">${perPt(r.dollars_per_started_point)}</td>
      <td class="n hide-sm">${viaTrades(r)}</td>
      ${best}
    </tr>
    <tr class="faab-detail" id="faab-d-${r.team}"${isOpen ? "" : " hidden"}><td colspan="9">
      ${summary}
      ${list.length ? `<ul class="faab-picks">${list.map(pickRow).join("")}</ul>` : '<div class="dim faab-none">No waiver or free-agent pickups yet.</div>'}
    </td></tr>`;
  }

  function drawTable() {
    const sorted = [...rows].sort(order[sortKey]);
    $("#faabTbl", root).innerHTML = `<thead><tr>
      <th>Team</th>
      <th class="n" title="Straight from ESPN. Can top the budget when FAAB came in through trades.">FAAB left</th>
      <th class="n hide-sm" title="Winning bids above $0">Bids won</th>
      <th class="n hide-sm" title="Total of this team's winning bids">$ on bids</th>
      <th class="n hide-sm" title="Waiver and free-agent adds">Pickups</th>
      <th class="n" title="Points pickups scored in this team's starting lineup, only in weeks he was on its roster">Started pts</th>
      <th class="n hide-xs" title="Dollars bid, divided by started points from all of this team's pickups">$ / started pt</th>
      <th class="n hide-sm" title="FAAB received (+) or sent (−) in trades, and any the commish handed out">Trades &amp; commish</th>
      <th class="hide-sm" title="Pickup with the most started points">Best pickup</th>
    </tr></thead><tbody>${sorted.map(rowHtml).join("")}</tbody>`;
  }

  // ── FAAB in trades ──────────────────────────────────────
  const mgrCount = {};
  teams.forEach((t) => { if (t.manager) mgrCount[t.manager] = (mgrCount[t.manager] || 0) + 1; });
  function who(id) {
    const t = T[id];
    if (!t) return "<b>Someone</b>";
    if (!t.manager) return `<b>${esc(t.name)}</b>`;
    return mgrCount[t.manager] > 1 ? `<b>${esc(t.manager)}</b> <span class="dim">(${esc(t.name)})</span>` : `<b>${esc(t.manager)}</b>`;
  }
  const moved = [...(F.faab_trades || [])].sort((a, b) => b.date - a.date);
  const total = moved.reduce((s, x) => s + x.amount, 0);
  const tradesHtml = moved.length
    ? `<h3 class="faab-h3">FAAB in trades</h3>
       <p class="sub">${moved.length} trade${moved.length === 1 ? "" : "s"} carried FAAB: ${usd(total)} changed hands.</p>
       <ul class="card faab-moved">${moved.map((x) => `<li><span class="amt">${usd(x.amount)}</span>
         <span>${who(x.from)} sent ${who(x.to)} ${usd(x.amount)} in ${x.trade_id ? `<a href="#trade/${x.trade_id}">trade #${x.trade_id}</a>` : "a trade"} <span class="dim">· ${fmtDate(x.date)}</span></span></li>`).join("")}</ul>`
    : '<p class="faab-quiet">No FAAB has changed hands in a trade yet.</p>';

  // ── assemble ────────────────────────────────────────────
  const over = rows.some((r) => r.left > budget);
  const calced = rows.some((r) => r.left_source !== "espn");
  // Commish adjustments aren't in ESPN's activity feed; they're the part of ESPN's number
  // that bids and trades don't explain.
  const gifts = rows.filter((r) => r.commish);
  const giftLine = gifts.length ? (() => {
    const amounts = new Set(gifts.map((r) => r.commish));
    const names = gifts.map((r) => T[r.team]?.manager || T[r.team]?.name || "?");
    const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : names[0];
    const one = gifts[0].commish;
    return amounts.size === 1
      ? `${list} ${one > 0 ? "got" : "lost"} ${usd(Math.abs(one))}${gifts.length > 1 ? " each" : ""} ${one > 0 ? "from" : "to"} the commish. ESPN doesn't log that, so it's worked out as the gap between ESPN's number and the bids and trades.`
      : `The commish adjusted FAAB by hand for ${list}. ESPN doesn't log that, so it's worked out as the gap between ESPN's number and the bids and trades.`;
  })() : "";
  const notes = [
    over ? `A team can sit above ${usd(budget)}: FAAB it received in trades is added to its balance.` : "",
    giftLine,
    calced ? "* ESPN didn't report this team's number, so it's worked out from bids and trades." : "",
  ].filter(Boolean);

  root.innerHTML = heading(`FAAB left comes straight from ESPN: the ${usd(budget)} budget, minus winning bids, plus or minus FAAB traded, plus anything the commish handed out. Pickup points count only the weeks the player was on that team's roster, and "started" means he was in the starting lineup.`)
    + `<div class="tiles faab-tiles">${tiles}</div>
    <p class="note">Value is started points per $ of the winning bid. Bust is ${bustRule}. Pickups with no finished week on the team that won them aren't judged.</p>
    <div class="controls faab-controls">
      <div class="faab-seg" role="group" aria-label="Sort teams by">
        <button type="button" data-sort="left" aria-pressed="true">FAAB left</button><button type="button" data-sort="pts" aria-pressed="false">Started pts</button>
      </div>
      <span class="faab-hint">Tap a team to see its pickups</span>
    </div>
    <div class="card tbl-wrap"><table class="faab-tbl" id="faabTbl"></table></div>
    ${notes.map((n) => `<p class="note">${esc(n)}</p>`).join("")}
    ${tradesHtml}`;

  drawTable();
  const tbl = $("#faabTbl", root);
  tbl.addEventListener("click", (e) => {
    const tr = e.target.closest(".faab-row");
    if (!tr || e.target.closest("a")) return;
    const id = +tr.dataset.team;
    const now = !open.has(id);
    if (now) open.add(id); else open.delete(id);
    tr.classList.toggle("open", now);
    tr.querySelector(".faab-toggle").setAttribute("aria-expanded", String(now));
    $("#faab-d-" + id, root).hidden = !now;
  });
  root.querySelectorAll(".faab-seg button").forEach((b) => b.addEventListener("click", () => {
    sortKey = b.dataset.sort;
    root.querySelectorAll(".faab-seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    drawTable();
  }));
})();
