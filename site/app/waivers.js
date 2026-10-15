// Waivers tab, bottom section: adds, drops and trades per team. (FAAB dollars live in
// the report card above; see faab.js.)
(function () {
  const A = window.App;
  if (!A) return;
  const { teams, $, chip } = A;

  const sub = $("#moves .sub");
  if (sub) sub.textContent = "Every add, drop and trade this season, per team. Adds are waiver claims plus free-agent pickups.";

  const cell = (n) => (n ? `<td class="n">${n}</td>` : '<td class="n dim">0</td>');
  const moves = [...teams].sort((a, b) => b.adds - a.adds || b.drops - a.drops || b.trades - a.trades);
  $("#moveTbl").innerHTML = `<thead><tr><th>Team</th><th class="n">Adds</th><th class="n">Drops</th><th class="n">Trades</th></tr></thead><tbody>${
    moves.map((t) => `<tr><td>${chip(t)}</td>${cell(t.adds)}${cell(t.drops)}${cell(t.trades)}</tr>`).join("")}</tbody>`;
})();
