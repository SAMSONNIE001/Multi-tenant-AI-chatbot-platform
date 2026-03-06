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

function signOut(next = "account-settings.html") {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
  window.location.href = `./auth.html?auth_required=1&next=${encodeURIComponent(next)}`;
}

(async function bootstrap() {
  const token = getToken();
  if (!token) {
    window.location.replace("./auth.html?auth_required=1&next=account-settings.html");
    return;
  }
  $("btnNavSignOut").onclick = () => signOut("account-settings.html");
  $("btnSignOutHere").onclick = () => signOut("account-settings.html");
  setStatus("outSession", "Current session active.");
  setStatus("outSecurity", "Use the flow below to rotate your password.");
  try {
    const me = await api("/api/v1/auth/me");
    $("acEmail").value = me.email || "";
    $("acTenantId").value = me.tenant_id || "";
    $("acRole").value = me.role || "";
    $("fpTenantId").value = me.tenant_id || "";
    $("navUserBadge").textContent = `Current User: ${me.email || "-"}`;
  } catch (e) {
    setStatus("outSession", cleanError(e));
  }

  $("btnForgotPassword").onclick = async () => {
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
  };

  $("btnResetPassword").onclick = async () => {
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
      setStatus("outSecurity", res.message || "Password reset successful.");
      $("fpNewPassword").value = "";
    } catch (e) {
      setStatus("outSecurity", cleanError(e));
    }
  };
})();
