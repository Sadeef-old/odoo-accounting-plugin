from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

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

# Odoo model and field policy is tenant-owned. The plugin validates request shape,
# then uses discovery results rather than a stale static catalog.

_SAFE_ERROR = "Odoo request failed: {detail}"
_DOMAIN_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "in", "not in", "like", "not like", "ilike", "not ilike", "child_of", "parent_of", "=?"}
_DISCOVERY_MODELS = {
    "ir.model": ("id", "model", "name", "state", "modules"),
    "ir.model.fields": ("id", "name", "field_description", "ttype", "relation", "required", "readonly", "store"),
}
_DISCOVERY_OPERATIONS = {"odoo_discover_models", "odoo_discover_fields", "odoo_read"}
_WRITE_OPERATIONS = {"odoo_create", "odoo_write", "odoo_action"}
_ALL_OPERATIONS = _DISCOVERY_OPERATIONS | _WRITE_OPERATIONS
_WRITE_ALLOWED_MODELS = {
    "account.move",
    "account.move.line",
    "account.payment",
    "res.partner",
    "account.bank.statement.line",
    "account.analytic.line",
}
_ALLOWED_ACTIONS = {
    "action_post",
    "action_draft",
    "button_draft",
    "action_register_payment",
    "action_cancel",
    "action_validate",
}


class OdooRemoteError(ValueError):
    """Carries the actual Odoo error message so the agent can self-correct."""

    def __init__(self, message: str):
        super().__init__(message)
        self.odoo_message = message


