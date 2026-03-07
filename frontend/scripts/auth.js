const $ = (id) => document.getElementById(id);
const TOKEN_KEY = "tenant_console_token";
const SESSION_EXPIRED_KEY = "tenant_console_session_expired";

function pretty(v) {
  try { return JSON.stringify(v, null, 2); } catch (_) { return String(v); }
}

function cleanError(e) {
  const raw = String(e || "Request failed");
  if (raw.includes("401")) return "Invalid email or password.";
  if (raw.includes("403")) return "You do not have permission to perform this action.";
  if (raw.includes("404")) return "Requested resource was not found.";
  if (raw.includes("409") && raw.includes("Provide tenant_id")) return "This email belongs to multiple tenants. Enter Tenant ID and try again.";
  if (raw.includes("422")) return "Some fields are invalid. Check your inputs and try again.";
  if (raw.includes("500")) return "Server error. Please try again in a moment.";
  return raw.replace(/^\d+\s+/, "").slice(0, 220);
}

function getApiBase() {
  return $("apiBase").value.trim().replace(/\/+$/, "");
}

function parseOrigins(s) {
  return String(s || "")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function setToken(token) {
  if (token && String(token).trim()) {
    sessionStorage.setItem(TOKEN_KEY, String(token).trim());
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
  }
  localStorage.removeItem(TOKEN_KEY);
}

function nextPath() {
  const params = new URLSearchParams(window.location.search || "");
  const next = String(params.get("next") || "").trim();
  const allowed = new Set([
    "dashboard.html",
    "tenant-console.html",
    "tenant-setup.html",
    "integrations.html",
    "profile.html",
    "account-settings.html",
    "settings.html",
  ]);
  return allowed.has(next) ? `./${next}` : "./dashboard.html";
}

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const res = await fetch(`${getApiBase()}${path}`, { ...options, headers });
  const text = await res.text();
  let data = text;
  try { data = JSON.parse(text); } catch (_) {}
  if (!res.ok) throw new Error(`${res.status} ${pretty(data)}`);
  return data;
}

$("btnLogin").onclick = async () => {
  const out = $("outLogin");
  out.textContent = "Signing in...";
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
    if (!data?.access_token) throw new Error("Login succeeded but access_token missing.");
    setToken(data.access_token);
    window.location.href = nextPath();
  } catch (e) {
    const raw = String(e || "");
    const msg = cleanError(e);
    if (raw.includes("409") && raw.includes("Provide tenant_id")) {
      $("lgTenantIdRow").style.display = "grid";
      $("lgTenantId").focus();
    }
    out.textContent = msg;
  }
};

$("btnOnboardCreate").onclick = async () => {
  const out = $("outOnboardCreate");
  out.textContent = "Creating account...";
  try {
    const body = {
      tenant_name: $("obTenantName").value.trim(),
      admin_email: $("obAdminEmail").value.trim(),
      admin_password: $("obAdminPassword").value,
      compliance_level: "standard",
      bot_name: $("obBotName").value.trim() || "Main Website Bot",
      allowed_origins: parseOrigins($("obAllowedOrigins").value),
    };
    if (!body.tenant_name || !body.admin_email || !body.admin_password) {
      throw new Error("Provide tenant name, admin email, and password.");
    }
    const data = await api("/api/v1/tenant/onboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!data?.access_token) throw new Error("Account created but access_token missing.");
    setToken(data.access_token);
    window.location.href = nextPath();
  } catch (e) {
    out.textContent = cleanError(e);
  }
};

$("btnForgotPassword").onclick = async () => {
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
    out.textContent = cleanError(e);
  }
};

$("btnResetPassword").onclick = async () => {
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
    out.textContent = cleanError(e);
  }
};

$("btnEnvProd").onclick = () => {
  $("apiBase").value = "https://api.staunchbot.com";
  localStorage.setItem("tenant_console_api_base", $("apiBase").value);
};
$("btnEnvStaging").onclick = () => {
  $("apiBase").value = $("stagingApiBase").value.trim();
  localStorage.setItem("tenant_console_api_base", $("apiBase").value);
};
$("btnEnvLocal").onclick = () => {
  $("apiBase").value = "http://localhost:8000";
  localStorage.setItem("tenant_console_api_base", $("apiBase").value);
};

(function bootstrap() {
  const savedBase = localStorage.getItem("tenant_console_api_base");
  const savedStaging = localStorage.getItem("tenant_console_staging_api_base");
  const defaultStagingBase = "https://multi-tenant-ai-chatbot-platform-staging.up.railway.app";
  const host = String(window.location.hostname || "").toLowerCase();
  const isProdHost = (host === "www.staunchbot.com" || host === "staunchbot.com");
  const hostedDefaultBase = isProdHost ? "https://api.staunchbot.com" : "";
  if (savedBase) $("apiBase").value = savedBase;
  if (hostedDefaultBase && (!savedBase || /^https?:\/\/localhost(:\d+)?/i.test(savedBase))) {
    $("apiBase").value = hostedDefaultBase;
  }
  $("stagingApiBase").value = savedStaging || defaultStagingBase;
  if (isProdHost) {
    const panel = $("connectionPanel");
    if (panel) panel.style.display = "none";
  }
  const params = new URLSearchParams(window.location.search || "");
  const authRequired = params.get("auth_required");
  const resetToken = params.get("reset_token");
  if (resetToken) $("fpResetToken").value = resetToken;
  if (sessionStorage.getItem(SESSION_EXPIRED_KEY) === "1") {
    $("outLogin").textContent = "Session expired. Please sign in again.";
    sessionStorage.removeItem(SESSION_EXPIRED_KEY);
  } else if (authRequired === "1") {
    $("outLogin").textContent = "Sign in to continue.";
  }
})();

