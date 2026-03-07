const $ = (id) => document.getElementById(id);
const TOKEN_KEY = "tenant_console_token";
const SESSION_EXPIRED_KEY = "tenant_console_session_expired";
const COMPANY_ASSISTANT_KEY = "staunchbot_company_assistant_bot_id";
const MAX_LOGIN_TRIALS = 3;
let loginFailures = 0;

function notify(message) {
  const text = String(message || "").trim();
  if (!text) return;
  const n = document.createElement("div");
  n.textContent = text;
  n.setAttribute("role", "status");
  n.style.position = "fixed";
  n.style.top = "18px";
  n.style.right = "18px";
  n.style.maxWidth = "360px";
  n.style.padding = "10px 12px";
  n.style.borderRadius = "10px";
  n.style.background = "#132748";
  n.style.color = "#fff";
  n.style.fontSize = "13px";
  n.style.fontWeight = "600";
  n.style.boxShadow = "0 10px 24px rgba(9, 20, 39, 0.25)";
  n.style.zIndex = "9999";
  document.body.appendChild(n);
  window.setTimeout(() => n.remove(), 3800);
}

function pretty(v) {
  try { return JSON.stringify(v, null, 2); } catch (_) { return String(v); }
}

function cleanError(e) {
  const raw = String(e || "Request failed");
  if (raw.includes("429")) return "Too many failed attempts. Your login is temporarily blocked. Reset your password to continue.";
  if (raw.includes("401")) return "Invalid email or password.";
  if (raw.includes("403")) return "You do not have permission to perform this action.";
  if (raw.includes("404")) return "Requested resource was not found.";
  if (raw.includes("409") && raw.includes("Provide tenant_id")) return "This email belongs to multiple tenants. Enter Tenant ID and try again.";
  if (raw.includes("422")) return "Some fields are invalid. Check your inputs and try again.";
  if (raw.includes("500")) return "Server error. Please try again in a moment.";
  return raw.replace(/^\d+\s+/, "").slice(0, 220);
}

function isSafePasswordInput(value) {
  const text = String(value || "");
  const bytes = new TextEncoder().encode(text).length;
  if (bytes > 72) return { ok: false, message: "Password is too long (max 72 bytes)." };
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    if (code < 32 || code === 127) {
      return { ok: false, message: "Password contains unsupported control characters." };
    }
  }
  return { ok: true, message: "" };
}

function getApiBase() {
  return $("apiBase").value.trim().replace(/\/+$/, "");
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

async function requestResetFromLoginContext() {
  const email = $("lgEmail").value.trim();
  const tenantId = $("lgTenantId").value.trim();
  if (!email) {
    notify("Enter your email and use Forgot Password.");
    return;
  }
  $("fpEmail").value = email;
  if (tenantId) $("fpTenantId").value = tenantId;
  await $("btnForgotPassword").onclick();
}

$("btnLogin").onclick = async () => {
  const out = $("outLogin");
  out.textContent = "Signing in...";
  try {
    const password = $("lgPassword").value;
    const passwordCheck = isSafePasswordInput(password);
    if (!passwordCheck.ok) throw new Error(passwordCheck.message);
    const body = {
      email: $("lgEmail").value.trim(),
      password,
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
    loginFailures = 0;
    window.location.href = nextPath();
  } catch (e) {
    const raw = String(e || "");
    const msg = cleanError(e);
    if (raw.includes("409") && raw.includes("Provide tenant_id")) {
      $("lgTenantIdRow").style.display = "grid";
      $("lgTenantId").focus();
    }
    if (raw.includes("401")) {
      loginFailures += 1;
      notify(`Wrong password (${loginFailures}/${MAX_LOGIN_TRIALS}).`);
      if (loginFailures >= MAX_LOGIN_TRIALS) {
        notify("3 failed attempts reached. Sending reset link + code.");
        await requestResetFromLoginContext();
      }
    } else if (raw.includes("429")) {
      notify("Account temporarily blocked. Sending reset link + code.");
      await requestResetFromLoginContext();
    }
    out.textContent = msg;
  }
};

$("btnOnboardCreate").onclick = async () => {
  const out = $("outOnboardCreate");
  out.textContent = "Creating account...";
  try {
    const password = $("obAdminPassword").value;
    const passwordCheck = isSafePasswordInput(password);
    if (!passwordCheck.ok) throw new Error(passwordCheck.message);
    const body = {
      tenant_name: $("obTenantName").value.trim(),
      admin_email: $("obAdminEmail").value.trim(),
      admin_password: password,
      compliance_level: "standard",
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
    if (data?.bot_id) {
      localStorage.setItem(COMPANY_ASSISTANT_KEY, String(data.bot_id));
    }
    window.location.href = nextPath();
  } catch (e) {
    const msg = cleanError(e);
    out.textContent = msg;
    notify(msg);
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
    notify("If this account exists, reset email was sent.");
  } catch (e) {
    const msg = cleanError(e);
    out.textContent = msg;
    notify(msg);
  }
};

$("btnResetPassword").onclick = async () => {
  const out = $("outResetPassword");
  out.textContent = "Resetting password...";
  try {
    const newPassword = $("fpNewPassword").value;
    const passwordCheck = isSafePasswordInput(newPassword);
    if (!passwordCheck.ok) throw new Error(passwordCheck.message);
    const code = $("fpCode").value.trim();
    if (!/^\d{6}$/.test(code)) throw new Error("Reset code must be exactly 6 digits.");
    const resetToken = $("fpResetToken").value.trim();
    const email = $("fpEmail").value.trim();
    const tenantId = $("fpTenantId").value.trim();
    const payload = {
      code,
      new_password: newPassword,
    };
    if (resetToken) payload.reset_token = resetToken;
    if (email) payload.email = email;
    if (tenantId) payload.tenant_id = tenantId;
    const data = await api("/api/v1/auth/password/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    out.textContent = data.message || "Password reset successful.";
    notify("Password reset successful. Sign in with your new password.");
    loginFailures = 0;
  } catch (e) {
    const msg = cleanError(e);
    out.textContent = msg;
    notify(msg);
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
  const setupPasswordToggle = (checkboxId, inputId) => {
    const checkbox = $(checkboxId);
    const input = $(inputId);
    if (!checkbox || !input) return;
    checkbox.addEventListener("change", () => {
      input.type = checkbox.checked ? "text" : "password";
    });
  };
  setupPasswordToggle("lgShowPassword", "lgPassword");
  setupPasswordToggle("fpShowPassword", "fpNewPassword");
  setupPasswordToggle("obShowPassword", "obAdminPassword");

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
