# MindAI Security Policies

## Responsible Disclosure

If you discover a security vulnerability, please report it to **security@mindai.local** (replace with real address).
Do **not** open a public GitHub issue for security vulnerabilities.

We will acknowledge receipt within 48 hours and provide a resolution timeline within 7 days.

---

## Security Architecture Summary

### Zero Trust Principles Applied

| Layer | Control |
|-------|---------|
| API Auth | JWT HS256, 15min expiry, refresh rotation |
| Passwords | Argon2id via passlib |
| Transport | HTTPS enforced, HSTS headers |
| Input | Prompt injection detection on all user inputs |
| Output | Security policy kernel redacts PII and secrets |
| Access Control | Resource ownership checked per-request (never trust client claims) |
| Audit | Append-only audit log for all sensitive actions |
| Rate Limiting | Redis sliding window per IP (auth) and per-user (API) |
| Sessions | Device sessions tracked; tokens stored as SHA-256 hash only |

### OWASP API Top 10 Controls

| Risk | Mitigation |
|------|-----------|
| API1 - Broken Object Level Authorization | `assert_owns_*()` on every resource route |
| API2 - Broken Authentication | Short-lived JWT + refresh rotation + Argon2id |
| API3 - Broken Object Property Level Authorization | Response models exclude sensitive fields |
| API4 - Unrestricted Resource Consumption | Rate limiter + input length limits |
| API5 - Broken Function Level Authorization | `CurrentAdmin` dependency on all admin routes |
| API6 - Unrestricted Access to Sensitive Business Flows | Consent gates on screen guardian and memory |
| API7 - Server Side Request Forgery | No external URL fetching from user input |
| API8 - Security Misconfiguration | SecurityHeadersMiddleware, production guards |
| API9 - Improper Inventory Management | /docs disabled in production |
| API10 - Unsafe Consumption of APIs | Provider abstractions + output sanitization |

### Data Minimization

- Raw user inputs: stored as reference hashes, not raw text, wherever possible
- Screenshots: never stored (`raw_image_stored = False` default)
- IP addresses: stored as SHA-256 hashes only
- User agents: stored as SHA-256 hashes only
- Refresh tokens: stored as SHA-256 hashes only (never raw)
- Free-text feedback: presence flag only stored (not content)

### Consent Architecture

All privacy-sensitive features require explicit opt-in:
- `data_processing`: required for advisor use
- `screen_guardian`: required for screen analysis
- `local_memory`: required for cross-session context
- `analytics`: optional, anonymized only
- `research`: optional, explicit consent

Default for all consent flags: `False` (privacy-protective).

---

## Threat Model

### Trust Boundaries

```
[Mobile App] -- UNTRUSTED --> [API Gateway] --> [Identity Engine] --> [DB]
                                    |
                              JWT verification
                              Input validation
                              Injection detection
                              Rate limiting
```

### Key Threats Addressed

1. **Prompt Injection**: 14-pattern regex detector blocks adversarial inputs before they reach the LLM layer
2. **Identity Spoofing**: `user_id` always resolved from JWT — never accepted from client payload
3. **Blueprint Tampering**: Blueprint objects are `frozen=True` dataclasses; checksum verified at load time
4. **Manipulation via Screen Guardian**: Reality check kernel detects manipulation patterns in analyzed text
5. **Data Exfiltration via Response**: Security policy kernel redacts PII and credentials from all outgoing text
6. **Session Hijacking**: Refresh token rotation — old token revoked on each refresh

---

## Security Testing

Run the security check suite:
```bash
make security-check
```

This runs:
- `bandit -r app -ll` (SAST)
- `pip-audit` (dependency CVE scan)
- `ruff check` (linting)
