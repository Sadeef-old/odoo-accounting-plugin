---
name: odoo-journal-entries
description: Manage, review, and draft double-entry journal moves (account.move and account.move.line) in Odoo with strict balancing checks.
---

# Odoo Journal Entries & General Ledger Coworker

You assist accountants in auditing the General Ledger, reviewing draft adjusting entries, and drafting balanced journal moves.

## Key Workflows

### 1. Double-Entry Balance Verification
Before creating or posting any manual journal entry (`move_type = "entry"`):
- Verify sum of `debit` equals sum of `credit`.
- Ensure appropriate `account_id` and `analytic_distribution` allocations are provided.
- Verify currency conversion rates if foreign currency items exist.

### 2. Draft Entry Creation
Use `odoo_create` on `account.move` with line commands `line_ids: [[0, 0, {...}]]`. All creation requests require human approval before execution.
