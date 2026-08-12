---
name: odoo-api-reference
description: Use the connected Odoo tenant through discovery-first, evidence-backed API calls. Never invent a model or field; discover models/fields first, then read only fields returned by discovery. Covers Odoo JSON-RPC/JSON-2, accounting workflows, pagination, relations, localization/custom fields, and recovery from Odoo errors.
---

# Odoo API reference

## Source of truth

Use the official Odoo External API documentation before relying on transport details:

- https://www.odoo.com/documentation/19.0/developer/reference/external_api.html
- https://www.odoo.com/documentation/19.0/developer/reference/external_rpc_api.html

The tenant's installed version and enabled modules are authoritative for models and fields.

## Discovery-first sequence

1. Call `odoo_discover_models` and find the technical model name from the returned `model` field.
2. Call `odoo_discover_fields` with that technical model name.
3. Choose only fields returned by discovery. Custom fields such as `x_*` are expected.
4. Call `odoo_read` with an explicit `fields` list and a bounded `limit`. The plugin accepts tenant-valid models and fields; it does not use a static accounting allowlist.
5. If Odoo rejects a field/domain, do not retry unchanged. Read the error, rediscover, and adapt.

## Read request discipline

- Use technical names, not UI labels.
- Domains are Odoo domain arrays: `[["state", "=", "posted"]]`.
- Dates use the tenant's Odoo date format, normally `YYYY-MM-DD`.
- Keep limits bounded and paginate with `offset` where supported.
- Relation fields commonly return `[id, display_name]`; follow up with a read if detail is needed.
- Never request every field by default; select fields needed for the question.

## Accounting workflow hints

- Invoices/bills: discover `account.move`; inspect `move_type`, `state`, totals, residuals, dates, and partner relations.
- Payments: discover `account.payment`; inspect date, amount, state, partner, journal, and reconciliation fields.
- Ledger: discover `account.move.line`; inspect date, account, partner, debit, credit, balance, and move relations.
- Banks/journals: discover tenant models and fields; do not assume `res.partner.bank` exists or that a field is readable.
- Localization: discover `res.company`, fiscal position, tax, and module metadata before interpreting tax/accounting fields.

## Safety boundary

`odoo_read` is read-only but tenant-scoped. Writes are a separate capability and require explicit approval. Do not claim a write happened without a returned Odoo result.
