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
  if (raw.includes("403")) return "Admin role is required for this setting.";
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
  window.location.href = "./auth.html?auth_required=1&next=settings.html";
}

async function loadLimits() {
  setStatus("outLimits", "Loading usage limits...");
  try {
    const res = await api("/api/v1/admin/usage/limits");
    $("setDailyLimit").value = String(res?.limits?.daily_request_limit ?? "");
    $("setMonthlyTokens").value = String(res?.limits?.monthly_token_limit ?? "");
    setStatus("outLimits", "Usage limits loaded.");
  } catch (e) {
    setStatus("outLimits", cleanError(e));
  }
}

async function saveLimits() {
  setStatus("outLimits", "Saving usage limits...");
  try {
    const body = {
      daily_request_limit: Number($("setDailyLimit").value || 0),
      monthly_token_limit: Number($("setMonthlyTokens").value || 0),
    };
    await api("/api/v1/admin/usage/limits", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setStatus("outLimits", "Usage limits saved.");
  } catch (e) {
    setStatus("outLimits", cleanError(e));
  }
}

async function loadRetention() {
  setStatus("outRetention", "Loading retention policy...");
  try {
    const res = await api("/api/v1/admin/retention");
    $("setAuditDays").value = String(res?.retention?.audit_days ?? "");
    $("setMessageDays").value = String(res?.retention?.messages_days ?? "");
    setStatus("outRetention", "Retention policy loaded.");
  } catch (e) {
    setStatus("outRetention", cleanError(e));
  }
}

async function saveRetention() {
  setStatus("outRetention", "Saving retention policy...");
  try {
    const body = {
      audit_days: Number($("setAuditDays").value || 0),
      messages_days: Number($("setMessageDays").value || 0),
    };
    await api("/api/v1/admin/retention", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setStatus("outRetention", "Retention policy saved.");
  } catch (e) {
    setStatus("outRetention", cleanError(e));
  }
}

(async function bootstrap() {
  const token = getToken();
  if (!token) {
    window.location.replace("./auth.html?auth_required=1&next=settings.html");
    return;
  }
  $("btnNavSignOut").onclick = signOut;
  $("btnLoadLimits").onclick = () => loadLimits();
  $("btnSaveLimits").onclick = () => saveLimits();
  $("btnLoadRetention").onclick = () => loadRetention();
  $("btnSaveRetention").onclick = () => saveRetention();
  setStatus("outSettings", "Loading account context...");
  try {
    const me = await api("/api/v1/auth/me");
    $("navUserBadge").textContent = `Current User: ${me.email || "-"}`;
    setStatus("outSettings", `Signed in as ${me.email || "-"} (${me.role || "-"}).`);
  } catch (e) {
    setStatus("outSettings", cleanError(e));
  }
  loadLimits();
  loadRetention();
})();
