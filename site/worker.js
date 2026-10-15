// Runs the league's Python in a Web Worker with Pyodide, so the page stays responsive and
// Python's network calls can use synchronous XHR (allowed in workers, not on the page).
// Messages in: {id, leagueId, season, s2, swid}. Out: {id, status} while working,
// then {id, result} (the JSON from py/browser.py) or {id, error}.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/";
importScripts(PYODIDE + "pyodide.js");

let ready = null;
let say = () => {};

async function boot() {
  say("Starting Python (first visit downloads about 6 MB)…");
  const py = await loadPyodide({ indexURL: PYODIDE });
  say("Loading Python packages…");
  await py.loadPackage(["requests"]);
  const zip = await fetch("py/bundle.zip", { cache: "no-cache" });
  if (!zip.ok) throw new Error("Couldn't load the dashboard's Python bundle.");
  py.unpackArchive(await zip.arrayBuffer(), "zip", { extractDir: "/home/pyodide/app" });
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide/app')");
  return py;
}

// espn-api's errors, in words a visitor can act on.
function explain(err) {
  const msg = String((err && err.message) || err);
  if (/ESPNAccessDenied|espn_s2 and swid are required|cannot be accessed/.test(msg)) {
    return "ESPN wouldn't share this league. It's private, so add your espn_s2 and SWID cookies (or check they're current).";
  }
  if (/ESPNInvalidLeague|does not exist/.test(msg)) return "ESPN has no league with that ID for that season.";
  if (/ESPNUnknownError/.test(msg)) return "ESPN returned an error. Try again in a minute.";
  if (/NetworkError|Failed to fetch|XMLHttpRequest/.test(msg)) return "Couldn't reach ESPN. Check your connection and try again.";
  const last = msg.trim().split("\n").pop();
  return "Something went wrong: " + last;
}

self.onmessage = async (e) => {
  const { id, leagueId, season, s2, swid } = e.data;
  say = (status) => self.postMessage({ id, status });
  try {
    ready = ready || boot();
    const py = await ready;
    say("Reading your league from ESPN…");
    const build = py.pyimport("browser").build;
    const relay = self.location.origin + "/api/espn/";
    const result = build(leagueId, season, s2 || null, swid || null, relay);
    build.destroy();
    self.postMessage({ id, result });
  } catch (err) {
    if (ready && !(await ready.catch(() => null))) ready = null; // a failed boot retries next time
    self.postMessage({ id, error: explain(err) });
  }
};
