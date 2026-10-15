// The page's driver. Shows the league picker (#gate), has the Python worker (worker.js) read the
// league and build the two datasets the dashboard is made of, then sets them as
// window.LEAGUE_DATA / window.LIVE_DATA and loads the dashboard's scripts (app/), which read
// them as they load. window.OpenLeague.refreshLive() is how the Live tab re-reads this week.
(function () {
  const $ = (s) => document.querySelector(s);
  const KEY = "open:league";
  // The dashboard's scripts, in load order: core first, main last (it starts the router).
  const APP = ["core", "home", "livescores", "standings", "odds", "trades", "waivers", "lineups", "power",
    "swap", "playoffs", "managers", "rivalries", "offers", "tree", "faab", "awards", "whatif", "regret",
    "streaks", "sos", "draft", "drops", "loyalty", "upsets", "sunday", "clinch", "style", "main"];

  // ── saved league (this browser only) ──
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
  const save = (v) => { try { v ? localStorage.setItem(KEY, JSON.stringify(v)) : localStorage.removeItem(KEY); } catch { /* private mode */ } };

  const thisSeason = (() => { const d = new Date(); return d.getMonth() >= 7 ? d.getFullYear() : d.getFullYear() - 1; })();
  $("#seasonPick").innerHTML = Array.from({ length: 8 }, (_, i) => thisSeason - i).map((y) => `<option>${y}</option>`).join("");

  const saved = load();
  if (saved.leagueId) {
    $("#league").value = saved.leagueId;
    if (saved.season) $("#seasonPick").value = saved.season;
    $("#s2").value = saved.s2 || "";
    $("#swid").value = saved.swid || "";
    $("#remember").checked = true;
    if (saved.s2 || saved.cookies) $("#private").open = true;
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
  function ask(msg, onStatus = () => {}) {
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
      worker.postMessage({ id, ...msg });
    });
  }
  window.OpenLeague = { refreshLive: () => ask({ type: "live" }) };

  function loadScripts(names) {
    return names.reduce((p, name) => p.then(() => new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `app/${name}.js`;
      s.onload = resolve;
      s.onerror = () => reject(new Error(`Couldn't load the ${name} tab.`));
      document.body.appendChild(s);
    })), Promise.resolve());
  }

  // A public league whose activity feed ESPN keeps to members: say why trades and waivers are
  // empty, and how to fill them in.
  function noteGaps(gaps) {
    if (!gaps.includes("activity")) return;
    const note = document.createElement("div");
    note.className = "wrap";
    note.innerHTML = `<p class="gap-note">ESPN only shares a league's adds, drops and trades with its members, so trades and waivers are missing here. <a href="#" data-new-league="cookies">Add your ESPN cookies</a> to see them.</p>`;
    $("#dash nav.sections").after(note);
  }

  function show(which) {
    $("#start").hidden = which !== "start";
    $("#working").hidden = which !== "working";
  }
  function formError(msg) {
    $("#formError").textContent = msg || "";
    $("#formError").hidden = !msg;
  }

  let current = {};
  async function open(args) {
    current = args;
    show("working");
    $("#status").textContent = "Starting…";
    try {
      const data = await ask({ type: "build", ...args }, (s) => { $("#status").textContent = s; });
      window.LEAGUE_DATA = data.report;
      window.LIVE_DATA = data.live;
      $("#gate").hidden = true;
      $("#dash").hidden = false;
      await loadScripts(APP);
      noteGaps(data.report.league.gaps || []);
    } catch (err) {
      $("#gate").hidden = false;
      $("#dash").hidden = true;
      show("start");
      formError(err.message);
      if (/private/.test(err.message)) $("#private").open = true;
    }
  }

  $("#form").addEventListener("submit", (e) => {
    e.preventDefault();
    const { id, season: urlSeason } = parseLeague($("#league").value);
    if (!id) return formError("Enter your league ID: the number after leagueId= in your league's URL.");
    if (urlSeason && [...$("#seasonPick").options].some((o) => o.value === urlSeason)) $("#seasonPick").value = urlSeason;
    const s2 = $("#s2").value.trim(), swid = $("#swid").value.trim();
    if (!!s2 !== !!swid) return formError("A private league needs both cookies: espn_s2 and SWID.");
    formError("");
    const args = { leagueId: id, season: +$("#seasonPick").value, s2, swid };
    save($("#remember").checked ? { leagueId: id, season: args.season, s2, swid } : null);
    open(args);
  });

  // Back to the form: "Load another league" (footer) or "Add your ESPN cookies" (the gaps note).
  document.addEventListener("click", (e) => {
    const link = e.target.closest("[data-new-league]");
    if (!link) return;
    e.preventDefault();
    const s = load();
    // Remember the league just for this trip back to the form (and open the cookie fields
    // when that's what they came for), whether or not they ticked "Remember".
    save({ ...s, leagueId: s.leagueId || current.leagueId, season: s.season || current.season,
      auto: false, cookies: link.dataset.newLeague === "cookies", keep: !!s.leagueId });
    location.href = location.pathname;
  });

  // A remembered league opens straight away (unless they just asked for another one).
  if (saved.leagueId && saved.auto !== false) {
    open({ leagueId: saved.leagueId, season: saved.season || thisSeason, s2: saved.s2 || "", swid: saved.swid || "" });
  } else if (saved.leagueId) {
    // Back on the form from the dashboard: keep a remembered league for next time, and drop
    // one that was only kept for this trip.
    const { auto, cookies, keep, ...rest } = saved;
    if (keep === false) { save(null); $("#remember").checked = false; } else save(rest);
  }
})();
