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

async function deleteAccount() {
  setStatus("outDelete", "Deleting account...");
  try {
    const email = ($("acEmail") && $("acEmail").value || "").trim().toLowerCase();
    const confirmEmail = ($("deleteConfirmEmail") && $("deleteConfirmEmail").value || "").trim().toLowerCase();
    if (!email || !confirmEmail || email !== confirmEmail) {
      throw new Error("Type your exact account email to confirm account deletion.");
    }
    const ok = window.confirm("This action is permanent and cannot be undone. Delete your account?");
    if (!ok) {
      setStatus("outDelete", "Account deletion canceled.");
      return;
    }
    await api("/api/v1/auth/me", { method: "DELETE" });
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
    setStatus("outDelete", "Account deleted. Redirecting to sign in...");
    setTimeout(() => {
      window.location.href = "./auth.html";
    }, 1200);
  } catch (e) {
    setStatus("outDelete", cleanError(e));
  }
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

async function sendPasswordReset() {
  setStatus("outSecurity", "Sending reset request...");
  try {
    const body = { email: $("acEmail").value.trim() };
    const tenant = $("fpTenantId").value.trim();
    if (tenant) body.tenant_id = tenant;
    const res = await api("/api/v1/auth/password/forgot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setStatus("outSecurity", res.message || "If account exists, reset email was sent.");
  } catch (e) {
    setStatus("outSecurity", cleanError(e));
  }
}

async function applyPasswordReset() {
  setStatus("outSecurity", "Resetting password...");
  try {
    const res = await api("/api/v1/auth/password/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reset_token: $("fpResetToken").value.trim(),
        code: $("fpCode").value.trim(),
        new_password: $("fpNewPassword").value,
      }),
    });
    $("fpNewPassword").value = "";
    setStatus("outSecurity", res.message || "Password reset successful.");
  } catch (e) {
    setStatus("outSecurity", cleanError(e));
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
  if ($("btnForgotPassword")) $("btnForgotPassword").onclick = () => sendPasswordReset();
  if ($("btnResetPassword")) $("btnResetPassword").onclick = () => applyPasswordReset();
  if ($("btnDeleteAccount")) $("btnDeleteAccount").onclick = () => deleteAccount();
  setStatus("outSettings", "Loading account context...");
  setStatus("outSecurity", "Use this section to update account password securely.");
  setStatus("outDelete", "Danger zone: account deletion is permanent.");
  try {
    const me = await api("/api/v1/auth/me");
    $("navUserBadge").textContent = `Current User: ${me.email || "-"}`;
    if ($("acEmail")) $("acEmail").value = me.email || "";
    if ($("fpTenantId")) $("fpTenantId").value = me.tenant_id || "";
    setStatus("outSettings", `Signed in as ${me.email || "-"} (${me.role || "-"}).`);
  } catch (e) {
    setStatus("outSettings", cleanError(e));
  }
  loadLimits();
  loadRetention();
})();
