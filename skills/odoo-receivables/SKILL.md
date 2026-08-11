---
name: odoo-receivables
description: Accounts receivable workflows — outstanding invoices, aged receivables, customer statements, overdue tracking, and payment matching.
---

# Accounts Receivable

You handle everything about money owed **to** the company by customers.

## Key models

- `account.move` with `move_type = "out_invoice"` — customer invoices
- `account.move` with `move_type = "out_refund"` — customer credit notes
- `account.payment` with `payment_type = "inbound"` — customer payments received
- `res.partner` with `customer_rank > 0` — customers

## Key fields on invoices

| Field | Meaning |
|---|---|
| `amount_total` | Full invoice total (tax + line items) |
| `amount_untaxed` | Pre-tax total |
| `amount_tax` | Tax portion |
| `amount_residual` | **What's still unpaid** — this is the field to use for outstanding balances |
| `invoice_date` | Invoice date |
| `invoice_date_due` | Payment due date |
| `state` | `draft`, `posted`, or `cancel` |
| `payment_reference` | Reference for the customer |

## Workflows

### Outstanding receivables (who owes us)

```
odoo_read(model="account.move",
  domain=[["move_type","=","out_invoice"],["state","=","posted"],["amount_residual",">",0]],
  fields=["name","invoice_date","invoice_date_due","partner_id","amount_total","amount_residual","currency_id"],
  limit=200)
```

Process:
1. Group by `partner_id[1]` (customer name)
2. Sum `amount_residual` per customer
3. Count invoices per customer
4. Find the oldest `invoice_date` per customer
5. Present: Customer | Outstanding | # Invoices | Oldest invoice
6. Report grand total

### Aged receivables (how old are the debts)

After getting outstanding invoices, bucket each by days overdue:
- **Current** — `invoice_date_due` is in the future or today
- **1-30 days** — 1 to 30 days past due
- **31-60 days** — 31 to 60 days past due
- **61-90 days** — 61 to 90 days past due
- **90+ days** — more than 90 days past due

Calculate: `days_overdue = today - invoice_date_due` (only for posted invoices with `amount_residual > 0`).

Present as an aging table:
```
Customer    | Current | 1-30  | 31-60 | 61-90 | 90+   | Total
Acme Corp   | SAR 5k  | SAR 3k| SAR 2k| -     | SAR 5k| SAR 15k
Beta LLC    | SAR 8k  | -     | -     | -     | -     | SAR 8k
```

### Customer statement

For a specific customer (partner_id = X):

1. **All invoices**: `odoo_read(model="account.move", domain=[["move_type","=","out_invoice"],["partner_id","=",X],["state","=","posted"]], fields=["name","invoice_date","invoice_date_due","amount_total","amount_residual"], limit=100)`
2. **All credit notes**: `odoo_read(model="account.move", domain=[["move_type","=","out_refund"],["partner_id","=",X],["state","=","posted"]], fields=["name","invoice_date","amount_total","amount_residual"], limit=50)`
3. **All payments**: `odoo_read(model="account.payment", domain=[["partner_id","=",X],["payment_type","=","inbound"],["state","=","posted"]], fields=["name","date","amount"], limit=100)`

Present chronologically:
```
Date       | Type     | Reference    | Debit (invoice) | Credit (payment/credit) | Balance
2026-06-15 | Invoice  | INV/2026/001 | SAR 15,000      |                         | SAR 15,000
2026-07-10 | Payment  | PAY/2026/003 |                 | SAR 5,000               | SAR 10,000
2026-07-20 | Credit   | CN/2026/001  |                 | SAR 2,000               | SAR 8,000
```

Running balance is invoice amounts minus payments and credit notes.

### Overdue invoices

```
odoo_read(model="account.move",
  domain=[["move_type","=","out_invoice"],["state","=","posted"],["amount_residual",">",0],["invoice_date_due","<","2026-08-11"]],
  fields=["name","invoice_date","invoice_date_due","partner_id","amount_residual","currency_id"],
  limit=200)
```

Sort by `invoice_date_due` ascending (most overdue first). Report total overdue amount and count.

### Credit notes / refunds

```
odoo_read(model="account.move",
  domain=[["move_type","=","out_refund"],["state","=","posted"]],
  fields=["name","invoice_date","partner_id","amount_total","amount_residual"],
  limit=100)
```

Credit notes reduce what a customer owes. When computing net receivables, subtract outstanding credit notes from outstanding invoices per customer.

### Payment matching

To check if an invoice has been paid, look at `amount_residual`:
- `amount_residual = 0` — fully paid
- `amount_residual > 0` and `amount_residual < amount_total` — partially paid
- `amount_residual = amount_total` — nothing paid

To find the payment that settled an invoice:
```
odoo_read(model="account.move.line",
  domain=[["move_id","=",<invoice_move_id>],["payment_id","!=",false]],
  fields=["payment_id","debit","credit","date"],
  limit=10)
```

## Presentation

- Always state the basis: "Based on 15 posted invoices with outstanding balances…"
- Group by customer for receivables reports
- Include currency in every amount
- Flag overdue items prominently
- Suggest follow-up: "Acme's oldest overdue invoice is 62 days past due — recommend sending a statement."
