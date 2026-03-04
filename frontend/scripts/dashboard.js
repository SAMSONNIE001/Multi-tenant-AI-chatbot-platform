const $ = (id) => document.getElementById(id);
const TOKEN_KEY = "tenant_console_token";
const SESSION_EXPIRED_KEY = "tenant_console_session_expired";

function pretty(v) {
  try { return JSON.stringify(v, null, 2); } catch (_) { return String(v); }
}

function getApiBase() {
  return $("apiBase").value.trim().replace(/\/+$/, "");
}

function getToken() {
  return $("accessToken").value.trim();
}

function setToken(token) {
  $("accessToken").value = token || "";
}

function saveSessionToken(token) {
  if (token && String(token).trim()) {
    sessionStorage.setItem(TOKEN_KEY, String(token).trim());
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
  }
  localStorage.removeItem(TOKEN_KEY);
}

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token.replace(/^Bearer\s+/i, "")}`;
  const res = await fetch(`${getApiBase()}${path}`, { ...options, headers });
  const text = await res.text();
  let data = text;
  try { data = JSON.parse(text); } catch (_) {}
  if (!res.ok) {
    if (res.status === 401) {
      sessionStorage.setItem(SESSION_EXPIRED_KEY, "1");
      saveSessionToken("");
      setToken("");
      renderWhoamiLine(null);
    }
    throw new Error(`${res.status} ${pretty(data)}`);
  }
  return data;
}

function setApiBase(url) {
  const v = String(url || "").trim();
  if (!v) return;
  $("apiBase").value = v;
  localStorage.setItem("tenant_console_api_base", v);
}

function renderWhoamiLine(me) {
  const line = $("whoamiLine");
  const nav = $("navUserBadge");
  if (!me) {
    line.textContent = "Current User: not authenticated";
    if (nav) nav.textContent = "Current User: not authenticated";
    return;
  }
  const txt = `Current User: ${me.email || "-"} | role=${me.role || "-"} | tenant=${me.tenant_id || "-"}`;
  line.textContent = txt;
  if (nav) nav.textContent = txt;
}

async function refreshSnapshot() {
  const out = $("outSnapshot");
  out.textContent = "Refreshing...";
  const grid = $("kpiGrid");
  try {
    const me = await api("/api/v1/auth/me");
    const bots = await api("/api/v1/tenant/bots");
    const knowledge = await api("/api/v1/tenant/knowledge/status");
    const metrics = await api("/api/v1/admin/handoff/metrics");

    renderWhoamiLine(me);
    const cards = [
      ["Role", me.role || "-"],
      ["Tenant", me.tenant_id || "-"],
      ["Bots", Array.isArray(bots) ? bots.length : 0],
      ["Docs", knowledge.document_count || 0],
      ["Chunks", knowledge.chunk_count || 0],
      ["Handoffs", metrics?.totals?.all_tickets ?? 0],
      ["Escalated", metrics?.totals?.escalated_tickets ?? 0],
      ["As Of", metrics?.as_of || "-"],
    ];
    grid.style.display = "grid";
    grid.innerHTML = cards
      .map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${String(v)}</div></div>`)
      .join("");

    const totals = metrics?.totals || {};
    out.textContent = [
      `Snapshot updated ${new Date().toLocaleString()}`,
      `Tenant ${me.tenant_id || "-"} (${me.role || "-"})`,
      `Handoffs: ${totals.unresolved_tickets ?? 0} unresolved, ${totals.escalated_tickets ?? 0} escalated`,
      `Knowledge: ${knowledge.document_count || 0} docs / ${knowledge.chunk_count || 0} chunks`,
    ].join("\n");
  } catch (e) {
    const msg = String(e);
    if (msg.includes("401")) {
      out.textContent = "Sign in to load snapshot.";
    } else {
      out.textContent = msg;
    }
    grid.style.display = "none";
    grid.innerHTML = "";
  }
}

$("btnLogin").onclick = async () => {
  const out = $("outLogin");
  out.textContent = "Running...";
  try {
    const body = {
      email: $("lgEmail").value.trim(),
      password: $("lgPassword").value,
    };
    const tenantId = $("lgTenantId").value.trim();
    if (tenantId) body.tenant_id = tenantId;
    const data = await api("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (data && data.access_token) {
      setToken(data.access_token);
      saveSessionToken(data.access_token);
    }
    $("lgTenantIdRow").style.display = "none";
    $("lgTenantId").value = "";
    out.textContent = `Login successful for ${body.email}.`;
    await refreshSnapshot();
  } catch (e) {
    const msg = String(e);
    if (msg.includes("409") && msg.includes("Provide tenant_id")) {
      $("lgTenantIdRow").style.display = "grid";
      $("lgTenantId").focus();
    }
    out.textContent = msg;
  }
};

