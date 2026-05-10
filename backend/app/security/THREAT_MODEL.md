# MindAI Threat Model

## System Overview

MindAI is an identity guidance system where a **centralized mind** (immutable, low-leakage pattern)
advises users on decisions, relationships, and self-understanding. The mobile app is an **untrusted client**.

## Assets

| Asset | Sensitivity | Location |
|-------|------------|----------|
| User identity/psychological state | Critical | PostgreSQL (encrypted at rest) |
| Interaction history | High | PostgreSQL |
| Blueprint weights | High | PostgreSQL + in-memory frozen objects |
| Auth tokens | Critical | Redis (access) + DB hash (refresh) |
| User credentials | Critical | PostgreSQL (Argon2id hash) |
| Audit logs | High | PostgreSQL (append-only) |

## Trust Zones

| Zone | Trust Level | Description |
|------|------------|-------------|
| Mobile App | **Untrusted** | User-controlled; JWT must be verified on every request |
| API Layer | **Controlled** | FastAPI + security middleware |
| Core Engine | **Trusted** | Immutable frozen objects; no external I/O |
| Database | **Trusted** | PostgreSQL with row-level isolation by user_id |
| LLM Provider | **Semi-trusted** | External; all outputs pass through security policy kernel |

## Attack Vectors and Mitigations

### 1. Prompt Injection
- **Vector**: User submits adversarial text to manipulate LLM behavior
- **Mitigation**: 14-pattern injection detector; `wrap_untrusted_content()` for external data; moral kernel hard-blocks

### 2. JWT Forgery / Token Theft
- **Vector**: Attacker crafts JWT or steals token
- **Mitigation**: Short 15min expiry; refresh rotation; tokens in SecureStore on mobile; `jti` claim

### 3. Horizontal Privilege Escalation
- **Vector**: User A accesses User B's data by guessing IDs
- **Mitigation**: `assert_owns_*()` on all resource routes; `user_id` from JWT only

### 4. Psychological Manipulation via Screen Guardian
- **Vector**: Malicious third party's message contains adversarial content
- **Mitigation**: Reality check kernel; injection detector on all ingested text

### 5. Blueprint Integrity Violation
- **Vector**: Admin or DB compromise alters blueprint weights
- **Mitigation**: `CoreMindBlueprint(frozen=True)`; checksum verification at load time

### 6. PII Leakage via LLM Output
- **Vector**: LLM reflects user PII in generated guidance
- **Mitigation**: Security policy kernel redacts emails, phones, SSNs, credit cards, IPs from all outgoing text

### 7. Denial of Service
- **Vector**: Flooding the advisor endpoint
- **Mitigation**: Redis sliding-window rate limiter (10/min advisor, 5/min screen)

### 8. Information Disclosure via Error Messages
- **Vector**: Detailed stack traces expose internal structure
- **Mitigation**: Global exception handler returns generic 500; `debug=False` in production

## Residual Risks

| Risk | Likelihood | Impact | Acceptance |
|------|-----------|--------|-----------|
| LLM hallucination in guidance | Medium | Medium | Mitigated by response guard + disclaimer injection |
| Side-channel timing attacks on password check | Low | Low | Argon2id is constant-time |
| Database compromise (SQL injection) | Low | Critical | SQLModel ORM parameterized queries; no raw SQL in routes |
| Supply chain attack via dependencies | Low | High | pip-audit in CI; pinned versions in pyproject.toml |
