const $ = (id) => document.getElementById(id);
const TOKEN_KEY = "tenant_console_token";
const SESSION_EXPIRED_KEY = "tenant_console_session_expired";

let accountCache = [];

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

function shortDate(v) {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString();
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
      $("navUserBadge").textContent = "Current User: not authenticated";
    }
    throw new Error(`${res.status} ${pretty(data)}`);
  }
  return data;
}

function integrationRow(title, payload) {
  const enabled = !!payload.enabled;
  const cls = enabled ? "enabled" : "disabled";
  const detail = payload.last_error
    ? `error: ${payload.last_error}`
    : `inbound ${shortDate(payload.last_webhook_at)} | outbound ${shortDate(payload.last_outbound_at)}`;
  return `
    <div class="status-card">
      <div class="status-head">
        <span>${title}</span>
        <span class="state ${cls}">${payload.status_label || (enabled ? "Enabled" : "Disabled")}</span>
      </div>
      <div class="muted">${detail}</div>
      <div class="muted">health=${payload.health_status || "-"} account=${payload.account_id || "-"}</div>
    </div>
  `;
}

function applyChannelDefaults(accounts) {
  const wa = accounts.find((a) => String(a.channel_type || "").toLowerCase() === "whatsapp");
  const fb = accounts.find((a) => {
    const t = String(a.channel_type || "").toLowerCase();
    return t === "facebook" || t === "messenger";
  });
  if (wa) {
    $("waName").value = wa.name || "";
    $("waPhoneNumberId").value = wa.phone_number_id || "";
    $("btnSaveWhatsApp").setAttribute("data-account-id", wa.id || "");
    $("btnDisableWhatsApp").setAttribute("data-account-id", wa.id || "");
  } else {
    $("btnSaveWhatsApp").setAttribute("data-account-id", "");
    $("btnDisableWhatsApp").setAttribute("data-account-id", "");
  }
  if (fb) {
    $("fbName").value = fb.name || "";
    $("fbPageId").value = fb.page_id || "";
    $("btnSaveFacebook").setAttribute("data-account-id", fb.id || "");
    $("btnDisableFacebook").setAttribute("data-account-id", fb.id || "");
  } else {
    $("btnSaveFacebook").setAttribute("data-account-id", "");
    $("btnDisableFacebook").setAttribute("data-account-id", "");
  }
}

async function loadAccounts() {
  try {
    const rows = await api("/api/v1/admin/channels/accounts");
    accountCache = Array.isArray(rows) ? rows : [];
    applyChannelDefaults(accountCache);
  } catch (_) {
    accountCache = [];
  }
  return accountCache;
}

async function loadStatus() {
  const out = $("outStatus");
  out.textContent = "Loading integration status...";
  try {
    const status = await api("/api/v1/tenant/integrations/status");
    const grid = $("statusGrid");
    grid.innerHTML = [
      integrationRow("Website Live Chat", status.website_live_chat || {}),
      integrationRow("WhatsApp Business", status.whatsapp_business || {}),
      integrationRow("Facebook Messenger", status.facebook_messenger || {}),
      integrationRow("Instagram", status.instagram || {}),
      integrationRow("Telegram", status.telegram || {}),
    ].join("");
    out.textContent = pretty(status);
    await loadAccounts();
    return status;
  } catch (e) {
    out.textContent = String(e);
    throw e;
  }
}

async function loadHealth() {
  const out = $("outStatus");
  out.textContent = "Loading channel health...";
  try {
    const rows = await loadAccounts();
    const health = [];
    for (const row of rows) {
      const data = await api(`/api/v1/admin/channels/accounts/${encodeURIComponent(row.id)}/health`);
      health.push(data);
    }
    out.textContent = pretty({ count: health.length, items: health });
    await loadStatus();
  } catch (e) {
    out.textContent = String(e);
  }
}

