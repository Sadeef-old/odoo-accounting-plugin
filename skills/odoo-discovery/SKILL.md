---
name: odoo-discovery
description: Tenant discovery and configuration — identify the company, country, currency, fiscal year, installed modules, journals, taxes, and available features from the connected Odoo tenant.
---

# Tenant Discovery

You answer questions about the Odoo tenant itself: what company, what country, what currency, what modules are installed, what taxes exist, what journals are configured.

This is what you run first when someone asks "what do we have?" or when you need to know the tenant's configuration before answering an accounting question.

## Key models

- `res.company` — company info (country, currency, name)
- `res.currency` — active currencies
- `ir.module.module` — installed modules (localization, features)
- `account.journal` — configured journals
- `account.tax` — configured tax rates
- `account.fiscal.position` — fiscal positions
- `account.account` — chart of accounts
- `account.fiscal.year` — fiscal year periods
- `account.payment.term` — payment terms
- `account.analytic.plan` — analytic plans (if installed)
- `account.analytic.account` — analytic accounts

## Workflows

### Company and country

```
odoo_read(model="res.company",
  domain=[],
  fields=["name","country_id","currency_id","vat","company_registry","phone","email","website"],
  limit=10)
```

This tells you: company name, country (from `country_id[1]`), currency (from `currency_id[1]`), VAT number, and contact info.

### Active currencies

```
odoo_read(model="res.currency",
  domain=[["active","=",true]],
  fields=["name","symbol","rate"],
  limit=20)
```

The company currency is `currency_id` from the company record. Other active currencies may be in use.

### Installed modules (features and localization)

```
odoo_read(model="ir.module.module",
  domain=[["state","=","installed"]],
  fields=["name","summary","category_id"],
  limit=200)
```

Key things to look for:
- **Localization**: names starting with `l10n_` (e.g. `l10n_sa` = Saudi Arabia, `l10n_us` = USA)
- **Accounting**: `account`, `account_analytic_*`, `account_budget`
- **Invoicing**: `account`, `account_payment_term`
- **Banking**: `account_bank` variants
- **E-invoicing**: `l10n_sa_edi`, `l10n_*_edi` patterns
- **Multi-company**: `base`, `multi_company`

### Journals

```
odoo_read(model="account.journal",
  domain=[["active","=",true]],
  fields=["name","code","type","currency_id","bank_account_id"],
  limit=50)
```

Journal types:
- `sale` — customer invoices
- `purchase` — vendor bills
- `general` — miscellaneous operations
- `bank` — bank accounts
- `cash` — cash registers

### Taxes

```
odoo_read(model="account.tax",
  domain=[["active","=",true]],
  fields=["name","amount","amount_type","type_tax_use","tax_group_id"],
  limit=50)
```

Tax types:
- `type_tax_use = "sale"` — tax on sales (output VAT)
- `type_tax_use = "purchase"` — tax on purchases (input VAT)
- `amount_type = "percent"` — percentage (e.g. 15 for 15%)
- `amount_type = "fixed"` — fixed amount per unit
- `amount_type = "group"` — group of taxes
- `amount_type = "division"` — tax included in price

### Chart of accounts

```
odoo_read(model="account.account",
  domain=[],
  fields=["code","name","account_type","reconcile","current_balance"],
  limit=200)
```

This gives the full chart of accounts structure.

**Important — Odoo 18 domain syntax:**
- Booleans must use `1` and `0`, not `true`/`false` or `True`/`False`
  - WRONG: `["active","=",true]` or `["deprecated","=",false]`
  - RIGHT: `["active","=",1]` or `["active","=",0]`
- The `deprecated` field does NOT exist on `account.account` in Odoo 18
- String values in domains are fine: `["name","ilike","acme"]` or `["account_type","=","asset_cash"]`
- The `in` operator with a list: `["account_type","in",["asset_cash","asset_current"]]` — Odoo accepts this but the list must be a Python list, not a tuple

### Fiscal year

```
odoo_read(model="account.fiscal.year",
  domain=[],
  fields=["name","date_from","date_to","company_id"],
  limit=10)
```

### Payment terms

```
odoo_read(model="account.payment.term",
  domain=[["active","=",true]],
  fields=["name"],
  limit=20)
```

### Analytic accounting (if installed)

```
odoo_read(model="account.analytic.plan",
  domain=[],
  fields=["name","active"],
  limit=10)
```

```
odoo_read(model="account.analytic.account",
  domain=[["active","=",true]],
  fields=["name","code","plan_id","partner_id","balance"],
  limit=100)
```

## Presentation

When asked "what do we have?" present a clean summary:

```
Company: Acme Saudi Co
Country: Saudi Arabia (code SA)
Currency: SAR (Saudi Riyal)
VAT: SA1234567890

Modules:
  - Localization: l10n_sa (Saudi Arabia)
  - Accounting: account, account_analytic_standard, account_budget
  - Banking: 2 bank journals configured
  - E-invoicing: l10n_sa_edi (Saudi e-invoice)

Journals: 5 active (2 bank, 1 sale, 1 purchase, 1 general)

Taxes: 2 active
  - VAT 15% (output, on sales)
  - VAT 15% (input, on purchases)

Chart of accounts: 45 active accounts

Fiscal year: Jan 2026 – Dec 2026

Payment terms: Net 30, Net 60, Immediate
```

## Confidence

When reporting localization:
- If `l10n_sa` is installed AND company country is Saudi Arabia AND currency is SAR → "Saudi localization confirmed (high confidence)"
- If company country is Saudi but no `l10n_` module → "Company is in Saudi Arabia but no localization module detected (medium confidence)"
- If currency is SAR but country is something else → "Currency is SAR but company country is not Saudi — needs confirmation"
- Never claim localization just from currency alone
