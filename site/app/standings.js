// Standings tab: the sortable standings table.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, L, MY_TEAM, teams, T, ranked, $, $$, esc, f1, sgn, cls, pct, fmtDate, chip, tipHtml, divergingBars, onRoute } = A;

  const cols = [
    { k: "rank", h: "#", n: true, v: (t) => t.rank },
    { k: "name", h: "Team", v: (t) => t.name, html: (t) => chip(t) },
    { k: "wins", h: "W-L", n: true, v: (t) => t.wins + t.ties / 2 - t.losses / 100, html: (t) => `${t.wins}-${t.losses}${t.ties ? "-" + t.ties : ""}` },
    { k: "points_for", h: "PF", n: true, v: (t) => t.points_for, html: (t) => f1(t.points_for) },
    { k: "points_against", h: "PA", n: true, v: (t) => t.points_against, html: (t) => f1(t.points_against) },
    { k: "allplay", h: "All-play", n: true, v: (t) => t.allplay_w / Math.max(1, t.allplay_w + t.allplay_l), html: (t) => `${t.allplay_w}-${t.allplay_l}` },
    { k: "luck", h: "Luck", n: true, v: (t) => t.luck, html: (t) => `<span class="${cls(t.luck)}">${sgn(t.luck)}</span>` },
    { k: "streak", h: "Streak", n: true, v: (t) => (t.streak[0] === "W" ? 1 : -1) * +t.streak.slice(1), html: (t) => esc(t.streak) },
  ];
  let sortK = "rank", sortDir = 1;
  function drawStand() {
    const c = cols.find((c) => c.k === sortK);
    const rows = [...teams].sort((a, b) => {
      const x = c.v(a), y = c.v(b);
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortDir;
    });
    $("#standTbl").innerHTML = `<thead><tr>${cols.map((c) => `<th class="sortable ${c.n ? "n" : ""}" data-k="${c.k}" aria-sort="${c.k === sortK ? (sortDir > 0 ? "ascending" : "descending") : "none"}">${c.h}${c.k === sortK ? `<span class="arr">${sortDir > 0 ? "▲" : "▼"}</span>` : ""}</th>`).join("")}</tr></thead><tbody>${rows.map((t) => `<tr>${cols.map((c) => `<td class="${c.n ? "n" : ""}">${c.html ? c.html(t) : esc(c.v(t))}</td>`).join("")}</tr>`).join("")}</tbody>`;
  }
  $("#standTbl").addEventListener("click", (e) => {
    const th = e.target.closest("th[data-k]"); if (!th) return;
    if (sortK === th.dataset.k) sortDir *= -1; else { sortK = th.dataset.k; sortDir = th.dataset.k === "rank" || th.dataset.k === "name" ? 1 : -1; }
    drawStand();
  });
  drawStand();
})();
