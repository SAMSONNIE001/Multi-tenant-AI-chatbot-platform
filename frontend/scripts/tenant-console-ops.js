(() => {
    const tcOps = window.TenantConsole;
    const {
      $,
      esc,
      shortDate,
      pretty,
      request,
      nowIso,
      currentActorId,
      appendOpsAudit,
      ensurePreflightForDestructive,
      requireReasonAndConfirm,
      updateQaChecklist,
      renderReleaseSnapshot,
      isProdApiBase,
      loadOpsAudit,
    } = tcOps;
    const state = tcOps.state;

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
      state.lastProfiles = profiles;
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
        ["Last Sweep", state.lastSweepRun ? shortDate(state.lastSweepRun.at) : "never"],
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
      state.lastReplyReview = {
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
      if (state.queueTimer) {
        clearInterval(state.queueTimer);
        state.queueTimer = null;
      }
      const seconds = parseInt($("hfAutoRefresh").value, 10) || 0;
      if (seconds > 0) {
        state.queueTimer = setInterval(() => {
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
        state.lastQueueItems = items;
        if (!silent) out.textContent = pretty({ ...data, items });
        renderQueueMetrics(items);
        renderQueueTable(items);
        if (items.length && items[0].id && !$("hfId").value.trim()) {
          $("hfId").value = items[0].id;
        }
      } catch (e) {
        out.textContent = String(e);
        state.lastQueueItems = [];
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
        state.lastMergeRun = { at: nowIso(), result: data };
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
        state.lastSweepRun = {
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
        renderOpsMonitorGrid(metrics, state.lastQueueItems);
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
        renderOpsMonitorGrid(metrics, state.lastQueueItems);
        out.textContent = pretty({
          tenant_id: metrics.tenant_id,
          as_of: metrics.as_of,
          urgent_backlog: (state.lastQueueItems || []).filter((x) => String(x.priority || "").toLowerCase() === "urgent" && ["new", "open", "pending_customer"].includes(String(x.status || ""))).length,
          escalated_open: (state.lastQueueItems || []).filter((x) => !!x.escalation_flag && ["new", "open", "pending_customer"].includes(String(x.status || ""))).length,
          last_sweep_at: state.lastSweepRun ? state.lastSweepRun.at : null,
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
          profiles_count: state.lastProfiles.length,
        });
      } catch (e) {
        out.textContent = String(e);
      }
    }

    Object.assign(tcOps, {
      renderQueueTable,
      queueMetrics,
      renderQueueMetrics,
      renderProfilesTable,
      renderEscalationMetricsCards,
      renderOpsMonitorGrid,
      applyQaAvailability,
      renderProductivityMetrics,
      renderLineSvg,
      renderBarSvg,
      renderProdCharts,
      roleClass,
      renderConversationThread,
      renderNotesTimeline,
      loadHandoffNotes,
      renderReplyReview,
      fetchReplyReview,
      priorityRank,
      isSlaBreached,
      sortQueueItems,
      setQueueAutoRefresh,
      loadHandoffQueue,
      loadProfiles,
      mergeProfiles,
      loadEscalationMetrics,
      runEscalationSweep,
      loadOpsMonitor,
      seedProfileActivity,
    });
})();

