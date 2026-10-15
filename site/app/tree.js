// Trades tab: trade tree. Who deals with whom (network of teams), the most
// frequent trade partners, and chains where a team flipped what it got.
(function () {
  const A = window.App;
  if (!A) return;
  const { D, teams, T, ranked, $, $$, esc, fmtDate, chip, logo, initials, tipHtml } = A;
  const root = $("#tree");
  if (!root) return;

  const trades = [...D.trades].sort((a, b) => a.date - b.date || a.id - b.id);
  const sideOf = (tr, id) => tr.sides.find((s) => s.team === id);
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const list = (xs) => (xs.length < 3 ? xs.join(" and ") : xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1]);

  // Short name for a team: the manager's first name. Two teams with the same
  // manager name get their abbreviation added so they can be told apart.
  const label = {};
  {
    const base = (t) => t.manager || t.abbrev || t.name || "?";
    const seen = {};
    teams.forEach((t) => (seen[base(t)] = (seen[base(t)] || 0) + 1));
    teams.forEach((t) => (label[t.id] = seen[base(t)] > 1 ? `${base(t)} (${t.abbrev || t.name})` : base(t)));
  }

  // ── model ───────────────────────────────────────────────
  // Every pair of teams on a trade counts as one trade between them, so a
  // three-team deal adds one to each of its three pairs.
  const info = new Map(teams.map((t) => [t.id, { t, n: 0, partners: new Map() }]));
  const pairMap = new Map();
  for (const tr of trades) {
    const ids = [...new Set(tr.sides.map((s) => s.team))].filter((id) => info.has(id));
    ids.forEach((id) => info.get(id).n++);
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const [a, b] = ids[i] < ids[j] ? [ids[i], ids[j]] : [ids[j], ids[i]];
        const k = a + "-" + b;
        if (!pairMap.has(k)) {
          const p = { a, b, trades: [] };
          pairMap.set(k, p);
          info.get(a).partners.set(b, p);
          info.get(b).partners.set(a, p);
        }
        pairMap.get(k).trades.push(tr);
      }
    }
  }
  const pairs = [...pairMap.values()];
  pairs.forEach((p) => { p.n = p.trades.length; p.last = Math.max(...p.trades.map((t) => t.date)); });

  root.innerHTML = '<h2>Trade tree</h2><p class="sub">Who keeps dealing with whom. Thicker line, more trades. Tap a team.</p>';
  if (!pairs.length) {
    root.insertAdjacentHTML("beforeend", '<div class="card empty">No trades yet. Nobody has anyone to deal with.</div>');
    return;
  }

  // ── layout: teams evenly around a circle ────────────────
  // Order the teams so heavy lines are short and few lines cross: a small
  // seeded local search (same data always gives the same picture).
  function arrange(ids, edges) {
    const N = ids.length;
    const cost = (perm) => {
      const pos = new Map(perm.map((id, i) => [id, i]));
      let len = 0, cross = 0;
      const segs = edges.map((e) => {
        let p = pos.get(e.a), q = pos.get(e.b);
        if (p > q) [p, q] = [q, p];
        len += e.n * Math.min(q - p, N - (q - p));
        return [p, q, e.a, e.b];
      });
      for (let i = 0; i < segs.length; i++) {
        for (let j = i + 1; j < segs.length; j++) {
          const s = segs[i], t = segs[j];
          if (s[2] === t[2] || s[2] === t[3] || s[3] === t[2] || s[3] === t[3]) continue;
          const inside = (x) => x > s[0] && x < s[1];
          if (inside(t[0]) !== inside(t[1])) cross++;
        }
      }
      return cross * 12 + len;
    };
    const descend = (perm) => {
      let best = cost(perm), moved = true;
      while (moved) {
        moved = false;
        for (let i = 0; i < N; i++) {
          for (let j = i + 1; j < N; j++) {
            [perm[i], perm[j]] = [perm[j], perm[i]];
            const c = cost(perm);
            if (c < best - 1e-9) { best = c; moved = true; } else [perm[i], perm[j]] = [perm[j], perm[i]];
          }
        }
      }
      return best;
    };
    let seed = 7;
    const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
    let bestPerm = ids.slice(), bestCost = descend(bestPerm);
    for (let r = 0; r < (N <= 16 ? 24 : 3); r++) {
      const perm = ids.slice();
      for (let i = N - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [perm[i], perm[j]] = [perm[j], perm[i]]; }
      const c = descend(perm);
      if (c < bestCost - 1e-9) { bestCost = c; bestPerm = perm; }
    }
    // busiest team at the top
    const top = bestPerm.reduce((k, id, i) => (info.get(id).n > info.get(bestPerm[k]).n ? i : k), 0);
    return [...bestPerm.slice(top), ...bestPerm.slice(0, top)];
  }
  const order = arrange((ranked || teams).map((t) => t.id), pairs);
  const maxN = Math.max(1, ...order.map((id) => info.get(id).n));

  const W = 600, H = 540, CX = 300, CY = 270, R = 180, FONT = 20;
  const nodes = order.map((id, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / order.length;
    const n = info.get(id).n;
    return { id, t: T[id], n, a, ux: Math.cos(a), uy: Math.sin(a), x: CX + R * Math.cos(a), y: CY + R * Math.sin(a), r: n ? 22 + 10 * (n / maxN) : 20 };
  });
  const nodeOf = new Map(nodes.map((nd) => [nd.id, nd]));

  // Count pills sit near the middle of a line, nudged along it when they'd
  // land on another pill or on a team.
  const pillAt = new Map();
  const placed = [];
  [...pairs].filter((e) => e.n >= 2).sort((x, y) => y.n - x.n).forEach((e) => {
    const A1 = nodeOf.get(e.a), B1 = nodeOf.get(e.b);
    let pick = null;
    for (const f of [0.5, 0.4, 0.6, 0.32, 0.68, 0.25, 0.75]) {
      const x = A1.x + (B1.x - A1.x) * f, y = A1.y + (B1.y - A1.y) * f;
      const free = placed.every((q) => Math.hypot(q.x - x, q.y - y) > 30)
        && nodes.every((nd) => Math.hypot(nd.x - x, nd.y - y) > nd.r + 16);
      if (free) { pick = { x, y }; break; }
    }
    pick = pick || { x: (A1.x + B1.x) / 2, y: (A1.y + B1.y) / 2 };
    placed.push(pick);
    pillAt.set(e, pick);
  });

  const f2 = (x) => Math.round(x * 10) / 10;
  const pairKey = (a, b) => (a < b ? a + "-" + b : b + "-" + a);

  function nodeSvg(nd) {
    const t = nd.t, id = nd.id;
    const rr = f2(nd.r), hit = Math.max(rr + 8, 36);
    // Name sits outside the circle, on the side facing away from the middle.
    const gap = rr + 9;
    const px = f2(nd.ux * gap), py = f2(nd.uy * gap);
    let anchor = "middle", dy = "0", room = 150;
    if (nd.ux > 0.3) { anchor = "start"; dy = "0.35em"; room = W - 6 - (nd.x + nd.ux * gap); }
    else if (nd.ux < -0.3) { anchor = "end"; dy = "0.35em"; room = nd.x + nd.ux * gap - 6; }
    else if (nd.uy < 0) dy = "-0.1em";
    else dy = "0.8em";
    const maxChars = Math.max(3, Math.floor(room / (FONT * 0.53)));
    let name = label[id];
    if (name.length > maxChars) name = name.slice(0, maxChars - 1).trimEnd() + "…";
    const info1 = info.get(id);
    const aria = `${label[id]}, ${t.name}. ${info1.n ? `${plural(info1.n, "trade")} with ${plural(info1.partners.size, "team")}` : "No trades yet"}.`;
    const img = t.logo
      ? `<clipPath id="trc-${id}"><circle r="${rr}"/></clipPath><image class="photo" href="${esc(t.logo)}" x="${-rr}" y="${-rr}" width="${rr * 2}" height="${rr * 2}" preserveAspectRatio="xMidYMid slice" clip-path="url(#trc-${id})" onerror="this.closest('.tn').classList.remove('has-img');this.remove()"/>`
      : "";
    return `<g class="tn${t.logo ? " has-img" : ""}${info1.n ? "" : " none"}" data-team="${id}" transform="translate(${f2(nd.x)} ${f2(nd.y)})" tabindex="0" role="button" aria-pressed="false" aria-label="${esc(aria)}">
      <circle class="hit" r="${hit}"/><circle class="under" r="${rr}"/>
      <g class="vis"><circle class="bg" r="${rr}"/><text class="ini" y="0.35em">${initials(t)}</text>${img}<circle class="ring" r="${rr}"/>
      <circle class="focus" r="${rr + 6}"/>
      <text class="lab" x="${px}" y="${py}" dy="${dy}" text-anchor="${anchor}">${esc(name)}</text></g></g>`;
  }

  function edgeSvg(e) {
    const p = nodeOf.get(e.a), q = nodeOf.get(e.b);
    const w = Math.min(16, 3 + 3.2 * (e.n - 1));
    const tip = tipHtml(`${label[e.a]} ↔ ${label[e.b]}: ${plural(e.n, "trade")}`, e.trades.map((tr) => [`Trade #${tr.id}`, fmtDate(tr.date)]));
    const c = `x1="${f2(p.x)}" y1="${f2(p.y)}" x2="${f2(q.x)}" y2="${f2(q.y)}"`;
    return `<g class="ed" data-pair="${pairKey(e.a, e.b)}" data-tip="${tip}" aria-hidden="true"><line class="hit" ${c} stroke="transparent" stroke-width="${Math.max(16, w + 8)}"/><line class="vis" ${c} stroke-width="${f2(w)}" stroke-linecap="round"/></g>`;
  }

  function pillSvg(e) {
    const at = pillAt.get(e);
    if (!at) return "";
    const w = 14 + 10 * String(e.n).length;
    return `<g class="pill" data-pair="${pairKey(e.a, e.b)}" transform="translate(${f2(at.x)} ${f2(at.y)})" aria-hidden="true"><rect x="${-w / 2}" y="-12" width="${w}" height="24" rx="12"/><text y="0.36em">${e.n}</text></g>`;
  }

  const svg = `<svg class="tr-net" viewBox="0 0 ${W} ${H}" role="group" aria-label="Network of teams that have traded with each other">
    <g>${[...pairs].sort((x, y) => x.n - y.n).map(edgeSvg).join("")}</g>
    <g>${nodes.map(nodeSvg).join("")}</g>
    <g class="pills">${[...pairs].filter((e) => e.n >= 2).map(pillSvg).join("")}</g>
  </svg>`;

  // ── details panel ───────────────────────────────────────
  function tradeLine(tr, id, partner) {
    const s = sideOf(tr, id);
    const got = (s.received || []).map((p) => esc(p.name));
    if (s.faab_received > 0) got.push(`$${+s.faab_received} FAAB`);
    const gave = (s.sent || []).map((p) => esc(p.name));
    if (s.faab_sent > 0) gave.push(`$${+s.faab_sent} FAAB`);
    const others = tr.sides.map((o) => o.team).filter((x) => x !== id && x !== partner && info.has(x)).map((x) => label[x]);
    const multi = tr.sides.length > 2 ? ` <span class="multi">${tr.sides.length}-team deal${others.length ? `, also ${esc(list(others))}` : ""}</span>` : "";
    return `<li><a href="#trade/${tr.id}"><b>Trade #${tr.id}</b></a> <span class="d">· ${fmtDate(tr.date)}</span>${multi} — <span class="k">got</span> ${got.join(", ") || "nothing"}; <span class="k">gave</span> ${gave.join(", ") || "nothing"}</li>`;
  }

  function panelHtml(id) {
    if (id == null) {
      const idle = teams.filter((t) => !info.get(t.id).n).map((t) => label[t.id]);
      return `<div class="tp-hint"><b>Tap a team</b> to see everyone it has traded with.</div>
        <p class="tp-sum">${plural(trades.length, "trade")} between ${plural(pairs.length, "pair")} of teams.${idle.length ? ` Haven't traded yet: ${esc(list(idle))}.` : ""}</p>`;
    }
    const x = info.get(id);
    const head = `<div class="tp-head">${chip(x.t)}<div class="tp-sum">${x.n ? `${plural(x.n, "trade")} · ${plural(x.partners.size, "partner")}` : "No trades yet"}</div></div>`;
    if (!x.n) return head + '<p class="tp-sum">Hasn\'t made a deal. Keeping every player, for better or worse.</p>';
    const groups = [...x.partners.entries()].map(([pid, p]) => ({ pid, p })).sort((u, v) => v.p.n - u.p.n || v.p.last - u.p.last);
    return head + groups.map(({ pid, p }) => `<section class="tp-g">
      <h4>${logo(T[pid])}<span>with ${esc(label[pid])}</span>${p.n > 1 ? `<span class="x">×${p.n}</span>` : ""}</h4>
      <ul>${p.trades.map((tr) => tradeLine(tr, id, pid)).join("")}</ul></section>`).join("");
  }

  // ── most frequent partners ──────────────────────────────
  function pairsHtml() {
    const rows = [...pairs].sort((u, v) => v.n - u.n || v.last - u.last);
    const rep = rows.filter((p) => p.n >= 2);
    let body;
    if (!rep.length) {
      body = '<p class="note">Nobody has traded with the same team twice yet.</p>';
    } else {
      const top = rep.slice(0, 3);
      const more = rep.length - top.length;
      const tied = rep.slice(3).filter((p) => p.n === top[top.length - 1].n).length;
      body = `<div class="tr-pairs">${top.map((p, i) => `<div class="card tr-pair">
        <div class="who"><span class="eb">#${i + 1}</span>${chip(T[p.a])}${chip(T[p.b])}</div>
        <div class="ct"><b>${p.n}</b><small>trades</small></div></div>`).join("")}</div>
        ${tied ? `<p class="note">${plural(tied, "other pair")} also traded ${top[top.length - 1].n} times.</p>` : more > 0 ? `<p class="note">${plural(more, "other pair")} traded more than once.</p>` : ""}`;
    }
    return `<h3>Most frequent trade partners</h3>${body}`;
  }

  // ── trade chains ────────────────────────────────────────
  // side.flipped_into lists the later trades where a team sent out what it got
  // (directly or down the line). Each is a chain starting at that trade; chains
  // contained in a longer one for the same team are dropped.
  function chainsHtml() {
    const byId = new Map(trades.map((t) => [t.id, t]));
    const raw = [];
    for (const tr of trades) {
      for (const s of tr.sides) {
        if (!T[s.team]) continue;
        const later = (s.flipped_into || []).map((id) => byId.get(id)).filter(Boolean).sort((a, b) => a.date - b.date || a.id - b.id);
        if (later.length) raw.push({ team: s.team, steps: [tr, ...later] });
      }
    }
    const sub = (c, o) => c.steps.every((t) => o.steps.includes(t));
    const chains = raw.filter((c, i) => !raw.some((o, j) => j !== i && o.team === c.team && sub(c, o) && (o.steps.length > c.steps.length || j < i)));
    if (!chains.length) return "";
    chains.sort((u, v) => v.steps.length - u.steps.length || u.steps[0].date - v.steps[0].date);

    const names = (arr, hot) => {
      const out = arr.slice(0, 6).map((p) => (hot && hot.has(String(p.id)) ? `<b>${esc(p.name)}</b>` : esc(p.name)));
      if (arr.length > 6) out.push(`+${arr.length - 6} more`);
      return out.join(", ");
    };
    const cards = chains.map((c) => {
      // Follow the players: what came in at step 0, and which of them went out later.
      const assets = new Set();
      const moved = c.steps.map((tr, k) => {
        const s = sideOf(tr, c.team);
        const out = k ? (s.sent || []).filter((p) => assets.has(String(p.id))) : [];
        (s.received || []).forEach((p) => assets.add(String(p.id)));
        return { tr, s, out: new Set(out.map((p) => String(p.id))) };
      });
      const lines = moved.map((m, k) => {
        const later = new Set();
        moved.slice(k + 1).forEach((n) => n.out.forEach((id) => later.add(id)));
        const who = m.tr.sides.map((o) => o.team).filter((x) => x !== c.team && info.has(x)).map((x) => label[x]);
        const got = names(m.s.received || [], later) || "nothing";
        const sent = k ? `sent ${names(m.s.sent || [], m.out) || "nothing"} · got ${got}` : `got ${got}`;
        return `<li><span class="sid">#${m.tr.id}</span><div><div class="sm">${fmtDate(m.tr.date)}${who.length ? ` · with ${esc(list(who))}` : ""}</div><div class="sp">${sent}</div></div></li>`;
      }).join("");
      const flow = c.steps.map((t, k) => (k ? `#${t.id}` : `Trade #${t.id}`)).join(' <span class="arr">→</span> ');
      // long chains start folded; the headline already shows the whole sequence
      return `<details class="card tr-chain"${c.steps.length <= 3 ? " open" : ""}><summary>${chip(T[c.team], { link: false })}<div class="flow"><b>${esc(label[c.team])}:</b> ${flow}</div></summary><ol class="ch-steps">${lines}</ol></details>`;
    }).join("");
    return `<h3>Trade chains</h3><p class="sub2">A team trades for players, then flips them in another deal. The ledger's grade follows the whole chain. Bold players are the ones who moved on. Tap a long chain to open it.</p><div class="tr-chains">${cards}</div>`;
  }

  root.insertAdjacentHTML("beforeend", `<div class="tr-wrap">
    <div class="card tr-stage" id="trStage">${svg}<p class="tr-cap">Bigger circle, more trades. Dashed ring, no trades yet.</p></div>
    <div class="card tr-panel" id="trPanel" aria-live="polite"></div>
  </div>${pairsHtml()}${chainsHtml()}`);

  // ── interaction ─────────────────────────────────────────
  const stage = $("#trStage", root), panel = $("#trPanel", root), net = $(".tr-net", root);
  const nodeEl = new Map($$(".tn", root).map((g) => [+g.dataset.team, g]));
  const edgeEls = new Map();
  $$(".ed, .pill", root).forEach((g) => { const k = g.dataset.pair; (edgeEls.get(k) || edgeEls.set(k, []).get(k)).push(g); });
  let sel = null, peek = null, shown = undefined;

  function update() {
    const a = peek ?? sel;
    net.classList.toggle("has-active", a != null);
    const partners = a != null ? info.get(a).partners : null;
    nodeEl.forEach((g, id) => {
      g.classList.toggle("on", id === a);
      g.classList.toggle("partner", partners != null && partners.has(id));
      g.setAttribute("aria-pressed", String(id === sel));
    });
    edgeEls.forEach((els, k) => {
      const [x, y] = k.split("-").map(Number);
      els.forEach((g) => g.classList.toggle("hot", a != null && (x === a || y === a)));
    });
    if (shown !== a) { panel.innerHTML = panelHtml(a); shown = a; }
  }
  // On phones the panel is under the diagram: bring it up if a tap left it off screen.
  function revealPanel() {
    if (!matchMedia("(max-width: 900px)").matches) return;
    const r = panel.getBoundingClientRect();
    if (r.top > innerHeight - 140) {
      const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollBy({ top: r.top - innerHeight + 260, behavior: smooth ? "smooth" : "auto" });
    }
  }
  function toggle(id) {
    sel = sel === id ? null : id;
    update();
    if (sel != null) revealPanel();
  }
  function clear() { sel = null; peek = null; update(); }

  nodeEl.forEach((g, id) => {
    g.addEventListener("pointerenter", (e) => { if (e.pointerType !== "touch") { peek = id; update(); } });
    g.addEventListener("pointerleave", (e) => { if (e.pointerType !== "touch" && peek === id) { peek = null; update(); } });
    g.addEventListener("focus", () => { if (g.matches(":focus-visible")) { peek = id; update(); } });
    g.addEventListener("blur", () => { if (peek === id) { peek = null; update(); } });
    g.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(id); }
    });
  });
  stage.addEventListener("click", (e) => {
    const g = e.target.closest(".tn");
    if (g) toggle(+g.dataset.team);
    else if (!e.target.closest(".ed")) clear();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && (sel != null || peek != null) && A.isShown("trades")) clear();
  });
  update();
})();
