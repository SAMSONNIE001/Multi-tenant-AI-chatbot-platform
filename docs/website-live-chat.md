# Website Live Chat Integration

This project already exposes public embed endpoints:

- `POST /api/v1/public/embed/widget-token/by-bot/{bot_id}`
- `POST /api/v1/public/embed/ask`

## 1) Create bot credentials (admin)

Login in Swagger, then create a bot:

`POST /api/v1/embed/bots`

```json
{
  "name": "Main Website Bot",
  "allowed_origins": ["http://localhost:3000"]
}
```

Save returned `id` as `bot_id`.

## 2) Use the widget script

Host `frontend/chat-widget.js` on your frontend domain, then add:

```html
<script src="https://YOUR-FRONTEND-DOMAIN/chat-widget.js"></script>
<script>
  window.MTChatWidget.init({
    apiBase: "https://multi-tenant-ai-chatbot-platform-production.up.railway.app",
    botId: "BOT_ID_HERE",
    mode: "bubble",
    title: "Ask us anything",
    placeholder: "Type your question..."
  });
</script>
```

## 3) Local test

Use the included page:

- `frontend/widget-test.html`

Run:

```powershell
python -m http.server 3000 --directory frontend
```

Open:

- `http://localhost:3000/widget-test.html`

## 4) Security notes

- Do not expose bot API keys in browser in production.
- Use `allowed_origins` strictly per tenant domain.
- Rotate bot keys periodically via `POST /api/v1/embed/bots/{bot_id}/rotate-key`.

