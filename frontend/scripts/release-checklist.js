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

function setApiBase(url) {
  const v = String(url || "").trim();
  if (!v) return;
  $("apiBase").value = v;
  localStorage.setItem("tenant_console_api_base", v);
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
      renderUser(null);
      const outLogin = $("outLogin");
      if (outLogin) outLogin.textContent = "Session expired. Please sign in again.";
    }
    throw new Error(`${res.status} ${pretty(data)}`);
  }
  return data;
}

function setBadge(id, ok, pending = false) {
  const el = $(id);
  if (!el) return;
  if (pending) {
    el.className = "badge pending";
    el.textContent = "pending";
    return;
  }
  if (ok) {
    el.className = "badge pass";
    el.textContent = "pass";
    return;
  }
  el.className = "badge fail";
  el.textContent = "fail";
}

function setStamp(id, text) {
  const el = $(id);
  if (el) el.textContent = text || "not run";
}

function setMiniIntegration(id, ok, stamp, pending = false) {
  setBadge(id, ok, pending);
  const stampId = `${id}Stamp`;
  const el = $(stampId);
  if (el) el.textContent = stamp || "not checked";
}

function renderUser(me) {
  const txt = me
    ? `Current User: ${me.email || "-"} | role=${me.role || "-"} | tenant=${me.tenant_id || "-"}`
    : "Current User: not authenticated";
  $("whoamiLine").textContent = txt;
  $("navUserBadge").textContent = txt;
}

function getManualState() {
  try {
    const raw = localStorage.getItem("tenant_release_manual");
    const parsed = JSON.parse(raw || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_) {
    return {};
  }
}

function saveManualState(next) {
  localStorage.setItem("tenant_release_manual", JSON.stringify(next || {}));
}

function renderManualChecks() {
  const manual = getManualState();
  const deployAt = manual.prod_deploy_at || "";
  const smokeAt = manual.prod_smoke_at || "";
  setBadge("chkProdDeploy", !!deployAt, !deployAt);
  setBadge("chkProdSmoke", !!smokeAt, !smokeAt);
}

async function refreshUser() {
  if (!getToken()) {
    renderUser(null);
    return null;
  }
  try {
    const me = await api("/api/v1/auth/me");
    renderUser(me);
    return me;
  } catch (_) {
    renderUser(null);
    return null;
  }
}

async function runChecks() {
  const out = $("outChecks");
  out.textContent = "Running release checks...";
  const runAt = new Date().toLocaleString();
  const result = {
    at: runAt,
    api_base: getApiBase(),
    checks: {},
    gate_pass: false,
  };

  try {
    const healthRes = await fetch(`${getApiBase()}/health`);
    result.checks.health = { ok: healthRes.ok, status: healthRes.status };
  } catch (e) {
    result.checks.health = { ok: false, error: String(e) };
  }
  setBadge("chkHealth", !!result.checks.health.ok);
  setStamp("stampHealth", runAt);

  try {
    const me = await api("/api/v1/auth/me");
    result.checks.auth_me = { ok: true, email: me.email || null, role: me.role || null };
  } catch (e) {
    result.checks.auth_me = { ok: false, error: String(e) };
  }
  setBadge("chkAuthMe", !!result.checks.auth_me.ok);
  setStamp("stampAuthMe", runAt);

  try {
    const metrics = await api("/api/v1/admin/handoff/metrics");
    result.checks.handoff_metrics = {
      ok: true,
      unresolved: metrics?.totals?.unresolved_tickets ?? 0,
      escalated: metrics?.totals?.escalated_tickets ?? 0,
    };
  } catch (e) {
    result.checks.handoff_metrics = { ok: false, error: String(e) };
  }
  setBadge("chkMetrics", !!result.checks.handoff_metrics.ok);
  setStamp("stampMetrics", runAt);

  try {
    const bots = await api("/api/v1/tenant/bots");
    result.checks.bots = { ok: true, count: Array.isArray(bots) ? bots.length : 0 };
  } catch (e) {
    result.checks.bots = { ok: false, error: String(e) };
  }
  setBadge("chkBots", !!result.checks.bots.ok);
  setStamp("stampBots", runAt);

  try {
    const knowledge = await api("/api/v1/tenant/knowledge/status");
    result.checks.knowledge = {
      ok: true,
      docs: knowledge?.document_count ?? 0,
      chunks: knowledge?.chunk_count ?? 0,
    };
  } catch (e) {
    result.checks.knowledge = { ok: false, error: String(e) };
  }
  setBadge("chkKnowledge", !!result.checks.knowledge.ok);
  setStamp("stampKnowledge", runAt);

  try {
    const integrations = await api("/api/v1/tenant/integrations/status");
    const website = !!(integrations?.website_live_chat?.enabled);
    const whatsapp = !!(integrations?.whatsapp_business?.enabled);
    const messenger = !!(integrations?.facebook_messenger?.enabled);
    const instagram = !!(integrations?.instagram?.enabled);
    const statusNote = `website=${website} whatsapp=${whatsapp} messenger=${messenger} instagram=${instagram}`;
    const ready = website && (whatsapp || messenger);
    result.checks.integrations = { ok: ready, detail: statusNote, raw: integrations };
    setMiniIntegration("miniWebsite", website, runAt);
    setMiniIntegration("miniWhatsapp", whatsapp, runAt);
    setMiniIntegration("miniMessenger", messenger, runAt);
    setMiniIntegration("miniInstagram", instagram, runAt);
  } catch (e) {
    result.checks.integrations = { ok: false, error: String(e) };
    setMiniIntegration("miniWebsite", false, "failed");
    setMiniIntegration("miniWhatsapp", false, "failed");
    setMiniIntegration("miniMessenger", false, "failed");
    setMiniIntegration("miniInstagram", false, "failed");
  }
  setBadge("chkIntegrations", !!result.checks.integrations.ok);
  setStamp("stampIntegrations", runAt);

  result.gate_pass = [
    result.checks.health?.ok,
    result.checks.auth_me?.ok,
    result.checks.handoff_metrics?.ok,
    result.checks.bots?.ok,
    result.checks.knowledge?.ok,
    result.checks.integrations?.ok,
  ].every(Boolean);

  out.textContent = pretty(result);
  localStorage.setItem("tenant_release_last_check", JSON.stringify(result));
  await refreshUser();
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
    out.textContent = pretty(data);
    await refreshUser();
  } catch (e) {
    const msg = String(e);
    if (msg.includes("409") && msg.includes("Provide tenant_id")) {
      $("lgTenantIdRow").style.display = "grid";
      $("lgTenantId").focus();
    }
    out.textContent = msg;
  }
};