$("btnRefreshAll").onclick = () => refreshSnapshot();
$("btnEnvProd").onclick = () => setApiBase("https://api.staunchbot.com");
$("btnEnvStaging").onclick = () => setApiBase($("stagingApiBase").value.trim());
$("btnEnvLocal").onclick = () => setApiBase("http://localhost:8000");
$("saveToken").onclick = () => {
  saveSessionToken($("accessToken").value);
  localStorage.setItem("tenant_console_api_base", $("apiBase").value);
  localStorage.setItem("tenant_console_staging_api_base", $("stagingApiBase").value);
};
$("clearToken").onclick = () => {
  saveSessionToken("");
  setToken("");
  renderWhoamiLine(null);
  $("outSnapshot").textContent = "Signed out. Login to load tenant snapshot.";
  $("kpiGrid").style.display = "none";
  $("kpiGrid").innerHTML = "";
};
const btnForgotPassword = $("btnForgotPassword");
if (btnForgotPassword) {
  btnForgotPassword.onclick = async () => {
    const out = $("outForgotPassword");
    out.textContent = "Sending reset request...";
    try {
      const body = { email: $("fpEmail").value.trim() };
      const tenantId = $("fpTenantId").value.trim();
      if (tenantId) body.tenant_id = tenantId;
      const data = await api("/api/v1/auth/password/forgot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      out.textContent = data.message || "If the account exists, reset email has been sent.";
    } catch (e) {
      out.textContent = String(e);
    }
  };
}

const btnResetPassword = $("btnResetPassword");
if (btnResetPassword) {
  btnResetPassword.onclick = async () => {
    const out = $("outResetPassword");
    out.textContent = "Resetting password...";
    try {
      const data = await api("/api/v1/auth/password/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reset_token: $("fpResetToken").value.trim(),
          code: $("fpCode").value.trim(),
          new_password: $("fpNewPassword").value,
        }),
      });
      out.textContent = data.message || "Password reset successful.";
    } catch (e) {
      out.textContent = String(e);
    }
  };
}
const navDashboard = $("navDashboard");
const navOps = $("navOps");
const navSetup = $("navSetup");
const navRelease = $("navRelease");
if (navDashboard) navDashboard.classList.add("active");
if (navOps) navOps.classList.remove("active");
if (navSetup) navSetup.classList.remove("active");
if (navRelease) navRelease.classList.remove("active");
const btnNavSignOut = $("btnNavSignOut");
if (btnNavSignOut) {
  btnNavSignOut.onclick = () => {
    saveSessionToken("");
    setToken("");
    renderWhoamiLine(null);
    $("outLogin").textContent = "Signed out.";
    $("outSnapshot").textContent = "Signed out. Login to load tenant snapshot.";
    $("kpiGrid").style.display = "none";
    $("kpiGrid").innerHTML = "";
  };
}

(function bootstrap() {
  const savedToken = sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
  const savedBase = localStorage.getItem("tenant_console_api_base");
  const savedStaging = localStorage.getItem("tenant_console_staging_api_base");
  const host = String(window.location.hostname || "").toLowerCase();
  const hostedDefaultBase = (host === "www.staunchbot.com" || host === "staunchbot.com") ? "https://api.staunchbot.com" : "";
  if (savedToken) {
    setToken(savedToken);
    saveSessionToken(savedToken);
  }
  if (savedBase) $("apiBase").value = savedBase;
  if (hostedDefaultBase && (!savedBase || /^https?:\/\/localhost(:\d+)?/i.test(savedBase))) {
    $("apiBase").value = hostedDefaultBase;
  }
  if (savedStaging) $("stagingApiBase").value = savedStaging;
  if (sessionStorage.getItem(SESSION_EXPIRED_KEY) === "1") {
    $("outLogin").textContent = "Session expired. Please sign in again.";
    sessionStorage.removeItem(SESSION_EXPIRED_KEY);
  }
  const params = new URLSearchParams(window.location.search || "");
  const resetToken = params.get("reset_token");
  if (resetToken && $("fpResetToken")) $("fpResetToken").value = resetToken;
  refreshSnapshot().catch(() => {});
})();
