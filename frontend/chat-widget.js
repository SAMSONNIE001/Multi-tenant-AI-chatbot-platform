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
      ".mtw-head{padding:12px 14px;border-bottom:1px solid #eef1f4;font-weight:700;color:#0f172a;background:#f8fafc}" +
      ".mtw-log{height:360px;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px;background:#fff}" +
      ".mtw-msg{padding:10px 12px;border-radius:12px;max-width:85%;line-height:1.35;white-space:pre-wrap;word-break:break-word;font-size:14px}" +
      ".mtw-msg-you{align-self:flex-end;background:#e7f0ff;color:#0f172a}" +
      ".mtw-msg-bot{align-self:flex-start;background:#f3f4f6;color:#111827}" +
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
    var head = el("div", { class: "mtw-head", text: opts.title || "Live Chat" }, shell);
    var log = el("div", { class: "mtw-log" }, shell);
    var row = el("div", { class: "mtw-row" }, shell);
    var input = el("input", {
      class: "mtw-input",
      placeholder: opts.placeholder || "Ask a question...",
      "aria-label": "Chat input",
    }, row);
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

  function addMessage(log, text, from) {
    var cls = from === "you" ? "mtw-msg mtw-msg-you" : "mtw-msg mtw-msg-bot";
    var node = el("div", { class: cls, text: text }, log);
    log.scrollTop = log.scrollHeight;
    return node;
  }

  function createClient(config) {
    var base = String(config.apiBase || "").replace(/\/+$/, "");
    var botId = config.botId;
    var origin = normalizeOrigin(config.origin || window.location.origin);
    var sessionId = config.sessionId || ("sess_" + Math.random().toString(36).slice(2));
    var convStoreKey = "mtw_conv_" + botId + "_" + btoa(origin).replace(/=+$/g, "");
    var conversationId = config.conversationId || null;
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

    return { ask: ask, getWidgetToken: getWidgetToken };
  }

  function init(userConfig) {
    var config = Object.assign(
      {
        apiBase: "",
        botId: "",
        mode: "bubble", // bubble | inline
        title: "Live Chat",
        placeholder: "Ask a question...",
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
    var pending = false;

    function setPending(v) {
      pending = v;
      ui.send.disabled = v;
      ui.input.disabled = v;
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
        addMessage(ui.log, res.answer || "No answer", "bot");
      } catch (err) {
        addMessage(ui.log, "Error: " + (err && err.message ? err.message : "Unknown"), "bot");
      } finally {
        setPending(false);
        ui.input.focus();
      }
    }

    ui.send.addEventListener("click", sendMessage);
    ui.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") sendMessage();
    });
  }

  window.MTChatWidget = { init: init };
})();
