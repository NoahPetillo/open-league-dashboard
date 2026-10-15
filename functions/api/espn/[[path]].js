// Stateless relay to ESPN's fantasy football API, for private leagues only.
//
// A page can't attach someone's espn_s2/SWID cookies to a request to ESPN itself (browsers
// forbid setting the Cookie header), so the page sends them as X-Espn-S2 / X-Espn-Swid headers
// and this turns them back into cookies. Public leagues skip the relay: ESPN answers browsers
// directly. Nothing is stored or logged, and only ESPN's football read API can be reached
// through here: /api/espn/<path> → https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/<path>.

const UPSTREAM = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/";
// The paths espn-api reads: a season's league (and its /communication/ feed), the season's
// players and pro schedule, and the leagueHistory endpoint older leagues answer on.
const PATH_OK = /^(seasons\/\d{4}(\/[A-Za-z0-9_\-\/]*)?|leagueHistory\/\d+)$/;
const COOKIE_OK = /^[A-Za-z0-9%{}\-_.+\/=]{1,1024}$/;

function fail(status, message) {
  return new Response(JSON.stringify({ error: message }), {
    status, headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function onRequestGet({ request, params }) {
  const url = new URL(request.url);
  const origin = request.headers.get("origin");
  if (origin && origin !== url.origin) return fail(403, "This relay only serves its own site.");

  const path = [].concat(params.path || []).join("/");
  if (!PATH_OK.test(path)) return fail(404, "Not an ESPN fantasy football path.");

  const s2 = request.headers.get("x-espn-s2") || "";
  const swid = request.headers.get("x-espn-swid") || "";
  if (!s2 || !swid) return fail(400, "Send both X-Espn-S2 and X-Espn-Swid (public leagues don't need the relay).");
  if (!COOKIE_OK.test(s2) || !COOKIE_OK.test(swid)) return fail(400, "Those don't look like ESPN cookies.");

  const headers = { accept: "application/json", cookie: `espn_s2=${s2}; SWID=${swid}` };
  const filter = request.headers.get("x-fantasy-filter");
  if (filter) headers["x-fantasy-filter"] = filter;

  const r = await fetch(UPSTREAM + path + url.search, { headers, redirect: "manual" });
  return new Response(r.body, {
    status: r.status,
    headers: { "content-type": r.headers.get("content-type") || "application/json", "cache-control": "no-store" },
  });
}
