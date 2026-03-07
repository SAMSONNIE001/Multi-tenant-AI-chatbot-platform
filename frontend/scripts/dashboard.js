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

function parseOrigins(s) {
  return String(s || "")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function initDashboardSearch() {
  const input = $("dashboardSearchInput");
  const suggest = $("dashboardSearchSuggest");
  if (!input || !suggest) return;

  const items = [
    { label: "Dashboard", action: () => { window.location.href = "./dashboard.html"; } },
    { label: "Profile", action: () => { window.location.href = "./profile.html"; } },
    { label: "Settings", action: () => { window.location.href = "./settings.html"; } },
    { label: "Integrations", action: () => { window.location.href = "./integrations.html"; } },
    { label: "Knowledge Base", action: () => { window.location.href = "./tenant-setup.html"; } },
    { label: "Unified Inbox", action: () => { window.location.href = "./tenant-console.html"; } },
    { label: "Release", action: () => { window.location.href = "./release-checklist.html"; } },
    { label: "Refresh Snapshot", action: () => { $("btnRefreshAll")?.click(); } },
    { label: "Sign Out", action: () => { $("btnNavSignOut")?.click(); } },
    { label: "Open Daily Ops", action: () => { window.location.href = "./tenant-console.html"; } },
  ];

  let filtered = items.slice();
  let activeIndex = -1;

  function closeSuggest() {
    suggest.classList.remove("open");
    suggest.innerHTML = "";
    activeIndex = -1;
  }

  function doSelect(idx) {
    if (idx < 0 || idx >= filtered.length) return;
    const picked = filtered[idx];
    input.value = picked.label;
    closeSuggest();
    picked.action();
  }

  function renderSuggest(list) {
    filtered = list.slice(0, 8);
    if (!filtered.length) {
      closeSuggest();
      return;
    }
    suggest.innerHTML = filtered
      .map((it, i) => `<button type="button" class="search-item${i === activeIndex ? " active" : ""}" data-idx="${i}">${it.label}</button>`)
      .join("");
    suggest.classList.add("open");
  }

  function runFilter() {
    const q = String(input.value || "").trim().toLowerCase();
    activeIndex = -1;
    if (!q) {
      renderSuggest(items);
      return;
    }
    renderSuggest(items.filter((it) => it.label.toLowerCase().includes(q)));
  }

  input.addEventListener("focus", runFilter);
  input.addEventListener("input", runFilter);
  input.addEventListener("keydown", (e) => {
    if (!suggest.classList.contains("open")) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, filtered.length - 1);
      renderSuggest(filtered);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      renderSuggest(filtered);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0) {
        doSelect(activeIndex);
      } else if (filtered.length) {
        doSelect(0);
      }
      return;
    }
    if (e.key === "Escape") {
      closeSuggest();
    }
  });

  suggest.addEventListener("click", (e) => {
    const btn = e.target.closest(".search-item");
    if (!btn) return;
    const idx = Number(btn.getAttribute("data-idx"));
    doSelect(idx);
  });

  document.addEventListener("click", (e) => {
    if (e.target === input || suggest.contains(e.target)) return;
    closeSuggest();
  });
}

function setAuthState(isAuthed) {
  const banner = $("authBanner");
  const signInPanel = $("signInPanel");
  if (!banner) return;
  banner.textContent = isAuthed
    ? "Authenticated. Dashboard shows your live tenant metrics."
    : "Sign in to load live tenant metrics and integration activity.";
  if (signInPanel) {
    signInPanel.style.display = isAuthed ? "none" : "block";
  }
}

function setHeroKpis(values) {
  const v = values || {};
  $("kpiOpenTickets").textContent = String(v.open ?? "-");
  $("kpiPendingCustomer").textContent = String(v.pending ?? "-");
  $("kpiSlaBreaches").textContent = String(v.breaches ?? "-");
  $("kpiResolvedToday").textContent = String(v.resolvedToday ?? "-");
  $("kpiNewTickets").textContent = String(v.newTickets ?? "-");
}

function getNextPathFromQuery() {
  const params = new URLSearchParams(window.location.search || "");
  const next = String(params.get("next") || "").trim();
  if (!next) return "";
  const allowed = new Set([
    "tenant-console.html",
    "tenant-setup.html",
    "integrations.html",
    "release-checklist.html",
  ]);
  return allowed.has(next) ? `./${next}` : "";
}

function redirectToNextIfPresent() {
  const nextPath = getNextPathFromQuery();
  if (nextPath) {
    window.location.href = nextPath;
    return true;
  }
  return false;
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
    line.textContent = "Session: Not signed in";
    if (nav) nav.textContent = "Not signed in";
    return;
  }
  line.textContent = "Session: Signed in";
  if (nav) nav.textContent = "Signed in";
}

