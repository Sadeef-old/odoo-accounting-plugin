---
name: odoo-banking
description: Banking and reconciliation workflows — bank accounts, cash flow, payment matching, and reconciliation status.
---

# Banking & Cash

You handle everything about the company's bank accounts, cash flow, and payment reconciliation.

## Key models

- `account.journal` with `type = "bank"` — bank journals (each bank account)
- `account.bank.account` — bank account numbers and details
- `res.bank` — bank master data
- `account.payment` — all payments (in and out)
- `account.move.line` with a bank journal — bank transaction lines

## Workflows

### Bank accounts overview

```
odoo_read(model="account.journal",
  domain=[["type","=","bank"],["active","=",true]],
  fields=["name","code","bank_account_id","currency_id","company_id","default_account_id"],
  limit=50)
```

Then for each bank journal, get the bank account:
```
odoo_read(model="account.bank.account",
  domain=[],
  fields=["acc_number","bank_id","currency_id","account_type"],
  limit=50)
```

And the bank:
```
odoo_read(model="res.bank",
  domain=[],
  fields=["name","bic","country","city"],
  limit=50)
```

Present: Bank | Account number | BIC | Currency.

### Cash flow summary

```
odoo_read(model="account.payment",
  domain=[["state","=","posted"],["date",">=","2026-08-01"],["date","<=","2026-08-31"]],
  fields=["name","date","amount","payment_type","partner_id","journal_id","currency_id"],
  limit=200)
```

Process:
1. Split into `inbound` (money received) and `outbound` (money paid)
2. Sum each direction per currency
3. Report: Cash in, Cash out, Net
4. If multiple bank journals, group by `journal_id[1]`

Present:
```
Bank          | In      | Out     | Net
Bank Al Rajhi | SAR 50k | SAR 30k | SAR 20k
Bank HSBC     | SAR 10k | SAR 15k | -SAR 5k
Total         | SAR 60k | SAR 45k | SAR 15k
```

### Payments needing reconciliation

```
odoo_read(model="account.payment",
  domain=[["state","=","posted"],["is_reconciled","=",false]],
  fields=["name","date","amount","payment_type","partner_id","journal_id","currency_id"],
  limit=200)
```

These are posted payments that haven't been matched to invoices/bills yet. Report count and total amount per direction.

### Bank transaction matching

To find journal lines on a bank journal that aren't reconciled:
```
odoo_read(model="account.move.line",
  domain=[["account_id","=",<bank_account_id>],["reconciled","=",false]],
  fields=["move_id","date","partner_id","debit","credit","name","payment_id"],
  limit=200)
```

Lines where `payment_id` is set are already linked to a payment. Lines where `payment_id` is null are standalone bank movements (bank fees, interest, etc.).

### Unreconciled invoice lines

To find invoice/bill lines that haven't been matched to a payment:
```
odoo_read(model="account.move.line",
  domain=[["reconciled","=",false],["full_reconcile_id","=",false],["account_id.account_type","in",["asset_receivable","liability_payable"]],
  fields=["move_id","date","partner_id","debit","credit","amount_currency","payment_id"],
  limit=200)
```

This shows open receivable/payable lines that still need matching to a payment.

### Recent bank activity

```
odoo_read(model="account.move.line",
  domain=[["journal_id","=",<bank_journal_id>],["date",">=","2026-08-01"]],
  fields=["move_id","date","partner_id","debit","credit","name","payment_id","reconciled"],
  limit=200)
```

Sort by `date` descending. Present recent transactions with: Date | Description | In (credit) | Out (debit) | Reconciled?

## Presentation

- Always group by bank account when multiple exist
- Distinguish posted vs draft payments — only posted payments affect the bank
- Flag unreconciled items: "12 payments totaling SAR 18,500 are posted but not yet reconciled to invoices"
- For bank fees or standalone lines: "These lines have no linked payment — they may be bank charges or interest. Verify in Odoo."
