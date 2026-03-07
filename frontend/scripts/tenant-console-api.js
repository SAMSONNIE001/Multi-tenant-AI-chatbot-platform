    const $ = (id) => document.getElementById(id);
    let queueTimer = null;
    let lastReplyReview = null;
    let lastQueueItems = [];
    let lastProfiles = [];
    let lastSweepRun = null;
    let lastMergeRun = null;
    let lastPreflight = null;
    let lastAuditRefreshAt = null;
    let lastQaPack = null;
    let activePane = "daily";
    let roleMode = "operator";
    let currentUser = null;
    const TOKEN_KEY = "tenant_console_token";
    const SESSION_EXPIRED_KEY = "tenant_console_session_expired";

    function pretty(v) {
      try { return JSON.stringify(v, null, 2); } catch (_) { return String(v); }
    }

    function getApiBase() {
      return $("apiBase").value.trim().replace(/\/+$/, "");
    }

    function isProdApiBase() {
      const base = getApiBase();
      try {
        const host = new URL(base).hostname.toLowerCase();
        return host === "api.staunchbot.com"
          || host === "www.staunchbot.com"
          || host === "staunchbot.com"
          || host === "multi-tenant-ai-chatbot-platform-production.up.railway.app";
      } catch (_) {
        const raw = String(base || "").toLowerCase();
        return raw.includes("api.staunchbot.com")
          || raw.includes("www.staunchbot.com")
          || raw.includes("staunchbot.com")
          || raw.includes("multi-tenant-ai-chatbot-platform-production.up.railway.app");
      }
    }

    function isProdFrontendHost() {
      const host = String(window.location.hostname || "").toLowerCase();
      return host === "www.staunchbot.com" || host === "staunchbot.com";
    }

    function nowIso() {
      return new Date().toISOString();
    }

    function preflightAgeMin() {
      if (!lastPreflight || !lastPreflight.at) return null;
      const ms = Date.now() - new Date(lastPreflight.at).getTime();
      if (!Number.isFinite(ms)) return null;
      return Math.floor(ms / 60000);
    }

    function setChecklistBadge(id, state) {
      const el = $(id);
      if (!el) return;
      const next = String(state || "").toLowerCase();
      el.className = "badge";
      if (next === "pass") el.classList.add("pass");
      if (next === "fail") el.classList.add("fail");
      el.textContent = next || "pending";
    }

    function updateQaChecklist() {
      if (!lastPreflight) setChecklistBadge("qaStepPreflight", "not run");
      else setChecklistBadge("qaStepPreflight", lastPreflight.critical_pass ? "pass" : "fail");

      if (!lastQaPack) setChecklistBadge("qaStepPack", "not run");
      else setChecklistBadge("qaStepPack", lastQaPack.ok ? "pass" : "fail");

      if (!lastSweepRun) setChecklistBadge("qaStepSweep", "pending");
      else setChecklistBadge("qaStepSweep", "pass");

      if (!lastMergeRun) setChecklistBadge("qaStepMerge", "pending");
      else setChecklistBadge("qaStepMerge", "pass");
    }

    function applyConsoleMode() {
      const prodFrontend = isProdFrontendHost();
      const paneNodes = document.querySelectorAll("[data-pane]");
      paneNodes.forEach((node) => {
        const panes = String(node.getAttribute("data-pane") || "")
          .split(/\s+/)
          .filter(Boolean);
        if (prodFrontend && panes.includes("qa")) {
          node.style.display = "none";
          return;
        }
        node.style.display = panes.includes(activePane) ? "block" : "none";
      });

      const roleSelect = $("roleMode");
      roleMode = roleSelect ? String(roleSelect.value || "operator").toLowerCase() : "operator";
      const toggle = $("toggleAdvanced");
      if (toggle) {
        if (roleMode !== "admin") {
          toggle.checked = false;
        }
        toggle.disabled = roleMode !== "admin";
      }
      const showAdvanced = roleMode === "admin" && !!(toggle && toggle.checked);
      const advancedBlocks = document.querySelectorAll(".advanced-only");
      advancedBlocks.forEach((el) => {
        el.style.display = showAdvanced ? "block" : "none";
      });
      updateQaChecklist();
    }

    function setActivePane(pane) {
      const prodFrontend = isProdFrontendHost();
      if (prodFrontend && pane === "qa") {
        activePane = document.getElementById("tabSetup") ? "setup" : "daily";
      } else {
        activePane = pane;
      }
      const tabs = document.querySelectorAll(".tab-btn");
      tabs.forEach((btn) => btn.classList.remove("active"));
      const btn = document.querySelector(`.tab-btn[data-tab="${pane}"]`);
      if (btn) btn.classList.add("active");
      applyConsoleMode();
    }

    function renderReleaseSnapshot() {
      const grid = $("snapshotGrid");
      const out = $("outSnapshot");
      const mode = isProdApiBase() ? "production" : "staging_or_local";
      const pfAge = preflightAgeMin();
      const cards = [
        ["Mode", mode],
        ["API Base", getApiBase()],
        ["Preflight", lastPreflight ? (lastPreflight.critical_pass ? "pass" : "fail") : "not run"],
        ["Preflight Age (min)", pfAge == null ? "-" : pfAge],
        ["Last Sweep", lastSweepRun ? shortDate(lastSweepRun.at) : "never"],
        ["Last Merge", lastMergeRun ? shortDate(lastMergeRun.at) : "never"],
        ["Ops Audit Refresh", lastAuditRefreshAt ? shortDate(lastAuditRefreshAt) : "never"],
        ["Build", "customer-profiles + escalation-ops (2026-03-01)"],
      ];
      grid.style.display = "grid";
      grid.innerHTML = cards
        .map(([k, v]) => `<div class="kpi"><div class="k">${esc(k)}</div><div class="v" style="font-size:13px;">${esc(v)}</div></div>`)
        .join("");
      out.textContent = pretty({
        mode,
        api_base: getApiBase(),
        last_preflight: lastPreflight,
        last_sweep: lastSweepRun || null,
        last_merge: lastMergeRun || null,
        last_ops_audit_refresh: lastAuditRefreshAt,
      });
    }

    function safeJwtField(index) {
      const token = getToken().replace(/^Bearer\s+/i, "");
      const parts = token.split(".");
      if (parts.length < 2) return null;
      try {
        const b64 = parts[index].replace(/-/g, "+").replace(/_/g, "/");
        const json = atob(b64);
        return JSON.parse(json);
      } catch (_) {
        return null;
      }
    }

    function currentActorId() {
      const claims = safeJwtField(1) || {};
      return claims.sub || claims.email || "unknown_actor";
    }

    function isBackendAdminLike() {
      const role = String((currentUser && currentUser.role) || "").toLowerCase();
      return role === "admin" || role === "owner";
    }

    function renderCurrentUserBadge() {
      const el = $("currentUserBadge");
      if (!el) return;
      if (!currentUser) {
        el.textContent = "Current User: not authenticated";
        return;
      }
      el.textContent = `Current User: ${currentUser.email || "-"} | role=${currentUser.role || "-"} | tenant=${currentUser.tenant_id || "-"}`;
    }

    function _setIntegrationState(id, enabled, enabledText = "Enabled", disabledText = "Not Connected") {
      const el = $(id);
      if (!el) return;
      el.className = `state ${enabled ? "enabled" : "disabled"}`;
      el.textContent = enabled ? enabledText : disabledText;
    }

    function _setIntegrationMeta(id, text) {
      const el = $(id);
      if (!el) return;
      el.textContent = text || "-";
    }

    function _integrationDetail(channel) {
      if (!channel) return "-";
      if (channel.last_error) return `error: ${channel.last_error}`;
      if (channel.last_webhook_at || channel.last_outbound_at) {
        const inbound = channel.last_webhook_at ? shortDate(channel.last_webhook_at) : "-";
        const outbound = channel.last_outbound_at ? shortDate(channel.last_outbound_at) : "-";
        return `inbound ${inbound} | outbound ${outbound}`;
      }
      return channel.note || channel.health_status || "-";
    }

    async function syncChannelIntegrations() {
      const sync = $("integrationSync");
      if (sync) sync.textContent = "Syncing configured channels from backend...";
      if (!getToken()) {
        _setIntegrationState("intWebsiteState", false, "Enabled", "Sign In Required");
        _setIntegrationState("intWhatsappState", false, "Enabled", "Sign In Required");
        _setIntegrationState("intMessengerState", false, "Enabled", "Sign In Required");
        _setIntegrationState("intInstagramState", false, "Enabled", "Coming Soon");
        _setIntegrationMeta("intWebsiteMeta", "Sign in to view live status");
        _setIntegrationMeta("intWhatsappMeta", "Sign in to view live status");
        _setIntegrationMeta("intMessengerMeta", "Sign in to view live status");
        _setIntegrationMeta("intInstagramMeta", "Coming soon");
        if (sync) sync.textContent = "Sign in required";
        return;
      }
      try {
        const data = await request("/api/v1/tenant/integrations/status");
        state.integrationStatus = data;
        const website = data.website_live_chat || {};
        const whatsapp = data.whatsapp_business || {};
        const messenger = data.facebook_messenger || {};
        const instagram = data.instagram || {};

        _setIntegrationState("intWebsiteState", !!website.enabled, website.status_label || "Enabled", "Not Configured");
        _setIntegrationState("intWhatsappState", !!whatsapp.enabled, whatsapp.status_label || "Enabled", "Not Connected");
        _setIntegrationState("intMessengerState", !!messenger.enabled, messenger.status_label || "Enabled", "Not Connected");
        _setIntegrationState("intInstagramState", !!instagram.enabled, instagram.status_label || "Enabled", "Coming Soon");
        _setIntegrationMeta("intWebsiteMeta", _integrationDetail(website));
        _setIntegrationMeta("intWhatsappMeta", _integrationDetail(whatsapp));
        _setIntegrationMeta("intMessengerMeta", _integrationDetail(messenger));
        _setIntegrationMeta("intInstagramMeta", _integrationDetail(instagram));
        if (sync) sync.textContent = `Last sync: ${new Date().toLocaleTimeString()}`;
      } catch (_) {
        _setIntegrationState("intWebsiteState", false, "Enabled", "Unavailable");
        _setIntegrationState("intWhatsappState", false, "Enabled", "Unavailable");
        _setIntegrationState("intMessengerState", false, "Enabled", "Unavailable");
        _setIntegrationState("intInstagramState", false, "Enabled", "Coming Soon");
        _setIntegrationMeta("intWebsiteMeta", "Unavailable");
        _setIntegrationMeta("intWhatsappMeta", "Unavailable");
        _setIntegrationMeta("intMessengerMeta", "Unavailable");
        _setIntegrationMeta("intInstagramMeta", "Coming soon");
        if (sync) sync.textContent = "Could not sync channel status";
      }
    }

    function appendOpsAuditLocal(entry) {
      try {
        const raw = localStorage.getItem("tenant_console_ops_audit");
        const parsed = JSON.parse(raw || "[]");
        const list = Array.isArray(parsed) ? parsed : [];
        list.unshift(entry);
        const trimmed = list.slice(0, 100);
        localStorage.setItem("tenant_console_ops_audit", JSON.stringify(trimmed));
      } catch (_) {}
    }

    async function appendOpsAudit(entry) {
      appendOpsAuditLocal(entry);
      try {
        await request("/api/v1/admin/ops/audit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action_type: entry.operation || "unknown",
            reason: entry.reason || "no_reason",
            metadata_json: entry,
          }),
        });
      } catch (_) {
        // Keep local fallback if backend endpoint is unavailable.
      }
    }

    async function loadOpsAudit() {
      const out = $("outOpsAudit");
      try {
        const data = await request("/api/v1/admin/ops/audit?limit=50&offset=0");
        lastAuditRefreshAt = nowIso();
        out.textContent = pretty({ source: "backend", count: data.count, items: data.entries || [] });
        renderReleaseSnapshot();
        return;
      } catch (_) {
        // Fallback to local cache.
      }
      try {
        const raw = localStorage.getItem("tenant_console_ops_audit");
        const parsed = JSON.parse(raw || "[]");
        const list = Array.isArray(parsed) ? parsed : [];
        lastAuditRefreshAt = nowIso();
        out.textContent = pretty({ source: "local_fallback", count: list.length, items: list.slice(0, 25) });
        renderReleaseSnapshot();
      } catch (e) {
        out.textContent = String(e);
      }
    }

    function switchApiBase(url) {
      const v = String(url || "").trim();
      if (!v) return;
      $("apiBase").value = v;
      localStorage.setItem("tenant_console_api_base", v);
      applyQaAvailability();
    }

    function requireReasonAndConfirm(reasonText, actionLabel) {
      const reason = String(reasonText || "").trim();
      if (reason.length < 8) {
        throw new Error("Provide a reason (at least 8 chars) before running this action.");
      }
      const ok = window.confirm(`${actionLabel}\n\nReason: ${reason}\n\nProceed?`);
      if (!ok) throw new Error("Action canceled by operator.");
      return reason;
    }

    function ensurePreflightForDestructive(actionLabel) {
      const age = preflightAgeMin();
      const fresh = age != null && age <= 30;
      const sameBase = !!(lastPreflight && lastPreflight.api_base === getApiBase());
      if (!lastPreflight || !sameBase || !fresh || !lastPreflight.critical_pass) {
        throw new Error(`Run Preflight Checks successfully (same API base, <=30min old) before: ${actionLabel}.`);
      }
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
      // Backward-compat cleanup from previous localStorage strategy.
      localStorage.removeItem(TOKEN_KEY);
    }

    function showSessionExpiredMessage() {
      const msg = "Session expired. Please sign in again.";
      const ids = ["outLogin", "outSnapshot", "outPreflight"];
      ids.forEach((id) => {
        const el = $(id);
        if (el) el.textContent = msg;
      });
    }

    function clearConsoleSession() {
      sessionStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_KEY);
      setToken("");
      currentUser = null;
      renderCurrentUserBadge();
    }

    async function request(path, options = {}) {
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
          clearConsoleSession();
          showSessionExpiredMessage();
        }
        const suffix = res.status === 403 ? " | Your role cannot run this action." : "";
        throw new Error(`${res.status} ${pretty(data)}${suffix}`);
      }
      return data;
    }

    async function syncCurrentUser() {
      const token = getToken();
      if (!token) {
        currentUser = null;
        renderCurrentUserBadge();
        return null;
      }
      try {
        const me = await request("/api/v1/auth/me");
        currentUser = me;
        const roleEl = $("roleMode");
        if (roleEl) {
          if (!isBackendAdminLike()) {
            roleEl.value = "operator";
            localStorage.setItem("tenant_console_role_mode", "operator");
          }
        }
        renderCurrentUserBadge();
        applyConsoleMode();
        await syncChannelIntegrations();
        return me;
      } catch (_) {
        currentUser = null;
        renderCurrentUserBadge();
        return null;
      }
    }

    async function runPreflightChecks(silent = false) {
      const out = $("outPreflight");
      if (!silent) out.textContent = "Running preflight checks...";
      const checks = [];
      const apiBase = getApiBase();
      const mode = isProdApiBase() ? "production" : "staging_or_local";

      const tokenPresent = !!getToken().trim();
      checks.push({
        name: "token_present",
        critical: true,
        ok: tokenPresent,
        detail: tokenPresent ? "access token set" : "missing access token",
      });

      try {
        await request("/api/v1/admin/handoff/metrics");
        checks.push({ name: "handoff_metrics", critical: true, ok: true, detail: "ok" });
      } catch (e) {
        checks.push({ name: "handoff_metrics", critical: true, ok: false, detail: String(e) });
      }

      try {
        await request("/api/v1/admin/channels/profiles?limit=5");
        checks.push({ name: "profiles_endpoint", critical: true, ok: true, detail: "ok" });
      } catch (e) {
        checks.push({ name: "profiles_endpoint", critical: true, ok: false, detail: String(e) });
      }

      try {
        await request("/api/v1/admin/ops/audit?limit=1&offset=0");
        checks.push({ name: "ops_audit_endpoint", critical: true, ok: true, detail: "ok" });
      } catch (e) {
        checks.push({ name: "ops_audit_endpoint", critical: true, ok: false, detail: String(e) });
      }

      try {
        const accounts = await request("/api/v1/admin/channels/accounts");
        const hasSeedAccount = (Array.isArray(accounts) ? accounts : []).some((a) =>
          ["messenger", "facebook", "instagram"].includes(String(a.channel_type || "").toLowerCase()) &&
          (a.page_id || a.instagram_account_id)
        );
        checks.push({
          name: "seed_channel_account",
          critical: false,
          ok: hasSeedAccount,
          detail: hasSeedAccount ? "found page/instagram account" : "missing social channel account for seed flow",
        });
      } catch (e) {
        checks.push({ name: "seed_channel_account", critical: false, ok: false, detail: String(e) });
      }

      const criticalPass = checks.filter((c) => c.critical).every((c) => c.ok);
      const pass = checks.every((c) => c.ok);
      lastPreflight = {
        at: nowIso(),
        api_base: apiBase,
        mode,
        critical_pass: criticalPass,
        pass,
        checks,
      };
      if (!silent) out.textContent = pretty(lastPreflight);
      updateQaChecklist();
      renderReleaseSnapshot();
      return lastPreflight;
    }

    function parseOrigins(s) {
      return String(s || "").split(",").map(v => v.trim()).filter(Boolean);
    }

    function esc(s) {
      return String(s == null ? "" : s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function shortDate(iso) {
      if (!iso) return "-";
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      return d.toLocaleString();
    }

    const tc = window.TenantConsole || {};
    const state = tc.state || {};
    Object.defineProperties(state, {
      queueTimer: { get: () => queueTimer, set: (v) => { queueTimer = v; }, enumerable: true },
      lastReplyReview: { get: () => lastReplyReview, set: (v) => { lastReplyReview = v; }, enumerable: true },
      lastQueueItems: { get: () => lastQueueItems, set: (v) => { lastQueueItems = v; }, enumerable: true },
      lastProfiles: { get: () => lastProfiles, set: (v) => { lastProfiles = v; }, enumerable: true },
      lastSweepRun: { get: () => lastSweepRun, set: (v) => { lastSweepRun = v; }, enumerable: true },
      lastMergeRun: { get: () => lastMergeRun, set: (v) => { lastMergeRun = v; }, enumerable: true },
      lastPreflight: { get: () => lastPreflight, set: (v) => { lastPreflight = v; }, enumerable: true },
      lastAuditRefreshAt: { get: () => lastAuditRefreshAt, set: (v) => { lastAuditRefreshAt = v; }, enumerable: true },
      lastQaPack: { get: () => lastQaPack, set: (v) => { lastQaPack = v; }, enumerable: true },
      activePane: { get: () => activePane, set: (v) => { activePane = v; }, enumerable: true },
      roleMode: { get: () => roleMode, set: (v) => { roleMode = v; }, enumerable: true },
      currentUser: { get: () => currentUser, set: (v) => { currentUser = v; }, enumerable: true },
    });

    Object.assign(tc, {
      $,
      pretty,
      getApiBase,
      isProdApiBase,
      isProdFrontendHost,
      nowIso,
      preflightAgeMin,
      setChecklistBadge,
      updateQaChecklist,
      applyConsoleMode,
      setActivePane,
      renderReleaseSnapshot,
      safeJwtField,
      currentActorId,
      appendOpsAuditLocal,
      appendOpsAudit,
      loadOpsAudit,
      switchApiBase,
      requireReasonAndConfirm,
      ensurePreflightForDestructive,
      getToken,
      setToken,
      clearConsoleSession,
      saveSessionToken,
      request,
      runPreflightChecks,
      parseOrigins,
      esc,
      shortDate,
      state,
      isBackendAdminLike,
      renderCurrentUserBadge,
      syncCurrentUser,
      syncChannelIntegrations,
    });
    window.TenantConsole = tc;

