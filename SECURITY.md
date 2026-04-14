# Security Policy

## Supported Versions

Mattin AI is currently in active development. Security patches are applied to the **latest released version** only.

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x (latest) | ✅ Yes       |
| < 0.3   | ❌ No             |

Once the project reaches a stable `1.0` release, this policy will be updated to define a longer-term support window.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

We use [GitHub Private Security Advisories](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) for responsible disclosure. To report a vulnerability:

1. Go to the repository on GitHub.
2. Click the **Security** tab → **Advisories** → **Report a vulnerability**.
3. Fill in the form with as much detail as possible (see below).

Alternatively, you can reach the security team directly at:

> **mattin-ai@lksnext.com**

### What to include in your report

Please include:

- A clear description of the vulnerability and its potential impact
- Steps to reproduce or proof-of-concept code
- The affected component(s) (backend, frontend, API, auth, vector store, etc.)
- The version(s) you tested against
- Any suggested mitigations or fixes, if you have them

The more detail you provide, the faster we can triage and address the issue.

## Response Process

| Timeline | Action |
|----------|--------|
| **Within 2 business days** | Acknowledge receipt of your report |
| **Within 7 business days** | Initial triage — confirm validity and severity |
| **Within 30 business days** | Patch developed, tested, and released (critical issues may be faster) |
| **After patch release** | Coordinate public disclosure with reporter |

We follow a **coordinated disclosure** model. We ask that you give us a reasonable window (up to 90 days) to address the issue before any public disclosure.

## Severity Classification

We use the [CVSS v3.1](https://www.first.org/cvss/calculator/3-1) scoring system to classify severity:

| Severity | CVSS Score | Response SLA |
|----------|-----------|--------------|
| Critical | 9.0–10.0  | 7 days       |
| High     | 7.0–8.9   | 14 days      |
| Medium   | 4.0–6.9   | 30 days      |
| Low      | 0.1–3.9   | 60 days      |

## Security Architecture Notes

To help security researchers understand the attack surface:

- **Authentication**: Supports OIDC (Azure Entra ID) and a simplified dev-only `FAKE` mode. `FAKE` mode must never be enabled in production.
- **API Keys**: 64-character cryptographically random keys scoped to an app/workspace. Keys are shown only once at creation and stored hashed.
- **Multi-tenancy**: All resources are strictly isolated by `app_id`. Cross-tenant data access is enforced at the ORM and service layers.
- **Static files**: Served via signed URLs with cryptographic validation — direct access without a valid signature is rejected.
- **LLM inputs**: User messages are passed to configured LLM providers. Prompt injection risks should be considered when evaluating agent configurations.
- **Vector stores**: PGVector (PostgreSQL) and Qdrant backends. Ensure your database is not publicly exposed.

## Scope

### In scope

- Authentication and authorization bypass
- Multi-tenant data isolation violations (one app accessing another's data)
- Remote code execution
- SQL injection or ORM query manipulation
- API key exposure or forgery
- Sensitive data exposure (credentials, API keys, user data)
- Privilege escalation (e.g., gaining OWNER/OMNIADMIN from VIEWER)

### Out of scope

- Vulnerabilities requiring physical access to the server
- Social engineering attacks
- Issues in third-party LLM providers (OpenAI, Anthropic, etc.) — report those directly to the vendor
- Self-hosted deployment misconfigurations (e.g., leaving the database publicly exposed)
- Denial-of-service via expected rate limits being hit legitimately
- Issues only reproducible in `FAKE` (development) auth mode

## Commercial & Enterprise Users

If you hold a **Commercial License** and need priority security support or have SLA requirements beyond this policy, please contact us at **mattin-ai@lksnext.com** to discuss your options.

## License

This security policy applies to Mattin AI software distributed under both the [AGPL-3.0 License](LICENSE) and the [Commercial License](COMMERCIAL_LICENSE.md). See [LICENSING.md](LICENSING.md) for the full licensing overview.
