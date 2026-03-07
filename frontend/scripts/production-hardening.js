(() => {
  const host = String(window.location.hostname || "").toLowerCase();
  const isProdHost = host === "www.staunchbot.com" || host === "staunchbot.com";
  if (!isProdHost) return;

  const path = String(window.location.pathname || "").toLowerCase();
  if (path.includes("release-checklist")) {
    window.location.replace("./dashboard.html");
    return;
  }

  const hide = (el) => {
    if (!el) return;
    el.style.display = "none";
  };

  document.querySelectorAll("[data-dev-only]").forEach(hide);
  document.querySelectorAll("a[href*='release-checklist']").forEach(hide);

  ["btnEnvLocal", "btnEnvStaging", "btnEnvProd", "btnRunStagingQaPack", "btnRunUatPack"].forEach((id) => {
    hide(document.getElementById(id));
  });

  document.querySelectorAll("details").forEach((d) => {
    const summary = d.querySelector("summary");
    const txt = String(summary?.textContent || "").toLowerCase();
    if (txt.includes("advanced connection settings")) {
      hide(d);
    }
  });
})();
