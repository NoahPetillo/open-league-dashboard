// Odds tab, "Clinching scenarios": what is already settled for sure (playoff spot, division,
// last place) and which results this week could settle it. Exact, not simulated (D.clinch).
// Also adds a pill per settled status under each manager's name (App.managerTags).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, $, esc, chip } = A;

  const C = D.clinch;
  const root = $("#clinch");
  if (!root || !C || !Array.isArray(C.teams) || !C.teams.length) return;

  const week = C.week == null ? null : C.week;
  const W = C.weeks_left || 0;
  const rows = C.teams.filter((r) => T[r.team]);
  const scenarios = (C.scenarios || []).filter((s) => T[s.team]);
  const stOf = (r) => r.status || {};
  const mgOf = (r) => r.magic || {};

  // ── what each kind of scenario says ─────────────────────
  // tone: pos (good news), neg (bad news), mute (smaller news)
  const KINDS = [
    { kind: "playoffs_in", label: "Can clinch a playoff spot", verb: "clinches a playoff spot", tone: "pos" },
    { kind: "division_won", label: "Can clinch the division", verb: "clinches the division", tone: "pos" },
    { kind: "last_safe", label: "Can get safe from last place", verb: "is safe from last place", tone: "pos" },
    { kind: "playoffs_out", label: "Can be eliminated from the playoffs", verb: "is eliminated from the playoffs", tone: "neg" },
    { kind: "division_out", label: "Can be knocked out of the division race", verb: "is out of the division race", tone: "mute" },
    { kind: "last_locked", label: "Can be locked into last place", verb: "is locked into last place", tone: "neg" },
  ];

  const nm = (id) => (T[id] ? T[id].manager || T[id].name : "Team " + id);
  const record = (r) => `${r.wins}-${r.losses}${r.ties ? "-" + r.ties : ""}`;
  // A way is a set of games that must ALL go that way: "Alex beats Sam and Pat beats Kim".
  const wayText = (way) => way.map((g) => `${nm(g.winner)} beats ${nm(g.loser)}`).join(" and ");

  // The words of "Alex clinches a playoff spot if A, or if B." as plain text. With more than 4 ways,
  // show the first 3 (n: show that many instead, for a Share card that has to fit in 300 characters).
  function words(s, k, n) {
    const ways = (s.ways || []).filter((w) => Array.isArray(w) && w.length);
    if (!ways.length) return null;
    const shown = ways.slice(0, n == null ? (ways.length > 4 ? 3 : ways.length) : n);
    const more = ways.length - shown.length;
    return {
      ways, shown, name: nm(s.team), verb: k.verb,
      body: shown.map((w, i) => (i ? "or if " : "if ") + wayText(w)).join(", "),
      tail: more > 0 ? `, or ${more} other combination${more === 1 ? "" : "s"} of results` : "",
    };
  }
  function sentence(s, k) {
    const p = words(s, k);
    return p ? `<b class="cl-name">${esc(p.name)}</b> <span class="cl-verb">${esc(p.verb)}</span> ${esc(p.body)}${p.tail}.` : "";
  }

  // ── "Share to the board" (account.js; the buttons are hidden unless you're signed in) ──
  const share = A.shareBtn || (() => "");
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
  const weekTitle = (what) => (week == null ? what[0].toUpperCase() + what.slice(1) : `Week ${week} ${what}`);
  // A scenario line, as plain text: the same sentence, with fewer ways if it won't fit in 300 characters.
  function scenarioStat(s, k) {
    let p = words(s, k), text = "";
    for (let n = p.shown.length; n >= 1; n--) {
      p = words(s, k, n);
      text = `${p.name} ${p.verb} ${p.body}${p.tail}.`;
      if (text.length <= 300) break;
    }
    const teams = [s.team];
    for (const g of p.shown.flat()) for (const id of [g.winner, g.loser]) if (T[id] && !teams.includes(id)) teams.push(id);
    return { kind: "clinch", title: weekTitle("clinching scenario"), text: clip(text, 300), facts: [["Ways it happens", String(p.ways.length)]], teams: teams.slice(0, 4), link: "#clinch" };
  }
  // A table row's magic numbers, as plain text; null when the row has nothing to say (both cells are dashes).
  function rowStat(r) {
    const s = stOf(r), m = mgOf(r), name = nm(r.team), lines = [], facts = [["Record", record(r)]];
    const wins = (n) => `${n} more win${n === 1 ? "" : "s"}`;
    if (s.playoffs_in || m.playoffs === 0) lines.push(`${name} has clinched a playoff spot.`);
    else if (s.playoffs_out) lines.push(`${name} is eliminated from the playoffs.`);
    else if (m.playoffs > 0) {
      lines.push(`${name} clinches a playoff spot with ${wins(m.playoffs)}, no help needed.`);
      facts.push(["Wins to clinch a spot", `${m.playoffs} of ${W} left`]);
    }
    if (s.division_won) lines.push(`${name} has won the division.`);
    if (s.last_locked) lines.push(`${name} is locked into last place.`);
    else if (s.last_safe || m.safe === 0) lines.push(`${name} is safe from last place.`);
    else if (m.safe > 0) {
      lines.push(`${name} is safe from last place with ${wins(m.safe)}, no help needed.`);
      facts.push(["Wins to be safe from last", `${m.safe} of ${W} left`]);
    }
    if (!lines.length) return null;
    const number = m.playoffs > 0 || m.safe > 0;
    return { kind: "clinch", title: weekTitle(number ? "magic number" : "clinch status"), text: clip(lines.join(" "), 300), facts, teams: [r.team], link: "#clinch" };
  }

  function scenarioBlock() {
    const groups = KINDS.map((k) => {
      const items = scenarios.filter((s) => s.kind === k.kind)
        .map((s) => ({ s, k, text: sentence(s, k) })).filter((x) => x.text);
      if (!items.length) return "";
      const li = items.map((x) => `<li class="cl-row">${chip(T[x.s.team])}<p class="cl-txt">${x.text}${share(scenarioStat(x.s, x.k))}</p></li>`).join("");
      return `<div class="cl-grp"><div class="cl-kind cl-${k.tone}"><i aria-hidden="true"></i>${esc(k.label)}</div><ul class="cl-list">${li}</ul></div>`;
    }).join("");
    if (groups) return `<div class="card cl-card">${groups}</div>`;
    const anyStatus = rows.some((r) => Object.values(stOf(r)).some(Boolean));
    return `<p class="cl-none">Nothing can be clinched or lost for good in week ${esc(week)}.${anyStatus ? "" : " Every team is still alive for the playoffs, and anyone can still finish last."}</p>`;
  }

  // ── the table: wins still needed ────────────────────────
  const tip = (s) => ` data-tip="${esc(`<div class="r"><span>${esc(s)}</span></div>`)}"`;
  const pill = (tone, text, tipText) => `<span class="cl-pill cl-${tone}"${tipText ? tip(tipText) : ""}>${esc(text)}</span>`;
  // The dash. Once the regular season is over there is nothing left to win, so no tip.
  const dash = () => `<span class="dim"${W ? tip("Even winning out doesn't guarantee it yet") : ""}>–</span>`;
  // "Win any 7 of the last 10", "Win out (all 10)": n is always at most the games left.
  const winPhrase = (n) => (n >= W ? (W === 1 ? "Win the last game" : `Win all ${W} remaining games`) : `Win any ${n} of the last ${W}`);

  // One cell of magic-number text. s is the team's status, m its magic numbers.
  function playoffCell(s, m) {
    if (s.playoffs_in || m.playoffs === 0) return pill("pos", "Clinched", "Already in the playoffs, whatever else happens");
    if (s.playoffs_out) return pill("neg", "Out", "Can't make the playoffs any more");
    if (m.playoffs > 0) return `<span class="cl-num"${tip(`${winPhrase(m.playoffs)} and they're in, whatever else happens`)}>${m.playoffs}</span>`;
    return dash();
  }
  function lastCell(s, m) {
    if (s.last_locked) return pill("neg", "Locked into last", "Can't climb out of last place now");
    if (s.last_safe || m.safe === 0) return pill("pos", "Safe", "Can't finish last, whatever else happens");
    if (m.safe > 0) return `<span class="cl-num"${tip(`${winPhrase(m.safe)} and they can't finish last, whatever else happens`)}>${m.safe}</span>`;
    return dash();
  }

  // Sort: fewest wins to clinch first (clinched, then numbers, then unknown, then out),
  // ties by wins to be safe (nobody-knows last), then most wins.
  const keyPlayoffs = (r) => {
    const s = stOf(r), m = mgOf(r);
    if (s.playoffs_in || m.playoffs === 0) return 0;
    if (s.playoffs_out) return 3000;
    return m.playoffs > 0 ? m.playoffs : 2000;
  };
  const keySafe = (r) => {
    const s = stOf(r), m = mgOf(r);
    if (s.last_safe || m.safe === 0) return 0;
    if (s.last_locked) return 3000;
    return m.safe > 0 ? m.safe : 2000;
  };
  const sorted = [...rows].sort((a, b) => keyPlayoffs(a) - keyPlayoffs(b) || keySafe(a) - keySafe(b) || b.wins - a.wins);

  function table() {
    const over = W === 0;
    const head = `<thead><tr><th>Team</th><th class="n">Record</th><th class="n">${over ? "Playoff spot" : "Wins to clinch a spot"}</th><th class="n">${over ? "Last place" : "Wins to be safe from last"}</th></tr></thead>`;
    const body = sorted.map((r) => {
      const s = stOf(r), m = mgOf(r);
      const div = s.division_won ? pill("pos", "Division", "Won its division") : "";
      const st = rowStat(r);
      return `<tr><td><div class="cl-tm">${chip(T[r.team])}${div}${st ? share(st) : ""}</div></td><td class="n">${esc(record(r))}</td><td class="n cl-m">${playoffCell(s, m)}</td><td class="n cl-m">${lastCell(s, m)}</td></tr>`;
    }).join("");
    const note = over ? "The regular season is over, so every spot is settled."
      : `Wins to clinch: win any that many of the ${W} games left and you're in, whatever else happens. – means even winning out doesn't guarantee it yet.`;
    return `<div class="card tbl-wrap"><table class="cl-tbl">${head}<tbody>${body}</tbody></table></div><p class="sub cl-note">${esc(note)}</p>`;
  }

  // ── render ──────────────────────────────────────────────
  const intro = (week == null ? "What's settled for sure." : `What's settled for sure, and what week ${esc(week)} could settle.`)
    + " Exact, not simulated: each line holds however every other game goes and whoever wins the tiebreakers. Assumes no tied games.";
  root.innerHTML = `<h2>Clinching scenarios</h2><p class="sub">${intro}</p>`
    + (week == null ? "" : `<h3 class="cl-h3">Week ${esc(week)}</h3>${scenarioBlock()}`)
    + `<h3 class="cl-h3">Where everyone stands</h3>${table()}`;
  root.hidden = false;

  // ── manager page: a pill for each settled status ────────
  const byTeam = Object.fromEntries(rows.map((r) => [r.team, r]));
  A.managerTags.push((t) => {
    const r = byTeam[t.id];
    if (!r) return "";
    const s = stOf(r);
    const tag = (tone, text, why) => `<span class="cl-pill cl-${tone}" title="${esc(why)}">${esc(text)}</span>`;
    const out = [];
    if (s.playoffs_in) out.push(tag("pos", "Clinched a playoff spot", "In the playoffs, whatever else happens"));
    if (s.division_won) out.push(tag("pos", week == null ? "Won the division" : "Clinched the division", "Wins the division, whatever else happens"));
    if (s.playoffs_out) out.push(tag("neg", "Eliminated", "Can't make the playoffs any more"));
    // Implied by a spot or an elimination, so no second pill for it.
    if (s.division_out && !s.playoffs_out && !s.division_won) out.push(tag("mute", "Out of the division race", "Can't win the division any more"));
    if (s.last_safe && !s.playoffs_in) out.push(tag("pos", "Safe from last", "Can't finish last, whatever else happens"));
    if (s.last_locked) out.push(tag("neg", "Locked into last", "Last place is locked in"));
    return out.join("");
  });
})();
