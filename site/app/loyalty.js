// Waivers tab: "Ride or die vs. revolving door" (#loyalty). Players who never left the roster that
// drafted them, and the roster spots with the most turnover. Data: D.loyalty (league/loyalty.py).
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, $, esc, f1, chip, tipHtml, divergingBars } = A;
  const root = $("#loyalty");
  const R = D.loyalty;
  if (!root || !R || !Array.isArray(R.teams)) return;

  const rows = R.teams.filter((r) => T[r.team] && r.drafted > 0);
  if (!rows.length) return;

  // ── small helpers ───────────────────────────────────────
  // How a position reads in a sentence: [one, many].
  const WORDS = { K: ["kicker", "kickers"], HC: ["head coach", "head coaches"], S: ["safety", "safeties"], "D/ST": ["defense", "defenses"] };
  const posWord = (pos, n) => (WORDS[pos] || [pos, pos + "s"])[n === 1 ? 0 : 1];
  const meta = (p) => (p.pos && p.pos !== "?" ? p.pos : "");
  const mgrCount = {};
  A.teams.forEach((t) => { if (t.manager) mgrCount[t.manager] = (mgrCount[t.manager] || 0) + 1; });
  function who(id) {
    const t = T[id];
    if (!t) return "Someone";
    if (!t.manager) return t.name;
    return mgrCount[t.manager] > 1 ? `${t.manager} (${t.name})` : t.manager;
  }
  const drafted = [...new Set(rows.map((r) => r.drafted))];
  const picks = drafted.length === 1 ? drafted[0] : null; // the same for every team, normally 19
  const ones = (r) => (r.day_ones || []).length;

  // ── "Share to the board" (account.js): plain-text stats ──
  const share = A.shareBtn || (() => "");
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  const doorStat = (d) => {
    const facts = [["Different players", String(d.count)], ["Position", clip(String(d.pos || "?"), 40)]];
    if (d.drafted != null) facts.push(["Drafted", String(d.drafted)], ["Added or traded for", String(d.count - d.drafted)]);
    return {
      kind: "loyalty", title: "Revolving door",
      text: clip(`${who(d.team)} has rostered ${d.count} different ${posWord(d.pos, d.count)} this season.`, 300),
      facts, teams: [d.team], link: "#loyalty",
    };
  };
  const riderStat = (p) => ({
    kind: "loyalty", title: "Top ride-or-die",
    text: clip(`${who(p.team)} drafted ${p.name} and never let him go. ${f1(p.points)} points so far.`, 300),
    facts: [["Player", clip(`${p.name}${meta(p) ? " · " + meta(p) : ""}`, 40)], ["Points", f1(p.points)]],
    teams: [p.team], link: "#loyalty",
  });
  const topRider = (R.ride_or_die || []).find((p) => T[p.team]) || null;

  // ── ride or die ─────────────────────────────────────────
  function riders() {
    const list = (R.ride_or_die || []).filter((p) => T[p.team]);
    if (!list.length) return '<div class="empty">Nobody has a pick that never moved.</div>';
    return `<div class="tbl-wrap"><table class="ly-tbl">
      <caption class="sr-only">Players who never left the roster that drafted them, by season points</caption>
      <thead><tr><th class="n ly-rk">#</th><th class="ly-pl">Player</th><th>Team</th><th class="n" title="Every completed week, bench weeks included">Pts</th></tr></thead>
      <tbody>${list.map((p, i) => `<tr><td class="n dim ly-rk">${i + 1}</td>
        <td class="ly-pl"><b>${esc(p.name)}</b>${meta(p) ? `<span class="ly-pos">${esc(meta(p))}</span>` : ""}</td>
        <td>${chip(T[p.team])}</td><td class="n"><b>${f1(p.points)}</b></td></tr>`).join("")}</tbody></table></div>`;
  }

  // ── revolving door ──────────────────────────────────────
  function doors() {
    const list = (R.revolving_doors || []).filter((d) => T[d.team]);
    if (!list.length) return '<div class="empty">No roster spot has turned over yet.</div>';
    return `<ol class="ly-doors">${list.map((d) => {
      const t = T[d.team];
      const added = d.count - (d.drafted || 0);
      const split = d.drafted != null ? `${d.drafted} drafted, ${added} added or traded for` : "";
      return `<li class="ly-door">
        <span class="ly-count" aria-hidden="true">${d.count}</span>
        <div class="ly-door-b">
          <p class="ly-door-t"><a href="#manager/${t.id}" title="${esc(t.name)}">${esc(who(d.team))}</a> has rostered <b>${d.count} different ${esc(posWord(d.pos, d.count))}</b></p>
          <div class="ly-door-r">${split ? `<p class="ly-door-s">${esc(split)}</p>` : ""}${share(doorStat(d))}</div>
          <details class="ly-names"><summary>The ${d.count}, in the order they arrived</summary><p>${esc((d.players || []).join(", "))}</p></details>
        </div>
      </li>`;
    }).join("")}</ol>`;
  }

  // ── bars ────────────────────────────────────────────────
  function keptBars(el) {
    const data = rows.map((r) => ({ t: T[r.team], v: r.kept, r })).sort((a, b) => b.v - a.v || ones(b.r) - ones(a.r));
    divergingBars(el, data, (v) => (picks ? `${v} of ${picks}` : String(v)), (x) => tipHtml(x.t.name, [
      ["Draft picks kept", `${x.r.kept} of ${x.r.drafted}`],
      ["Never moved", String(ones(x.r))],
      ["Left and came back", String(x.r.kept - ones(x.r))],
    ]), { top: "gold" });
  }

  function distinctBars(el) {
    const data = rows.map((r) => ({ t: T[r.team], v: r.distinct, r })).sort((a, b) => b.v - a.v);
    divergingBars(el, data, (v) => String(v), (x) => tipHtml(x.t.name,
      [["Different players", String(x.r.distinct)], ...Object.entries(x.r.by_pos || {}).map(([k, n]) => [k, String(n)])]), { top: "laugh" });
  }

  // ── the section ─────────────────────────────────────────
  root.innerHTML = `<h2>Ride or die vs. revolving door</h2>
    <p class="sub">From the draft and ESPN's transaction log.</p>
    <div class="two">
      <div class="card ly-card">
        <div class="ly-hd"><h3>Ride or die</h3>${topRider ? share(riderStat(topRider), { label: "Share top pick" }) : ""}</div>
        <p class="cap">Drafted, then never dropped, traded or picked up by anyone, and still on the roster that drafted them. Best seasons first.</p>
        ${riders()}
        <h4 class="ly-h4">Draft picks kept</h4>
        <p class="cap">How many of each team's ${picks ? `${picks} ` : ""}draft picks are still on its roster. Counts a pick who was cut and brought back, or traded away and back.</p>
        <div class="bars" id="lyKept"></div>
      </div>
      <div class="card ly-card">
        <h3>Revolving door</h3>
        <p class="cap">The roster spots with the most turnover: how many different players a team has had at one position.</p>
        ${doors()}
        <h4 class="ly-h4">Different players rostered</h4>
        <p class="cap">Draft picks plus everyone added or traded for. Kickers and head coaches count.</p>
        <div class="bars" id="lyDistinct"></div>
      </div>
    </div>`;
  root.hidden = false;
  keptBars($("#lyKept", root));
  distinctBars($("#lyDistinct", root));
})();