function setIntegrationState(id, enabled, enabledText = "Connected", disabledText = "Not Connected") {
  const el = $(id);
  if (!el) return;
  el.className = `state ${enabled ? "enabled" : "disabled"}`;
  el.textContent = enabled ? enabledText : disabledText;
}

function setIntegrationMeta(id, text) {
  const el = $(id);
  if (!el) return;
  el.textContent = text || "-";
}

function shortDate(v) {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString();
}

function describeIntegration(channel) {
  if (!channel) return "-";
  if (channel.last_error) return `error: ${channel.last_error}`;
  if (channel.last_webhook_at || channel.last_outbound_at) {
    const inbound = channel.last_webhook_at ? shortDate(channel.last_webhook_at) : "-";
    const outbound = channel.last_outbound_at ? shortDate(channel.last_outbound_at) : "-";
    return `inbound ${inbound} | outbound ${outbound}`;
  }
  return channel.note || channel.health_status || "-";
}

function renderInboxPreview(metrics) {
  const box = $("inboxPreview");
  if (!box) return;
  const totals = (metrics && metrics.totals) || {};
  const rows = [
    ["Open Queue", totals.unresolved_tickets ?? 0, "Live unresolved tickets"],
    ["Escalated", totals.escalated_tickets ?? 0, "Tickets currently escalated"],
    ["Resolved", totals.resolved_tickets ?? 0, "Resolved in current reporting window"],
  ];
  box.innerHTML = rows
    .map(
      ([title, value, note]) => `
      <div class="ticket-row">
        <div>
          <strong>${title}</strong>
          <div class="tiny">${note}</div>
        </div>
        <span class="tiny">${value}</span>
      </div>
    `
    )
    .join("");
}

async function refreshIntegrationStatus() {
  const sync = $("integrationSync");
  if (sync) sync.textContent = "Syncing...";
  if (!getToken()) {
    setIntegrationState("intWebsiteState", false, "Enabled", "Sign In Required");
    setIntegrationState("intWhatsappState", false, "Enabled", "Sign In Required");
    setIntegrationState("intMessengerState", false, "Enabled", "Sign In Required");
    setIntegrationState("intInstagramState", false, "Enabled", "Coming Soon");
    setIntegrationMeta("intWebsiteMeta", "Sign in to view live status");
    setIntegrationMeta("intWhatsappMeta", "Sign in to view live status");
    setIntegrationMeta("intMessengerMeta", "Sign in to view live status");
    setIntegrationMeta("intInstagramMeta", "Coming soon");
    if (sync) sync.textContent = "Sign in required";
    return;
  }
  try {
    const data = await api("/api/v1/tenant/integrations/status");
    const website = data.website_live_chat || {};
    const whatsapp = data.whatsapp_business || {};
    const messenger = data.facebook_messenger || {};
    const instagram = data.instagram || {};

    setIntegrationState("intWebsiteState", !!website.enabled, website.status_label || "Enabled", "Not Configured");
    setIntegrationMeta("intWebsiteMeta", describeIntegration(website));

    setIntegrationState("intWhatsappState", !!whatsapp.enabled, whatsapp.status_label || "Enabled", "Not Connected");
    setIntegrationMeta("intWhatsappMeta", describeIntegration(whatsapp));

    setIntegrationState("intMessengerState", !!messenger.enabled, messenger.status_label || "Enabled", "Not Connected");
    setIntegrationMeta("intMessengerMeta", describeIntegration(messenger));

    setIntegrationState("intInstagramState", !!instagram.enabled, instagram.status_label || "Enabled", "Coming Soon");
    setIntegrationMeta("intInstagramMeta", describeIntegration(instagram));

    if (sync) sync.textContent = `Last sync: ${new Date().toLocaleTimeString()}`;
  } catch (_) {
    setIntegrationState("intWebsiteState", false, "Enabled", "Unavailable");
    setIntegrationState("intWhatsappState", false, "Enabled", "Unavailable");
    setIntegrationState("intMessengerState", false, "Enabled", "Unavailable");
    setIntegrationState("intInstagramState", false, "Enabled", "Coming Soon");
    setIntegrationMeta("intWebsiteMeta", "Unavailable");
    setIntegrationMeta("intWhatsappMeta", "Unavailable");
    setIntegrationMeta("intMessengerMeta", "Unavailable");
    setIntegrationMeta("intInstagramMeta", "Coming soon");
    if (sync) sync.textContent = "Integration status unavailable";
  }
}