class OdooRuntime:
    """Odoo JSON-2-first adapter with a bounded JSON-RPC compatibility fallback."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = "https://sadeefcapital.odoo.com",
        protocol: str = "json2",
    ):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Odoo base_url must be an https URL")
        if protocol not in {"json2", "jsonrpc", "auto"}:
            raise ValueError("Odoo protocol must be json2, jsonrpc, or auto")
        self.transport = transport
        self.base_url = base_url.rstrip("/") + "/"
        self.protocol = protocol

    def _json2_url(self, model: str, method: str) -> str:
        return urljoin(self.base_url, f"json/2/{model}/{method}")

    def _headers(self, credential: dict[str, str]) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"bearer {credential.get('api_key', '')}",
        }
        database = credential.get("database")
        if database:
            headers["X-Odoo-Database"] = database
        return headers

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _authenticate(self, client, credential) -> int | None:
        """Resolve a numeric legacy uid only when the JSON-RPC fallback needs it."""
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

    @staticmethod
    def _is_json2_fallback_response(response: httpx.Response) -> bool:
        return response.status_code in {404, 405, 415, 501}

    async def _execute_json2(
        self, client, *, credential, model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None
    ) -> Any:
        body: dict[str, Any] = {}
        if method == "search_read":
            body = {"domain": args[0] if args else [], **(kwargs or {})}
        elif method == "create":
            body = {"vals": args[0] if args else {}}
        elif method == "write":
            body = {"ids": args[0] if args else [], "vals": args[1] if len(args) > 1 else {}}
        elif method == "fields_get":
            body = kwargs or {}
        elif args:
            body = {"ids": args[0]} if len(args) == 1 else {"ids": args[0], "params": args[1:]}
        body.setdefault("context", {})
        response = await client.post(
            self._json2_url(model, method),
            json=body,
            headers=self._headers(credential),
        )
        if self._is_json2_fallback_response(response):
            raise httpx.HTTPStatusError("JSON-2 endpoint unavailable", request=response.request, response=response)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise OdooRemoteError(message or str(error))
        if isinstance(payload, dict):
            return payload.get("result", payload)
        return payload

    async def _execute(
        self, client, *, credential, model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None
    ) -> Any:
        if self.protocol in {"json2", "auto"}:
            try:
                return await self._execute_json2(
                    client, credential=credential, model=model, method=method, args=args, kwargs=kwargs
                )
            except httpx.HTTPStatusError as exc:
                if self.protocol == "json2" and not self._is_json2_fallback_response(exc.response):
                    raise
        uid = await self._authenticate(client, credential)
        if uid is None:
            raise OdooRemoteError("Odoo authentication failed: JSON-RPC requires uid or username")
        return await self._execute_kw(
            client,
            database=credential.get("database"),
            uid=uid,
            api_key=credential.get("api_key"),
            model=model,
            method=method,
            args=args,
            kwargs=kwargs,
        )

    async def _execute_kw(
        self, client, *, database, uid, api_key, model, method,
        args, kwargs=None,
    ) -> Any:
        """Send one execute_kw call and return the parsed result."""
        full_args = [database, int(uid), api_key, model, method]
        if method == "search_read" and kwargs is not None:
            full_args.extend([list(args), kwargs])
        else:
            full_args += list(args)
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
            headers={"Accept": "application/json", "Content-Type": "application/json"},
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
        if operation.id not in _ALL_OPERATIONS:
            return ConnectorResult(text="Odoo operation is not available.", is_error=True)
        if operation.id in _DISCOVERY_OPERATIONS and operation.mode != "read":
            return ConnectorResult(text="Odoo operation is not available.", is_error=True)
        if operation.id in _WRITE_OPERATIONS and operation.mode != "write":
            return ConnectorResult(text="Odoo operation is not available.", is_error=True)

        if operation.id == "odoo_discover_models":
            arguments = {**arguments, "model": "ir.model", "fields": list(_DISCOVERY_MODELS["ir.model"])}
        elif operation.id == "odoo_discover_fields":
            model = arguments.get("model")
            if not isinstance(model, str) or not model:
                return ConnectorResult(text="odoo_discover_fields requires a model name.", is_error=True)
            arguments = {**arguments, "model": "ir.model.fields", "domain": [["model", "=", model]], "fields": list(_DISCOVERY_MODELS["ir.model.fields"])}
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
        if operation.method != "POST" or operation.path not in {"/jsonrpc", "/json/2"}:
            return ConnectorResult(text="Odoo operation is not available.", is_error=True)

        if operation.id in _DISCOVERY_OPERATIONS:
            return await self._odoo_read(operation, arguments, credential=credential)
        elif operation.id == "odoo_create":
            return await self._odoo_create(operation, arguments, credential=credential)
        elif operation.id == "odoo_write":
            return await self._odoo_write(operation, arguments, credential=credential)
        elif operation.id == "odoo_action":
            return await self._odoo_action(operation, arguments, credential=credential)

        return ConnectorResult(text="Odoo operation is not available.", is_error=True)

    # ------------------------------------------------------------------
    # Mutation operations (Guarded)
    # ------------------------------------------------------------------

    async def _odoo_create(
        self,
        operation: ConnectorOperation,
        arguments: dict[str, Any],
        *,
        credential: dict[str, str],
    ) -> ConnectorResult:
        model = arguments.get("model")
        values = arguments.get("values")
        if not isinstance(model, str) or model not in _WRITE_ALLOWED_MODELS:
            return ConnectorResult(
                text=f"Model {model!r} is not permitted for record creation. Permitted models: {', '.join(sorted(_WRITE_ALLOWED_MODELS))}",
                is_error=True,
            )
        if not isinstance(values, dict) or not values:
            return ConnectorResult(text="Record creation requires a non-empty values dictionary.", is_error=True)

        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                new_id = await self._execute(
                    client,
                    credential=credential,
                    model=model,
                    method="create",
                    args=[values],
                )
                return ConnectorResult(text=json.dumps({"success": True, "model": model, "id": new_id}))
        except OdooRemoteError as exc:
            return ConnectorResult(text=f"Odoo request failed: {exc.odoo_message}", is_error=True)
        except Exception as exc:
            return ConnectorResult(text=f"Odoo request failed: {exc}", is_error=True)

    async def _odoo_write(
        self,
        operation: ConnectorOperation,
        arguments: dict[str, Any],
        *,
        credential: dict[str, str],
    ) -> ConnectorResult:
        model = arguments.get("model")
        record_id = arguments.get("id")
        values = arguments.get("values")
        if not isinstance(model, str) or model not in _WRITE_ALLOWED_MODELS:
            return ConnectorResult(
                text=f"Model {model!r} is not permitted for record updates. Permitted models: {', '.join(sorted(_WRITE_ALLOWED_MODELS))}",
                is_error=True,
            )
        if not isinstance(record_id, int) or isinstance(record_id, bool) or record_id <= 0:
            return ConnectorResult(text="Record update requires a positive integer record ID.", is_error=True)
        if not isinstance(values, dict) or not values:
            return ConnectorResult(text="Record update requires a non-empty values dictionary.", is_error=True)

        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                updated = await self._execute(
                    client,
                    credential=credential,
                    model=model,
                    method="write",
                    args=[[record_id], values],
                )
                return ConnectorResult(text=json.dumps({"success": bool(updated), "model": model, "id": record_id}))
        except OdooRemoteError as exc:
            return ConnectorResult(text=f"Odoo request failed: {exc.odoo_message}", is_error=True)
        except Exception as exc:
            return ConnectorResult(text=f"Odoo request failed: {exc}", is_error=True)

    async def _odoo_action(
        self,
        operation: ConnectorOperation,
        arguments: dict[str, Any],
        *,
        credential: dict[str, str],
    ) -> ConnectorResult:
        model = arguments.get("model")
        action = arguments.get("action")
        ids = arguments.get("ids")
        if not isinstance(model, str) or model not in _WRITE_ALLOWED_MODELS:
            return ConnectorResult(
                text=f"Model {model!r} is not permitted for action execution.",
                is_error=True,
            )
        if not isinstance(action, str) or action not in _ALLOWED_ACTIONS:
            return ConnectorResult(
                text=f"Action {action!r} is not permitted. Permitted actions: {', '.join(sorted(_ALLOWED_ACTIONS))}",
                is_error=True,
            )
        if not isinstance(ids, list) or not ids or any(not isinstance(i, int) or isinstance(i, bool) or i <= 0 for i in ids):
            return ConnectorResult(text="Action execution requires a non-empty list of positive integer IDs.", is_error=True)

        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                res = await self._execute(
                    client,
                    credential=credential,
                    model=model,
                    method=action,
                    args=[ids],
                )
                return ConnectorResult(text=json.dumps({"success": True, "model": model, "action": action, "result": res}))
        except OdooRemoteError as exc:
            return ConnectorResult(text=f"Odoo request failed: {exc.odoo_message}", is_error=True)
        except Exception as exc:
            return ConnectorResult(text=f"Odoo request failed: {exc}", is_error=True)

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
        if not isinstance(model, str) or not model or len(model) > 128 or "." not in model:
            return ConnectorResult(text="A valid Odoo technical model name is required.", is_error=True)
        requested_fields = arguments.get("fields")
        if not isinstance(requested_fields, list) or not requested_fields:
            return ConnectorResult(text="fields is required; discover the model fields first.", is_error=True)
        if any(not isinstance(field, str) or not field or len(field) > 128 for field in requested_fields):
            return ConnectorResult(text="fields must contain valid field names.", is_error=True)
        fields = requested_fields
        if model == "ir.model.fields":
            relation_model = next((term[2] for term in (arguments.get("domain") or []) if isinstance(term, list) and len(term) == 3 and term[0] == "model" and isinstance(term[2], str)), None)
            if relation_model:
                fields = list(_DISCOVERY_MODELS["ir.model.fields"])
        elif model == "ir.model":
            fields = list(_DISCOVERY_MODELS["ir.model"])
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
                records = await self._execute(
                    client,
                    credential=credential,
                    model=model,
                    method="search_read",
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
    async def call(self, operation, arguments, *, credential, approval_id=None, autonomous=False, **kwargs):
        # The connection credential is the plugin's source of runtime configuration;
        # never fall back to the placeholder manifest URL when a connection is bound.
        runtime = OdooRuntime(
            base_url=credential.get("base_url", "https://odoo.example.com"),
            protocol=credential.get("protocol", "json2"),
        )
        return await runtime.call(
            operation,
            arguments,
            credential=credential,
            approval_id=approval_id,
            autonomous=autonomous,
            **kwargs,
        )

    def call_sync(self, operation, arguments, credential, *, approval_id=None, autonomous=False):
        result = asyncio.run(
            self.call(
                operation,
                arguments,
                credential=credential,
                approval_id=approval_id,
                autonomous=autonomous,
            )
        )
        return {"text": result.text, "is_error": result.is_error}

PLUGIN_RUNTIME = _PluginRuntime()
