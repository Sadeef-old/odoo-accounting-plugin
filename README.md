# Odoo Accounting plugin — pilot draft

This draft is deliberately read-only. It is intended to be imported as an approved Sadeef capability pack and configured through Extensions.

## Planned first capabilities

- Search customer invoices
- List customers and vendors
- Read one invoice's bounded summary

No invoice creation, posting, payment, update, or deletion is included.

## Authentication boundary

The plugin contains no credentials. The Connection setup form collects the Odoo tenant base URL, database, user identifier/UID, and API key, then encrypts the values at the application boundary. The tenant URL is supplied at setup time; the manifest URL is only a safe HTTPS placeholder used for validation and preview.

## Repository decision pending

The external GitHub repository name has not yet been chosen. This is a local contract draft only.
