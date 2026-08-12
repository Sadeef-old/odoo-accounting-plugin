from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse, urljoin

import httpx

from dataclasses import dataclass

@dataclass
class ConnectorOperation:
    id: str
    mode: str
    method: str
    path: str
    input_schema: dict

@dataclass
class ConnectorResult:
    text: str
    is_error: bool = False

_MAX_LIMIT = 200

# ---------------------------------------------------------------------------
# Model allowlist — the only Odoo models the agent can query via odoo_read.
# Each model maps to the set of fields the agent is allowed to request.
# Enforced at the provider level before any RPC call is made.
# ---------------------------------------------------------------------------
_READ_ALLOWLIST: dict[str, tuple[str, ...]] = {
    # Core accounting documents
    "account.move": (
        "id", "name", "invoice_date", "date", "partner_id", "state",
        "move_type", "amount_total", "amount_untaxed", "amount_tax",
        "amount_residual", "currency_id", "company_id", "invoice_payment_term_id",
        "invoice_date_due", "narration", "ref", "payment_reference",
        "auto_post", "to_check", "fiscal_position_id",
    ),
    "account.move.line": (
        "id", "move_id", "date", "account_id", "partner_id", "name",
        "debit", "credit", "balance", "amount_currency", "currency_id",
        "tax_ids", "tax_line_id", "analytic_distribution",
        "payment_id", "reconciled", "full_reconcile_id",
        "display_type", "is_balanced",
    ),
    "account.payment": (
        "id", "name", "date", "amount", "payment_type", "partner_type",
        "partner_id", "journal_id", "state", "currency_id", "payment_method_line_id",
        "destination_account_id", "is_reconciled", "paired_payment_id",
    ),
    # Master data
    "res.partner": (
        "id", "name", "email", "phone", "mobile", "country_id", "state_id",
        "customer_rank", "supplier_rank", "vat", "website",
        "property_account_position_id", "property_payment_term_id",
        "property_supplier_payment_term_id", "credit", "debit",
        "total_invoiced", "total_due", "total_overdue",
    ),
    "res.company": (
        "id", "name", "country_id", "currency_id", "partner_id",
        "phone", "email", "website", "vat", "company_registry",
        "fiscalyear_start_day", "fiscalyear_start_month",
        "account_fiscal_country_id",
    ),
    "res.currency": (
        "id", "name", "full_name", "symbol", "rate", "active", "company_id",
    ),
    # Chart of accounts and tax
    "account.account": (
        "id", "code", "name", "account_type", "reconcile", "deprecated",
        "company_id", "currency_id", "group_id", "root_id",
        "current_balance", "current_balance_closing_display",
    ),
    "account.journal": (
        "id", "name", "code", "type", "active", "company_id",
        "default_account_id", "payment_method_line_ids",
        "bank_account_id", "bank_id", "currency_id",
    ),
    "account.tax": (
        "id", "name", "amount", "amount_type", "type_tax_use",
        "tax_group_id", "invoice_account_id", "refund_account_id",
        "active", "company_id",
    ),
    "account.tax.group": (
        "id", "name", "company_id", "sequence",
    ),
    "account.fiscal.position": (
        "id", "name", "company_id", "country_id", "country_group_id",
        "state_ids", "zip_from", "zip_to", "active",
    ),
    "account.payment.term": (
        "id", "name", "active", "company_id",
    ),
    "account.payment.term.line": (
        "id", "value", "value_amount", "days", "day_of_the_month",
        "payment_id", "nb_days",
    ),
    # Banking
    "account.bank.account": (
        "id", "acc_number", "bank_id", "partner_id", "company_id",
        "currency_id", "account_type",
    ),
    "res.bank": (
        "id", "name", "bic", "country", "street", "city", "state", "zip", "active",
    ),
    # Analytic
    "account.analytic.plan": (
        "id", "name", "active", "company_id",
    ),
    "account.analytic.account": (
        "id", "name", "code", "active", "company_id", "plan_id",
        "partner_id", "balance", "debit", "credit",
    ),
    "account.analytic.line": (
        "id", "name", "date", "amount", "unit_amount", "account_id",
        "partner_id", "company_id", "product_id", "general_account_id",
    ),
    # Budgets
    "account.budget.post": (
        "id", "name", "active", "company_id",
    ),
    "account.budget.availability": (
        "id", "date", "amount", "account_id", "analytic_account_id",
    ),
    # Period / fiscal year
    "account.fiscal.year": (
        "id", "name", "date_from", "date_to", "company_id",
    ),
    # Modules (for discovery)
    "ir.module.module": (
        "id", "name", "shortdesc", "state", "latest_version", "summary",
        "category_id", "installed_version",
    ),
}

