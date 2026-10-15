// The open dashboard's page: the league form, the Pyodide worker (worker.js) that computes
// everything, and the standings + power rankings it returns.
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const f1 = (x) => (Math.floor(x * 10 + 0.5) / 10).toFixed(1); // same rounding as league/power.py
  const record = (w, l, t) => `${w}-${l}${t ? "-" + t : ""}`;
  const KEY = "open:league";

  // ── saved form (this browser only) ──
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
  const save = (v) => { try { v ? localStorage.setItem(KEY, JSON.stringify(v)) : localStorage.removeItem(KEY); } catch { /* private mode */ } };

  const thisSeason = (() => { const d = new Date(); return d.getMonth() >= 7 ? d.getFullYear() : d.getFullYear() - 1; })();
  $("#season").innerHTML = Array.from({ length: 8 }, (_, i) => thisSeason - i).map((y) => `<option>${y}</option>`).join("");

  const saved = load();
  if (saved.leagueId) {
    $("#league").value = saved.leagueId;
    if (saved.season) $("#season").value = saved.season;
    $("#s2").value = saved.s2 || "";
    $("#swid").value = saved.swid || "";
    $("#remember").checked = true;
    if (saved.s2) $("#private").open = true;
  }

  // A pasted league URL works too: fantasy.espn.com/football/league?leagueId=123&seasonId=2025
  function parseLeague(raw) {
    const s = raw.trim();
    const id = (s.match(/leagueId=(\d+)/i) || [])[1] || (/^\d+$/.test(s) ? s : null);
    const season = (s.match(/seasonId=(\d{4})/i) || [])[1];
    return { id, season };
  }

  // ── the worker ──
  let worker = null, seq = 0;
  function run(args, onStatus) {
    worker = worker || new Worker("worker.js");
    const id = ++seq;
    return new Promise((resolve, reject) => {
      const onMsg = (e) => {
        if (e.data.id !== id) return;
        if (e.data.status) return onStatus(e.data.status);
        worker.removeEventListener("message", onMsg);
        e.data.error ? reject(new Error(e.data.error)) : resolve(JSON.parse(e.data.result));
      };
      worker.addEventListener("message", onMsg);
      worker.postMessage({ id, ...args });
    });
  }

  function show(which) {
    for (const s of ["#start", "#working", "#result"]) $(s).hidden = s !== which;
    window.scrollTo(0, 0);
  }
  function formError(msg) {
    $("#formError").textContent = msg || "";
    $("#formError").hidden = !msg;
  }

  $("#form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const { id, season: urlSeason } = parseLeague($("#league").value);
    if (!id) return formError("Enter your league ID: the number after leagueId= in your league's URL.");
    if (urlSeason && [...$("#season").options].some((o) => o.value === urlSeason)) $("#season").value = urlSeason;
    const s2 = $("#s2").value.trim(), swid = $("#swid").value.trim();
    if (!!s2 !== !!swid) return formError("A private league needs both cookies: espn_s2 and SWID.");
    formError("");
    const args = { leagueId: id, season: +$("#season").value, s2, swid };
    save($("#remember").checked ? { leagueId: id, season: args.season, s2, swid } : null);

    show("#working");
    $("#status").textContent = "Starting…";
    try {
      const data = await run(args, (s) => { $("#status").textContent = s; });
      render(data);
      show("#result");
    } catch (err) {
      show("#start");
      formError(err.message);
      if (/private/.test(err.message)) $("#private").open = true;
    }
  });
  $("#again").addEventListener("click", () => show("#start"));

  // ── results ──
  function render(d) {
    const L = d.league;
    const teams = Object.fromEntries(d.teams.map((t) => [t.id, t]));
    document.title = `${L.name} · League Dashboard`;
    $("#leagueName").textContent = L.name;
    $("#leagueMeta").textContent = L.through_week
      ? `${L.season} season · through week ${L.through_week}`
      : `${L.season} season · no games finished yet`;

    const P = d.power;
    const weeks = (P && P.weeks) || [];
    const latest = weeks[weeks.length - 1];
    $("#powerSec").hidden = !latest;
    if (latest) {
      const blurb = Object.fromEntries((P.blurbs || []).map((b) => [b.team, b.text]));
      const prev = weeks.length > 1 ? weeks[weeks.length - 2].week : null;
      const end = latest.week === L.regular_season_weeks && L.through_week > latest.week ? ", the end of the regular season" : "";
      $("#powerMethod").textContent = `After week ${latest.week}${end}. ${P.method}.`;
      $("#powerList").innerHTML = latest.teams.map((r) => {
        const t = teams[r.team] || { name: `Team ${r.team}` };
        const c = r.change;
        const mv = !c
          ? `<span class="p-mv" title="${c === 0 ? `No change from week ${prev}` : "First week of rankings"}">–</span>`
          : `<span class="p-mv ${c > 0 ? "up" : "down"}" title="${c > 0 ? "Up" : "Down"} ${Math.abs(c)} from week ${prev}">${c > 0 ? "▲" : "▼"}${Math.abs(c)}</span>`;
        return `<li class="prow">
          <span class="p-rk ${r.rank <= 3 ? "r" + r.rank : ""}">${r.rank}</span>
          ${mv}
          <span class="p-team"><b>${esc(t.name)}</b>${t.manager ? `<small>${esc(t.manager)}</small>` : ""}</span>
          <span class="p-why">${esc(blurb[r.team] || "")}</span>
          <span class="p-rec" title="All-play ${esc(r.allplay)}">${esc(r.record)}</span>
          <span class="p-score" title="Power score out of 100"><b>${f1(r.score)}</b><span class="p-bar"><i style="width:${Math.max(0, Math.min(100, r.score))}%"></i></span></span>
        </li>`;
      }).join("");
    }

    const rows = d.teams;
    $("#standTbl").innerHTML = `<thead><tr>
        <th class="n">#</th><th>Team</th><th class="n">W-L</th><th class="n">PF</th><th class="n">PA</th><th class="n">All-play</th><th>Streak</th>
      </tr></thead><tbody>${rows.map((t, i) => `<tr>
        <td class="n">${t.standing || i + 1}</td>
        <td class="team"><span class="t-name">${esc(t.name)}</span>${t.manager ? `<small>${esc(t.manager)}</small>` : ""}</td>
        <td class="n">${record(t.wins, t.losses, t.ties)}</td>
        <td class="n">${f1(t.points_for)}</td>
        <td class="n">${f1(t.points_against)}</td>
        <td class="n">${t.allplay_w}-${t.allplay_l}</td>
        <td>${esc(t.streak)}</td>
      </tr>`).join("")}</tbody>`;
  }
})();
