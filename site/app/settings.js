// Settings tab: R-rated mode (core.js A.rRated) and whether this league is remembered on this
// device (start.js window.OpenLeague). Everything here is saved in this browser only.
(function () {
  const A = window.App;
  if (!A) return;
  const { L, $, esc } = A;
  const root = $("#settings");
  if (!root) return;
  const OL = window.OpenLeague || {};

  function leagueText() {
    const saved = OL.isSaved && OL.isSaved();
    const cookies = OL.isPrivate && OL.isPrivate() ? " and your ESPN cookies" : "";
    return saved
      ? `This device remembers ${esc(L.name)}${cookies}, so the dashboard opens straight to it.`
      : `${esc(L.name)} isn't saved. Next time you'll enter the league ID again.`;
  }

  function draw() {
    const saved = OL.isSaved && OL.isSaved();
    root.innerHTML = `<h2>Settings</h2>
      <p class="sub">Saved in this browser only. Nothing here goes to a server.</p>
      <div class="card set-list">
        <div class="set-row">
          <div class="set-text">
            <h3 id="setRatedLabel">R-rated mode</h3>
            <p>Bring back the crude names some group chats use: the most-traded player gets a cruder title, and scoring under 100 drops an f-bomb. Off unless you switch it on.</p>
          </div>
          <label class="set-switch">
            <input type="checkbox" role="switch" id="setRated" aria-labelledby="setRatedLabel" ${A.rRated() ? "checked" : ""}>
            <span aria-hidden="true"></span>
          </label>
        </div>
        <div class="set-row">
          <div class="set-text">
            <h3>This league</h3>
            <p>${leagueText()}</p>
          </div>
          <div class="set-actions">
            <button type="button" class="set-btn" id="setSave">${saved ? "Forget on this device" : "Remember on this device"}</button>
            <a href="#" class="set-link" data-new-league>Load another league</a>
          </div>
        </div>
      </div>`;
  }

  draw();
  root.addEventListener("change", (e) => {
    if (e.target.id === "setRated") A.setRRated(e.target.checked);
  });
  root.addEventListener("click", (e) => {
    if (e.target.id !== "setSave") return;
    if (OL.isSaved && OL.isSaved()) OL.forget && OL.forget();
    else OL.remember && OL.remember();
    draw();
    $("#setSave").focus();
  });
})();
