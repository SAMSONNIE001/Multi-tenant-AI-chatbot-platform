    const tcQa = window.TenantConsole;
    const {
      $,
      pretty,
      nowIso,
      getApiBase,
      isProdApiBase,
      switchApiBase,
      runPreflightChecks,
      updateQaChecklist,
      request,
      seedProfileActivity,
      loadProfiles,
      runEscalationSweep,
      loadHandoffQueue,
      loadEscalationMetrics,
      mergeProfiles,
    } = tcQa;
    const state = tcQa.state;

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
        if (state.lastProfiles.length >= 2) {
          $("cpSourceId").value = state.lastProfiles[0].id;
          $("cpTargetId").value = state.lastProfiles[1].id;
          $("cpMergeReason").value = `staging qa merge ${new Date().toISOString()}`;
          await runQaMergeFlow();
        }
        out.textContent = pretty({
          qa_pack: "staging_full",
          api_base: getApiBase(),
          profiles_loaded: state.lastProfiles.length,
          sweep_test: "completed",
          merge_test: state.lastProfiles.length >= 2 ? "completed" : "skipped_not_enough_profiles",
        });
        state.lastQaPack = { at: nowIso(), ok: true };
      } catch (e) {
        out.textContent = String(e);
        state.lastQaPack = { at: nowIso(), ok: false, error: String(e) };
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
        if (!state.lastQaPack || !state.lastQaPack.ok) throw new Error("staging qa pack reported failure");
        return state.lastQaPack;
      });

      await runStep("daily_ops.queue_load", async () => {
        await loadHandoffQueue(true);
        return { items: Array.isArray(state.lastQueueItems) ? state.lastQueueItems.length : 0 };
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
          before = (state.lastQueueItems || []).find((x) => x.id === selectedId) || null;
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
          before = (state.lastQueueItems || []).find((x) => x.id === selectedId) || candidate;
        }
        const beforePriority = String(before.priority || "").toLowerCase();
        const beforeEsc = !!before.escalation_flag;
        if (!$("escSweepReason").value.trim()) {
          $("escSweepReason").value = `qa sweep validation ${new Date().toISOString()}`;
        }
        const sweep = await runEscalationSweep();
        const after = (state.lastQueueItems || []).find((x) => x.id === selectedId);
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

    Object.assign(tcQa, {
      runStagingQaPack,
      runUatPack,
      runQaSweepFlow,
      runQaMergeFlow,
    });

