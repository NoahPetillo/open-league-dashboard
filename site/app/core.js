// Shared data, helpers and the tab router. Every other file in site/app/ reads
// window.App; main.js calls App.start() once they've all registered.
(function () {
  const D = window.LEAGUE_DATA;
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  if (!D) {
    $("#lname").textContent = "No data yet";
    $("#meta").textContent = "Couldn't read this league.";
    window.App = null;
    return;
  }
  const L = D.league;
  const MY_TEAM = null; // set to a team id to tag "you"
  const teams = D.teams;
  const T = Object.fromEntries(teams.map((t) => [t.id, t]));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const f1 = (x) => (Math.round(x * 10) / 10).toFixed(1);
  const sgn = (x) => (x > 0.05 ? "+" : x < -0.05 ? "−" : "") + f1(Math.abs(x));
  const cls = (x) => (x > 0.05 ? "pos" : x < -0.05 ? "neg" : "dim");
  const pct = (x) => (x == null ? "–" : x === 0 ? "~0%" : x < 0.005 ? "<1%" : x > 0.995 && x < 1 ? ">99%" : Math.round(x * 100) + "%");
  const fmtDate = (ms) => new Date(ms).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const initials = (t) => esc((t.abbrev || t.name || "?").slice(0, 3).toUpperCase());

  function logo(t) {
    if (t.logo) return `<img class="logo" src="${esc(t.logo)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=&quot;logo ph&quot;>${initials(t)}</span>'">`;
    return `<span class="logo ph">${initials(t)}</span>`;
  }
  // A team chip links to that manager's page unless {link: false} (e.g. inside a <button>).
  function chip(t, opts = {}) {
    if (!t) return "";
    const inner = `${opts.noLogo ? "" : logo(t)}<span class="stack"><span class="nm">${esc(t.name)}${t.id === MY_TEAM ? '<span class="you">you</span>' : ""}</span>${t.manager ? `<span class="mgr">${esc(t.manager)}</span>` : ""}</span>`;
    return opts.link === false ? `<span class="team">${inner}</span>` : `<a class="team" href="#manager/${t.id}">${inner}</a>`;
  }

  // ── tooltip ─────────────────────────────────────────────
  const tip = $("#tip");
  function showTip(e, html) {
    tip.innerHTML = html; tip.style.opacity = 1;
    const r = tip.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  const hideTip = () => (tip.style.opacity = 0);
  document.addEventListener("mousemove", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el) showTip(e, el.dataset.tip); else hideTip();
  });
  const tipHtml = (title, rows) => esc(`<div class="t">${esc(title)}</div>` + rows.map(([k, v]) => `<div class="r"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join(""));

  // ── header ──────────────────────────────────────────────
  $("#season").textContent = `${L.season} season · through week ${L.through_week}`;
  $("#lname").textContent = L.name;
  document.title = `${L.name} · Dashboard`;
  const gen = new Date(L.generated_at);
  $("#meta").textContent = `${teams.length} teams · ${D.trades.length} trades · updated ${gen.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} at ${gen.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  $("#foot").innerHTML = `<p>Data from ESPN, through week ${L.through_week}. Worked out in your browser; nothing is saved on a server. <a href="#" data-new-league>Load another league</a></p>`;

  // ── derived ─────────────────────────────────────────────
  for (const t of teams) {
    const gp = t.wins + t.losses + t.ties;
    const ap = t.allplay_w + t.allplay_l;
    t.exp_wins = ap ? (t.allplay_w / ap) * gp : 0;
    t.luck = t.wins + t.ties / 2 - t.exp_wins;
  }
  const ranked = [...teams].sort((a, b) => (a.standing ?? 99) - (b.standing ?? 99) || b.wins - a.wins || b.points_for - a.points_for);
  ranked.forEach((t, i) => (t.rank = i + 1));

  // ── bar lists ───────────────────────────────────────────
  // The league leader's bar can show off: {top: "gold"} makes the highest positive
  // value(s) shimmer gold; {top: "laugh"} has laughing emojis fall out of it (for
  // leading the league in something embarrassing). Ties share the effect.
  const LAUGHS = ["😂", "🤣", "😂", "🤣"];
  const laughs = (at) => `<span class="laughs" style="left:${at}%" aria-hidden="true">${LAUGHS.map((e) => `<i>${e}</i>`).join("")}</span>`;
  function leaders(rows) {
    const top = Math.max(...rows.map((r) => r.v));
    return top > 0 ? new Set(rows.filter((r) => r.v === top)) : new Set();
  }
  function divergingBars(el, rows, fmt, tipFor, opts = {}) {
    const max = Math.max(1, ...rows.map((r) => Math.abs(r.v)));
    const hasNeg = rows.some((r) => r.v < 0);
    const zero = hasNeg ? 50 : 0;
    const span = hasNeg ? 50 : 100;
    const best = opts.top ? leaders(rows) : new Set();
    el.innerHTML = rows.map((r) => {
      const w = (Math.abs(r.v) / max) * span;
      const left = r.v >= 0 ? zero : zero - w;
      const fx = best.has(r) ? opts.top : "";
      return `<div class="bar-row${fx ? " top-" + fx : ""}" data-tip="${tipFor(r)}">${chip(r.t)}<div class="bar-track"><span class="zero" style="left:${zero}%"></span><span class="b ${r.v >= 0 ? "p" : "m"}${fx === "gold" ? " gold" : ""}" style="left:${left}%;width:${Math.max(w, r.v ? 0.6 : 0)}%"></span>${fx === "laugh" ? laughs(left + w) : ""}</div><div class="v ${hasNeg ? cls(r.v) : ""}">${fmt(r.v)}${fx ? `<span class="sr-only"> (league ${fx === "gold" ? "best" : "worst"})</span>` : ""}</div></div>`;
    }).join("");
  }

  // ── player headshots (ESPN's CDN, keyed by the same player id the data uses) ──
  // p: {id, pro_team}. D/ST ids are negative → that NFL team's logo instead.
  function headshot(p) {
    if (+p.id < 0) return p.pro_team ? `https://a.espncdn.com/i/teamlogos/nfl/500/${p.pro_team.toLowerCase()}.png` : "";
    return `https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/${p.id}.png&w=350&h=254`;
  }

  // ── line chart (SVG, redraws at its real width; shows week values on hover) ──
  // opts: {x: [labels], series: [{name, values: [number|null], color, muted, dashed}],
  //        yMin=0, yMax=1, yTicks, yFmt, xFmt(i) → tooltip title, tipRows(i) → [[k, v]],
  //        height=220, label (for screen readers)}. Muted series draw thin and grey.
  function lineChart(el, opts) {
    const yMin = opts.yMin ?? 0, yMax = opts.yMax ?? 1;
    const yFmt = opts.yFmt || ((v) => f1(v));
    const xFmt = opts.xFmt || ((i) => String(opts.x[i]));
    const ticks = opts.yTicks || [yMin, (yMin + yMax) / 2, yMax];
    function draw() {
      const W = Math.round(el.clientWidth);
      if (!W) return;
      const H = opts.height || 220, m = { l: 42, r: 20, t: 10, b: 26 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b, n = opts.x.length;
      const xs = (i) => m.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
      const ys = (v) => m.t + ih - ((Math.min(yMax, Math.max(yMin, v)) - yMin) / (yMax - yMin || 1)) * ih;
      const every = Math.max(1, Math.ceil(n / Math.max(1, Math.floor(iw / 34))));
      const grid = ticks.map((t) => `<line class="g" x1="${m.l}" x2="${W - m.r}" y1="${ys(t)}" y2="${ys(t)}"/><text class="yl" x="${m.l - 8}" y="${ys(t) + 4}">${esc(yFmt(t))}</text>`).join("");
      const xl = opts.x.map((x, i) => (i % every && i !== n - 1 ? "" : `<text class="xl" x="${xs(i)}" y="${H - 8}">${esc(x)}</text>`)).join("");
      const order = [...opts.series].sort((a, b) => !!b.muted - !!a.muted); // highlighted lines on top
      const lines = order.map((s) => {
        let d = "", pen = false;
        s.values.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`; pen = true; });
        const last = s.values.reduce((k, v, i) => (v == null ? k : i), -1);
        const col = s.muted ? "var(--axis)" : s.color || "var(--accent)";
        return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${s.muted ? 1.5 : 2.5}" ${s.dashed ? 'stroke-dasharray="5 4"' : ""} stroke-linejoin="round" stroke-linecap="round"/>`
          + (last >= 0 && !s.muted ? `<circle cx="${xs(last)}" cy="${ys(s.values[last])}" r="3.5" fill="${col}"/>` : "");
      }).join("");
      const colW = n <= 1 ? iw : iw / (n - 1);
      const hover = opts.x.map((_, i) => {
        const rows = opts.tipRows ? opts.tipRows(i) : opts.series.filter((s) => !s.muted).map((s) => [s.name, s.values[i] == null ? "–" : yFmt(s.values[i])]);
        return `<rect class="hv" x="${Math.max(m.l, xs(i) - colW / 2)}" y="${m.t}" width="${Math.min(colW, W - m.r - Math.max(m.l, xs(i) - colW / 2))}" height="${ih}" data-tip="${tipHtml(xFmt(i), rows)}"/>`;
      }).join("");
      el.innerHTML = `<svg class="lc" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "Line chart")}">${grid}${xl}${lines}${hover}</svg>`;
    }
    if (el._ro) el._ro.disconnect();
    let seen = 0;
    el._ro = new ResizeObserver(() => { const w = Math.round(el.clientWidth); if (w && w !== seen) { seen = w; draw(); } });
    el._ro.observe(el);
    draw();
  }

  // ── manager page extension points (managers.js renders these) ──
  // Any tab can add a block to every manager's page:
  //   A.managerBlocks.push({ order, place: "top" | "bottom", render(t) → html, after(t, root) })
  // "top" blocks sit right under the tiles (full width); "bottom" ones share a two-column grid
  // at the end of the page, by `order`. render returns "" to skip a team; after() runs once the
  // page is in the DOM (to draw charts). A small badge next to the manager's name:
  //   A.managerTags.push((t) → html)
  const managerBlocks = [], managerTags = [];

  // ── tabs ────────────────────────────────────────────────
  // URLs: #standings (a tab), #manager/5 (a tab + params), #ledger (any element
  // id inside a tab: opens that tab and scrolls to it). No hash → home. A route hook
  // that scrolls the page itself returns true, so the router doesn't jump to the top.
  const VIEWS = $$(".view").map((v) => v.dataset.view);
  const ALIAS = { manager: "managers", rivalry: "rivalries", trade: "trades" };
  const hooks = {};
  const onRoute = (view, fn) => (hooks[view] = hooks[view] || []).push(fn);
  let shown = null;
  function resolve(hash) {
    const h = decodeURIComponent(hash.replace(/^#\/?/, ""));
    const [head, ...params] = h.split("/");
    if (VIEWS.includes(head)) return { view: head, params };
    if (ALIAS[head]) return { view: ALIAS[head], params };
    const el = head && document.getElementById(head);
    const v = el && el.closest(".view");
    if (v) return { view: v.dataset.view, params: [], anchor: el };
    return { view: "home", params: [] };
  }
  function route() {
    const r = resolve(location.hash);
    const key = r.view + "/" + r.params.join("/");
    $$(".view").forEach((v) => (v.hidden = v.dataset.view !== r.view));
    $$("nav.sections a[data-view]").forEach((a) => {
      const on = a.dataset.view === r.view;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      if (on) a.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
    let scrolled = false;
    for (const fn of hooks[r.view] || []) {
      try { scrolled = fn(r.params) === true || scrolled; } catch (e) { console.error(e); }
    }
    if (r.anchor) r.anchor.scrollIntoView();
    else if (!scrolled && shown !== null && shown !== key) window.scrollTo(0, 0);
    shown = key;
  }
  function start() {
    addEventListener("hashchange", route);
    route();
  }

  window.App = {
    D, L, MY_TEAM, teams, T, ranked, $, $$, esc, f1, sgn, cls, pct, fmtDate, initials,
    logo, chip, tipHtml, divergingBars, leaders, laughs, headshot, lineChart, onRoute, start,
    managerBlocks, managerTags,
    isShown: (view) => !document.querySelector(`.view[data-view="${view}"]`)?.hidden,
  };
})();
