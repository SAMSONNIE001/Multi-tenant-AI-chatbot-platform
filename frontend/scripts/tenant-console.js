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

    function pretty(v) {
      try { return JSON.stringify(v, null, 2); } catch (_) { return String(v); }
    }

    function getApiBase() {
      return $("apiBase").value.trim().replace(/\/+$/, "");
    }

    function isProdApiBase() {
      const base = getApiBase().toLowerCase();
      return base.includes("api.staunchbot.com");
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
      const sections = document.querySelectorAll("section.card[data-pane]");
      sections.forEach((section) => {
        const panes = String(section.getAttribute("data-pane") || "")
          .split(/\s+/)
          .filter(Boolean);
        section.style.display = panes.includes(activePane) ? "block" : "none";
      });

      const showAdvanced = !!$("toggleAdvanced").checked;
      const advancedBlocks = document.querySelectorAll(".advanced-only");
      advancedBlocks.forEach((el) => {
        el.style.display = showAdvanced ? "block" : "none";
      });
      updateQaChecklist();
    }

    function setActivePane(pane) {
      activePane = pane;
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

    async function request(path, options = {}) {
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
        const res = await fetch(`${apiBase}/health`);
        checks.push({
          name: "health",
          critical: true,
          ok: res.ok,
          detail: `${res.status}`,
        });
      } catch (e) {
        checks.push({
          name: "health",
          critical: true,
          ok: false,
          detail: String(e),
        });
      }

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

    function renderQueueTable(items) {
      const wrap = $("queueTableWrap");
      const body = $("queueTableBody");
      body.innerHTML = "";
      if (!Array.isArray(items) || !items.length) {
        wrap.style.display = "none";
        return;
      }
      wrap.style.display = "block";
      for (const item of items) {
        const tr = document.createElement("tr");
        const statusClass = esc(item.status || "");
        const firstBreached = !!(item.first_response_due_at && !item.first_responded_at && ["new", "open"].includes(item.status));
        const resolutionBreached = !!(item.resolution_due_at && ["open", "pending_customer"].includes(item.status));
        const isBreached = firstBreached || resolutionBreached;
        const isEscalated = !!item.escalation_flag;
        if (isBreached) tr.className = "sla-breach";
        if (isEscalated) tr.className = `${tr.className ? `${tr.className} ` : ""}escalation-row`;
        const priority = String(item.priority || "").toLowerCase();
        const breachBadges = [
          firstBreached ? '<span class="sla-badge">first response breached</span>' : "",
          resolutionBreached ? '<span class="sla-badge">resolution breached</span>' : "",
        ].filter(Boolean).join(" ");
        const escalationBadge = isEscalated
          ? `<span class="tag escalated" title="${esc(shortDate(item.escalated_at))}">escalated</span>`
          : "";
        const priorityBadge = `<span class="tag priority ${esc(priority)}">${esc(item.priority || "-")}</span>`;
        tr.innerHTML = `
          <td title="${esc(item.id)}">${esc(item.id || "-")}</td>
          <td><span class="tag ${statusClass}">${esc(item.status || "-")}</span>${breachBadges ? `<div style="margin-top:4px;">${breachBadges}</div>` : ""}</td>
          <td>${priorityBadge}${escalationBadge ? `<div style="margin-top:4px;">${escalationBadge}${priority === "urgent" ? '<span class="sla-badge">priority bumped</span>' : ""}</div>` : ""}</td>
          <td>${esc(item.source_channel || "-")}</td>
          <td>${esc(item.assigned_to_user_id || "-")}</td>
          <td>${esc(shortDate(item.created_at))}</td>
          <td title="${esc(item.question || "")}" style="max-width:280px;white-space:normal;">${esc(item.question || "-")}</td>
          <td><button class="row-action" data-hid="${esc(item.id || "")}">Use</button></td>
        `;
        body.appendChild(tr);
      }
      body.querySelectorAll("button[data-hid]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const handoffId = btn.getAttribute("data-hid") || "";
          $("hfId").value = handoffId;
          const selected = (items || []).find((x) => x.id === handoffId);
          if (selected && selected.conversation_id) {
            $("convId").value = selected.conversation_id;
          }
          $("outHandoffAgent").textContent = `Selected handoff: ${$("hfId").value}`;
          $("btnLoadNotes").click();
        });
      });
    }

    function queueMetrics(items) {
      const rows = Array.isArray(items) ? items : [];
      const byStatus = { new: 0, open: 0, pending_customer: 0, resolved: 0, closed: 0 };
      let breached = 0;
      let unassigned = 0;
      let escalated = 0;
      for (const x of rows) {
        const s = String(x.status || "");
        if (Object.prototype.hasOwnProperty.call(byStatus, s)) byStatus[s] += 1;
        if (!x.assigned_to_user_id) unassigned += 1;
        if (isSlaBreached(x)) breached += 1;
        if (x.escalation_flag) escalated += 1;
      }
      return { total: rows.length, breached, unassigned, escalated, ...byStatus };
    }

    function renderQueueMetrics(items) {
      const box = $("queueMetrics");
      const m = queueMetrics(items);
      if (!m.total) {
        box.style.display = "none";
        box.innerHTML = "";
        return;
      }
      box.style.display = "grid";
      const cards = [
        ["Total", m.total],
        ["New", m.new],
        ["Open", m.open],
        ["Pending", m.pending_customer],
        ["Resolved", m.resolved],
        ["Closed", m.closed],
        ["Breached", m.breached],
        ["Escalated", m.escalated],
        ["Unassigned", m.unassigned],
      ];
      box.innerHTML = cards.map(([k, v]) => `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
    }

    function renderProfilesTable(data) {
      const wrap = $("profilesTableWrap");
      const body = $("profilesTableBody");
      body.innerHTML = "";
      const profiles = Array.isArray(data && data.profiles) ? data.profiles : [];
      lastProfiles = profiles;
      if (!profiles.length) {
        wrap.style.display = "none";
        return;
      }
      wrap.style.display = "block";
      body.innerHTML = profiles.map((p) => {
        const handles = Array.isArray(p.handles) ? p.handles : [];
        const handleText = handles.length
          ? handles.map((h) => `${h.channel_type}:${h.external_user_id}`).join(", ")
          : "-";
        return `
          <tr>
            <td class="mono">${esc(p.id || "-")}</td>
            <td>${esc(p.display_name || "-")}</td>
            <td title="${esc(handleText)}" style="max-width:320px;white-space:normal;">${esc(handleText)}</td>
            <td>${esc(p.conversation_count || 0)}</td>
            <td>${esc(p.handoff_count || 0)}</td>
            <td>${esc(shortDate(p.updated_at))}</td>
            <td>
              <button class="row-action" data-cp-source="${esc(p.id || "")}">Source</button>
              <button class="row-action" data-cp-target="${esc(p.id || "")}">Target</button>
            </td>
          </tr>
        `;
      }).join("");
      body.querySelectorAll("button[data-cp-source]").forEach((btn) => {
        btn.addEventListener("click", () => {
          $("cpSourceId").value = btn.getAttribute("data-cp-source") || "";
        });
      });
      body.querySelectorAll("button[data-cp-target]").forEach((btn) => {
        btn.addEventListener("click", () => {
          $("cpTargetId").value = btn.getAttribute("data-cp-target") || "";
        });
      });
    }

    function renderEscalationMetricsCards(data) {
      const box = $("escMetricsGrid");
      if (!data || !data.window_24h || !data.window_7d || !data.totals) {
        box.style.display = "none";
        box.innerHTML = "";
        return;
      }
      const w24 = data.window_24h;
      const w7d = data.window_7d;
      const t = data.totals;
      const cards = [
        ["Escalated (total)", t.escalated_tickets ?? "-"],
        ["24h Escalation %", `${((w24.escalation_rate || 0) * 100).toFixed(1)}%`],
        ["7d Escalation %", `${((w7d.escalation_rate || 0) * 100).toFixed(1)}%`],
        ["24h Breach %", `${((w24.breach_rate || 0) * 100).toFixed(1)}%`],
        ["7d Breach %", `${((w7d.breach_rate || 0) * 100).toFixed(1)}%`],
        ["As Of", shortDate(data.as_of)],
      ];
      box.style.display = "grid";
      box.innerHTML = cards.map(([k, v]) => `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
    }

    function renderOpsMonitorGrid(metricsData, queueItems) {
      const box = $("opsMonitorGrid");
      const items = Array.isArray(queueItems) ? queueItems : [];
      const urgentBacklog = items.filter((x) => String(x.priority || "").toLowerCase() === "urgent" && ["new", "open", "pending_customer"].includes(String(x.status || ""))).length;
      const escalatedOpen = items.filter((x) => x.escalation_flag && ["new", "open", "pending_customer"].includes(String(x.status || ""))).length;
      const m = metricsData || {};
      const t = m.totals || {};
      const w24 = m.window_24h || {};
      const cards = [
        ["Urgent Backlog", urgentBacklog],
        ["Escalated Open", escalatedOpen],
        ["Escalated Total", t.escalated_tickets ?? "-"],
        ["24h Escalation %", w24.escalation_rate != null ? `${(Number(w24.escalation_rate) * 100).toFixed(1)}%` : "-"],
        ["24h Tickets", w24.total_tickets ?? "-"],
        ["Last Sweep", lastSweepRun ? shortDate(lastSweepRun.at) : "never"],
      ];
      box.style.display = "grid";
      box.innerHTML = cards.map(([k, v]) => `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
    }

    function applyQaAvailability() {
      const isProd = isProdApiBase();
      const qaBtns = ["btnQaSweepFlow", "btnQaMergeFlow"];
      for (const id of qaBtns) {
        const el = $(id);
        if (el) el.disabled = isProd;
      }
      $("qaEnvBanner").style.display = isProd ? "block" : "none";
      renderReleaseSnapshot();
    }

    function renderProductivityMetrics(data) {
      const grid = $("prodMetricsGrid");
      const body = $("prodAgentBody");
      const wrap = $("prodAgentWrap");
      const charts = $("prodCharts");
      if (!data || !data.window_24h || !data.window_7d) {
        grid.style.display = "none";
        grid.innerHTML = "";
        charts.style.display = "none";
        wrap.style.display = "none";
        body.innerHTML = "";
        return;
      }

      const w24 = data.window_24h;
      const w7d = data.window_7d;
      const totals = data.totals || {};
      const cards = [
        ["All Tickets", totals.all_tickets ?? "-"],
        ["Resolved", totals.resolved_tickets ?? "-"],
        ["Unresolved", totals.unresolved_tickets ?? "-"],
        ["Resolved %", totals.resolved_rate != null ? `${(totals.resolved_rate * 100).toFixed(1)}%` : "-"],
        ["24h Tickets", w24.total_tickets],
        ["24h Breach %", `${(w24.breach_rate * 100).toFixed(1)}%`],
        ["24h First Resp (min)", w24.avg_first_response_min ?? "-"],
        ["24h Resolution (min)", w24.avg_resolution_min ?? "-"],
        ["7d Tickets", w7d.total_tickets],
        ["7d Breach %", `${(w7d.breach_rate * 100).toFixed(1)}%`],
        ["7d First Resp (min)", w7d.avg_first_response_min ?? "-"],
        ["7d Resolution (min)", w7d.avg_resolution_min ?? "-"],
      ];
      grid.style.display = "grid";
      grid.innerHTML = cards.map(([k, v]) => `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
      charts.style.display = "grid";
      renderProdCharts(data);

      const agents = Array.isArray(data.by_agent) ? data.by_agent : [];
      if (!agents.length) {
        wrap.style.display = "none";
        body.innerHTML = "";
        return;
      }
      wrap.style.display = "block";
      body.innerHTML = agents.map((a) => `
        <tr>
          <td>${esc(a.agent_user_id || "-")}</td>
          <td>${esc(a.assigned_count || 0)}</td>
          <td>${esc(a.resolved_count || 0)}</td>
        </tr>
      `).join("");
    }

    function renderLineSvg(svgId, values, color, yLabelSuffix = "") {
      const svg = $(svgId);
      if (!svg) return;
      const w = 600;
      const h = 130;
      const pad = 18;
      const maxV = Math.max(1, ...values);
      const n = values.length;
      const step = n > 1 ? (w - pad * 2) / (n - 1) : 0;
      const points = values.map((v, i) => {
        const x = pad + i * step;
        const y = h - pad - ((v / maxV) * (h - pad * 2));
        return `${x},${y}`;
      }).join(" ");
      const circles = values.map((v, i) => {
        const x = pad + i * step;
        const y = h - pad - ((v / maxV) * (h - pad * 2));
        return `<circle cx="${x}" cy="${y}" r="2.5" fill="${color}"></circle>`;
      }).join("");
      svg.innerHTML = `
        <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#cbd5e1" stroke-width="1"></line>
        <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h - pad}" stroke="#cbd5e1" stroke-width="1"></line>
        <polyline fill="none" stroke="${color}" stroke-width="2.5" points="${points}"></polyline>
        ${circles}
        <text x="${w - pad}" y="${pad}" text-anchor="end" fill="#64748b" font-size="10">max ${maxV}${yLabelSuffix}</text>
      `;
    }

    function renderBarSvg(svgId, values, labels, color) {
      const svg = $(svgId);
      if (!svg) return;
      const w = 600;
      const h = 130;
      const pad = 18;
      const maxV = Math.max(1, ...values);
      const n = Math.max(1, values.length);
      const slot = (w - pad * 2) / n;
      const barW = Math.max(8, slot * 0.6);
      const bars = values.map((v, i) => {
        const bh = (v / maxV) * (h - pad * 2);
        const x = pad + i * slot + (slot - barW) / 2;
        const y = h - pad - bh;
        const lab = esc(String(labels[i] || ""));
        return `<rect x="${x}" y="${y}" width="${barW}" height="${bh}" fill="${color}" rx="2"></rect>
                <title>${lab}: ${v}</title>`;
      }).join("");
      svg.innerHTML = `
        <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#cbd5e1" stroke-width="1"></line>
        ${bars}
        <text x="${w - pad}" y="${pad}" text-anchor="end" fill="#64748b" font-size="10">max ${maxV}</text>
      `;
    }

    function renderProdCharts(data) {
      const totals = data.totals || {};
      const splitVals = [
        Number(totals.resolved_tickets || 0),
        Number(totals.unresolved_tickets || 0),
        Number(totals.all_tickets || 0),
      ];
      renderBarSvg("chartResolvedSplit", splitVals, ["Resolved", "Unresolved", "All"], "#7c3aed");

      const daily = Array.isArray(data.daily) ? data.daily : [];
      const ticketSeries = daily.map((d) => Number(d.tickets || 0));
      const breachSeries = daily.map((d) => Number(d.breach_rate || 0) * 100);
      renderLineSvg("chartTickets", ticketSeries.length ? ticketSeries : [0], "#1d4ed8");
      renderLineSvg("chartBreach", breachSeries.length ? breachSeries : [0], "#b91c1c", "%");

      const agents = (Array.isArray(data.by_agent) ? data.by_agent : []).slice(0, 8);
      const agentVals = agents.map((a) => Number(a.assigned_count || 0));
      const agentLabs = agents.map((a) => String(a.agent_user_id || "-"));
      renderBarSvg("chartAgents", agentVals.length ? agentVals : [0], agentLabs.length ? agentLabs : ["-"], "#0f766e");
    }

    function roleClass(role) {
      const r = String(role || "").toLowerCase();
      if (r === "user") return "user";
      if (r === "assistant") return "assistant";
      if (r === "agent") return "agent";
      return "";
    }

    function renderConversationThread(payload) {
      const box = $("conversationThread");
      if (!payload || !Array.isArray(payload.messages) || !payload.messages.length) {
        box.style.display = "none";
        box.innerHTML = "";
        return;
      }
      box.style.display = "block";
      box.innerHTML = payload.messages.map((m) => {
        const role = esc(m.role || "unknown");
        return `
          <div class="msg ${roleClass(m.role)}">
            <div class="meta">${role} - ${esc(shortDate(m.created_at))}</div>
            <div>${esc(m.content || "")}</div>
          </div>
        `;
      }).join("");
      box.scrollTop = box.scrollHeight;
    }

    function renderNotesTimeline(payload) {
      const box = $("notesTimeline");
      if (!payload || !Array.isArray(payload.items) || !payload.items.length) {
        box.style.display = "none";
        box.innerHTML = "";
        return;
      }
      box.style.display = "block";
      box.innerHTML = payload.items.map((n) => {
        return `
          <div class="note">
            <div class="meta">${esc(n.author_user_id || "-")} - ${esc(shortDate(n.created_at))}</div>
            <div>${esc(n.content || "")}</div>
          </div>
        `;
      }).join("");
      box.scrollTop = box.scrollHeight;
    }

    async function loadHandoffNotes() {
      const handoffId = $("hfId").value.trim();
      if (!handoffId) throw new Error("Provide handoff id.");
      const data = await request(`/api/v1/admin/handoff/${encodeURIComponent(handoffId)}/notes?limit=200&offset=0`);
      renderNotesTimeline(data);
      return data;
    }

    function renderReplyReview(data) {
      const out = $("outReplyReview");
      if (!data) {
        out.textContent = "";
        return;
      }
      out.textContent = pretty({
        handoff_id: data.handoff_id,
        confidence: data.confidence,
        requires_override: data.requires_override,
        risk_flags: data.risk_flags || [],
      });
    }

    async function fetchReplyReview(mode = "none") {
      const handoffId = $("hfId").value.trim();
      if (!handoffId) throw new Error("Provide handoff id.");
      const draft = $("hfAgentReply").value.trim();
      if (!draft) throw new Error("Write an agent reply first.");
      const data = await request(`/api/v1/admin/handoff/reply-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          handoff_id: handoffId,
          draft,
          rewrite_mode: mode,
        }),
      });
      lastReplyReview = {
        handoff_id: handoffId,
        draft_before_send: draft,
        requires_override: !!data.requires_override,
        confidence: data.confidence,
      };
      return data;
    }

    function priorityRank(priority) {
      const p = String(priority || "").toLowerCase();
      if (p === "urgent") return 4;
      if (p === "high") return 3;
      if (p === "normal") return 2;
      if (p === "low") return 1;
      return 0;
    }

    function isSlaBreached(item) {
      const firstBreached = !!(item.first_response_due_at && !item.first_responded_at && ["new", "open"].includes(item.status));
      const resolutionBreached = !!(item.resolution_due_at && ["open", "pending_customer"].includes(item.status));
      return firstBreached || resolutionBreached;
    }

    function sortQueueItems(items) {
      const mode = $("hfSort").value;
      const arr = Array.isArray(items) ? [...items] : [];
      if (mode === "newest") {
        return arr.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
      }
      if (mode === "urgent_escalated") {
        return arr.sort((a, b) => {
          const escDiff = Number(!!b.escalation_flag) - Number(!!a.escalation_flag);
          if (escDiff !== 0) return escDiff;
          const urgentDiff = Number(String(b.priority || "").toLowerCase() === "urgent") - Number(String(a.priority || "").toLowerCase() === "urgent");
          if (urgentDiff !== 0) return urgentDiff;
          const highDiff = Number(String(b.priority || "").toLowerCase() === "high") - Number(String(a.priority || "").toLowerCase() === "high");
          if (highDiff !== 0) return highDiff;
          const breachDiff = Number(isSlaBreached(b)) - Number(isSlaBreached(a));
          if (breachDiff !== 0) return breachDiff;
          return new Date(b.created_at || 0) - new Date(a.created_at || 0);
        });
      }
      return arr.sort((a, b) => {
        const breachDiff = Number(isSlaBreached(b)) - Number(isSlaBreached(a));
        if (breachDiff !== 0) return breachDiff;
        const prioDiff = priorityRank(b.priority) - priorityRank(a.priority);
        if (prioDiff !== 0) return prioDiff;
        return new Date(b.created_at || 0) - new Date(a.created_at || 0);
      });
    }

    function setQueueAutoRefresh() {
      if (queueTimer) {
        clearInterval(queueTimer);
        queueTimer = null;
      }
      const seconds = parseInt($("hfAutoRefresh").value, 10) || 0;
      if (seconds > 0) {
        queueTimer = setInterval(() => {
          loadHandoffQueue(true);
        }, seconds * 1000);
      }
    }

    async function loadHandoffQueue(silent = false) {
      const out = $("outHandoffList");
      if (!silent) out.textContent = "Loading queue...";
      try {
        const params = new URLSearchParams();
        const status = $("hfStatus").value.trim();
        const assignedTo = $("hfAssignedTo").value.trim();
        const priority = $("hfPriorityFilter").value.trim();
        const breachedOnly = $("hfBreachedOnly").value === "true";
        const escalatedOnly = $("hfEscalatedOnly").value === "true";
        if (status && status !== "new_open") params.set("status", status);
        if (assignedTo) params.set("assigned_to", assignedTo);
        if (priority) params.set("priority", priority);
        if (breachedOnly) params.set("breached_only", "true");
        const query = params.toString() ? `?${params.toString()}` : "";
        const data = await request(`/api/v1/admin/handoff${query}`);
        let items = Array.isArray(data && data.items) ? data.items : [];
        if (status === "new_open") {
          items = items.filter((x) => ["new", "open"].includes(String(x.status || "")));
        }
        if (escalatedOnly) {
          items = items.filter((x) => !!x.escalation_flag);
        }
        items = sortQueueItems(items);
        lastQueueItems = items;
        if (!silent) out.textContent = pretty({ ...data, items });
        renderQueueMetrics(items);
        renderQueueTable(items);
        if (items.length && items[0].id && !$("hfId").value.trim()) {
          $("hfId").value = items[0].id;
        }
      } catch (e) {
        out.textContent = String(e);
        lastQueueItems = [];
        renderQueueMetrics([]);
        renderQueueTable([]);
      }
    }

    async function loadProfiles() {
      const out = $("outProfilesList");
      out.textContent = "Loading profiles...";
      try {
        const limit = Math.max(1, Math.min(500, parseInt($("cpLimit").value, 10) || 100));
        const data = await request(`/api/v1/admin/channels/profiles?limit=${limit}`);
        out.textContent = pretty({ tenant_id: data.tenant_id, count: Array.isArray(data.profiles) ? data.profiles.length : 0 });
        renderProfilesTable(data);
        return data;
      } catch (e) {
        out.textContent = String(e);
        renderProfilesTable(null);
        throw e;
      }
    }

    async function mergeProfiles() {
      const out = $("outProfilesMerge");
      out.textContent = "Merging profiles...";
      try {
        ensurePreflightForDestructive("Merge customer profiles");
        const source = $("cpSourceId").value.trim();
        const target = $("cpTargetId").value.trim();
        if (!source || !target) throw new Error("Provide both source and target profile IDs.");
        const reason = requireReasonAndConfirm($("cpMergeReason").value, "Merge customer profiles");
        const data = await request("/api/v1/admin/channels/profiles/merge", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_profile_id: source, target_profile_id: target }),
        });
        await appendOpsAudit({
          at: nowIso(),
          actor: currentActorId(),
          operation: "profiles.merge",
          reason,
          source_profile_id: source,
          target_profile_id: target,
          result: data,
        });
        out.textContent = pretty(data);
        lastMergeRun = { at: nowIso(), result: data };
        await loadProfiles();
        await loadOpsAudit();
        updateQaChecklist();
        renderReleaseSnapshot();
        return data;
      } catch (e) {
        out.textContent = String(e);
        throw e;
      }
    }

    async function loadEscalationMetrics() {
      const out = $("outEscalationOps");
      out.textContent = "Loading escalation metrics...";
      try {
        const data = await request("/api/v1/admin/handoff/metrics");
        out.textContent = pretty({ tenant_id: data.tenant_id, as_of: data.as_of, escalated_total: data.totals && data.totals.escalated_tickets });
        renderEscalationMetricsCards(data);
        return data;
      } catch (e) {
        out.textContent = String(e);
        renderEscalationMetricsCards(null);
        throw e;
      }
    }

    async function runEscalationSweep() {
      const out = $("outEscalationOps");
      out.textContent = "Running escalation sweep...";
      try {
        ensurePreflightForDestructive("Run escalation sweep");
        const reason = requireReasonAndConfirm($("escSweepReason").value, "Run escalation sweep");
        const data = await request("/api/v1/admin/handoff/escalation/sweep", { method: "POST" });
        lastSweepRun = {
          at: nowIso(),
          result: data,
        };
        await appendOpsAudit({
          at: nowIso(),
          actor: currentActorId(),
          operation: "handoff.escalation_sweep",
          reason,
          result: data,
        });
        out.textContent = pretty(data);
        await loadHandoffQueue(true);
        const metrics = await loadEscalationMetrics();
        renderOpsMonitorGrid(metrics, lastQueueItems);
        await loadOpsAudit();
        updateQaChecklist();
        renderReleaseSnapshot();
        return data;
      } catch (e) {
        out.textContent = String(e);
        throw e;
      }
    }

    async function loadOpsMonitor() {
      const out = $("outEscalationOps");
      out.textContent = "Loading ops monitor...";
      try {
        await loadHandoffQueue(true);
        const metrics = await request("/api/v1/admin/handoff/metrics");
        renderEscalationMetricsCards(metrics);
        renderOpsMonitorGrid(metrics, lastQueueItems);
        out.textContent = pretty({
          tenant_id: metrics.tenant_id,
          as_of: metrics.as_of,
          urgent_backlog: (lastQueueItems || []).filter((x) => String(x.priority || "").toLowerCase() === "urgent" && ["new", "open", "pending_customer"].includes(String(x.status || ""))).length,
          escalated_open: (lastQueueItems || []).filter((x) => !!x.escalation_flag && ["new", "open", "pending_customer"].includes(String(x.status || ""))).length,
          last_sweep_at: lastSweepRun ? lastSweepRun.at : null,
        });
      } catch (e) {
        out.textContent = String(e);
      }
    }

    async function seedProfileActivity() {
      const out = $("outProfileSeed");
      out.textContent = "Seeding profile activity...";
      try {
        const externalId = $("cpSeedExternalId").value.trim() || `ext_customer_${Date.now()}`;
        const message = $("cpSeedMessage").value.trim() || "I need human support with my order.";
        const accounts = await request("/api/v1/admin/channels/accounts");
        const pageLike = (Array.isArray(accounts) ? accounts : []).find((a) =>
          ["messenger", "facebook", "instagram"].includes(String(a.channel_type || "").toLowerCase()) &&
          (a.page_id || a.instagram_account_id)
        );
        if (!pageLike) {
          throw new Error("No messenger/facebook/instagram channel account with page_id/instagram_account_id found. Configure one first.");
        }
        const recipientId = pageLike.page_id || pageLike.instagram_account_id;
        const objectType = String(pageLike.channel_type || "").toLowerCase() === "instagram" ? "instagram" : "page";
        const payload = {
          object: objectType,
          entry: [
            {
              id: "seed_entry",
              time: Date.now(),
              messaging: [
                {
                  sender: { id: externalId },
                  recipient: { id: recipientId },
                  timestamp: Date.now(),
                  message: { mid: `seed_${Date.now()}`, text: message },
                },
              ],
            },
          ],
        };
        const res = await request("/api/v1/channels/meta/webhook", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        await loadProfiles();
        out.textContent = pretty({
          seeded: true,
          channel_account_id: pageLike.id,
          channel_type: pageLike.channel_type,
          external_user_id: externalId,
          webhook_result: res,
          profiles_count: lastProfiles.length,
        });
      } catch (e) {
        out.textContent = String(e);
      }
    }

    async function runStagingQaPack() {
      const out = $("outEscalationOps");
      out.textContent = "Running staging QA pack...";
      try {
        if (isProdApiBase()) {
          const staging = $("stagingApiBase").value.trim();
          if (!staging) {
            alert("Set Staging API Base first, then click Run Staging QA Pack again.");
            $("stagingApiBase").focus();
            throw new Error("Missing staging API base.");
          }
          switchApiBase(staging);
        }
        const pf = await runPreflightChecks(true);
        if (!pf.critical_pass) {
          throw new Error("Preflight critical checks failed. Run Preflight Checks and resolve failing items.");
        }
        await seedProfileActivity();
        await loadProfiles();
        if (!$("escSweepReason").value.trim()) {
          $("escSweepReason").value = `staging qa sweep ${new Date().toISOString()}`;
        }
        await runQaSweepFlow();
        if (lastProfiles.length >= 2) {
          $("cpSourceId").value = lastProfiles[0].id;
          $("cpTargetId").value = lastProfiles[1].id;
          $("cpMergeReason").value = `staging qa merge ${new Date().toISOString()}`;
          await runQaMergeFlow();
        }
        out.textContent = pretty({
          qa_pack: "staging_full",
          api_base: getApiBase(),
          profiles_loaded: lastProfiles.length,
          sweep_test: "completed",
          merge_test: lastProfiles.length >= 2 ? "completed" : "skipped_not_enough_profiles",
        });
        lastQaPack = { at: nowIso(), ok: true };
      } catch (e) {
        out.textContent = String(e);
        lastQaPack = { at: nowIso(), ok: false, error: String(e) };
      } finally {
        updateQaChecklist();
      }
    }

    async function runUatPack() {
      const out = $("outUatPack");
      out.textContent = "Running UAT pack...";
      const report = {
        at: nowIso(),
        api_base: getApiBase(),
        mode: isProdApiBase() ? "production" : "staging_or_local",
        steps: [],
      };

      async function runStep(name, fn, critical = true) {
        const step = { name, critical, ok: false, detail: "" };
        try {
          const result = await fn();
          step.ok = true;
          step.detail = "ok";
          if (result && typeof result === "object") step.result = result;
        } catch (e) {
          step.ok = false;
          step.detail = String(e);
        }
        report.steps.push(step);
      }

      await runStep("preflight", async () => {
        const pf = await runPreflightChecks(true);
        if (!pf.critical_pass) throw new Error("critical preflight checks failed");
        return pf;
      });

      await runStep("staging_qa_pack", async () => {
        if (isProdApiBase()) throw new Error("UAT pack is intended for staging/local API base");
        await runStagingQaPack();
        if (!lastQaPack || !lastQaPack.ok) throw new Error("staging qa pack reported failure");
        return lastQaPack;
      });

      await runStep("daily_ops.queue_load", async () => {
        await loadHandoffQueue(true);
        return { items: Array.isArray(lastQueueItems) ? lastQueueItems.length : 0 };
      });

      await runStep("daily_ops.metrics_load", async () => loadEscalationMetrics());
      await runStep("daily_ops.profiles_load", async () => loadProfiles());
      await runStep("setup_admin.bots_load", async () => request("/api/v1/tenant/bots"));
      await runStep("setup_admin.knowledge_status", async () => request("/api/v1/tenant/knowledge/status"));

      const criticalPass = report.steps.filter((s) => s.critical).every((s) => s.ok);
      report.critical_pass = criticalPass;
      report.pass = report.steps.every((s) => s.ok);
      out.textContent = pretty(report);
      return report;
    }

    async function runQaSweepFlow() {
      const out = $("outEscalationOps");
      out.textContent = "Running QA sweep flow...";
      try {
        if (isProdApiBase()) throw new Error("QA sweep flow disabled on production API base.");
        let selectedId = $("hfId").value.trim();
        let before = null;
        if (selectedId) {
          await loadHandoffQueue(true);
          before = (lastQueueItems || []).find((x) => x.id === selectedId) || null;
        }
        if (!before) {
          const breached = await request("/api/v1/admin/handoff?breached_only=true");
          const candidate = Array.isArray(breached && breached.items) && breached.items.length ? breached.items[0] : null;
          if (!candidate || !candidate.id) {
            throw new Error("No breached tickets found. Create or wait for an SLA breach, then rerun QA flow.");
          }
          selectedId = candidate.id;
          $("hfId").value = selectedId;
          await loadHandoffQueue(true);
          before = (lastQueueItems || []).find((x) => x.id === selectedId) || candidate;
        }
        const beforePriority = String(before.priority || "").toLowerCase();
        const beforeEsc = !!before.escalation_flag;
        if (!$("escSweepReason").value.trim()) {
          $("escSweepReason").value = `qa sweep validation ${new Date().toISOString()}`;
        }
        const sweep = await runEscalationSweep();
        const after = (lastQueueItems || []).find((x) => x.id === selectedId);
        out.textContent = pretty({
          qa_flow: "breached_ticket_sweep",
          selected_handoff_id: selectedId,
          before: {
            priority: beforePriority,
            escalation_flag: beforeEsc,
          },
          after: after
            ? {
                priority: after.priority,
                escalation_flag: !!after.escalation_flag,
                escalated_at: after.escalated_at || null,
              }
            : null,
          sweep_result: sweep,
          verified: !!(after && after.escalation_flag && ["high", "urgent"].includes(String(after.priority || "").toLowerCase())),
        });
      } catch (e) {
        out.textContent = String(e);
      }
    }

    async function runQaMergeFlow() {
      const out = $("outProfilesMerge");
      out.textContent = "Running QA merge flow...";
      try {
        if (isProdApiBase()) throw new Error("QA merge flow disabled on production API base.");
        const source = $("cpSourceId").value.trim();
        const target = $("cpTargetId").value.trim();
        if (!source || !target) throw new Error("Provide source and target profile IDs.");
        const beforeData = await loadProfiles();
        const beforeProfiles = Array.isArray(beforeData.profiles) ? beforeData.profiles : [];
        const beforeSource = beforeProfiles.find((p) => p.id === source) || null;
        const beforeTarget = beforeProfiles.find((p) => p.id === target) || null;
        if (!beforeSource || !beforeTarget) throw new Error("Source/target must exist in profile list before merge.");
        const merge = await mergeProfiles();
        const afterData = await loadProfiles();
        const afterProfiles = Array.isArray(afterData.profiles) ? afterData.profiles : [];
        const afterSource = afterProfiles.find((p) => p.id === source) || null;
        const afterTarget = afterProfiles.find((p) => p.id === target) || null;
        const beforeSourceConv = beforeSource.conversation_count || 0;
        const beforeSourceHandoff = beforeSource.handoff_count || 0;
        const beforeTargetConv = beforeTarget.conversation_count || 0;
        const beforeTargetHandoff = beforeTarget.handoff_count || 0;
        const afterTargetConv = afterTarget ? (afterTarget.conversation_count || 0) : null;
        const afterTargetHandoff = afterTarget ? (afterTarget.handoff_count || 0) : null;
        out.textContent = pretty({
          qa_flow: "merge_profiles_ownership_move",
          source_profile_id: source,
          target_profile_id: target,
          merge_result: merge,
          checks: {
            source_removed: !afterSource,
            target_conversations_before: beforeTargetConv,
            target_conversations_after: afterTargetConv,
            target_handoffs_before: beforeTargetHandoff,
            target_handoffs_after: afterTargetHandoff,
            expected_target_conversations_min: beforeTargetConv + beforeSourceConv,
            expected_target_handoffs_min: beforeTargetHandoff + beforeSourceHandoff,
            ownership_moved_conversations: afterTargetConv != null ? afterTargetConv >= (beforeTargetConv + Math.max(merge.moved_conversations || 0, beforeSourceConv)) : false,
            ownership_moved_handoffs: afterTargetHandoff != null ? afterTargetHandoff >= (beforeTargetHandoff + Math.max(merge.moved_handoffs || 0, beforeSourceHandoff)) : false,
          },
        });
      } catch (e) {
        out.textContent = String(e);
      }
    }

    $("saveToken").onclick = () => {
      localStorage.setItem("tenant_console_token", $("accessToken").value);
      localStorage.setItem("tenant_console_api_base", $("apiBase").value);
      localStorage.setItem("tenant_console_staging_api_base", $("stagingApiBase").value);
      alert("Saved.");
    };

    $("clearToken").onclick = () => {
      localStorage.removeItem("tenant_console_token");
      setToken("");
    };

    $("btnOnboard").onclick = async () => {
      const out = $("outOnboard");
      out.textContent = "Running...";
      try {
        const body = {
          tenant_name: $("obTenantName").value.trim(),
          admin_email: $("obAdminEmail").value.trim(),
          admin_password: $("obAdminPassword").value,
          compliance_level: "standard",
          bot_name: $("obBotName").value.trim(),
          allowed_origins: parseOrigins($("obAllowedOrigins").value),
        };
        const data = await request("/api/v1/tenant/onboard", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        out.textContent = pretty(data);
        if (data && data.access_token) setToken(data.access_token);
        if (data && data.bot_id) $("botId").value = data.bot_id;
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnLogin").onclick = async () => {
      const out = $("outLogin");
      out.textContent = "Running...";
      try {
        const body = {
          tenant_id: $("lgTenantId").value.trim(),
          email: $("lgEmail").value.trim(),
          password: $("lgPassword").value,
        };
        const data = await request("/api/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        out.textContent = pretty(data);
        if (data && data.access_token) setToken(data.access_token);
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnBots").onclick = async () => {
      const out = $("outBots");
      out.textContent = "Loading...";
      try {
        const data = await request("/api/v1/tenant/bots");
        out.textContent = pretty(data);
        if (Array.isArray(data) && data.length && data[0].id) {
          $("botId").value = data[0].id;
        }
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnSnippet").onclick = async () => {
      const out = $("outSnippet");
      out.textContent = "Loading...";
      try {
        const botId = $("botId").value.trim();
        if (!botId) throw new Error("Provide bot id first.");
        const data = await request(`/api/v1/tenant/embed/snippet?bot_id=${encodeURIComponent(botId)}`);
        out.textContent = data.snippet_html || pretty(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnUpload").onclick = async () => {
      const out = $("outUpload");
      out.textContent = "Uploading...";
      try {
        const file = $("kgFile").files[0];
        if (!file) throw new Error("Pick a file first.");
        const fd = new FormData();
        fd.append("file", file);
        const data = await request("/api/v1/tenant/knowledge/upload", {
          method: "POST",
          body: fd,
        });
        out.textContent = pretty(data);
        if (data && data.document_id) $("kgDocId").value = data.document_id;
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnStatus").onclick = async () => {
      const out = $("outStatus");
      out.textContent = "Checking...";
      try {
        const data = await request("/api/v1/tenant/knowledge/status");
        out.textContent = pretty(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnReindex").onclick = async () => {
      const out = $("outStatus");
      out.textContent = "Reindexing...";
      try {
        const docId = $("kgDocId").value.trim();
        if (!docId) throw new Error("Provide document id.");
        const data = await request("/api/v1/tenant/knowledge/reindex", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ document_id: docId }),
        });
        out.textContent = pretty(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnHandoffList").onclick = () => loadHandoffQueue(false);
    $("hfAutoRefresh").onchange = () => setQueueAutoRefresh();
    $("hfSort").onchange = () => {
      if ($("queueTableWrap").style.display !== "none") loadHandoffQueue(true);
    };
    $("btnQuickOpenNew").onclick = () => {
      $("hfStatus").value = "new_open";
      $("hfEscalatedOnly").value = "false";
      $("hfBreachedOnly").value = "false";
      $("hfSort").value = "urgent_escalated";
      loadHandoffQueue(false);
    };
    $("btnQuickEscalated").onclick = () => {
      $("hfEscalatedOnly").value = "true";
      $("hfStatus").value = "new_open";
      $("hfSort").value = "urgent_escalated";
      loadHandoffQueue(false);
    };
    $("btnQuickResetQueue").onclick = () => {
      $("hfStatus").value = "";
      $("hfAssignedTo").value = "";
      $("hfPriorityFilter").value = "";
      $("hfBreachedOnly").value = "false";
      $("hfEscalatedOnly").value = "false";
      $("hfSort").value = "urgent_escalated";
      loadHandoffQueue(false);
    };

    $("btnHandoffPatch").onclick = async () => {
      const out = $("outHandoffPatch");
      out.textContent = "Patching...";
      try {
        const handoffId = $("hfId").value.trim();
        if (!handoffId) throw new Error("Provide handoff id.");
        const body = {};
        const status = $("hfSetStatus").value.trim();
        const assignTo = $("hfAssignTo").value.trim();
        const priority = $("hfPriority").value.trim();
        const resolutionNote = $("hfResolutionNote").value.trim();
        if (status) body.status = status;
        if (assignTo) body.assigned_to_user_id = assignTo;
        if (priority) body.priority = priority;
        if (resolutionNote) body.resolution_note = resolutionNote;
        if (!Object.keys(body).length) throw new Error("Pick at least one field to update.");

        const data = await request(`/api/v1/admin/handoff/${encodeURIComponent(handoffId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        out.textContent = pretty(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnHandoffClaim").onclick = async () => {
      const out = $("outHandoffAgent");
      out.textContent = "Claiming...";
      try {
        const handoffId = $("hfId").value.trim();
        if (!handoffId) throw new Error("Provide handoff id.");
        const claimUser = $("hfClaimUser").value.trim();
        const body = {};
        if (claimUser) body.assigned_to_user_id = claimUser;
        const data = await request(`/api/v1/admin/handoff/${encodeURIComponent(handoffId)}/claim`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        out.textContent = pretty(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnHandoffReply").onclick = async () => {
      const out = $("outHandoffAgent");
      out.textContent = "Sending agent reply...";
      try {
        const handoffId = $("hfId").value.trim();
        if (!handoffId) throw new Error("Provide handoff id.");
        const review = await fetchReplyReview("none");
        renderReplyReview(review);
        if (review.requires_override && !$("hfSendOverride").checked) {
          throw new Error("High-risk flag detected. Tick 'Send anyway if high-risk flagged' to proceed.");
        }
        const message = $("hfAgentReply").value.trim();
        if (!message) throw new Error("Write an agent reply message.");
        const markPendingCustomer = $("hfMarkPending").value === "true";
        const body = {
          message,
          mark_pending_customer: markPendingCustomer,
        };
        const data = await request(`/api/v1/admin/handoff/${encodeURIComponent(handoffId)}/reply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        out.textContent = pretty(data);
        $("hfAgentReply").value = "";
        $("hfSendOverride").checked = false;
        lastReplyReview = null;
        if ($("convId").value.trim()) {
          $("btnLoadConversation").click();
        }
      } catch (e) {
        out.textContent = String(e);
      }
    };

    $("btnReviewReply").onclick = async () => {
      const out = $("outReplyReview");
      out.textContent = "Reviewing...";
      try {
        const data = await fetchReplyReview("none");
        renderReplyReview(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };
    $("btnRewriteShorter").onclick = async () => {
      const out = $("outReplyReview");
      out.textContent = "Rewriting (shorter)...";
      try {
        const data = await fetchReplyReview("shorter");
        $("hfAgentReply").value = data.improved_draft || $("hfAgentReply").value;
        renderReplyReview(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };
    $("btnRewriteFriendlier").onclick = async () => {
      const out = $("outReplyReview");
      out.textContent = "Rewriting (friendlier)...";
      try {
        const data = await fetchReplyReview("friendlier");
        $("hfAgentReply").value = data.improved_draft || $("hfAgentReply").value;
        renderReplyReview(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };
    $("btnRewriteFormal").onclick = async () => {
      const out = $("outReplyReview");
      out.textContent = "Rewriting (formal)...";
      try {
        const data = await fetchReplyReview("formal");
        $("hfAgentReply").value = data.improved_draft || $("hfAgentReply").value;
        renderReplyReview(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };

    async function setAIToggle(aiPaused) {
      const out = $("outHandoffAgent");
      out.textContent = aiPaused ? "Pausing AI..." : "Resuming AI...";
      try {
        const handoffId = $("hfId").value.trim();
        if (!handoffId) throw new Error("Provide handoff id.");
        const data = await request(`/api/v1/admin/handoff/${encodeURIComponent(handoffId)}/ai-toggle`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ai_paused: aiPaused }),
        });
        out.textContent = pretty(data);
      } catch (e) {
        out.textContent = String(e);
      }
    }

    $("btnPauseAI").onclick = () => setAIToggle(true);
    $("btnResumeAI").onclick = () => setAIToggle(false);
    $("btnAddInternalNote").onclick = async () => {
      const out = $("outHandoffAgent");
      out.textContent = "Saving internal note...";
      try {
        const handoffId = $("hfId").value.trim();
        if (!handoffId) throw new Error("Provide handoff id.");
        const note = $("hfInternalNote").value.trim();
        if (!note) throw new Error("Write an internal note first.");
        const data = await request(`/api/v1/admin/handoff/${encodeURIComponent(handoffId)}/notes`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: note }),
        });
        $("hfInternalNote").value = "";
        out.textContent = pretty(data);
        await loadHandoffNotes();
      } catch (e) {
        out.textContent = String(e);
      }
    };
    $("btnLoadNotes").onclick = async () => {
      const out = $("outHandoffAgent");
      out.textContent = "Loading notes...";
      try {
        const data = await loadHandoffNotes();
        out.textContent = pretty({ handoff_id: data.handoff_id, count: data.count });
      } catch (e) {
        out.textContent = String(e);
        renderNotesTimeline(null);
      }
    };

    $("btnLoadConversation").onclick = async () => {
      const out = $("outConversationMeta");
      out.textContent = "Loading conversation...";
      try {
        const conversationId = $("convId").value.trim();
        if (!conversationId) throw new Error("Provide conversation id.");
        const data = await request(
          `/api/v1/admin/conversations/${encodeURIComponent(conversationId)}/messages?limit=200&offset=0`
        );
        out.textContent = `Conversation: ${data.conversation_id}\nMessages: ${Array.isArray(data.messages) ? data.messages.length : 0}`;
        renderConversationThread(data);
      } catch (e) {
        out.textContent = String(e);
        renderConversationThread(null);
      }
    };

    $("btnLoadProdMetrics").onclick = async () => {
      const out = $("outProdMetrics");
      out.textContent = "Loading metrics...";
      try {
        const data = await request("/api/v1/admin/handoff/metrics");
        out.textContent = pretty({ tenant_id: data.tenant_id, as_of: data.as_of });
        renderProductivityMetrics(data);
      } catch (e) {
        out.textContent = String(e);
        renderProductivityMetrics(null);
      }
    };

    $("btnProfilesList").onclick = () => loadProfiles();
    $("btnProfilesMerge").onclick = async () => {
      try { await mergeProfiles(); } catch (_) {}
    };
    $("btnQaMergeFlow").onclick = () => runQaMergeFlow();
    $("btnSeedProfileData").onclick = () => seedProfileActivity();

    $("btnEscMetrics").onclick = () => loadEscalationMetrics();
    $("btnEscSweep").onclick = async () => {
      try { await runEscalationSweep(); } catch (_) {}
    };
    $("btnQaSweepFlow").onclick = () => runQaSweepFlow();
    $("btnLoadOpsMonitor").onclick = () => loadOpsMonitor();
    $("btnLoadOpsAudit").onclick = () => loadOpsAudit();
    $("btnRunPreflight").onclick = () => runPreflightChecks(false);
    $("btnRefreshSnapshot").onclick = () => renderReleaseSnapshot();
    $("btnEnvProd").onclick = () => switchApiBase("https://api.staunchbot.com");
    $("btnEnvStaging").onclick = () => switchApiBase($("stagingApiBase").value.trim());
    $("btnEnvLocal").onclick = () => switchApiBase("http://localhost:8000");
    $("btnRunStagingQaPack").onclick = () => runStagingQaPack();
    $("btnRunUatPack").onclick = () => runUatPack();
    $("apiBase").onchange = () => applyQaAvailability();
    $("tabDaily").onclick = () => {
      localStorage.setItem("tenant_console_active_pane", "daily");
      setActivePane("daily");
    };
    $("tabQa").onclick = () => {
      localStorage.setItem("tenant_console_active_pane", "qa");
      setActivePane("qa");
    };
    $("tabSetup").onclick = () => {
      localStorage.setItem("tenant_console_active_pane", "setup");
      setActivePane("setup");
    };
    $("toggleAdvanced").onchange = () => {
      localStorage.setItem("tenant_console_advanced", $("toggleAdvanced").checked ? "1" : "0");
      applyConsoleMode();
    };

    (function bootstrap() {
      const savedToken = localStorage.getItem("tenant_console_token");
      const savedBase = localStorage.getItem("tenant_console_api_base");
      const savedStaging = localStorage.getItem("tenant_console_staging_api_base");
      const savedPane = localStorage.getItem("tenant_console_active_pane");
      const savedAdvanced = localStorage.getItem("tenant_console_advanced");
      if (savedToken) setToken(savedToken);
      if (savedBase) $("apiBase").value = savedBase;
      if (savedStaging) $("stagingApiBase").value = savedStaging;
      if (savedAdvanced === "1") $("toggleAdvanced").checked = true;
      $("hfStatus").value = "new_open";
      $("hfSort").value = "urgent_escalated";
      $("hfEscalatedOnly").value = "false";
      if (!$("escSweepReason").value.trim()) $("escSweepReason").value = "scheduled SLA triage sweep";
      if (!$("cpMergeReason").value.trim()) $("cpMergeReason").value = "dedupe duplicate customer identities";
      setActivePane(savedPane && ["daily", "qa", "setup"].includes(savedPane) ? savedPane : "daily");
      applyQaAvailability();
      loadOpsAudit();
      runPreflightChecks(true).catch(() => {});
      renderReleaseSnapshot();
      setQueueAutoRefresh();
    })();
