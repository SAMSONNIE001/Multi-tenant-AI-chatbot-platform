const TOKEN_KEY = "tenant_console_token";
const $ = (id) => document.getElementById(id);

function getApiBase() {
  const saved = localStorage.getItem("tenant_console_api_base") || "";
  const host = String(window.location.hostname || "").toLowerCase();
  const prod = host === "www.staunchbot.com" || host === "staunchbot.com";
  if (prod && (!saved || /^https?:\/\/localhost(:\d+)?/i.test(saved))) return "https://api.staunchbot.com";
  return String(saved || "http://localhost:8000").trim().replace(/\/+$/, "");
}

function getToken() {
  return (sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || "").trim();
}

function setStatus(id, msg) {
  const el = $(id);
  if (el) el.textContent = msg;
}

function cleanError(e) {
  const raw = String(e || "Request failed");
  if (raw.includes("401")) return "Session expired. Please sign in again.";
  if (raw.includes("403")) return "Access denied for this action.";
  return raw.replace(/^\d+\s+/, "").slice(0, 220);
}

async function api(path, options = {}) {
  const token = getToken();
  const headers = Object.assign({}, options.headers || {});
  if (token) headers.Authorization = `Bearer ${token.replace(/^Bearer\s+/i, "")}`;
  const res = await fetch(`${getApiBase()}${path}`, { ...options, headers });
  const text = await res.text();
  let data = text;
  try { data = JSON.parse(text); } catch (_) {}
  if (!res.ok) throw new Error(`${res.status} ${typeof data === "string" ? data : JSON.stringify(data)}`);
  return data;
}

function signOut() {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
  window.location.href = "./auth.html?auth_required=1&next=profile.html";
}

function initPrefs() {
  $("btnSavePrefs").onclick = async () => {
    setStatus("outPrefs", "Saving preferences...");
    try {
      await api("/api/v1/auth/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preferred_name: $("prefName").value.trim() || null,
          timezone: $("prefTimezone").value || null,
        }),
      });
      setStatus("outPrefs", "Preferences saved.");
    } catch (e) {
      setStatus("outPrefs", cleanError(e));
    }
  };
  $("btnResetPrefs").onclick = async () => {
    setStatus("outPrefs", "Resetting preferences...");
    try {
      await api("/api/v1/auth/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferred_name: null, timezone: null }),
      });
      $("prefName").value = "";
      $("prefTimezone").value = "";
      setStatus("outPrefs", "Preferences reset.");
    } catch (e) {
      setStatus("outPrefs", cleanError(e));
    }
  };
}

(async function bootstrap() {
  const token = getToken();
  if (!token) {
    window.location.replace("./auth.html?auth_required=1&next=profile.html");
    return;
  }
  $("btnNavSignOut").onclick = signOut;
  setStatus("outProfile", "Loading profile...");
  setStatus("outWorkspace", "Loading workspace summary...");
  setStatus("outPrefs", "Set your personal workspace preferences.");
  try {
    const me = await api("/api/v1/auth/me");
    const display = me.email ? me.email.split("@")[0] : "-";
    $("pfDisplayName").textContent = display;
    $("pfEmail").textContent = me.email || "-";
    $("pfRole").textContent = me.role || "-";
    $("pfTenantId").textContent = me.tenant_id || "-";
    $("pfUserId").textContent = me.id || "-";
    $("navUserBadge").textContent = `Current User: ${me.email || "-"}`;
    setStatus("outProfile", "Profile loaded.");
    initPrefs();

    try {
      const pref = await api("/api/v1/auth/preferences");
      $("prefName").value = pref?.preferred_name || "";
      $("prefTimezone").value = pref?.timezone || "";
    } catch (_) {}

    let bots = 0;
    let docs = 0;
    let req7d = "-";
    let tok7d = "-";
    try {
      const botsRes = await api("/api/v1/tenant/bots");
      bots = Array.isArray(botsRes) ? botsRes.length : 0;
    } catch (_) {}
    try {
      const ks = await api("/api/v1/tenant/knowledge/status");
      docs = Number(ks.document_count || 0);
    } catch (_) {}
    try {
      const us = await api("/api/v1/admin/usage/summary?window_days=7");
      req7d = us?.summary?.total_requests ?? "-";
      tok7d = us?.summary?.total_tokens ?? "-";
    } catch (_) {}
    $("wsBots").textContent = String(bots);
    $("wsDocs").textContent = String(docs);
    $("wsReq7d").textContent = String(req7d);
    $("wsTokens7d").textContent = String(tok7d);
    setStatus("outWorkspace", "Workspace summary loaded.");
  } catch (e) {
    const msg = cleanError(e);
    setStatus("outProfile", msg);
    setStatus("outWorkspace", "Unable to load workspace summary.");
  }
})();
