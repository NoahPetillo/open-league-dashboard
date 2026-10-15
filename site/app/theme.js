// Night mode: a sun/moon button in the header. Until someone presses it the site follows the
// device's light/dark setting; pressing it pins the other one (remembered in this browser).
// Picking the same mode as the device goes back to following the device. Loaded in <head> so the
// saved mode is on <html> before anything paints. The colors themselves live in app.css
// (:root[data-theme]).
(function () {
  const KEY = "theme";
  const root = document.documentElement;
  const media = matchMedia("(prefers-color-scheme: dark)");
  const get = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  const put = (v) => { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch { /* private mode */ } };

  const saved = get();
  if (saved === "light" || saved === "dark") root.dataset.theme = saved;
  const device = () => (media.matches ? "dark" : "light");
  const current = () => root.dataset.theme || device();

  const SUN = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="4.2" fill="currentColor"/><g stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/></g></svg>';
  const MOON = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M20.5 14.6A8.5 8.5 0 0 1 9.4 3.5a8.5 8.5 0 1 0 11.1 11.1Z" fill="currentColor"/></svg>';

  function paint(btn) {
    const dark = current() === "dark";
    btn.innerHTML = dark ? SUN : MOON;
    const label = dark ? "Switch to light mode" : "Switch to night mode";
    btn.setAttribute("aria-label", label);
    btn.title = label;
  }

  function mount() {
    const head = document.querySelector("header.top");
    if (!head || head.querySelector(".theme-btn")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theme-btn";
    paint(btn);
    btn.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      if (next === device()) { delete root.dataset.theme; put(null); }
      else { root.dataset.theme = next; put(next); }
      paint(btn);
    });
    media.addEventListener("change", () => paint(btn));
    head.appendChild(btn);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