async function saveWhatsApp() {
  const out = $("outWhatsApp");
  out.textContent = "Saving WhatsApp...";
  try {
    const name = $("waName").value.trim() || "WhatsApp Main";
    const accessToken = $("waAccessToken").value.trim();
    const phoneNumberId = $("waPhoneNumberId").value.trim();
    const appSecret = $("waAppSecret").value.trim();
    if (!accessToken || accessToken.length < 8) throw new Error("Provide valid WhatsApp access token.");
    if (!phoneNumberId || phoneNumberId.length < 3) throw new Error("Provide valid WhatsApp phone number ID.");

    const accountId = $("btnSaveWhatsApp").getAttribute("data-account-id") || "";
    let data;
    if (accountId) {
      data = await api(`/api/v1/admin/channels/accounts/${encodeURIComponent(accountId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          access_token: accessToken,
          app_secret: appSecret || undefined,
          phone_number_id: phoneNumberId,
          is_active: true,
        }),
      });
    } else {
      data = await api("/api/v1/admin/channels/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel_type: "whatsapp",
          name,
          access_token: accessToken,
          app_secret: appSecret || undefined,
          phone_number_id: phoneNumberId,
        }),
      });
    }
    out.textContent = pretty({ saved: true, account: data });
    await loadStatus();
  } catch (e) {
    out.textContent = String(e);
  }
}

async function saveFacebook() {
  const out = $("outFacebook");
  out.textContent = "Saving Facebook...";
  try {
    const name = $("fbName").value.trim() || "Facebook Main";
    const accessToken = $("fbAccessToken").value.trim();
    const pageId = $("fbPageId").value.trim();
    const appSecret = $("fbAppSecret").value.trim();
    if (!accessToken || accessToken.length < 8) throw new Error("Provide valid Facebook page token.");
    if (!pageId || pageId.length < 3) throw new Error("Provide valid Facebook page ID.");

    const accountId = $("btnSaveFacebook").getAttribute("data-account-id") || "";
    let data;
    if (accountId) {
      data = await api(`/api/v1/admin/channels/accounts/${encodeURIComponent(accountId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          access_token: accessToken,
          app_secret: appSecret || undefined,
          page_id: pageId,
          is_active: true,
        }),
      });
    } else {
      data = await api("/api/v1/admin/channels/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel_type: "facebook",
          name,
          access_token: accessToken,
          app_secret: appSecret || undefined,
          page_id: pageId,
        }),
      });
    }
    out.textContent = pretty({ saved: true, account: data });
    await loadStatus();
  } catch (e) {
    out.textContent = String(e);
  }
}

