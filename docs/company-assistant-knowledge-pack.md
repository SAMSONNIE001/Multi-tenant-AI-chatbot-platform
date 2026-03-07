# StaunchBot Product Guide: Company Assistant Knowledge Pack

## What is StaunchBot?
StaunchBot is a multi-tenant AI customer support platform. Each company account has its own workspace, bot credentials, knowledge base, integrations, and unified inbox.

## Main Pages and What They Do
### 1) Dashboard
- Gives a live summary of operations.
- Shows open queue, escalations, resolved volume, and integration status.
- Use this page for quick health checks.

### 2) Unified Inbox
- Central place for incoming support conversations.
- Agents can review tickets, add notes, send replies, and track escalations.
- Use this page for day-to-day customer response operations.

### 3) Integrations
- Connect customer channels such as:
  - Website Live Chat
  - WhatsApp Business
  - Facebook Messenger
- Shows whether each channel is connected and healthy.

### 4) Knowledge Base
- Upload support documents and internal help content.
- Reindex content after major edits.
- The AI uses this content to generate grounded support responses.

### 5) Profile
- Lets users manage personal profile info and image.
- Can also set user-level preferences.

### 6) Settings
- Account security and password management.
- Use “Forgot Password” flow to receive reset email + 6-digit code.
- If login fails repeatedly, account may be temporarily blocked and user should reset password.

## Authentication Flow
### Sign In
- User enters email + password.
- If same email exists in multiple tenants, tenant ID may be required.

### Create Account
- User provides company name, admin email, and admin password.
- System creates tenant workspace and signs user in automatically.

### Forgot/Reset Password
- User requests reset using account email.
- System sends reset email and 6-digit code.
- User enters code and new password to complete reset.

## Best Practices for Teams
- Use strong passwords and avoid password reuse.
- Keep integrations connected only with valid production tokens.
- Upload approved, up-to-date knowledge documents.
- Review inbox regularly and escalate unresolved conversations quickly.
- Keep bot content aligned with real product workflows.

## Common Issues and Fixes
### “Login failed”
- Check email and password.
- If multiple tenants share the email, provide tenant ID.
- After repeated failures, request password reset.

### “Integration not connected”
- Verify channel access token and channel IDs.
- Confirm app permissions on provider side (Meta/WhatsApp).

### “Knowledge base not answering correctly”
- Upload missing documents.
- Reindex after edits.
- Remove outdated or conflicting documents.

### “No live data on dashboard”
- Confirm user is signed in.
- Confirm API base points to production (`https://api.staunchbot.com`) on production host.

## Support Tone for Assistant
- Be concise and practical.
- Give step-by-step instructions for UI actions.
- Use user-friendly language.
- Suggest the next single best action when user is stuck.

