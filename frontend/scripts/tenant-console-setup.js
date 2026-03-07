(() => {
    const tcSetup = window.TenantConsole;
    const {
      $,
      setToken,
      saveSessionToken,
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
      syncChannelIntegrations,
      isProdFrontendHost,
    } = tcSetup;
    const state = tcSetup.state;

    function cleanError(e) {
      const raw = String(e || "Request failed");
      if (raw.includes("401")) return "Session expired. Please sign in again.";
      if (raw.includes("403")) return "You do not have permission to perform this action.";
      if (raw.includes("404")) return "Requested resource was not found.";
      if (raw.includes("409") && raw.includes("Provide tenant_id")) return "This email belongs to multiple tenants. Enter Tenant ID and try again.";
      if (raw.includes("Handoff has no conversation_id")) return "This ticket has no linked conversation yet. Wait for a real inbound message before sending an agent reply.";
      if (raw.includes("422")) return "Some fields are invalid. Check your inputs and try again.";
      if (raw.includes("500")) return "Server error. Please try again in a moment.";
      return raw.replace(/^\d+\s+/, "").slice(0, 220);
    }

    function pluralize(count, one, many) {
      return `${count} ${count === 1 ? one : many}`;
    }

    function setKnowledgeEmptyState(visible) {
      const el = $("kbEmptyState");
      if (!el) return;
      el.style.display = visible ? "block" : "none";
    }

    $("saveToken").onclick = () => {
      saveSessionToken($("accessToken").value);
      localStorage.setItem("tenant_console_api_base", $("apiBase").value);
      localStorage.setItem("tenant_console_staging_api_base", $("stagingApiBase").value);
      alert("Saved.");
    };

    $("clearToken").onclick = () => {
      sessionStorage.removeItem("tenant_console_token");
      localStorage.removeItem("tenant_console_token");
      setToken("");
      syncChannelIntegrations().catch(() => {});
    };

    const btnOnboard = $("btnOnboard");
    if (btnOnboard) btnOnboard.onclick = async () => {
      const out = $("outOnboard");
      out.textContent = "Creating tenant workspace...";
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
        out.textContent = `Tenant created successfully${data?.tenant?.id ? ` (ID: ${data.tenant.id})` : ""}.`;
        if (data && data.access_token) {
          setToken(data.access_token);
          saveSessionToken(data.access_token);
        }
        if (data && data.bot_id) $("botId").value = data.bot_id;
      } catch (e) {
        out.textContent = String(e);
      }
    };

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
        const data = await request("/api/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        $("lgTenantIdRow").style.display = "none";
        $("lgTenantId").value = "";
        out.textContent = `Signed in successfully as ${body.email}.`;
        if (data && data.access_token) {
          setToken(data.access_token);
          saveSessionToken(data.access_token);
          await syncCurrentUser();
          await populateChannelSetupFields();
        }
      } catch (e) {
        const msg = String(e || "");
        if (msg.includes("409") && msg.includes("Provide tenant_id")) {
          $("lgTenantIdRow").style.display = "grid";
          $("lgTenantId").focus();
        }
        out.textContent = cleanError(e);
      }
    };

    async function populateChannelSetupFields() {
      const waName = $("waName");
      if (!waName) return;
      try {
        const accounts = await request("/api/v1/admin/channels/accounts");
        const rows = Array.isArray(accounts) ? accounts : [];
        const wa = rows.find((a) => String(a.channel_type || "").toLowerCase() === "whatsapp");
        const fb = rows.find((a) => {
          const t = String(a.channel_type || "").toLowerCase();
          return t === "facebook" || t === "messenger";
        });
        if (wa) {
          $("waName").value = wa.name || "";
          $("waPhoneNumberId").value = wa.phone_number_id || "";
          $("btnSaveWhatsApp").setAttribute("data-account-id", wa.id || "");
        } else {
          $("btnSaveWhatsApp").setAttribute("data-account-id", "");
        }
        if (fb) {
          $("fbName").value = fb.name || "";
          $("fbPageId").value = fb.page_id || "";
          $("btnSaveFacebook").setAttribute("data-account-id", fb.id || "");
        } else {
          $("btnSaveFacebook").setAttribute("data-account-id", "");
        }
      } catch (_) {
        // Non-admin users can still use console, but cannot mutate channel accounts.
      }
    }

    const btnReloadIntegrations = $("btnReloadIntegrations");
    if (btnReloadIntegrations) {
      btnReloadIntegrations.onclick = async () => {
        const out = $("outIntegrationSetup");
        out.textContent = "Reloading integration status...";
        try {
          await syncChannelIntegrations();
          await populateChannelSetupFields();
          out.textContent = "Integration status reloaded.";
        } catch (e) {
          out.textContent = cleanError(e);
        }
      };
    }

    const btnSaveWhatsApp = $("btnSaveWhatsApp");
    if (btnSaveWhatsApp) {
      btnSaveWhatsApp.onclick = async () => {
        const out = $("outIntegrationSetup");
        out.textContent = "Saving WhatsApp channel...";
        try {
          const name = $("waName").value.trim() || "WhatsApp Main";
          const accessToken = $("waAccessToken").value.trim();
          const phoneNumberId = $("waPhoneNumberId").value.trim();
          const appSecret = $("waAppSecret").value.trim();
          if (!accessToken || accessToken.length < 8) throw new Error("Provide a valid WhatsApp access token.");
          if (!phoneNumberId || phoneNumberId.length < 3) throw new Error("Provide a valid phone number ID.");

          const body = {
            name,
            access_token: accessToken,
            phone_number_id: phoneNumberId,
            is_active: true,
          };
          if (appSecret) body.app_secret = appSecret;

          const accountId = $("btnSaveWhatsApp").getAttribute("data-account-id") || "";
          const data = accountId
            ? await request(`/api/v1/admin/channels/accounts/${encodeURIComponent(accountId)}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            })
            : await request("/api/v1/admin/channels/accounts", {
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
          out.textContent = `WhatsApp channel saved${data?.id ? ` (Account ID: ${data.id})` : ""}.`;
          await syncChannelIntegrations();
          await populateChannelSetupFields();
        } catch (e) {
          out.textContent = cleanError(e);
        }
      };
    }

    const btnSaveFacebook = $("btnSaveFacebook");
    if (btnSaveFacebook) {
      btnSaveFacebook.onclick = async () => {
        const out = $("outIntegrationSetup");
        out.textContent = "Saving Facebook Messenger channel...";
        try {
          const name = $("fbName").value.trim() || "Facebook Main";
          const accessToken = $("fbAccessToken").value.trim();
          const pageId = $("fbPageId").value.trim();
          const appSecret = $("fbAppSecret").value.trim();
          if (!accessToken || accessToken.length < 8) throw new Error("Provide a valid Facebook page token.");
          if (!pageId || pageId.length < 3) throw new Error("Provide a valid Facebook page ID.");

          const body = {
            name,
            access_token: accessToken,
            page_id: pageId,
            is_active: true,
          };
          if (appSecret) body.app_secret = appSecret;

          const accountId = $("btnSaveFacebook").getAttribute("data-account-id") || "";
          const data = accountId
            ? await request(`/api/v1/admin/channels/accounts/${encodeURIComponent(accountId)}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            })
            : await request("/api/v1/admin/channels/accounts", {
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
          out.textContent = `Facebook Messenger channel saved${data?.id ? ` (Account ID: ${data.id})` : ""}.`;
          await syncChannelIntegrations();
          await populateChannelSetupFields();
        } catch (e) {
          out.textContent = cleanError(e);
        }
      };
    }

    const btnBots = $("btnBots");
    if (btnBots) btnBots.onclick = async () => {
      const out = $("outBots");
      out.textContent = "Loading bots...";
      try {
        const data = await request("/api/v1/tenant/bots");
        const bots = Array.isArray(data) ? data : [];
        out.textContent = bots.length
          ? `${pluralize(bots.length, "bot", "bots")} available for this workspace.`
          : "No bots found yet. Create your first bot to continue.";
        if (Array.isArray(data) && data.length && data[0].id) {
          $("botId").value = data[0].id;
        }
      } catch (e) {
        out.textContent = cleanError(e);
      }
    };

    const btnSnippet = $("btnSnippet");
    if (btnSnippet) btnSnippet.onclick = async () => {
      const out = $("outSnippet");
      out.textContent = "Generating embed snippet...";
      try {
        const botId = $("botId").value.trim();
        if (!botId) throw new Error("Provide bot id first.");
        const data = await request(`/api/v1/tenant/embed/snippet?bot_id=${encodeURIComponent(botId)}`);
        out.textContent = data.snippet_html
          ? "Embed snippet generated. Copy the code and add it to your website."
          : "Snippet generated successfully.";
      } catch (e) {
        out.textContent = cleanError(e);
      }
    };

    const btnUpload = $("btnUpload");
    if (btnUpload) btnUpload.onclick = async () => {
      const out = $("outUpload");
      out.textContent = "Uploading document...";
      try {
        const file = $("kgFile").files[0];
        if (!file) throw new Error("Pick a file first.");
        const fd = new FormData();
        fd.append("file", file);
        const data = await request("/api/v1/tenant/knowledge/upload", {
          method: "POST",
          body: fd,
        });
        const docId = data && data.document_id ? String(data.document_id) : "";
        out.textContent = docId
          ? `Upload complete. Document ID: ${docId}`
          : "Upload complete. Document queued for indexing.";
        setKnowledgeEmptyState(false);
        if (data && data.document_id) $("kgDocId").value = data.document_id;
      } catch (e) {
        out.textContent = cleanError(e);
      }
    };

    const btnStatus = $("btnStatus");
    if (btnStatus) btnStatus.onclick = async () => {
      const out = $("outStatus");
      out.textContent = "Checking knowledge base status...";
      try {
        const data = await request("/api/v1/tenant/knowledge/status");
        const docs = Number(data?.documents_total ?? data?.total_documents ?? 0);
        const indexed = Number(data?.indexed_documents ?? data?.ready_documents ?? 0);
        out.textContent = `Knowledge base status: ${pluralize(docs, "document", "documents")} total, ${indexed} indexed.`;
        setKnowledgeEmptyState(docs <= 0);
      } catch (e) {
        out.textContent = cleanError(e);
      }
    };

    const btnReindex = $("btnReindex");
    if (btnReindex) btnReindex.onclick = async () => {
      const out = $("outStatus");
      out.textContent = "Starting reindex job...";
      try {
        const docId = $("kgDocId").value.trim();
        if (!docId) throw new Error("Provide document id.");
        const data = await request("/api/v1/tenant/knowledge/reindex", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ document_id: docId }),
        });
        const jobId = data?.job_id || data?.task_id || null;
        out.textContent = jobId
          ? `Reindex started for ${docId}. Job ID: ${jobId}`
          : `Reindex started for ${docId}.`;
      } catch (e) {
        out.textContent = cleanError(e);
      }
    };

    const btnAuthSecurityEvents = $("btnAuthSecurityEvents");
    if (btnAuthSecurityEvents) btnAuthSecurityEvents.onclick = async () => {
      const out = $("outAuthSecurityEvents");
      out.textContent = "Loading auth security events...";
      try {
        const sinceHours = Number($("aseSinceHours").value || 24);
        const qs = new URLSearchParams({
          limit: "50",
          offset: "0",
          since_hours: String(Number.isFinite(sinceHours) && sinceHours > 0 ? sinceHours : 24),
        });
        const eventType = $("aseEventType").value.trim();
        const outcome = $("aseOutcome").value.trim();
        if (eventType) qs.set("event_type", eventType);
        if (outcome) qs.set("outcome", outcome);
        const data = await request(`/api/v1/admin/auth/security-events?${qs.toString()}`);
        const count = Number(data?.count ?? 0);
        out.textContent = `${pluralize(count, "security event", "security events")} loaded.`;
      } catch (e) {
        out.textContent = cleanError(e);
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
        const selected = (state.lastQueueItems || []).find((x) => String(x.id || "") === handoffId);
        const convId = String((selected && selected.conversation_id) || $("convId").value.trim() || "");
        if (!convId) throw new Error("This ticket has no linked conversation yet. Wait for a real inbound message before sending an agent reply.");
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
        out.textContent = cleanError(e);
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
      localStorage.setItem("tenant_console_active_pane", "daily");
      setActivePane("daily");
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
        syncChannelIntegrations().catch(() => {});
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
      const prodFrontend = isProdFrontendHost();
      const savedToken = sessionStorage.getItem("tenant_console_token") || localStorage.getItem("tenant_console_token");
      if (!savedToken) {
        const page = (window.location.pathname || "").toLowerCase().includes("tenant-setup")
          ? "tenant-setup.html"
          : "tenant-console.html";
        window.location.replace(`./auth.html?auth_required=1&next=${encodeURIComponent(page)}`);
        return;
      }
      const savedBase = localStorage.getItem("tenant_console_api_base");
      const savedStaging = localStorage.getItem("tenant_console_staging_api_base");
      const defaultStagingBase = "https://multi-tenant-ai-chatbot-platform-staging.up.railway.app";
      const savedPane = localStorage.getItem("tenant_console_active_pane");
      const savedAdvanced = localStorage.getItem("tenant_console_advanced");
      const savedRoleMode = localStorage.getItem("tenant_console_role_mode");
      const onSetupPage = (window.location.pathname || "").toLowerCase().includes("tenant-setup");
      setKnowledgeEmptyState(onSetupPage);
      const tabDaily = $("tabDaily");
      const tabQa = $("tabQa");
      if (onSetupPage && tabDaily) tabDaily.style.display = "none";
      if (tabQa) tabQa.style.display = "none";
      if (savedToken) setToken(savedToken);
      if (savedToken) saveSessionToken(savedToken);
      const host = String(window.location.hostname || "").toLowerCase();
      const hostedDefaultBase = (host === "www.staunchbot.com" || host === "staunchbot.com") ? "https://api.staunchbot.com" : "";
      if (savedBase) $("apiBase").value = savedBase;
      if (hostedDefaultBase && (!savedBase || /^https?:\/\/localhost(:\d+)?/i.test(savedBase))) {
        $("apiBase").value = hostedDefaultBase;
      }
      $("stagingApiBase").value = savedStaging || defaultStagingBase;
      if (savedRoleMode && roleModeEl && ["operator", "admin"].includes(savedRoleMode)) {
        roleModeEl.value = savedRoleMode;
      }
      if (roleModeEl) {
        const roleRow = roleModeEl.closest(".row");
        if (roleRow) roleRow.style.display = "none";
      }
      const advToggle = $("toggleAdvanced");
      if (advToggle) {
        const toggleLabel = advToggle.closest("label");
        if (toggleLabel) toggleLabel.style.display = "none";
      }
      if (savedAdvanced === "1") $("toggleAdvanced").checked = true;
      $("hfStatus").value = "new_open";
      $("hfSort").value = "urgent_escalated";
      $("hfEscalatedOnly").value = "false";
      if (!$("escSweepReason").value.trim()) $("escSweepReason").value = "scheduled SLA triage sweep";
      if (!$("cpMergeReason").value.trim()) $("cpMergeReason").value = "dedupe duplicate customer identities";
      const allowedPanes = onSetupPage
        ? ["setup"]
        : (tabSetup ? ["daily", "setup"] : ["daily"]);
      const defaultPane = onSetupPage && tabSetup ? "setup" : "daily";
      setActivePane(savedPane && allowedPanes.includes(savedPane) ? savedPane : defaultPane);
      applyQaAvailability();
      renderCurrentUserBadge();
      if (sessionStorage.getItem("tenant_console_session_expired") === "1") {
        const outLogin = $("outLogin");
        if (outLogin) outLogin.textContent = "Session expired. Please sign in again.";
        sessionStorage.removeItem("tenant_console_session_expired");
      }
      syncCurrentUser().catch(() => {});
      syncChannelIntegrations().catch(() => {});
      populateChannelSetupFields().catch(() => {});
      if (savedToken) {
        loadOpsAudit();
        runPreflightChecks(true).catch(() => {});
        renderReleaseSnapshot();
      } else {
        const outLogin = $("outLogin");
        if (outLogin) outLogin.textContent = "Sign in to load tenant operations.";
      }
      setQueueAutoRefresh();
    })();
})();