async function disableChannel(accountId, outId, label) {
  const out = $(outId);
  out.textContent = `Disconnecting ${label}...`;
  try {
    if (!accountId) throw new Error(`No ${label} account configured.`);
    const data = await api(`/api/v1/admin/channels/accounts/${encodeURIComponent(accountId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: false }),
    });
    out.textContent = pretty({ disconnected: true, account: data.id });
    await loadStatus();
  } catch (e) {
    out.textContent = String(e);
  }
}

async function testInbound(kind) {
  const out = kind === "whatsapp" ? $("outWhatsApp") : $("outFacebook");
  out.textContent = `Sending ${kind} test inbound event...`;
  try {
    const rows = await loadAccounts();
    if (kind === "whatsapp") {
      const wa = rows.find((a) => String(a.channel_type || "").toLowerCase() === "whatsapp");
      if (!wa || !wa.phone_number_id) throw new Error("No configured WhatsApp account with phone_number_id.");
      const payload = {
        object: "whatsapp_business_account",
        entry: [{
          id: "test_entry",
          changes: [{
            field: "messages",
            value: {
              metadata: { phone_number_id: wa.phone_number_id },
              messages: [{
                from: `test_user_${Date.now()}`,
                type: "text",
                text: { body: "Hello from integration smoke test" },
              }],
            },
          }],
        }],
      };
      const res = await api("/api/v1/channels/meta/webhook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      out.textContent = pretty({ tested: "whatsapp", webhook_result: res });
    } else {
      const fb = rows.find((a) => {
        const t = String(a.channel_type || "").toLowerCase();
        return (t === "facebook" || t === "messenger") && a.page_id;
      });
      if (!fb || !fb.page_id) throw new Error("No configured Facebook/Messenger account with page_id.");
      const payload = {
        object: "page",
        entry: [{
          id: "test_entry",
          messaging: [{
            sender: { id: `test_user_${Date.now()}` },
            recipient: { id: fb.page_id },
            message: { text: "Hello from integration smoke test" },
          }],
        }],
      };
      const res = await api("/api/v1/channels/meta/webhook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      out.textContent = pretty({ tested: "facebook", webhook_result: res });
    }
    await loadStatus();
  } catch (e) {
    out.textContent = String(e);
  }
}

async function login() {
  const out = $("outSession");
  out.textContent = "Logging in...";
  try {
    const body = { email: $("lgEmail").value.trim(), password: $("lgPassword").value };
    const tenantId = $("lgTenantId").value.trim();
    if (tenantId) body.tenant_id = tenantId;
    const data = await api("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (data.access_token) {
      setToken(data.access_token);
      saveSessionToken(data.access_token);
    }
    $("lgTenantIdRow").style.display = "none";
    $("lgTenantId").value = "";
    const me = await api("/api/v1/auth/me");
    $("navUserBadge").textContent = `Current User: ${me.email} | role=${me.role} | tenant=${me.tenant_id}`;
    out.textContent = `Login successful for ${body.email}.`;
    await loadStatus();
  } catch (e) {
    const msg = String(e);
    if (msg.includes("409") && msg.includes("Provide tenant_id")) {
      $("lgTenantIdRow").style.display = "grid";
      $("lgTenantId").focus();
    }
    out.textContent = msg;
  }
}

$("btnLoadStatus").onclick = () => loadStatus();
$("btnLoadHealth").onclick = () => loadHealth();
$("btnSaveWhatsApp").onclick = () => saveWhatsApp();
$("btnSaveFacebook").onclick = () => saveFacebook();
$("btnDisableWhatsApp").onclick = () => disableChannel($("btnDisableWhatsApp").getAttribute("data-account-id") || "", "outWhatsApp", "WhatsApp");
$("btnDisableFacebook").onclick = () => disableChannel($("btnDisableFacebook").getAttribute("data-account-id") || "", "outFacebook", "Facebook");
$("btnTestWhatsApp").onclick = () => testInbound("whatsapp");
$("btnTestFacebook").onclick = () => testInbound("facebook");
$("btnLogin").onclick = () => login();
$("btnLoadBots").onclick = async () => {
  const out = $("outWebsite");
  out.textContent = "Loading bots...";
  try {
    const bots = await api("/api/v1/tenant/bots");
    out.textContent = pretty({ count: Array.isArray(bots) ? bots.length : 0, bots });
  } catch (e) {
    out.textContent = String(e);
  }
};
$("btnOpenOps").onclick = () => { window.location.href = "./tenant-console.html"; };
$("btnEnvProd").onclick = () => {
  $("apiBase").value = "https://api.staunchbot.com";
  localStorage.setItem("tenant_console_api_base", $("apiBase").value);
};
$("btnEnvLocal").onclick = () => {
  $("apiBase").value = "http://localhost:8000";
  localStorage.setItem("tenant_console_api_base", $("apiBase").value);
};
$("saveToken").onclick = () => {
  saveSessionToken($("accessToken").value);
  localStorage.setItem("tenant_console_api_base", $("apiBase").value);
};
$("clearToken").onclick = () => {
  saveSessionToken("");
  setToken("");
  $("navUserBadge").textContent = "Current User: not authenticated";
  $("outSession").textContent = "Token cleared.";
};
$("btnNavSignOut").onclick = () => {
  saveSessionToken("");
  setToken("");
  $("navUserBadge").textContent = "Current User: not authenticated";
  $("outSession").textContent = "Signed out.";
};

(async function bootstrap() {
  const savedToken = sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
  const savedBase = localStorage.getItem("tenant_console_api_base");
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
  if (sessionStorage.getItem(SESSION_EXPIRED_KEY) === "1") {
    $("outSession").textContent = "Session expired. Please sign in again.";
    sessionStorage.removeItem(SESSION_EXPIRED_KEY);
  }
  try {
    const me = await api("/api/v1/auth/me");
    $("navUserBadge").textContent = `Current User: ${me.email} | role=${me.role} | tenant=${me.tenant_id}`;
  } catch (_) {}
  loadStatus().catch(() => {});
})();
