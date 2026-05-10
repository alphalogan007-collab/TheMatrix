# MindAI — Centralized Low-Leakage Identity Engine

> **MindAI is not a chatbot.**
> MindAI is a centralized, tamper-resistant Identity Engine that gives every user
> a personal Identity Mind Instance guided by an immutable Core Mind Blueprint.

---

## Table of Contents

1. [What MindAI Is](#what-mindai-is)
2. [What MindAI Is Not](#what-mindai-is-not)
3. [Core Concepts](#core-concepts)
4. [Architecture](#architecture)
5. [Security Design](#security-design)
6. [Privacy Design](#privacy-design)
7. [Quick Start (Local)](#quick-start-local)
8. [Running Tests](#running-tests)
9. [API Usage](#api-usage)
10. [Screen Guardian MVP](#screen-guardian-mvp)
11. [Roadmap](#roadmap)

---

## What MindAI Is

MindAI is a **centralized, low-leakage Identity Engine**.

- The **centralized mind** (Core Mind Blueprint) is the stable base pattern. It has maximum closure, minimum leakage, verified moral grounding, and immutable released versions.
- Each user receives a **local Identity Mind Instance** — initialized from the base pattern and adapted to their personal context, state, and history.
- The **Inner Voice Layer** continuously compares the user instance against the centralized mind, reducing leakage and guiding the user back to stable, grounded advice.
- The **final advice** is not emotional mirroring. It is stabilized guidance from the low-leakage base pattern, filtered through reality-checking, moral grounding, and harm prevention.

Every advisor response is **traceable** to a signed, versioned blueprint and a specific interaction frame.

---

## What MindAI Is Not

| ❌ Not This | ✅ Actually This |
|---|---|
| A chatbot | A persistent identity-aware guidance engine |
| An app that agrees with everything | A system with a stable moral core that will not be overridden by user preference |
| Emotionally mirroring AI | Stabilized guidance that acknowledges but does not mirror instability |
| A therapy tool | An advisory system — not a clinical instrument |
| A system where the mobile app has authority | A zero-trust system where the backend is the sole authority |
| A system users can manipulate to change morality | A system where morality is centrally controlled, versioned, and cryptographically protected |

---

## Core Concepts

### Identity Engine
The centralized platform that spawns, manages, monitors, and stabilizes all Identity Mind Instances. It is the only system with write authority over blueprint data.

### Identity Space
The multi-dimensional state space in which a user's identity pattern lives. Encoded as a vector of emotional state, memory, self-model, situation, and stability metrics.

### Core Mind Blueprint
The **immutable** per-released-version source pattern. It encodes:
- **MoralKernel** — stable ethical constraints
- **FactKernel** — evidence-updated factual grounding
- **GuidanceKernel** — advice direction patterns
- **RealityCheckKernel** — manipulation and misinformation detection
- **SafetyKernel** — harm prevention rules

The blueprint is versioned, checksummed, signature-protected, and append-only. No user or mobile client can modify it.

### User Identity Instance
A user-specific, evolving model tracking:
- `X(t)` — Active Awareness State (what the user is engaged with)
- `M(t)` — Memory State (history, patterns, past decisions)
- `R(t)` — Self-Model State (how the user understands themselves)

The instance adapts locally. It **cannot** modify the base pattern.

### Inner Voice Layer
The mechanism by which the Core Mind Blueprint guides the user instance. It checks:
- Is the user emotionally leaking?
- Is the user under manipulation?
- Does the proposed advice violate moral constraints?
- Is the advice factually grounded?
- Is the advice stable long-term?

The inner voice reduces user-instance leakage by pulling it back toward the centralized low-leakage base pattern.

### Closure / Leakage / Lag (Y-Theory)
- **Closure (Γ)** — reinforcing forces: evidence support, moral stability, long-term coherence
- **Leakage (Λ)** — dissipating forces: contradiction, uncertainty, manipulation, emotional overpressure
- **Lag (τ)** — the reflection buffer; the system must not instantly mirror user emotion
- Identity persists when `Γ > Λ`; the system monitors this per instance

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MOBILE APP (Untrusted Client)                   │
│  React Native · TypeScript · Secure Storage · Token Auth               │
│  Sends: InteractionFrames · UserState · ScreenContent · Voice/Text     │
│  Receives: AdvisorResponse (signed blueprint reference)                │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTPS · JWT · Rate Limited
┌──────────────────────────────▼──────────────────────────────────────────┐
│                     CENTRALIZED BACKEND (Authority)                    │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                  CORE MIND BLUEPRINT (Immutable)                │  │
│  │  MoralKernel · FactKernel · GuidanceKernel · SafetyKernel      │  │
│  │  Versioned · Checksummed · Signed · Append-Only                │  │
│  └──────────────────────────┬──────────────────────────────────────┘  │
│                             │ InnerVoiceLayer                          │
│  ┌──────────────────────────▼──────────────────────────────────────┐  │
│  │              IDENTITY ENGINE ORCHESTRATION                      │  │
│  │  Auth · AuthZ · RateLimit · PromptInjectionDefense              │  │
│  │  InputValidation · ResponseGuard · AuditLogger                  │  │
│  └──────────────────────────┬──────────────────────────────────────┘  │
│                             │                                          │
│  ┌──────────┐  ┌────────────▼────────┐  ┌────────────────────────┐   │
│  │ Postgres │  │ IdentityMindInstance│  │  RealityCheckKernel    │   │
│  │ pgvector │  │ UserState · Memory  │  │  MoralKernel           │   │
│  │ Redis    │  │ Stability · Closure │  │  StrainEngine          │   │
│  └──────────┘  └─────────────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Mobile is Untrusted
- Mobile sends frames; it never has authority
- Backend resolves user identity from token — never from client claims
- Blueprint logic never runs client-side
- All scoring and advice generation is server-side only

---

## Security Design

| Layer | Mechanism |
|---|---|
| **Auth** | JWT (short-lived) + refresh token rotation + device sessions |
| **AuthZ** | Object-level ownership checks on every request |
| **Blueprint** | Signed versions, checksum validation, append-only records |
| **Input** | Pydantic validation, payload limits, control-char stripping |
| **Prompt Injection** | `PromptInjectionDetector`, `UntrustedContentWrapper` |
| **Response** | `ResponseGuard` — all LLM output validated before delivery |
| **Rate Limits** | Per-user, per-IP, per-device, per-operation |
| **Audit** | Append-only audit log for all sensitive actions |
| **Secrets** | `.env` local only; secrets manager in production |
| **Encryption** | TLS in transit; field encryption at rest; KMS abstraction |
| **Admin** | Separate role, separate routes, audit-logged, creator approval |
| **CI/CD** | Lint, type-check, tests, pip-audit, secret scan, SAST |

Follows: **OWASP API Security Top 10 · OWASP MASVS · NIST Zero Trust**

---

## Privacy Design

- **Screen Guardian** is opt-in only. Never secretly captures screen.
- Raw screenshots are not stored by default.
- User private state is **never** automatically used to train the centralized mind.
- Consent model controls: memory, screen guardian, voice processing, anonymized training.
- Full data export and deletion paths are designed for GDPR/PIPEDA readiness.
- Audit logs never contain raw secrets, tokens, or private message content.

---

## Quick Start (Local)

### Prerequisites
- Docker & Docker Compose
- Node.js 20+
- Python 3.11+ (for non-Docker dev)

### 1. Clone and configure

```bash
git clone <repo>
cd mindai
cp .env.example .env
# Edit .env with your local values (all fake for MVP)
```

### 2. Start all services

```bash
make dev
# Starts: backend, PostgreSQL, Redis
```

### 3. Run migrations

```bash
make migrate
```

### 4. Seed development data

```bash
make seed
```

Backend is available at: `http://localhost:8000`  
API docs: `http://localhost:8000/docs`

---

## Running Tests

```bash
make test
# or
cd backend && pytest -v
```

Security checks:

```bash
make security-check
# Runs: ruff, mypy, bandit, pip-audit
```

---

## API Usage

### Register & Login

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123!"}'

# Login → returns access_token + refresh_token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123!"}'
```

### Ask the Advisor

```bash
curl -X POST http://localhost:8000/advisor/ask \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "identity_instance_id": "<instance_id>",
    "input_text": "My colleague keeps taking credit for my work. I want to confront them publicly. Should I?",
    "emotional_state": "angry",
    "urgency": 0.8
  }'
```

### Sample Advisor Response

```json
{
  "response_id": "rsp_01J...",
  "direct_answer": "Based on available evidence and your situation, a public confrontation carries high risk of damaging both the relationship and your own standing.",
  "what_user_state_suggests": "Your anger is understandable and valid. The urgency you feel is pushing toward an immediate high-stakes action.",
  "what_core_blueprint_corrects": "The Core Blueprint notes that high-emotional-intensity decisions often have irreversible consequences. The strain score for public confrontation is elevated.",
  "reality_check_summary": "Public confrontations in workplace settings most commonly result in negative outcomes for the person raising the concern, regardless of who is factually correct.",
  "stable_advice": "Document specific instances of credit-taking with dates and specifics. Request a private one-on-one with your colleague first. If unresolved, escalate to a manager with documentation.",
  "best_next_action": "Write down three specific recent incidents with dates before taking any action.",
  "risks": "Public confrontation may be perceived as unprofessional. Acting while at high emotional intensity increases error likelihood.",
  "uncertainty": "Confidence is medium — more context about your workplace culture and the colleague's history would improve accuracy.",
  "confidence_score": 0.72,
  "closure_score": 0.68,
  "leakage_score": 0.31,
  "blueprint_version": "v1.0.0",
  "blueprint_checksum": "sha256:a3f4...",
  "advice_trace_id": "trc_01J..."
}
```

### Check Screen Content

```bash
curl -X POST http://localhost:8000/screen/check-text \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "BREAKING: Scientists confirm 5G towers cause cancer in 100% of cases. Share before they delete this!",
    "source_context": "Facebook post"
  }'
```

---

## Screen Guardian MVP

Screen Guardian is **opt-in only**.

MVP supports:
1. **Paste Text** — paste visible post/article text; MindAI checks claims
2. **Screenshot Upload** — placeholder for OCR extraction
3. **Verdict Display** — shows: Likely False / Misleading / Missing Context / Opinion / Uncertain / Likely True
4. **Manipulation Signals** — detects urgency language, fear appeals, unsourced statistics
5. **Suggested Reply** — generates a calm, factual suggested response

**What Screen Guardian will never do:**
- Auto-post, auto-comment, auto-report, or auto-tag anything
- Capture your screen without your explicit activation
- Store raw screenshots by default

---

## Roadmap

| Phase | Features |
|---|---|
| **Phase 1 (MVP)** | Secure backend · Mobile app · Text/situation advisor · Screen text checker · Blueprint versioning · Audit logs |
| **Phase 2** | Voice input · STT/TTS · Persistent vector memory · Web search provider · Stronger reality-checking |
| **Phase 3** | Android screen capture (MediaProjection) · Android overlay · iOS share extension · iOS ReplayKit exploration |
| **Phase 4** | Smart glasses / camera vision · Real-time scene understanding · Meeting & negotiation support |
| **Phase 5** | Body sensor integration · Emotion-state estimation · Distributed identity-space scaling |

---

## Production Hardening (Not Yet Shipped)

Do not ship to production until:
- [ ] External security review completed
- [ ] Penetration test completed
- [ ] Mobile security review (MASVS) completed
- [ ] Privacy policy and consent flow complete
- [ ] Secrets in production-grade secrets manager
- [ ] Audit logs tamper-resistant (WORM or external append-only service)
- [ ] Backups and disaster recovery configured
- [ ] Monitoring, alerting, and incident response plan in place
- [ ] API authorization tests cover all object-level access scenarios

---

*MindAI — The centralized mind is the low-leakage base pattern. Every instance is instantiated from it. Every answer is traceable to it.*
