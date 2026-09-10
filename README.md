# Meridian — Zoho CRM workspace

A client-ready Zoho CRM example for **Helios Industrial**: command center, leads, accounts, contacts, pipeline kanban, activities, blueprints, and a Zoho CRM API v8 integration map.

The org is a realistic demo so anyone can click through without Zoho credentials. The same modules, field API names, COQL, convert payload, and OAuth scopes are what you wire to a live `zoho.eu` org.

## Run locally

```bash
npm install
npm run dev -- --port 43123
```

Open [http://localhost:43123](http://localhost:43123).

## What to show a client

- **Command center** — Q3 pipeline, weighted forecast, quota, win rate
- **Scoring** — live Zoho-style rules (firmographic, intent, behavioral, negative). Toggle a rule and every lead recalculates; Rating / Hot status follow thresholds.
- **Leads** — capture with a live score preview, then convert to Account + Contact + Deal
- **Pipeline** — drag deals between stages; Blueprint blocks invalid moves (discovery call, PO number, lost reason)
- **Blueprints** — workflow rules and a Deluge closed-won handoff
- **Zoho API v8** — scopes, endpoints, field map, COQL, convert body, sync log

## Live Zoho (optional)

This preview uses an in-memory demo org. To point it at a real Zoho CRM org later:

1. Create a Zoho API console client (Self Client or Server-based).
2. Request scopes listed on `/integration`.
3. Exchange a grant token for a refresh token on `accounts.zoho.eu` (or `.com` / `.in`).
4. Call `/crm/v8/{module}` with `Authorization: Zoho-oauthtoken {access_token}`.

Until those secrets exist, the UI stays fully usable.

## Stack

Next.js 16, TypeScript, Tailwind CSS, shadcn/ui.