async function refreshSnapshot() {
  const out = $("outSnapshot");
  out.textContent = "Refreshing...";
  const grid = $("kpiGrid");
  if (!getToken()) {
    renderWhoamiLine(null);
    setAuthState(false);
    setHeroKpis(null);
    grid.style.display = "none";
    grid.innerHTML = "";
    out.textContent = "Sign in to load tenant snapshot.";
    renderInboxPreview({ totals: { unresolved_tickets: 0, escalated_tickets: 0, resolved_tickets: 0 } });
    await refreshIntegrationStatus();
    return;
  }
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
    const today = new Date().toISOString().slice(0, 10);
    const todayRow = Array.isArray(metrics?.daily) ? metrics.daily.find((d) => d.day === today) : null;
    setAuthState(true);
    setHeroKpis({
      open: totals.unresolved_tickets ?? 0,
      pending: totals.unresolved_tickets ?? 0,
      breaches: metrics?.window_24h?.breached_tickets ?? 0,
      resolvedToday: todayRow?.tickets ?? 0,
      newTickets: metrics?.window_24h?.total_tickets ?? 0,
    });
    out.textContent = [
      `Snapshot updated ${new Date().toLocaleString()}`,
      `Tenant ${me.tenant_id || "-"} (${me.role || "-"})`,
      `Handoffs: ${totals.unresolved_tickets ?? 0} unresolved, ${totals.escalated_tickets ?? 0} escalated`,
      `Knowledge: ${knowledge.document_count || 0} docs / ${knowledge.chunk_count || 0} chunks`,
    ].join("\n");
    renderInboxPreview(metrics);
    await refreshIntegrationStatus();
  } catch (e) {
    const msg = String(e);
    if (msg.includes("401")) {
      out.textContent = "Sign in to load snapshot.";
    } else {
      out.textContent = msg;
    }
    grid.style.display = "none";
    grid.innerHTML = "";
    setAuthState(false);
    setHeroKpis(null);
    renderInboxPreview({ totals: { unresolved_tickets: 0, escalated_tickets: 0, resolved_tickets: 0 } });
    await refreshIntegrationStatus();
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
    if (redirectToNextIfPresent()) return;
    await refreshSnapshot();
    await refreshIntegrationStatus();
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
  setAuthState(false);
  setHeroKpis(null);
  refreshIntegrationStatus().catch(() => {});
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
    setAuthState(false);
    setHeroKpis(null);
    refreshIntegrationStatus().catch(() => {});
  };
}

const btnOnboardCreate = $("btnOnboardCreate");
if (btnOnboardCreate) {
  btnOnboardCreate.onclick = async () => {
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
      if (data && data.access_token) {
        setToken(data.access_token);
        saveSessionToken(data.access_token);
      }
      $("lgEmail").value = body.admin_email;
      $("lgPassword").value = body.admin_password;
      out.textContent = `Account created.\nTenant: ${data?.tenant?.id || "-"}\nAdmin: ${data?.admin?.email || body.admin_email}`;
      if (redirectToNextIfPresent()) return;
      await refreshSnapshot();
      await refreshIntegrationStatus();
    } catch (e) {
      out.textContent = String(e);
    }
  };
}

(function bootstrap() {
  const savedToken = sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
  if (!savedToken) {
    window.location.replace("./auth.html?auth_required=1&next=dashboard.html");
    return;
  }
  const savedBase = localStorage.getItem("tenant_console_api_base");
  const savedStaging = localStorage.getItem("tenant_console_staging_api_base");
  const defaultStagingBase = "https://multi-tenant-ai-chatbot-platform-staging.up.railway.app";
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
  $("stagingApiBase").value = savedStaging || defaultStagingBase;
  if (sessionStorage.getItem(SESSION_EXPIRED_KEY) === "1") {
    $("outLogin").textContent = "Session expired. Please sign in again.";
    sessionStorage.removeItem(SESSION_EXPIRED_KEY);
  }
  const params = new URLSearchParams(window.location.search || "");
  const resetToken = params.get("reset_token");
  const authRequired = params.get("auth_required");
  const nextPath = getNextPathFromQuery();
  if (resetToken && $("fpResetToken")) $("fpResetToken").value = resetToken;
  if (authRequired === "1" && !savedToken) {
    const outLogin = $("outLogin");
    if (outLogin) outLogin.textContent = nextPath
      ? `Sign in to continue to ${nextPath.replace("./", "")}.`
      : "Sign in to continue.";
  }
  setHeroKpis(null);
  initDashboardSearch();
  setAuthState(!!savedToken);
  refreshIntegrationStatus().catch(() => {});
  refreshSnapshot().catch(() => {});
})();


