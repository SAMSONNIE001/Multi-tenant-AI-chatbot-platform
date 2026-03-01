/* Multi-tenant website chat widget (vanilla JS, no build step) */
(function () {
  "use strict";

  function el(tag, attrs, parent) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "text") node.textContent = attrs[k];
        else if (k === "html") node.innerHTML = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  function normalizeOrigin(origin) {
    return String(origin || "").trim().replace(/\/+$/, "").toLowerCase();
  }

  function createStyles() {
    if (document.getElementById("mt-chat-widget-css")) return;
    var style = el("style", { id: "mt-chat-widget-css" });
    style.textContent =
      ".mtw-shell{position:fixed;right:18px;bottom:18px;width:360px;max-width:calc(100vw - 24px);background:#fff;border:1px solid #e4e6eb;border-radius:12px;box-shadow:0 20px 45px rgba(0,0,0,.18);font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;overflow:hidden;z-index:999999}" +
      ".mtw-head{padding:10px 12px;border-bottom:1px solid #eef1f4;font-weight:700;color:#0f172a;background:#f8fafc;display:flex;align-items:center;gap:10px}" +
      ".mtw-head-titles{line-height:1.2;display:flex;flex-direction:column}" +
      ".mtw-head-title{font-weight:700}" +
      ".mtw-head-subtitle{font-size:11px;color:#64748b;font-weight:500;margin-top:2px}" +
      ".mtw-avatar{width:28px;height:28px;border-radius:999px;object-fit:cover;display:inline-block;background:#dbeafe}" +
      ".mtw-avatar-fallback{width:28px;height:28px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;background:#0f766e;color:#fff;font-size:12px;font-weight:700}" +
      ".mtw-log{height:360px;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px;background:#fff}" +
      ".mtw-msg{padding:10px 12px;border-radius:12px;max-width:85%;line-height:1.35;white-space:pre-wrap;word-break:break-word;font-size:14px}" +
      ".mtw-msg-you{align-self:flex-end;background:#e7f0ff;color:#0f172a}" +
      ".mtw-msg-bot{align-self:flex-start;background:#f3f4f6;color:#111827}" +
      ".mtw-bot-row{display:flex;align-items:flex-start;gap:8px;align-self:flex-start;max-width:100%}" +
      ".mtw-bot-row .mtw-avatar,.mtw-bot-row .mtw-avatar-fallback{width:22px;height:22px;flex:0 0 22px;margin-top:2px}" +
      ".mtw-row{display:flex;gap:8px;padding:10px;border-top:1px solid #eef1f4;background:#fff}" +
      ".mtw-input{flex:1;min-width:0;padding:9px 10px;border:1px solid #d1d5db;border-radius:9px;outline:none}" +
      ".mtw-input:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.15)}" +
      ".mtw-send{padding:9px 12px;border:0;border-radius:9px;background:#0f766e;color:#fff;cursor:pointer}" +
      ".mtw-send:disabled{opacity:.6;cursor:not-allowed}" +
      ".mtw-fab{position:fixed;right:18px;bottom:18px;width:56px;height:56px;border-radius:999px;border:0;background:#0f766e;color:#fff;box-shadow:0 12px 28px rgba(0,0,0,.22);cursor:pointer;z-index:999998;font-size:22px}" +
      ".mtw-hidden{display:none}";
    document.head.appendChild(style);
  }

  function createUI(opts) {
    var showFab = opts.mode === "bubble";
    var shell = el("section", { class: "mtw-shell" });
    var head = el("div", { class: "mtw-head" }, shell);
    var titles = el("div", { class: "mtw-head-titles" }, head);
    var title = el("div", { class: "mtw-head-title", text: opts.title || "Live Chat" }, titles);
    if (opts.subtitle) {
      el("div", { class: "mtw-head-subtitle", text: opts.subtitle }, titles);
    }
    if (opts.avatarUrl) {
      var avatar = el("img", { class: "mtw-avatar", src: opts.avatarUrl, alt: "Bot avatar" }, head);
      avatar.onerror = function () {
        avatar.replaceWith(el("span", { class: "mtw-avatar-fallback", text: "AI" }));
      };
      head.insertBefore(avatar, titles);
    } else {
      head.insertBefore(el("span", { class: "mtw-avatar-fallback", text: "AI" }), titles);
    }

    var log = el("div", { class: "mtw-log" }, shell);
    var row = el("div", { class: "mtw-row" }, shell);
    var input = el(
      "input",
      {
        class: "mtw-input",
        placeholder: opts.placeholder || "Ask a question...",
        "aria-label": "Chat input",
      },
      row
    );
    var send = el("button", { class: "mtw-send", text: "Send", type: "button" }, row);

    var fab = null;
    if (showFab) {
      shell.classList.add("mtw-hidden");
      fab = el("button", { class: "mtw-fab", type: "button", text: "💬", "aria-label": "Open chat" }, document.body);
      fab.addEventListener("click", function () {
        fab.classList.add("mtw-hidden");
        shell.classList.remove("mtw-hidden");
      });
      head.style.cursor = "pointer";
      head.title = "Click to minimize";
      head.addEventListener("click", function () {
        shell.classList.add("mtw-hidden");
        fab.classList.remove("mtw-hidden");
      });
    }

    document.body.appendChild(shell);
    return { shell: shell, log: log, input: input, send: send, fab: fab };
  }

  function addMessage(log, text, from, opts) {
    opts = opts || {};
    var cls = from === "you" ? "mtw-msg mtw-msg-you" : "mtw-msg mtw-msg-bot";
    var node = null;
    if (from === "bot") {
      var row = el("div", { class: "mtw-bot-row" }, log);
      if (opts.avatarUrl) {
        var img = el("img", { class: "mtw-avatar", src: opts.avatarUrl, alt: "Bot avatar" }, row);
        img.onerror = function () {
          img.replaceWith(el("span", { class: "mtw-avatar-fallback", text: "AI" }));
        };
      } else {
        el("span", { class: "mtw-avatar-fallback", text: "AI" }, row);
      }
      node = el("div", { class: cls, text: text }, row);
    } else {
      node = el("div", { class: cls, text: text }, log);
    }
    log.scrollTop = log.scrollHeight;
    return node;
  }

  function cleanAssistantText(text) {
    var s = String(text || "");
    s = s.replace(/\s*\[[^\]]+:[^\]]+\]\s*/g, " ").trim();
    s = s.replace(/\s{2,}/g, " ");
    return s;
  }

  function createClient(config) {
    var base = String(config.apiBase || "").replace(/\/+$/, "");
    var botId = config.botId;
    var origin = normalizeOrigin(config.origin || window.location.origin);
    var sessionId = config.sessionId || ("sess_" + Math.random().toString(36).slice(2));
    var convStoreKey = "mtw_conv_" + botId + "_" + btoa(origin).replace(/=+$/g, "");
    var conversationId = config.conversationId || null;
    var updatesCursorIso = null;
    try {
      if (!conversationId && window.localStorage) {
        conversationId = window.localStorage.getItem(convStoreKey);
      }
    } catch (_) {}
    var widgetToken = null;

    async function getWidgetToken() {
      var res = await fetch(base + "/api/v1/public/embed/widget-token/by-bot/" + encodeURIComponent(botId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin: origin, session_id: sessionId }),
      });
      if (!res.ok) throw new Error("widget-token failed (" + res.status + ")");
      var data = await res.json();
      widgetToken = data.token;
      return widgetToken;
    }

    async function ask(question, topK, memoryTurns) {
      if (!widgetToken) await getWidgetToken();
      var res = await fetch(base + "/api/v1/public/embed/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          widget_token: widgetToken,
          question: question,
          top_k: topK || 5,
          memory_turns: memoryTurns || 8,
          conversation_id: conversationId,
        }),
      });

      if (res.status === 401) {
        widgetToken = null;
      }
      if (!res.ok) throw new Error("ask failed (" + res.status + ")");
      var data = await res.json();
      if (data && data.conversation_id) {
        conversationId = data.conversation_id;
        try {
          if (window.localStorage) {
            window.localStorage.setItem(convStoreKey, conversationId);
          }
        } catch (_) {}
      }
      return data;
    }

    async function getUpdates() {
      if (!conversationId) return { conversation_id: null, items: [] };
      if (!widgetToken) await getWidgetToken();

      var payload = {
        widget_token: widgetToken,
        conversation_id: conversationId,
      };
      if (updatesCursorIso) payload.since_iso = updatesCursorIso;

      var res = await fetch(base + "/api/v1/public/embed/conversation/updates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.status === 401) widgetToken = null;
      if (!res.ok) throw new Error("conversation-updates failed (" + res.status + ")");

      var data = await res.json();
      var items = (data && data.items) || [];
      if (items.length > 0) {
        updatesCursorIso = items[items.length - 1].created_at || updatesCursorIso;
      }
      return data;
    }

    return { ask: ask, getWidgetToken: getWidgetToken, getUpdates: getUpdates };
  }

  function init(userConfig) {
    var config = Object.assign(
      {
        apiBase: "",
        botId: "",
        mode: "bubble",
        title: "Live Chat",
        subtitle: "",
        companyName: "",
        assistantName: "",
        welcomeMessage: "",
        placeholder: "Ask a question...",
        avatarUrl: "",
        topK: 5,
        memoryTurns: 8,
      },
      userConfig || {}
    );

    if (!config.apiBase) throw new Error("MTChatWidget: apiBase is required");
    if (!config.botId) throw new Error("MTChatWidget: botId is required");

    createStyles();
    var ui = createUI(config);
    var client = createClient(config);
    var seenAgentMessageIds = {};
    var pollHandle = null;
    var pending = false;
    function setPending(v) {
      pending = v;
      ui.send.disabled = v;
      ui.input.disabled = v;
    }

    function buildWelcomeMessage() {
      if (config.welcomeMessage && String(config.welcomeMessage).trim()) {
        return String(config.welcomeMessage).trim();
      }
      var company = String(config.companyName || "").trim() || "our company";
      var assistant = String(config.assistantName || "").trim() || "AI Assistant";
      return "Welcome to " + company + ". I'm " + assistant + ", your AI customer agent. How can I help you today?";
    }

    async function sendMessage() {
      if (pending) return;
      var q = ui.input.value.trim();
      if (!q) return;
      ui.input.value = "";
      addMessage(ui.log, q, "you");
      setPending(true);
      try {
        var res = await client.ask(q, config.topK, config.memoryTurns);
        addMessage(ui.log, cleanAssistantText(res.answer || "No answer"), "bot", {
          avatarUrl: config.avatarUrl || "",
        });
      } catch (err) {
        addMessage(ui.log, "Error: " + (err && err.message ? err.message : "Unknown"), "bot", {
          avatarUrl: config.avatarUrl || "",
        });
      } finally {
        setPending(false);
        ui.input.focus();
      }
    }

    async function pollAgentUpdates() {
      try {
        var data = await client.getUpdates();
        var items = (data && data.items) || [];
        for (var i = 0; i < items.length; i++) {
          var item = items[i];
          if (!item || item.role !== "agent") continue;
          if (item.id && seenAgentMessageIds[item.id]) continue;
          if (item.id) seenAgentMessageIds[item.id] = 1;
          addMessage(ui.log, cleanAssistantText(item.content || ""), "bot", {
            avatarUrl: config.avatarUrl || "",
          });
        }
      } catch (_) {
        // Silent: polling should not interrupt chat flow.
      }
    }

    ui.send.addEventListener("click", sendMessage);
    ui.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") sendMessage();
    });

    // Show immediate welcome when chat opens, before user sends first message.
    addMessage(ui.log, buildWelcomeMessage(), "bot", {
      avatarUrl: config.avatarUrl || "",
    });

    pollHandle = window.setInterval(pollAgentUpdates, 3000);
    ui.shell.addEventListener("remove", function () {
      if (pollHandle) window.clearInterval(pollHandle);
    });
  }

  window.MTChatWidget = { init: init };
})();
