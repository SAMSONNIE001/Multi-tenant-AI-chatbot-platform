    const tc = window.TenantConsole;
    const {
      $,
      setToken,
      clearConsoleSession,
      request,
      parseOrigins,
      pretty,
      fetchReplyReview,
      renderReplyReview,
      loadHandoffNotes,
      renderNotesTimeline,
      renderConversationThread,
      renderProductivityMetrics,
      loadHandoffQueue,
      setQueueAutoRefresh,
      loadProfiles,
      mergeProfiles,
      runQaMergeFlow,
      seedProfileActivity,
      loadEscalationMetrics,
      runEscalationSweep,
      runQaSweepFlow,
      loadOpsMonitor,
      loadOpsAudit,
      runPreflightChecks,
      renderReleaseSnapshot,
      switchApiBase,
      runStagingQaPack,
      runUatPack,
      applyQaAvailability,
      setActivePane,
      applyConsoleMode,
      syncCurrentUser,
      renderCurrentUserBadge,
    } = tc;
    const state = tc.state;

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

    const btnOnboard = $("btnOnboard");
    if (btnOnboard) btnOnboard.onclick = async () => {
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
          email: $("lgEmail").value.trim(),
          password: $("lgPassword").value,
        };
        const tenantId = $("lgTenantId").value.trim();
        if (tenantId) body.tenant_id = tenantId;
        const data = await request("/api/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        $("lgTenantIdRow").style.display = "none";
        $("lgTenantId").value = "";
        out.textContent = pretty(data);
        if (data && data.access_token) {
          setToken(data.access_token);
          await syncCurrentUser();
        }
      } catch (e) {
        const msg = String(e);
        if (msg.includes("409") && msg.includes("Provide tenant_id")) {
          $("lgTenantIdRow").style.display = "grid";
          $("lgTenantId").focus();
        }
        out.textContent = String(e);
      }
    };

    const btnBots = $("btnBots");
    if (btnBots) btnBots.onclick = async () => {
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

    const btnSnippet = $("btnSnippet");
    if (btnSnippet) btnSnippet.onclick = async () => {
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

    const btnUpload = $("btnUpload");
    if (btnUpload) btnUpload.onclick = async () => {
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

    const btnStatus = $("btnStatus");
    if (btnStatus) btnStatus.onclick = async () => {
      const out = $("outStatus");
      out.textContent = "Checking...";
      try {
        const data = await request("/api/v1/tenant/knowledge/status");
        out.textContent = pretty(data);
      } catch (e) {
        out.textContent = String(e);
      }
    };

    const btnReindex = $("btnReindex");
    if (btnReindex) btnReindex.onclick = async () => {
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
        state.lastReplyReview = null;
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
    $("btnLoadOpsAudit").onclick = () => loadOpsAudit();
    $("btnRunPreflight").onclick = () => runPreflightChecks(false);
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
    const tabSetup = $("tabSetup");
    if (tabSetup) {
      tabSetup.onclick = () => {
        localStorage.setItem("tenant_console_active_pane", "setup");
        setActivePane("setup");
      };
    }
    const navDashboard = $("navDashboard");
    const navOps = $("navOps");
    const navSetup = $("navSetup");
    const path = (window.location.pathname || "").toLowerCase();
    if (path.includes("tenant-setup")) {
      if (navSetup) navSetup.classList.add("active");
    } else {
      if (navOps) navOps.classList.add("active");
    }
    if (navDashboard && !path.includes("dashboard")) navDashboard.classList.remove("active");
    const btnNavSignOut = $("btnNavSignOut");
    if (btnNavSignOut) {
      btnNavSignOut.onclick = () => {
        clearConsoleSession();
        $("outLogin").textContent = "Signed out.";
      };
    }
    $("toggleAdvanced").onchange = () => {
      localStorage.setItem("tenant_console_advanced", $("toggleAdvanced").checked ? "1" : "0");
      applyConsoleMode();
    };
    const roleModeEl = $("roleMode");
    if (roleModeEl) {
      roleModeEl.onchange = () => {
        localStorage.setItem("tenant_console_role_mode", roleModeEl.value || "operator");
        applyConsoleMode();
      };
    }

    (function bootstrap() {
      const savedToken = localStorage.getItem("tenant_console_token");
      const savedBase = localStorage.getItem("tenant_console_api_base");
      const savedStaging = localStorage.getItem("tenant_console_staging_api_base");
      const savedPane = localStorage.getItem("tenant_console_active_pane");
      const savedAdvanced = localStorage.getItem("tenant_console_advanced");
      const savedRoleMode = localStorage.getItem("tenant_console_role_mode");
      if (savedToken) setToken(savedToken);
      if (savedBase) $("apiBase").value = savedBase;
      if (savedStaging) $("stagingApiBase").value = savedStaging;
      if (savedRoleMode && roleModeEl && ["operator", "admin"].includes(savedRoleMode)) {
        roleModeEl.value = savedRoleMode;
      }
      if (savedAdvanced === "1") $("toggleAdvanced").checked = true;
      $("hfStatus").value = "new_open";
      $("hfSort").value = "urgent_escalated";
      $("hfEscalatedOnly").value = "false";
      if (!$("escSweepReason").value.trim()) $("escSweepReason").value = "scheduled SLA triage sweep";
      if (!$("cpMergeReason").value.trim()) $("cpMergeReason").value = "dedupe duplicate customer identities";
      const allowedPanes = tabSetup ? ["daily", "qa", "setup"] : ["daily", "qa"];
      const onSetupPage = (window.location.pathname || "").toLowerCase().includes("tenant-setup");
      const defaultPane = onSetupPage && tabSetup ? "setup" : "daily";
      setActivePane(savedPane && allowedPanes.includes(savedPane) ? savedPane : defaultPane);
      applyQaAvailability();
      renderCurrentUserBadge();
      syncCurrentUser().catch(() => {});
      loadOpsAudit();
      runPreflightChecks(true).catch(() => {});
      renderReleaseSnapshot();
      setQueueAutoRefresh();
    })();
