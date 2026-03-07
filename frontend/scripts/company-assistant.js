(function () {
  "use strict";

  var DEFAULT_BOT_ID = "bot_20260226004603512396";
  var PROD_API_BASE = "https://api.staunchbot.com";
  var STAGING_API_BASE = "https://multi-tenant-ai-chatbot-platform-staging.up.railway.app";
  var COMPANY_ASSISTANT_KEY = "staunchbot_company_assistant_bot_id";

  function hostName() {
    return String(window.location.hostname || "").toLowerCase();
  }

  function isProdHost() {
    var host = hostName();
    return host === "www.staunchbot.com" || host === "staunchbot.com";
  }

  function isStagingHost() {
    return hostName().indexOf("staging") >= 0;
  }

  function resolveApiBase() {
    var hostBasedDefault = isProdHost() ? PROD_API_BASE : (isStagingHost() ? STAGING_API_BASE : PROD_API_BASE);
    var fromWindow = String(window.STAUNCHBOT_HELP_API_BASE || "").trim();
    if (fromWindow) return fromWindow.replace(/\/+$/, "");
    var fromStorage = "";
    try {
      fromStorage = String(localStorage.getItem("tenant_console_api_base") || "").trim();
    } catch (_) {}
    if (fromStorage && /^https?:\/\//i.test(fromStorage) && !/^https?:\/\/localhost(:\d+)?/i.test(fromStorage)) {
      return fromStorage.replace(/\/+$/, "");
    }
    return hostBasedDefault;
  }

  function resolveBotId() {
    var fromWindow = String(window.STAUNCHBOT_HELP_BOT_ID || "").trim();
    if (fromWindow) return fromWindow;
    var fromStorage = "";
    try {
      fromStorage = String(localStorage.getItem(COMPANY_ASSISTANT_KEY) || "").trim();
    } catch (_) {}
    return fromStorage || DEFAULT_BOT_ID;
  }

  function ensureWidgetLoaded(onReady) {
    if (window.MTChatWidget && typeof window.MTChatWidget.init === "function") {
      onReady();
      return;
    }
    var existing = document.getElementById("sb-company-assistant-widget-loader");
    if (existing) {
      existing.addEventListener("load", onReady, { once: true });
      return;
    }
    var script = document.createElement("script");
    script.id = "sb-company-assistant-widget-loader";
    script.src = "./chat-widget.js";
    script.async = true;
    script.onload = onReady;
    script.onerror = function () {};
    document.head.appendChild(script);
  }

  function initCompanyAssistant() {
    if (window.__sbCompanyAssistantMounted) return;
    if (!window.MTChatWidget || typeof window.MTChatWidget.init !== "function") return;

    window.__sbCompanyAssistantMounted = true;
    var apiBase = resolveApiBase();
    var botId = resolveBotId();

    try {
      window.MTChatWidget.init({
        apiBase: apiBase,
        botId: botId,
        mode: "bubble",
        title: "StaunchBot Help",
        subtitle: "Product Guide Assistant",
        companyName: "StaunchBot",
        assistantName: "StaunchBot Guide",
        welcomeMessage:
          "Welcome to StaunchBot. I can guide you through account setup, integrations, unified inbox, and knowledge base workflows.",
        placeholder: "Ask how to use any feature...",
      });
    } catch (_) {
      window.__sbCompanyAssistantMounted = false;
    }
  }

  function boot() {
    ensureWidgetLoaded(initCompanyAssistant);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();

