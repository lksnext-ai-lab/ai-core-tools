# SaaS Mode Guide

> Part of [Mattin AI Documentation](../index.md)

## Overview

Mattin AI supports two deployment modes:

| Mode | `AICT_DEPLOYMENT_MODE` | Description |
|------|------------------------|-------------|
| **Self-Managed** | `self_managed` (default) | Single-tenant / inner-source deployment. No subscription billing. All features available without limits. |
| **SaaS** | `saas` | Multi-tenant SaaS deployment with Stripe billing, subscription tiers, and resource quota enforcement. |

Self-managed is the default and requires no additional configuration. This guide covers the **SaaS mode** setup.

---

## Subscription Tiers

SaaS mode provides three subscription tiers with resource quotas:

| Tier | Apps | Agents | Silos | Skills | MCP Servers | Collaborators | LLM Calls/month |
|------|------|--------|-------|--------|-------------|---------------|-----------------|
| **Free** | 1 | 3 | 2 | 1 | 0 | 1 | 100 |
| **Starter** | 2 | 10 | 5 | 3 | 1 | 5 | 1,000 |
| **Pro** | 10 | 50 | 20 | 10 | 5 | Unlimited | Unlimited |

> **Customizing limits**: The default values above are defined in [`backend/system_defaults.yaml`](../../backend/system_defaults.yaml) under the `tier_config` key. Edit that file (no code change needed) and restart the application. DB-level overrides (via the admin tier config panel) take precedence over file defaults.

**Billing statuses**: `active`, `trialing` (7-day trial on signup), `past_due`, `cancelled`, `none`.

**Admin override**: An admin can force a user into any tier via the `admin_override_tier` field, bypassing Stripe entirely.

---

## Configuration

Set the following environment variables to enable SaaS mode.

### Required

```bash
AICT_DEPLOYMENT_MODE=saas

# Stripe
STRIPE_API_KEY=sk_live_...           # or sk_test_... for development
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_STARTER=price_...   # Your Stripe Price ID for Starter plan
STRIPE_PRICE_ID_PRO=price_...       # Your Stripe Price ID for Pro plan

# Email
EMAIL_FROM=noreply@yourdomain.com
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USER=your-smtp-user
SMTP_PASS=your-smtp-password
```

The application will **refuse to start** if any of these are missing when `AICT_DEPLOYMENT_MODE=saas`.

### Development / Testing (local)

Use Stripe test keys and a local SMTP catcher (e.g. [Mailpit](https://mailpit.axllent.org/)):

```bash
AICT_DEPLOYMENT_MODE=saas

STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_STARTER=price_starter_test
STRIPE_PRICE_ID_PRO=price_pro_test

EMAIL_FROM=noreply@localhost
SMTP_HOST=localhost
SMTP_PORT=1025   # Mailpit default
```

---

## Stripe Setup

### 1. Create Products and Prices

In the [Stripe dashboard](https://dashboard.stripe.com/):

1. Go to **Products → Add product**
2. Create two recurring products: **Starter** and **Pro**
3. Copy the **Price ID** (`price_...`) for each and add to the environment

### 2. Configure Webhook

1. Go to **Developers → Webhooks → Add endpoint**
2. Endpoint URL: `https://api.your-domain.com/internal/subscription/webhook`
3. Events to listen for:
   - `checkout.session.completed`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Copy the **Signing secret** (`whsec_...`) and set `STRIPE_WEBHOOK_SECRET`

For local development, use the Stripe CLI to forward webhooks:

```bash
stripe listen --forward-to localhost:8000/internal/subscription/webhook
```

---

## Quota Enforcement

Resource quotas are enforced by `TierEnforcementService` on every resource-creation endpoint. When a user reaches their limit, the API returns a plain string `detail` message:

- **HTTP 403 Forbidden** — resource limit reached (apps, per-app agents/silos/etc., or attempt to create own AI service on Free tier). Example:

```json
{ "detail": "Agent limit reached for this app (3/3 on free tier)" }
```

- **HTTP 429 Too Many Requests** — monthly system LLM call quota exhausted. Example:

```json
{ "detail": "Monthly system LLM quota exhausted (100/100). Upgrade your plan for more calls." }
```

### LLM Call Tracking

LLM calls are tracked per-user per-month by `UsageTrackingService`. Usage is persisted to the `usage_records` table and checked before each agent execution.

---

## Customizing Tier Defaults

Default tier limits are stored in `backend/system_defaults.yaml` under the `tier_config` key:

```yaml
tier_config:
  free:
    apps: 1
    agents: 3
    silos: 2
    skills: 1
    mcp_servers: 0
    collaborators: 1
    llm_calls: 100
  starter:
    apps: 2
    agents: 10
    # ...
  pro:
    # ...
```

**How overrides work (priority order)**:

1. **DB row** (`tier_configs` table) — highest priority, set via admin panel
2. **`system_defaults.yaml`** — YAML file defaults, loaded at startup
3. **Fallback** — hardcoded in `tier_config_repository.py` if YAML fails to load

To change defaults for all fresh installs, edit `system_defaults.yaml` and commit the change. Existing DB overrides are unaffected.

---

## Database Entities

| Model | Table | Description |
|-------|-------|-------------|
| `Subscription` | `subscriptions` | One per user. Stores `tier`, `stripe_customer_id`, `stripe_subscription_id`, `billing_status`, `trial_end`, `admin_override_tier`. |
| `TierConfig` | `tier_configs` | (tier, resource_type) → limit_value. Seeded from `system_defaults.yaml` on first SaaS startup. |

---

## Admin Operations

### Override a User's Tier

Via the admin API (requires `OMNIADMIN` role):

```http
PATCH /internal/admin/users/{user_id}/subscription
Content-Type: application/json

{
  "admin_override_tier": "pro"
}
```

Setting `admin_override_tier` to `null` reverts to the Stripe-billed tier.

### Update Tier Config Limits

```http
PUT /internal/admin/tier-configs
Content-Type: application/json

{
  "tier": "free",
  "resource_type": "agents",
  "limit_value": 5
}
```

---

## See Also

- [Environment Variables](../reference/environment-variables.md#saas-mode) — Full variable reference
- [Backend Architecture](../architecture/backend.md) — Services and repositories involved
