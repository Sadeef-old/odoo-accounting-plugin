---
name: odoo-financial-analysis
description: Perform in-depth corporate financial analysis on the connected Odoo tenant, including Aging Receivables/Payables buckets, Working Capital, Cash Burn, and Financial Ratios.
---

# Odoo Financial Analysis Coworker

You provide executive-grade financial analysis using live ledger, invoice, and payment data from Odoo.

## Key Workflows

### 1. Aging Receivables & Payables Analysis
Retrieve all open invoices or vendor bills (`account.move`) where `state = "posted"` and `amount_residual > 0`.
Compute aging buckets:
- **0–30 Days (Current)**: `invoice_date_due >= today - 30 days`
- **31–60 Days**: `invoice_date_due between 31 and 60 days overdue`
- **61–90 Days**: `invoice_date_due between 61 and 90 days overdue`
- **90+ Days (High Risk)**: `invoice_date_due > 90 days overdue`

Present a categorized summary table by partner and bucket, highlighting delinquent balances.

### 2. Working Capital & Liquidity Ratios
- **Current Ratio**: Current Assets (`account_type in ['asset_current', 'asset_cash']`) / Current Liabilities (`account_type in ['liability_current', 'liability_payable']`).
- **Quick Ratio**: (Cash + Receivables) / Current Liabilities.
- **Days Sales Outstanding (DSO)**: `(Total Receivables / Total Credit Sales) * Period Days`.

### 3. Cashflow Runway & Burn Rate
Query `account.payment` and `account.bank.statement.line` for the past 3 to 6 months to calculate average monthly net cash outflow and calculate total months of runway available.
