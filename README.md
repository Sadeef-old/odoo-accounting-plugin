# Odoo Accounting Plugin

A read-only Odoo accounting coworker plugin for Sadeef AI. Version 0.3.0.

## What it does

Connects to a live Odoo tenant and lets the AI agent answer real accounting questions: who owes us, who do we owe, cash position, trial balance, VAT position, chart of accounts, and more.

## Architecture

**One flexible read tool** (`odoo_read`) backed by a model allowlist with field-level projection. The agent can query any of 20+ Odoo accounting models with arbitrary domains, but only read — no writes, no arbitrary model access.

**Six convenience tools** for quick lookups: `search_invoices`, `list_vendor_bills`, `list_partners`, `list_payments`, `list_journal_entries`, `list_accounts`.

**Six detailed skills** that teach the agent how to be an accountant, not just a tool-caller:

| Skill | Covers |
|---|---|
| `odoo-accounting` | Main skill — tool reference, domain syntax, presentation rules, all common workflows |
| `odoo-receivables` | AR: outstanding invoices, aged receivables, customer statements, overdue tracking, payment matching |
| `odoo-payables` | AP: outstanding bills, aged payables, vendor statements, payment status, upcoming dues |
| `odoo-banking` | Bank accounts, cash flow, payment reconciliation, unreconciled items |
| `odoo-reporting` | Trial balance, P&L, balance sheet, general ledger, tax/VAT report, audit trail |
| `odoo-discovery` | Tenant config: company, country, currency, modules, journals, taxes, chart of accounts, fiscal year |

## Safety

- Read-only. No create, write, post, cancel, or delete.
- Model allowlist enforced at the provider level — the agent cannot access models not on the list.
- Field-level projection caps — only allowlisted fields are returned.
- Result limit capped at 200 rows.
- Credentials encrypted at the application boundary; never exposed in results.
- All queries go through the Sadeef connector broker with binding and policy enforcement.

## Connection setup

The Connection setup form collects:
- `base_url` — Odoo tenant URL (https)
- `database` — Odoo database name
- `username` — Odoo user login/email
- `api_key` — Odoo API key (encrypted)

No credentials are stored in the plugin.
