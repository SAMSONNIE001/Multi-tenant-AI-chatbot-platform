(() => {
  const KEY = "sb_debug_panels";
  const BTN_ID = "sbDebugToggle";

  function isEnabled() {
    return localStorage.getItem(KEY) === "1";
  }

  function setEnabled(v) {
    localStorage.setItem(KEY, v ? "1" : "0");
  }

  function ensureToggle() {
    if (document.getElementById(BTN_ID)) return;
    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.type = "button";
    btn.style.position = "fixed";
    btn.style.right = "14px";
    btn.style.bottom = "14px";
    btn.style.zIndex = "9999";
    btn.style.border = "1px solid #cbd5e1";
    btn.style.borderRadius = "999px";
    btn.style.padding = "6px 10px";
    btn.style.fontSize = "12px";
    btn.style.fontWeight = "700";
    btn.style.cursor = "pointer";
    btn.style.background = "#ffffff";
    btn.style.color = "#334155";
    btn.style.boxShadow = "0 6px 18px rgba(15,23,42,0.12)";
    btn.onclick = () => {
      setEnabled(!isEnabled());
      apply();
    };
    document.body.appendChild(btn);
  }

  function apply() {
    const enabled = isEnabled();
    document.documentElement.classList.toggle("sb-debug-panels", enabled);
    const panels = document.querySelectorAll(".out");
    panels.forEach((el) => {
      el.style.display = enabled ? "" : "none";
    });
    const btn = document.getElementById(BTN_ID);
    if (btn) {
      btn.textContent = enabled ? "Debug: ON" : "Debug: OFF";
      btn.style.background = enabled ? "#ecfeff" : "#ffffff";
      btn.style.borderColor = enabled ? "#67e8f9" : "#cbd5e1";
      btn.style.color = enabled ? "#0e7490" : "#334155";
    }
  }

  function init() {
    ensureToggle();
    apply();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