$("btnRunChecks").onclick = () => runChecks();
$("btnRunChecksRight").onclick = () => runChecks();

$("btnMarkDeploy").onclick = () => {
  const next = getManualState();
  next.prod_deploy_at = new Date().toISOString();
  saveManualState(next);
  renderManualChecks();
};

$("btnMarkSmoke").onclick = () => {
  const next = getManualState();
  next.prod_smoke_at = new Date().toISOString();
  saveManualState(next);
  renderManualChecks();
};

$("btnClearManual").onclick = () => {
  saveManualState({});
  renderManualChecks();
};

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
  renderUser(null);
};

const navDashboard = $("navDashboard");
const navOps = $("navOps");
const navIntegrations = $("navIntegrations");
const navSetup = $("navSetup");
const navRelease = $("navRelease");
if (navDashboard) navDashboard.classList.remove("active");
if (navOps) navOps.classList.remove("active");
if (navIntegrations) navIntegrations.classList.remove("active");
if (navSetup) navSetup.classList.remove("active");
if (navRelease) navRelease.classList.add("active");

const btnNavSignOut = $("btnNavSignOut");
if (btnNavSignOut) {
  btnNavSignOut.onclick = () => {
    saveSessionToken("");
    setToken("");
    renderUser(null);
    $("outLogin").textContent = "Signed out.";
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

  renderManualChecks();
  setMiniIntegration("miniWebsite", false, "not checked", true);
  setMiniIntegration("miniWhatsapp", false, "not checked", true);
  setMiniIntegration("miniMessenger", false, "not checked", true);
  setMiniIntegration("miniInstagram", false, "not checked", true);
  refreshUser().catch(() => {});

  try {
    const raw = localStorage.getItem("tenant_release_last_check");
    const parsed = JSON.parse(raw || "null");
    if (parsed && typeof parsed === "object") {
      $("outChecks").textContent = pretty(parsed);
    }
  } catch (_) {}
})();