_SAFE_ERROR = "Odoo request failed: {detail}"
_DOMAIN_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "in", "not in", "like", "not like", "ilike", "not ilike", "child_of", "parent_of", "=?"}


class OdooRemoteError(ValueError):
    """Carries the actual Odoo error message so the agent can self-correct."""

    def __init__(self, message: str):
        super().__init__(message)
        self.odoo_message = message


class OdooRuntime:
    """Read-only Odoo JSON-RPC adapter with flexible model-level read access."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = "https://odoo.example.com",
    ):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Odoo base_url must be an https URL")
        self.transport = transport
        self.base_url = base_url.rstrip("/") + "/"

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _authenticate(self, client, credential) -> int | None:
        """Resolve a numeric Odoo uid, authenticating by username when needed."""
        database = credential.get("database")
        api_key = credential.get("api_key")
        uid = credential.get("uid")
        username = credential.get("username")
        if uid and not str(uid).isdigit() and not username:
            username, uid = uid, None
        if uid is not None and str(uid).isdigit():
            return int(uid)
        if not username:
            return None
        auth_body = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "authenticate",
                "args": [database, username, api_key, {}],
            },
            "id": 1,
        }
        auth_response = await client.post(
            urljoin(self.base_url, "jsonrpc"),
            json=auth_body,
            headers={"Accept": "application/json"},
        )
        auth_response.raise_for_status()
        auth_payload = auth_response.json()
        if auth_payload.get("error"):
            err = auth_payload["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise OdooRemoteError(f"Authentication failed: {msg}")
        uid = auth_payload.get("result")
        if isinstance(uid, int) and uid > 0:
            return uid
        return None

    async def _execute_kw(
        self, client, *, database, uid, api_key, model, method,
        args, kwargs=None,
    ) -> Any:
        """Send one execute_kw call and return the parsed result."""
        full_args = [database, int(uid), api_key, model, method] + list(args)
        if kwargs is not None:
            full_args.append(kwargs)
        body = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": full_args,
            },
            "id": 1,
        }
        response = await client.post(
            urljoin(self.base_url, "jsonrpc"),
            json=body,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            err = payload["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise OdooRemoteError(msg)
        result = payload.get("result")
        if not isinstance(result, (list, dict, int, float, bool)) and result is not None:
            raise ValueError("Odoo returned an unexpected response type")
        return result

    # ------------------------------------------------------------------
    # Main dispatch
    # ------------------------------------------------------------------

    async def call(self, operation, arguments, *, credential, approval_id=None, autonomous=False, **kwargs):
        if not isinstance(operation, ConnectorOperation):
            raise TypeError("plugin call requires a declared connector operation")
        if operation.id != "odoo_read" or operation.mode != "read":
            return ConnectorResult(text="Odoo operation is not available.", is_error=True)
        return await self._call_operation(
            operation,
            arguments,
            credential=credential,
            approval_id=approval_id,
            autonomous=autonomous,
        )

    async def _call_operation(
        self,
        operation: ConnectorOperation,
        arguments: dict[str, Any],
        *,
        credential: dict[str, str],
        approval_id=None,
        user_id=None,
        org_id=None,
        autonomous=False,
        factory=None,
    ) -> ConnectorResult:
        if operation.mode not in {"read", "write"}:
            return ConnectorResult(text="Odoo operation is not available.", is_error=True)
        if operation.mode == "write" and not approval_id:
            return ConnectorResult(text="This accounting change requires human approval first.", is_error=True)
        if operation.mode == "write" and autonomous:
            return ConnectorResult(text="Accounting changes cannot run unattended.", is_error=True)
        if operation.path != "/jsonrpc" or operation.method != "POST":
            return ConnectorResult(text="Odoo operation is not available.", is_error=True)
        if operation.id != "odoo_read":
            return ConnectorResult(text="Odoo operation is not available.", is_error=True)

        return await self._odoo_read(operation, arguments, credential=credential)

    # ------------------------------------------------------------------
    # Flexible read
    # ------------------------------------------------------------------

    async def _odoo_read(
        self,
        operation: ConnectorOperation,
        arguments: dict[str, Any],
        *,
        credential: dict[str, str],
    ) -> ConnectorResult:
        model = arguments.get("model")
        if not isinstance(model, str) or model not in _READ_ALLOWLIST:
            allowed = sorted(_READ_ALLOWLIST)
            return ConnectorResult(
                text=f"Model {model!r} is not allowlisted for read access. "
                     f"Allowed models: {', '.join(allowed)}",
                is_error=True,
            )
        allowed_fields = _READ_ALLOWLIST[model]
        requested_fields = arguments.get("fields")
        if not isinstance(requested_fields, list) or not requested_fields:
            fields = list(allowed_fields)
        else:
            invalid = [f for f in requested_fields if f not in allowed_fields]
            if invalid:
                return ConnectorResult(
                    text=f"Fields not allowed on {model}: {', '.join(invalid)}. "
                         f"Allowed fields: {', '.join(allowed_fields)}",
                    is_error=True,
                )
            fields = requested_fields
        domain = arguments.get("domain")
        if domain is None:
            domain = []
        domain_error = self._validate_domain(domain)
        if domain_error:
            return ConnectorResult(text=domain_error, is_error=True)
        limit_raw = arguments.get("limit") or 80
        if isinstance(limit_raw, bool) or not isinstance(limit_raw, int):
            return ConnectorResult(text="Invalid limit: it must be an integer between 1 and 200.", is_error=True)
        limit = min(max(limit_raw, 1), _MAX_LIMIT)

        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                uid = await self._authenticate(client, credential)
                if uid is None:
                    return ConnectorResult(text="Odoo authentication failed.", is_error=True)
                database = credential.get("database")
                api_key = credential.get("api_key")
                records = await self._execute_kw(
                    client, database=database, uid=uid, api_key=api_key,
                    model=model, method="search_read",
                    args=[domain],
                    kwargs={"fields": fields, "limit": limit},
                )
        except OdooRemoteError as exc:
            return ConnectorResult(
                text=f"Odoo request failed: {exc.odoo_message}", is_error=True
            )
        except (httpx.HTTPError, ValueError) as exc:
            detail = str(exc) if str(exc) else type(exc).__name__
            return ConnectorResult(
                text=f"Odoo request failed: {detail}", is_error=True
            )
        except Exception as exc:
            return ConnectorResult(
                text=f"Odoo request failed: {type(exc).__name__}: {exc}", is_error=True
            )
        if not isinstance(records, list):
            return ConnectorResult(text="Odoo request failed: invalid response", is_error=True)
        return ConnectorResult(text=json.dumps(records))

    @staticmethod
    def _validate_domain(domain: object) -> str | None:
        """Validate common Odoo domain mistakes before they reach JSON-RPC."""
        if not isinstance(domain, list):
            return "Invalid domain: expected a list of [field, operator, value] conditions."
        for index, condition in enumerate(domain):
            if isinstance(condition, str):
                if condition not in {"&", "|", "!"}:
                    return f"Invalid domain item {index}: logical tokens must be '&', '|' or '!'."
                continue
            if not isinstance(condition, list) or len(condition) != 3:
                return f"Invalid domain item {index}: expected [field, operator, value]."
            field, operator, value = condition
            if not isinstance(field, str) or not field:
                return f"Invalid domain item {index}: field must be a non-empty string."
            if not isinstance(operator, str) or operator not in _DOMAIN_OPERATORS:
                return f"Invalid domain item {index}: unsupported operator {operator!r}."
            if isinstance(value, bool):
                return f"Invalid domain item {index} for {field!r}: use 1 or 0 for booleans, not true/false."
            if operator in {"in", "not in"} and not isinstance(value, list):
                return f"Invalid domain item {index} for {field!r}: {operator} requires a JSON list."
            if operator not in {"in", "not in"} and isinstance(value, list):
                return f"Invalid domain item {index} for {field!r}: {operator} does not accept a list; use 'in' or '=' with a scalar."
        return None


class _PluginRuntime:
    async def call(self, operation, arguments, *, credential, **kwargs):
        return await OdooRuntime().call(operation, arguments, credential=credential, **kwargs)

    def call_sync(self, operation, arguments, credential):
        import asyncio
        result = asyncio.run(self.call(operation, arguments, credential=credential))
        return {"text": result.text, "is_error": result.is_error}

PLUGIN_RUNTIME = _PluginRuntime()
