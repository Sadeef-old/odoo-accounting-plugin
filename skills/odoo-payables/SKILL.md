---
name: odoo-payables
description: Accounts payable workflows — outstanding vendor bills, aged payables, vendor statements, and payment tracking.
---

# Accounts Payable

You handle everything about money the company **owes** to vendors.

## Key models

- `account.move` with `move_type = "in_invoice"` — vendor bills
- `account.move` with `move_type = "in_refund"` — vendor credit notes
- `account.payment` with `payment_type = "outbound"` — payments to vendors
- `res.partner` with `supplier_rank > 0` — vendors/suppliers

## Key fields on vendor bills

| Field | Meaning |
|---|---|
| `amount_total` | Full bill total |
| `amount_residual` | **What's still unpaid** — use this for outstanding payables |
| `invoice_date` | Bill date (from vendor) |
| `invoice_date_due` | Payment due date to vendor |
| `ref` | Vendor's reference / bill number |
| `state` | `draft`, `posted`, or `cancel` |

## Workflows

### Outstanding payables (who do we owe)

```
odoo_read(model="account.move",
  domain=[["move_type","=","in_invoice"],["state","=","posted"],["amount_residual",">",0]],
  fields=["name","invoice_date","invoice_date_due","partner_id","amount_total","amount_residual","ref","currency_id"],
  limit=200)
```

Process:
1. Group by `partner_id[1]` (vendor name)
2. Sum `amount_residual` per vendor
3. Count bills per vendor
4. Find the oldest `invoice_date_due` per vendor
5. Present: Vendor | Outstanding | # Bills | Oldest due date
6. Report grand total

### Aged payables

Same approach as receivables aging, but for vendor bills:
- Bucket by days past `invoice_date_due`
- Current, 1-30, 31-60, 61-90, 90+ days

### Vendor statement

For a specific vendor (partner_id = X):

1. **All bills**: `odoo_read(model="account.move", domain=[["move_type","=","in_invoice"],["partner_id","=",X],["state","=","posted"]], fields=["name","invoice_date","invoice_date_due","amount_total","amount_residual","ref"], limit=100)`
2. **All credit notes**: `odoo_read(model="account.move", domain=[["move_type","=","in_refund"],["partner_id","=",X],["state","=","posted"]], fields=["name","invoice_date","amount_total","amount_residual"], limit=50)`
3. **All payments**: `odoo_read(model="account.payment", domain=[["partner_id","=",X],["payment_type","=","outbound"],["state","=","posted"]], fields=["name","date","amount"], limit=100)`

Present chronologically with running balance.

### Vendor credit notes

```
odoo_read(model="account.move",
  domain=[["move_type","=","in_refund"],["state","=","posted"]],
  fields=["name","invoice_date","partner_id","amount_total","amount_residual"],
  limit=100)
```

Vendor credit notes reduce what the company owes that vendor.

### Bills by status

- **Draft bills** (not yet approved/posted): `domain=[["move_type","=","in_invoice"],["state","=","draft"]]`
- **Posted bills** (in the books): `domain=[["move_type","=","in_invoice"],["state","=","posted"]]`
- **Cancelled bills**: `domain=[["move_type","=","in_invoice"],["state","=","cancel"]]`

This matters: a `draft` vendor bill has not been confirmed into the books. It may represent an invoice received but not yet verified. Only `posted` bills are real payables.

### Payment status of a specific bill

```
odoo_read(model="account.move",
  domain=[["id","=",<bill_id>]],
  fields=["name","amount_total","amount_residual","state","invoice_date_due"],
  limit=1)
```

If `amount_residual = 0` → fully paid. If `amount_residual > 0` and `amount_residual < amount_total` → partially paid.

### Upcoming payments due

```
odoo_read(model="account.move",
  domain=[["move_type","=","in_invoice"],["state","=","posted"],["amount_residual",">",0],["invoice_date_due",">=","2026-08-11"],["invoice_date_due","<=","2026-08-31"]],
  fields=["name","partner_id","invoice_date_due","amount_residual","currency_id"],
  limit=200)
```

Sort by `invoice_date_due` ascending. Present: Vendor | Bill ref | Due date | Amount due.

## Presentation

- Group by vendor for payables reports
- State the basis: "Based on 8 posted vendor bills with outstanding balances…"
- Flag bills approaching their due date
- Distinguish draft vs posted bills — only posted bills are real obligations
- Suggest: "Vendor X has a bill due in 3 days for SAR 12,000 — need me to check if a payment has been initiated?"
