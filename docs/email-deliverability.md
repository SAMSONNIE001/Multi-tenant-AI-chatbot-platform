# SMTP + Deliverability Checklist

## App Env Vars
Set these in Railway for reliable password reset delivery:

- `SMTP_HOST`
- `SMTP_PORT` (commonly `587`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM` (must match sending domain policy)
- `SMTP_STARTTLS` (`true` for most providers)
- `FRONTEND_PUBLIC_BASE_URL` (used to generate reset link)
- `PASSWORD_RESET_EXP_MINUTES` (default `15`)

## DNS Records (Sending Domain)
Configure on the same domain used by `SMTP_FROM`:

1. SPF:
`TXT @ "v=spf1 include:<your-provider-spf> ~all"`

2. DKIM:
Add provider DKIM selector records (usually CNAME or TXT).

3. DMARC:
`TXT _dmarc "v=DMARC1; p=quarantine; rua=mailto:postmaster@<your-domain>; adkim=s; aspf=s"`

Use `p=none` only during warm-up, then move to `quarantine`/`reject`.

## Sender Hygiene
- Use a dedicated subdomain for transactional mail if possible (for example `mail.example.com`).
- Keep reset email short, plain, and non-promotional.
- Avoid URL shorteners in reset links.
- Ensure `From` domain alignment with SPF/DKIM.

## Verification Steps
1. Trigger forgot-password from staging dashboard.
2. Confirm email received in inbox (not spam).
3. Validate reset link opens dashboard with `reset_token`.
4. Reset password with token + code.
5. Confirm old password fails and new password succeeds.

## Production Execution Order
1. Confirm app env vars are set on production Railway service:
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`
   - `FRONTEND_PUBLIC_BASE_URL=https://www.staunchbot.com`
2. Confirm DNS alignment for the `SMTP_FROM` domain:
   - SPF includes your provider
   - DKIM selectors are valid
   - DMARC policy exists (`none` during warm-up, then `quarantine`/`reject`)
3. Run live production verification:
   - Open `https://www.staunchbot.com/dashboard.html`
   - Use Forgot Password with a real mailbox
   - Complete reset using token + code
4. Track placement across at least 2 mailbox providers (for example Gmail + Outlook).
5. If placement is stable for 48-72 hours, tighten DMARC policy.

## Troubleshooting
- If no email arrives:
  - Check startup logs for `Password reset email: partially configured`.
  - Verify SMTP creds and port.
  - Confirm provider account is out of sandbox mode.
- If email lands in spam:
  - Re-check SPF/DKIM/DMARC alignment.
  - Reduce template complexity and remove marketing phrases.
