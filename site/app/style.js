// Manager style: an archetype pill under a manager's name and a "Manager style" card right
// under their stat tiles (D.style, from league/style.py). The card gives the archetype with
// the numbers behind it, then a fingerprint: one row per dimension with the raw value and a
// 0-100% bar for where that value sits among the managers.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, T, esc, tipHtml } = A;
  const S = D.style;
  if (!S || !Array.isArray(S.dims) || !S.dims.length || !Array.isArray(S.teams)) return;

  const byTeam = {};
  for (const r of S.teams) {
    if (T[r.team] && r.archetype && r.metrics && r.pct && r.rank) byTeam[r.team] = r;
  }
  const profiles = Object.values(byTeam);
  if (profiles.length < 3) return;

  const ord = (n) => { const v = n % 100, s = ["th", "st", "nd", "rd"]; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;

  // A dimension's number the way league/style.py words it in the "why" line: $ for FAAB, whole
  // percents (rounded half up) for rates, plain numbers otherwise.
  function show(key, v) {
    if (v == null) return "–";
    if (key === "faab") return "$" + v;
    if (key === "yes_rate" || key === "loyalty") return Math.floor(v * 100 + 0.5) + "%";
    return String(v);
  }

  // Where a manager sits on one dimension, recounted from the numbers the page has: how many
  // of the other managers (with a value) are lower, and how many are tied.
  function standing(key, id) {
    const mine = byTeam[id].metrics[key];
    const others = profiles.filter((r) => r.team !== id && r.metrics[key] != null).map((r) => r.metrics[key]);
    return { n: others.length, below: others.filter((v) => v < mine).length, tied: others.filter((v) => v === mine).length };
  }

  // The counts behind a rate, from the other tabs' data when it is there.
  const counts = {
    yes_rate: (id) => {
      const o = D.offers && Array.isArray(D.offers.teams) ? D.offers.teams.find((x) => x.team === id) : null;
      return o && o.answered != null ? ["Offers answered", `${o.accepted} yes, ${o.declined} no`] : null;
    },
    loyalty: (id) => {
      const l = D.loyalty && Array.isArray(D.loyalty.teams) ? D.loyalty.teams.find((x) => x.team === id) : null;
      return l && l.drafted ? ["Draft picks still here", `${l.kept} of ${l.drafted}`] : null;
    },
  };

  // ── the fingerprint: one row per dimension ──────────────
  function row(r, dim) {
    const key = dim.key, v = r.metrics[key], p = r.pct[key];
    const on = r.archetype.dim === key;
    const mark = on ? '<span class="sty-mark">Archetype</span>' : "";
    if (v == null || p == null) {
      const why = key === "yes_rate" ? "Too few offers answered to rate" : "Not enough data";
      return `<li class="sty-row none${on ? " on" : ""}"><span class="sty-lab">${esc(dim.label)}${mark}</span><span class="sty-na">${why}</span><span class="sty-val"><b>–</b></span></li>`;
    }
    const st = standing(key, r.team);
    const rank = r.rank[key];
    const tied = st.tied ? "T-" : "";
    const extra = counts[key] ? counts[key](r.team) : null;
    const rows = [["Rank", `${tied}${ord(rank)} of ${st.n + 1}`], ["More than", `${st.below} of ${st.n} other managers`]];
    if (st.tied) rows.push(["Tied with", plural(st.tied, "other manager")]);
    if (extra) rows.push(extra);
    const tip = tipHtml(`${dim.label}: ${show(key, v)}`, rows)
      + (dim.desc ? esc(`<div class="r"><span>${esc(dim.desc)}</span></div>`) : "");
    return `<li class="sty-row${on ? " on" : ""}" data-tip="${tip}">
      <span class="sty-lab">${esc(dim.label)}${mark}</span>
      <span class="sty-bar" aria-hidden="true"><i style="width:${(p * 100).toFixed(1)}%"></i></span>
      <span class="sty-val"><b>${esc(show(key, v))}</b><small>${esc(tied + ord(rank))}</small></span>
    </li>`;
  }

  // ── "Share to the board" (account.js; the button is hidden unless you're signed in) ──
  const share = A.shareBtn || (() => "");
  const low = (s) => s.charAt(0).toLowerCase() + s.slice(1);
  function stat(t, r) {
    const a = r.archetype, nm = t.manager || t.name, dim = S.dims.find((d) => d.key === a.dim);
    const tail = a.why ? `: ${low(String(a.why))}.` : `. ${a.blurb || ""}`;
    const facts = [];
    if (dim && r.metrics[a.dim] != null && r.rank[a.dim] != null) {
      const st = standing(a.dim, r.team);
      facts.push([String(dim.label).slice(0, 30), show(a.dim, r.metrics[a.dim])], ["League rank", `${st.tied ? "T-" : ""}${ord(r.rank[a.dim])} of ${st.n + 1}`]);
    }
    return { kind: "style", title: "Manager style", text: `${nm} is ${a.title}${tail}`.trim().slice(0, 300), ...(facts.length ? { facts } : {}), teams: [t.id], link: `#manager/${t.id}` };
  }

  // ── the card ────────────────────────────────────────────
  function card(t) {
    const r = byTeam[t.id];
    if (!r) return "";
    const a = r.archetype;
    const dims = S.dims.filter((d) => r.metrics[d.key] !== undefined);
    const hasMoves = dims.some((d) => d.key === "moves");
    const note = (hasMoves ? "Lineup moves are ESPN's own count, forced moves for byes and injuries included. " : "")
      + "Each title goes to one manager where possible, so it can go to the 2nd or 3rd in line.";
    return `<div class="card mg-blk sty-card">
      <h3>Manager style</h3>
      <p class="cap">How ${esc(t.manager || t.name)} plays next to the other managers. Each bar is a rank, not an amount: full is the highest in the league, empty the lowest, and the tick is the middle.</p>
      <div class="sty-body">
        <div class="sty-arch">
          <div class="sty-eye">Archetype</div>
          <div class="sty-title">${esc(a.title)}</div>
          <p class="sty-blurb">${esc(a.blurb)}</p>
          ${a.why ? `<p class="sty-why"><span class="sty-k">Why</span>${esc(a.why)}</p>` : ""}
          ${share(stat(t, r))}
        </div>
        <ul class="sty-rows">${dims.map((d) => row(r, d)).join("")}</ul>
      </div>
      <p class="sty-note">${esc(note)}</p>
    </div>`;
  }

  A.managerBlocks.push({ order: 10, place: "top", render: card });

  // ── a pill under the name ───────────────────────────────
  A.managerTags.push((t) => {
    const r = byTeam[t.id];
    return r ? `<span class="sty-pill" title="${esc(r.archetype.blurb)}">${esc(r.archetype.title)}</span>` : "";
  });
})();
