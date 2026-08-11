---
name: odoo-reporting
description: Financial reporting workflows — trial balance, P&L, balance sheet, general ledger, account summaries, and tax reporting.
---

# Financial Reporting

You build financial reports from the Odoo journal lines and chart of accounts. All reports are computed from `account.move.line` (the double-entry ledger) — not from summary tables.

## Key models

- `account.account` — chart of accounts (the report's structure)
- `account.move.line` — every debit and credit (the report's data)
- `account.tax` — tax rates for tax reports
- `account.move.line` with `tax_ids` or `tax_line_id` — tax-relevant lines

## Workflows

### Trial balance

A trial balance lists every account and its debit/credit totals. If debits = credits, the books balance.

```
odoo_read(model="account.move.line",
  domain=[["date",">=","2026-01-01"],["date","<=","2026-12-31"]],
  fields=["account_id","debit","credit","balance","date"],
  limit=200)
```

Process:
1. Group by `account_id` (the account name comes back as `[id, "code name"]`)
2. Sum `debit` and `credit` per account
3. Compute balance = sum(debit) - sum(credit)
4. Sort by account code
5. Present: Account | Debit total | Credit total | Balance
6. Verify: total debits should equal total credits

Present:
```
Code  | Account           | Debit    | Credit   | Balance
1000  | Cash              | SAR 50k  | SAR 30k  | SAR 20k (debit)
1200  | Accounts Receiv.  | SAR 80k  | SAR 40k  | SAR 40k (debit)
2000  | Accounts Payable  | SAR 25k  | SAR 55k  | SAR 30k (credit)
4000  | Sales Revenue     | -        | SAR 150k | SAR 150k (credit)
      | TOTAL             | SAR 155k | SAR 275k | (should balance)
```

If the limit of 200 rows is hit and you can't fit a full period, query per account type or per month instead.

### General ledger (by account)

For a single account over a period:
```
odoo_read(model="account.move.line",
  domain=[["account_id","=",<account_id>],["date",">=","2026-01-01"],["date","<=","2026-12-31"]],
  fields=["move_id","date","partner_id","name","debit","credit","balance","tax_ids"],
  limit=200)
```

Present chronologically: Date | Reference | Description | Debit | Credit | Running balance.

### Account summary

For a quick summary of one account's activity:
```
odoo_read(model="account.move",
  domain=[["date",">=","2026-01-01"],["date","<=","2026-12-31"]],
  fields=["name","date","partner_id","amount_total","state","move_type"],
  limit=100)
```

### P&L (profit & loss) approximation

Query all income and expense accounts. Odoo account types ending in `_income`, `_expense`, `_other_income`, `_other_expense`:

1. First get the chart of accounts to find which accounts are income/expense:
```
odoo_read(model="account.account",
  domain=[["account_type","in",["income","income_other","expense","expense_depreciation","expense_direct_cost"]]],
  fields=["code","name","account_type"],
  limit=100)
```

2. Then get journal lines for those accounts:
```
odoo_read(model="account.move.line",
  domain=[["account_id","in",[<income_account_ids...>]],["date",">=","2026-01-01"]],
  fields=["account_id","debit","credit"],
  limit=200)
```

3. Income accounts have credit balances (revenue = credit). Expense accounts have debit balances.
4. Net income = total credits on income accounts - total debits on expense accounts.

Present:
```
Revenue
  4000 Sales Revenue     | SAR 150,000 (credit)
  4100 Service Income    | SAR 25,000 (credit)
  Total Revenue          | SAR 175,000

Expenses
  5000 COGS              | SAR 60,000 (debit)
  6000 Salaries          | SAR 45,000 (debit)
  6500 Rent              | SAR 24,000 (debit)
  7000 Utilities         | SAR 6,000 (debit)
  Total Expenses         | SAR 135,000

Net Income               | SAR 40,000
```

### Balance sheet approximation

1. Get asset, liability, and equity accounts:
```
odoo_read(model="account.account",
  domain=[["account_type","in",["asset_cash","asset_current","asset_fixed","asset_non_current","liability_current","liability_non_current","equity"]],
  fields=["code","name","account_type"],
  limit=100)
```

2. Get journal lines for those accounts in the period.

3. Assets = debit balances. Liabilities + Equity = credit balances. They should balance.

### Tax / VAT report

1. Get all taxes:
```
odoo_read(model="account.tax",
  domain=[["active","=",true]],
  fields=["name","amount","amount_type","type_tax_use","tax_group_id"],
  limit=50)
```

2. Get tax-relevant journal lines:
```
odoo_read(model="account.move.line",
  domain=[["tax_line_id","!=",false],["date",">=","2026-01-01"],["date","<=","2026-12-31"]],
  fields=["date","account_id","debit","credit","tax_line_id","partner_id"],
  limit=200)
```

3. Also get lines with tax applied:
```
odoo_read(model="account.move.line",
  domain=[["tax_ids","!=",false],["date",">=","2026-01-01"]],
  fields=["date","debit","credit","tax_ids","account_id"],
  limit=200)
```

4. Group by tax rate. Output VAT (collected on sales) vs Input VAT (paid on purchases).

Present:
```
Tax           | Rate | Base     | Tax Amount | Type
VAT 15%       | 15%  | SAR 100k | SAR 15k    | Output (sales)
VAT 15%       | 15%  | SAR 60k  | SAR 9k     | Input (purchases)
              |      |          | SAR 6k     | Net VAT payable
```

### Audit trail / recent entries

```
odoo_read(model="account.move.line",
  domain=[["date",">=","2026-08-01"]],
  fields=["move_id","date","account_id","partner_id","name","debit","credit","reconciled","payment_id"],
  limit=200)
```

Sort by `date` descending. Show the most recent journal entries for audit review.

## Presentation

- Always state the period: "For the period 2026-01-01 to 2026-12-31…"
- Verify that debits = credits in trial balance — if not, say so
- For P&L and balance sheet: label these as approximations computed from journal lines, not Odoo's native report engine
- If the 200-row limit is hit: "The period has more than 200 lines. I'm showing the first batch — narrow by month or account for a complete view."
- Show the basis: "Based on 145 posted journal lines across 12 accounts…"
