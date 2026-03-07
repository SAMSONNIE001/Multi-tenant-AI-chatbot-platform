(() => {
  const KEY = "sb_onboarding_flow_v2";
  const DASHBOARD_PATH = "dashboard.html";
  const STEPS = [
    "Dashboard",
    "Profile",
    "Settings",
    "Integrations",
    "Knowledge Base",
    "Unified Inbox",
  ];

  function currentPath() {
    const p = String(window.location.pathname || "").toLowerCase();
    return p.split("/").pop() || "";
  }

  function readState() {
    try {
      const parsed = JSON.parse(localStorage.getItem(KEY) || "{}");
      return (parsed && typeof parsed === "object") ? parsed : {};
    } catch (_) {
      return {};
    }
  }

  function writeState(state) {
    localStorage.setItem(KEY, JSON.stringify(state || {}));
  }

  function ensureStyles() {
    if (document.getElementById("sbFlowStyle")) return;
    const style = document.createElement("style");
    style.id = "sbFlowStyle";
    style.textContent = `
      .sb-flow { margin: 12px 0; border: 1px solid #dbe3ee; border-radius: 12px; background: #ffffff; padding: 10px; }
      .sb-flow-title { font-size: 14px; font-weight: 700; color: #0f172a; }
      .sb-flow-sub { font-size: 12px; color: #64748b; margin-top: 2px; }
      .sb-flow-track { display: grid; gap: 6px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-top: 8px; }
      .sb-step { border: 1px solid #dbe3ee; border-radius: 8px; padding: 6px 8px; font-size: 12px; color: #475569; background: #f8fafc; }
      .sb-flow-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
      .sb-flow-next, .sb-flow-done { border: 0; border-radius: 8px; padding: 7px 10px; font-size: 12px; font-weight: 700; cursor: pointer; }
      .sb-flow-next { background: #2563eb; color: #fff; }
      .sb-flow-done { background: #0f766e; color: #fff; }
    `;
    document.head.appendChild(style);
  }

  function mountFlow() {
    if (currentPath() !== DASHBOARD_PATH) return;

    const state = readState();
    if (state.completed) return;

    ensureStyles();

    const container = document.createElement("section");
    container.className = "sb-flow";
    container.innerHTML = `
      <div class="sb-flow-title">Setup Journey</div>
      <div class="sb-flow-sub">Complete your core setup once. This panel hides permanently after completion.</div>
      <div class="sb-flow-track"></div>
      <div class="sb-flow-actions">
        <button type="button" class="sb-flow-next" id="sbFlowNext">Continue: Profile</button>
        <button type="button" class="sb-flow-done" id="sbFlowDone">Mark Setup Complete</button>
      </div>
    `;

    const track = container.querySelector(".sb-flow-track");
    STEPS.forEach((label, index) => {
      const node = document.createElement("div");
      node.className = "sb-step";
      node.textContent = `${index + 1}. ${label}`;
      track.appendChild(node);
    });

    container.querySelector("#sbFlowNext").onclick = () => {
      window.location.href = "./profile.html";
    };
    container.querySelector("#sbFlowDone").onclick = () => {
      writeState({ completed: true, completed_at: new Date().toISOString() });
      container.remove();
    };

    const anchor = document.querySelector(".topbar, .topnav, .hero");
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(container, anchor.nextSibling);
      return;
    }
    const main = document.querySelector(".main, .wrap, body");
    if (main) main.insertBefore(container, main.firstChild);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountFlow);
  } else {
    mountFlow();
  }
})();
