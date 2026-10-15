// Waivers tab: "The ones that got away" (#dropregret), plus a block on every manager page.
// Players a team cut who kept scoring: points from the drop until the same team picked him back
// up, wherever he played. Data: D.drops (league/drops.py).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, teams, $, esc, f1, fmtDate, chip, tipHtml, divergingBars, headshot } = A;

  const R = D.drops;
  if (!R || !Array.isArray(R.drops)) return;

  // ── small helpers ───────────────────────────────────────
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
  const meta = (d) => [d.pos, d.pro_team].filter((x) => x && x !== "?").join(" · ");
  const mgrCount = {};
  teams.forEach((t) => { if (t.manager) mgrCount[t.manager] = (mgrCount[t.manager] || 0) + 1; });
  // A manager's name, or "Name (Team)" when two teams share a name, or the team's name.
  function who(id) {
    const t = T[id];
    if (!t) return "Someone";
    if (!t.manager) return t.name;
    return mgrCount[t.manager] > 1 ? `${t.manager} (${t.name})` : t.manager;
  }
  const possessive = (s) => (/s$/i.test(s) ? `${s}'` : `${s}'s`);
  const nowText = (d) => (d.now_team != null && T[d.now_team] ? `now with ${who(d.now_team)}` : "now a free agent");

  // Only drops with a finished week since mean anything; the rest are too fresh to judge.
  const seen = R.drops.filter((d) => T[d.team] && d.weeks_since > 0);
  const scored = seen.filter((d) => d.points_since > 0);

  // The team that started him the most (for weeks he was on someone else's roster).
  function startedBy(d) {
    const by = new Map();
    for (const w of d.weeks || []) {
      if (w.started && w.holder != null && w.holder !== d.team && T[w.holder]) by.set(w.holder, (by.get(w.holder) || 0) + w.points);
    }
    const best = [...by].sort((a, b) => b[1] - a[1])[0];
    return best && best[1] > 0 ? { team: best[0], points: best[1] } : null;
  }

  // ── "Share to the board" (account.js): one drop as a plain-text stat ──
  const share = A.shareBtn || (() => "");
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  function dropStat(d, title = "The one that got away") {
    const pts = f1(d.points_since);
    const first = d.readded
      ? `${who(d.team)} dropped ${d.name}, watched him score ${pts}, then took him back.`
      : `${who(d.team)} dropped ${d.name} and has watched him score ${pts} since.`;
    const sb = d.for_others && d.for_others.started_points > 0 ? startedBy(d) : null;
    const now = d.now_team != null && T[d.now_team] ? who(d.now_team) : "Free agent";
    return {
      kind: "drop", title,
      text: clip(first + (sb ? ` ${f1(sb.points)} of them in ${possessive(who(sb.team))} lineup.` : ""), 300),
      facts: [["Points since", pts], ["Cut", fmtDate(d.date)], ["Weeks since", String(d.weeks_since)], ["Now with", clip(now, 40)]],
      teams: sb ? [d.team, +sb.team] : [d.team], link: "#dropregret",
    };
  }

  // ── headline ────────────────────────────────────────────
  function headline(d) {
    const ini = esc((d.name.match(/[A-Za-z0-9]+/g) || ["?"]).map((w) => w[0]).slice(0, 2).join(""));
    const src = headshot(d);
    const img = src
      ? `<img src="${esc(src)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=&quot;ph&quot;>${ini}</span>'">`
      : `<span class="ph">${ini}</span>`;
    const pts = `<b class="neg">${f1(d.points_since)}</b>`;
    const line = d.readded
      ? `${esc(who(d.team))} dropped <b>${esc(d.name)}</b>, watched him score ${pts}, then took him back.`
      : `${esc(who(d.team))} dropped <b>${esc(d.name)}</b> and has watched him score ${pts} since.`;
    const sb = d.for_others && d.for_others.started_points > 0 ? startedBy(d) : null;
    const facts = [meta(d), `cut ${fmtDate(d.date)}`, plural(d.weeks_since, "week"),
      nowText(d)].filter(Boolean);
    return `<div class="card dr-top">
      <div class="dr-shot">${img}</div>
      <div class="dr-copy">
        <div class="dr-top-hd"><div class="dr-label">Biggest regret</div>${share(dropStat(d, "Biggest regret"))}</div>
        <p class="dr-line">${line}</p>
        ${sb ? `<p class="dr-line dr-line2">${f1(sb.points)} of them in ${esc(possessive(who(sb.team)))} lineup.</p>` : ""}
        <p class="dr-facts">${esc(facts.join(" · "))}</p>
      </div>
    </div>`;
  }

  // ── table ───────────────────────────────────────────────
  const SHOW = 15;
  const tipRows = (d) => (d.weeks || []).map((w) => {
    const at = w.holder == null ? "free agent" : w.holder === d.team ? "the team that cut him" : who(w.holder) + (w.started ? ", started" : ", benched");
    return [`Wk ${w.week} · ${at}`, f1(w.points)];
  });

  function rowHtml(d, i) {
    const fo = d.for_others || { points: 0, started_points: 0 };
    const now = d.now_team != null && T[d.now_team] ? chip(T[d.now_team]) : '<span class="dim">Free agent</span>';
    // Under the name on narrow screens, where the Dropped, Wks and Now with columns are hidden.
    const sum = [`cut ${fmtDate(d.date)}`, plural(d.weeks_since, "wk"), nowText(d)].join(" · ");
    const sumX = fo.points > 0 ? ` · ${f1(fo.points)} for other teams${fo.started_points > 0 ? `, ${f1(fo.started_points)} started` : ""}` : "";
    const others = fo.points > 0
      ? `<b>${f1(fo.points)}</b>${fo.started_points > 0 ? `<small>${f1(fo.started_points)} started</small>` : ""}`
      : '<span class="dim">–</span>';
    return `<tr${i >= SHOW ? " hidden" : ""}>
      <td class="dr-pl"><span class="dr-nm"><b>${esc(d.name)}</b>${meta(d) ? `<span class="dr-pos">${esc(meta(d))}</span>` : ""}</span><span class="dr-sum">${esc(sum)}<span class="dr-sum-x">${esc(sumX)}</span></span></td>
      <td>${chip(T[d.team])}</td>
      <td class="hide-sm dim">${fmtDate(d.date)}</td>
      <td class="n" data-tip="${tipHtml(d.name, tipRows(d))}"><b class="dr-pts">${f1(d.points_since)}</b></td>
      <td class="n hide-sm">${d.weeks_since}</td>
      <td class="hide-sm">${now}</td>
      <td class="n dr-oth hide-xs">${others}</td>
      <td class="dr-sh" data-acct>${share(dropStat(d))}</td>
    </tr>`;
  }

  function tableHtml() {
    const more = scored.length > SHOW
      ? `<button type="button" class="dr-more" aria-expanded="false" aria-controls="drTbl">Show all ${scored.length}</button>` : "";
    return `<div class="card dr-card"><div class="tbl-wrap"><table class="dr-tbl" id="drTbl">
      <caption class="sr-only">Players dropped who kept scoring, biggest regret first</caption>
      <thead><tr><th>Player</th><th>Dropped by</th><th class="hide-sm">Dropped</th>
        <th class="n" title="Points he has scored since the drop, until the same team took him back">Points since</th>
        <th class="n hide-sm" title="Weeks since the drop that count: his game kicked off after the drop">Wks</th>
        <th class="hide-sm">Now with</th>
        <th class="n hide-xs" title="Points he scored while on another team's roster, and how many of those were in its starting lineup">For other teams</th>
        <th class="dr-sh" data-acct><span class="sr-only">Share</span></th></tr></thead>
      <tbody>${scored.map(rowHtml).join("")}</tbody></table></div>${more}</div>`;
  }

  // ── bars ────────────────────────────────────────────────
  function drawBars(el) {
    const rows = (R.teams || []).filter((r) => T[r.team])
      .map((r) => ({ t: T[r.team], v: r.regret_points || 0, n: r.drops || 0 }))
      .sort((a, b) => b.v - a.v);
    divergingBars(el, rows, f1,
      (r) => tipHtml(r.t.name, [["QB/RB/WR/TE drops", r.n], ["Points scored since", f1(r.v)]]), { top: "laugh" });
  }

  // ── the section ─────────────────────────────────────────
  const root = $("#dropregret");
  if (root && seen.length) {
    const body = scored.length
      ? `${headline(scored[0])}
        <h3 class="dr-h3">Everyone's regrets</h3>
        ${tableHtml()}
        <h3 class="dr-h3">Regret points by team</h3>
        <p class="sub">Everything the players each team cut have scored since.</p>
        <div class="card"><div class="bars" id="drBars"></div></div>
        <p class="note">A week counts when his game kicked off after the drop. "For other teams" is what he scored while on another team's roster; "started" means that team had him in its starting lineup. Cuts made this week count once the week is done.</p>`
      : '<div class="card empty">No regrets yet. Every cut has stayed cut.</div>';
    root.innerHTML = `<h2>The ones that got away</h2>
      <p class="sub">Players a team cut who kept scoring. Points count from the drop until that same team picked him back up, wherever he played. QBs, RBs, WRs and TEs only: everyone streams kickers, coaches and defenders.</p>
      ${body}`;
    root.hidden = false;
    const bars = $("#drBars", root);
    if (bars) drawBars(bars);
    const more = $(".dr-more", root);
    if (more) {
      more.addEventListener("click", () => {
        const open = more.getAttribute("aria-expanded") !== "true";
        root.querySelectorAll("#drTbl tbody tr").forEach((tr, i) => { tr.hidden = !open && i >= SHOW; });
        more.setAttribute("aria-expanded", String(open));
        more.textContent = open ? "Show fewer" : `Show all ${scored.length}`;
      });
    }
  }

  // ── manager pages: this team's three biggest regrets ────
  A.managerBlocks.push({
    order: 50,
    place: "bottom",
    render(t) {
      const mine = scored.filter((d) => d.team === t.id);
      const head = '<h3>The ones that got away</h3>';
      if (!mine.length) {
        return `<div class="card mg-blk">${head}<p class="cap">Players this team cut who kept scoring.</p><div class="empty">No regrets yet. Every cut has stayed cut.</div></div>`;
      }
      const total = (R.teams || []).find((r) => r.team === t.id);
      const items = mine.slice(0, 3).map((d) => {
        const fo = d.for_others || { started_points: 0 };
        const sub = [`Cut ${fmtDate(d.date)}`, plural(d.weeks_since, "week"), d.readded ? "took him back" : nowText(d),
          fo.started_points > 0 ? `${f1(fo.started_points)} started for other teams` : ""].filter(Boolean).join(" · ");
        return `<li class="dr-mg-i" data-tip="${tipHtml(d.name, tipRows(d))}">
          <div class="dr-mg-top"><span class="dr-mg-n"><b>${esc(d.name)}</b>${meta(d) ? `<small>${esc(meta(d))}</small>` : ""}</span><span class="dr-mg-p"><b class="neg">${f1(d.points_since)}</b> pts</span></div>
          <div class="dr-mg-bot"><div class="dr-mg-sub">${esc(sub)}</div>${share(dropStat(d))}</div></li>`;
      }).join("");
      const cap = total
        ? `Players this team cut have scored ${f1(total.regret_points)} points since. ${mine.length > 3 ? "The three biggest:" : "Biggest first:"}`
        : "Players this team cut who kept scoring.";
      return `<div class="card mg-blk">${head}<p class="cap">${esc(cap)}</p><ul class="dr-mg">${items}</ul>
        <p class="mg-foot"><a href="#dropregret">Everyone's regrets ›</a></p></div>`;
    },
  });
})();
