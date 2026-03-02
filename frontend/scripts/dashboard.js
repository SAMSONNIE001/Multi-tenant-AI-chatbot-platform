const $ = (id) => document.getElementById(id);

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

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token.replace(/^Bearer\s+/i, "")}`;
  const res = await fetch(`${getApiBase()}${path}`, { ...options, headers });
  const text = await res.text();
  let data = text;
  try { data = JSON.parse(text); } catch (_) {}
  if (!res.ok) throw new Error(`${res.status} ${pretty(data)}`);
  return data;
}

function setApiBase(url) {
  const v = String(url || "").trim();
  if (!v) return;
  $("apiBase").value = v;
  localStorage.setItem("dashboard_api_base", v);
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
      `Status refreshed at: ${new Date().toLocaleString()}`,
      `Tenant: ${me.tenant_id || "-"}`,
      `Role: ${me.role || "-"}`,
      `Bots configured: ${Array.isArray(bots) ? bots.length : 0}`,
      `Knowledge docs/chunks: ${knowledge.document_count || 0} / ${knowledge.chunk_count || 0}`,
      `Handoffs: all=${totals.all_tickets ?? 0}, unresolved=${totals.unresolved_tickets ?? 0}, escalated=${totals.escalated_tickets ?? 0}`,
    ].join("\n");
  } catch (e) {
    out.textContent = String(e);
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
    if (data && data.access_token) setToken(data.access_token);
    $("lgTenantIdRow").style.display = "none";
    $("lgTenantId").value = "";
    out.textContent = pretty(data);
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
  localStorage.setItem("dashboard_token", $("accessToken").value);
  localStorage.setItem("dashboard_api_base", $("apiBase").value);
  localStorage.setItem("dashboard_staging_api_base", $("stagingApiBase").value);
};
$("clearToken").onclick = () => {
  localStorage.removeItem("dashboard_token");
  setToken("");
  renderWhoamiLine(null);
  $("outSnapshot").textContent = "Signed out. Login to load tenant snapshot.";
  $("kpiGrid").style.display = "none";
  $("kpiGrid").innerHTML = "";
};
const navDashboard = $("navDashboard");
const navOps = $("navOps");
const navSetup = $("navSetup");
if (navDashboard) navDashboard.classList.add("active");
if (navOps) navOps.classList.remove("active");
if (navSetup) navSetup.classList.remove("active");
const btnNavSignOut = $("btnNavSignOut");
if (btnNavSignOut) {
  btnNavSignOut.onclick = () => {
    localStorage.removeItem("dashboard_token");
    setToken("");
    renderWhoamiLine(null);
    $("outLogin").textContent = "Signed out.";
    $("outSnapshot").textContent = "Signed out. Login to load tenant snapshot.";
    $("kpiGrid").style.display = "none";
    $("kpiGrid").innerHTML = "";
  };
}

(function bootstrap() {
  const savedToken = localStorage.getItem("dashboard_token");
  const savedBase = localStorage.getItem("dashboard_api_base");
  const savedStaging = localStorage.getItem("dashboard_staging_api_base");
  if (savedToken) setToken(savedToken);
  if (savedBase) $("apiBase").value = savedBase;
  if (savedStaging) $("stagingApiBase").value = savedStaging;
  refreshSnapshot().catch(() => {});
})();
