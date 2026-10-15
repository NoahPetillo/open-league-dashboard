// Trades tab: who says yes. How every team answers the trade offers it gets, and who
// starts the deals that go through (D.offers, from league/offers.py).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, $, esc, chip, tipHtml, fmtDate } = A;
  const root = $("#offers");
  const O = D.offers;
  if (!root) return;
  if (!O || !O.teams || !O.teams.some((r) => r.answered)) { root.hidden = true; return; }

  const pc = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
  const rows = O.teams.filter((r) => T[r.team]);
  const answered = O.accepted + O.declined;
  const who = (r) => `<b>${esc(T[r.team].name)}</b> · ${esc(T[r.team].manager)}`;
  const MIN = 5; // fewer answers than this and a yes rate is just noise
  const hasSent = rows.some((r) => r.sent != null);
  // Offers sent is a floor for everyone but the team the site reads ESPN as (see league/offers.py).
  const sentLabel = (r) => `${r.sent}${r.sent_exact ? "" : "+"}`;
  const viewer = O.viewer != null && T[O.viewer] ? T[O.viewer] : null;

  // ── tiles (ties name everyone tied) ──────────────────────
  const names = (list) => {
    const n = list.map((r) => `<b>${esc(T[r.team].manager || T[r.team].name)}</b>`);
    return n.length > 1 ? `${n.slice(0, -1).join(", ")} and ${n.at(-1)}` : n[0];
  };
  const best = (arr, key) => {
    if (!arr.length) return [];
    const top = Math.max(...arr.map(key));
    return arr.filter((r) => key(r) === top);
  };
  const rated = rows.filter((r) => r.answered >= MIN);
  const wall = best(rows, (r) => r.declined).filter((r) => r.declined > 0);
  const easy = best(rated, (r) => r.accept_rate);
  const hard = best(rated, (r) => -r.accept_rate);
  const starter = best(rows, (r) => r.started).filter((r) => r.started > 0);
  const spammer = best(rows, (r) => r.sent || 0).filter((r) => r.sent > 0);
  const each = (list) => (list.length > 1 ? " each" : "");
  const tile = (label, value, whoHtml) => `<div class="card tile"><div class="label">${label}</div><div class="value">${value}</div><div class="who">${whoHtml}</div></div>`;
  const tiles = [
    wall.length ? tile("The wall", `${wall[0].declined} no's`, wall.length === 1 ? `${who(wall[0])} · said yes to ${wall[0].accepted} of ${wall[0].answered}` : `${names(wall)}${each(wall)}`) : "",
    easy.length ? tile("Easiest yes", pc(easy[0].accept_rate), easy.length === 1 ? `${who(easy[0])} · ${easy[0].accepted} of ${easy[0].answered} accepted` : `${names(easy)}`) : "",
    hard.length && hard[0].accept_rate !== easy[0]?.accept_rate ? tile("Hardest sell", pc(hard[0].accept_rate), hard.length === 1 ? `${who(hard[0])} · ${hard[0].accepted} of ${hard[0].answered} accepted` : `${names(hard)} · ${hard.map((r) => `${r.accepted} of ${r.answered}`).join(", ")}`) : "",
    spammer.length === 1 ? tile("Serial offerer", `${sentLabel(spammer[0])} offers`, `${who(spammer[0])} · ${spammer[0].sent_unanswered} never got an answer${starter.length === 1 && starter[0] === spammer[0] ? ` · started ${spammer[0].started} trades, the most` : ""}`) : "",
    starter.length && !(spammer.length === 1 && starter.length === 1 && starter[0] === spammer[0]) ? tile("Deal starter", `${starter[0].started} deals`, starter.length === 1 ? `${who(starter[0])} · started ${starter[0].started} of the ${D.trades.length} trades` : `${names(starter)}${each(starter)}`) : "",
  ].filter(Boolean).join("");

  // ── table ───────────────────────────────────────────────
  const sorted = [...rows].sort((a, b) => b.answered - a.answered || (a.accept_rate ?? 1) - (b.accept_rate ?? 1));
  const body = sorted.map((r) => {
    const tip = tipHtml(T[r.team].name, [["Offers answered", r.answered], ["Accepted", r.accepted], ["Declined", r.declined], ["Trades it started", r.started]]);
    const sentTip = tipHtml(`${T[r.team].name}: offers sent`, [["Went through", r.started], ["No answer (withdrawn, expired or replaced)", r.sent_unanswered],
      [r.sent_exact ? "Declined" : "Declined (only ones ESPN shows)", r.sent_declined], ["Total", sentLabel(r) + (r.sent_exact ? "" : " (at least)")]]);
    const sent = hasSent ? `<td class="n" data-tip="${sentTip}">${r.sent_exact ? `<b>${r.sent}</b>` : `${r.sent}<span class="of-plus">+</span>`}</td>` : "";
    const rate = r.accept_rate == null ? '<span class="dim">–</span>'
      : `<span class="of-rate"><b>${pc(r.accept_rate)}</b><span class="of-meter" aria-hidden="true"><i style="width:${(r.accept_rate * 100).toFixed(1)}%"></i></span></span>`;
    return `<tr data-tip="${tip}"><td>${chip(T[r.team])}</td><td class="n">${r.answered}</td><td class="n hide-xs">${r.accepted}</td><td class="n hide-xs">${r.declined}</td><td class="n">${rate}</td>${sent}<td class="n">${r.started}</td></tr>`;
  }).join("");

  root.innerHTML = `<h2>Who says yes?</h2>
    <p class="sub">Every trade offer each team has answered${O.since ? ` since ${fmtDate(O.since)}` : ""}: ${answered} answers, ${O.accepted} yes (${pc(answered ? O.accepted / answered : null)}). ESPN shows the league who answered each offer, but not always who sent it. Sent is a floor ("98+" means at least 98): it counts offers that went through, offers that never got an answer, and declined offers only when ESPN shows the sender, which it hides for ${O.unknown_sender_declines ?? "most"} of the ${O.declined} declined offers.${viewer ? ` ${esc(viewer.manager || viewer.name)}'s number is exact, since the site reads ESPN through ${esc(viewer.manager || viewer.name)}'s account.` : ""}</p>
    ${tiles ? `<div class="tiles of-tiles">${tiles}</div>` : ""}
    <div class="card tbl-wrap"><table class="of-tbl">
      <thead><tr><th>Team</th><th class="n" title="Offers this team accepted or declined"><span class="lg">Answered</span><span class="sm">Asked</span></th><th class="n hide-xs">Yes</th><th class="n hide-xs">No</th><th class="n" title="Share of answered offers it accepted"><span class="lg">Yes rate</span><span class="sm">Yes %</span></th>${hasSent ? '<th class="n" title="Offers this team sent: at least this many (+), exactly for the team the site reads ESPN as">Sent</th>' : ""}<th class="n" title="Trades that went through where this team sent the offer"><span class="lg">Started</span><span class="sm">Deals</span></th></tr></thead>
      <tbody>${body}</tbody>
    </table></div>
    <p class="note">Sorted by offers answered. A yes rate needs at least ${MIN} answers to make a tile.</p>`;
})();
