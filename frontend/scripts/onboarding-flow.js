(() => {
  const KEY = "sb_onboarding_flow_v1";

  const steps = [
    { id: "dashboard", label: "1. Dashboard", path: "dashboard.html" },
    { id: "profile", label: "2. Profile", path: "profile.html" },
    { id: "settings", label: "3. Settings", path: "settings.html" },
    { id: "integrations", label: "4. Integrations", path: "integrations.html" },
    { id: "knowledge", label: "5. Knowledge Base", path: "tenant-setup.html" },
    { id: "inbox", label: "6. Unified Inbox", path: "tenant-console.html" },
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
      .sb-flow {
        margin: 12px 0;
        border: 1px solid #dbe3ee;
        border-radius: 12px;
        background: #ffffff;
        padding: 10px;
      }
      .sb-flow-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;
      }
      .sb-flow-title {
        font-size: 14px;
        font-weight: 700;
        color: #0f172a;
      }
      .sb-flow-sub {
        font-size: 12px;
        color: #64748b;
      }
      .sb-flow-track {
        display: grid;
        gap: 6px;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      }
      .sb-step {
        border: 1px solid #dbe3ee;
        border-radius: 8px;
        padding: 6px 8px;
        font-size: 12px;
        color: #475569;
        background: #f8fafc;
      }
      .sb-step.current {
        border-color: #93c5fd;
        background: #eff6ff;
        color: #1d4ed8;
        font-weight: 700;
      }
      .sb-step.done {
        border-color: #bbf7d0;
        background: #ecfdf5;
        color: #166534;
      }
      .sb-flow-actions {
        margin-top: 8px;
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .sb-flow-actions button, .sb-flow-actions a {
        border: 0;
        border-radius: 8px;
        padding: 7px 10px;
        font-size: 12px;
        font-weight: 700;
        text-decoration: none;
      }
      .sb-flow-next {
        background: #2563eb;
        color: #fff;
      }
      .sb-flow-skip {
        background: #e2e8f0;
        color: #334155;
      }
    `;
    document.head.appendChild(style);
  }

  function resolveStep() {
    const path = currentPath();
    return steps.findIndex((s) => s.path.toLowerCase() === path);
  }

  function mountFlow() {
    const current = resolveStep();
    if (current < 0) return;

    ensureStyles();
    const state = readState();
    const nowId = steps[current].id;
    // Keep journey as guidance only; do not force-redirect page navigation.

    const container = document.createElement("section");
    container.className = "sb-flow";
    container.innerHTML = `
      <div class="sb-flow-head">
        <div>
          <div class="sb-flow-title">Setup Journey</div>
          <div class="sb-flow-sub">Follow this order for a complete, user-friendly workspace setup.</div>
        </div>
      </div>
      <div class="sb-flow-track"></div>
      <div class="sb-flow-actions"></div>
    `;

    const track = container.querySelector(".sb-flow-track");
    steps.forEach((step, idx) => {
      const node = document.createElement("div");
      node.className = "sb-step";
      if (idx === current) node.classList.add("current");
      if (state[step.id]) node.classList.add("done");
      node.textContent = step.label;
      track.appendChild(node);
    });

    const actions = container.querySelector(".sb-flow-actions");
    const next = steps[current + 1];
    if (next) {
      const btn = document.createElement("button");
      btn.className = "sb-flow-next";
      btn.type = "button";
      btn.textContent = `Complete and Continue: ${next.label}`;
      btn.onclick = () => {
        const latest = readState();
        latest[nowId] = true;
        writeState(latest);
        window.location.href = `./${next.path}`;
      };
      actions.appendChild(btn);
    } else {
      const doneBtn = document.createElement("button");
      doneBtn.className = "sb-flow-next";
      doneBtn.type = "button";
      doneBtn.textContent = "Mark Journey Complete";
      doneBtn.onclick = () => {
        const latest = readState();
        latest[nowId] = true;
        writeState(latest);
        window.location.reload();
      };
      actions.appendChild(doneBtn);

      const done = document.createElement("div");
      done.className = "sb-flow-sub";
      done.textContent = "Journey complete. Your workspace is ready for daily operations.";
      actions.appendChild(done);
    }

    const reset = document.createElement("button");
    reset.className = "sb-flow-skip";
    reset.type = "button";
    reset.textContent = "Reset Journey";
    reset.onclick = () => {
      localStorage.removeItem(KEY);
      window.location.reload();
    };
    actions.appendChild(reset);

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






