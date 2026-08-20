from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from sadeef_plugins.odoo_accounting.runtime import ConnectorOperation, OdooRuntime  # noqa: E402


def _credential() -> dict[str, str]:
    return {"database": "odoo", "api_key": "secret", "uid": "7"}


@pytest.mark.asyncio
async def test_json2_is_primary_for_reads_and_sends_odoo_headers():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"id": 1, "name": "Acme"}])

    runtime = OdooRuntime(transport=httpx.MockTransport(handler))
    result = await runtime.call(
        ConnectorOperation("odoo_read", "read", "POST", "/json/2", {"type": "object"}),
        {"model": "res.partner", "domain": [], "fields": ["id", "name"], "limit": 5},
        credential=_credential(),
    )

    assert result.is_error is False
    assert json.loads(result.text) == [{"id": 1, "name": "Acme"}]
    assert seen[0].url.path == "/json/2/res.partner/search_read"
    assert seen[0].headers["authorization"] == "bearer secret"
    assert seen[0].headers["x-odoo-database"] == "odoo"
    assert json.loads(seen[0].content) == {"domain": [], "fields": ["id", "name"], "limit": 5, "context": {}}


@pytest.mark.asyncio
async def test_json2_404_falls_back_to_jsonrpc():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.startswith("/json/2/"):
            return httpx.Response(404, json={"error": "not supported"})
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": [{"id": 2, "name": "Legacy"}]},
        )

    runtime = OdooRuntime(transport=httpx.MockTransport(handler))
    result = await runtime.call(
        ConnectorOperation("odoo_read", "read", "POST", "/json/2", {"type": "object"}),
        {"model": "res.partner", "domain": [], "fields": ["id", "name"]},
        credential=_credential(),
    )

    assert result.is_error is False
    assert json.loads(result.text) == [{"id": 2, "name": "Legacy"}]
    assert paths == ["/json/2/res.partner/search_read", "/jsonrpc"]


@pytest.mark.asyncio
async def test_json2_create_requires_approval_and_executes_after_approval():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=101)

    runtime = OdooRuntime(transport=httpx.MockTransport(handler))
    operation = ConnectorOperation("odoo_create", "write", "POST", "/json/2", {"type": "object"})
    values = {"name": "Acme"}

    held = await runtime.call(operation, {"model": "res.partner", "values": values}, credential=_credential())
    assert held.is_error is True
    assert "approval" in held.text
    assert seen == []

    result = await runtime.call(
        operation,
        {"model": "res.partner", "values": values},
        credential=_credential(),
        approval_id="approval-1",
    )
    assert result.is_error is False
    assert json.loads(result.text) == {"success": True, "model": "res.partner", "id": 101}
    assert seen[0].url.path == "/json/2/res.partner/create"
    assert json.loads(seen[0].content) == {"vals": values, "context": {}}


@pytest.mark.asyncio
async def test_autonomous_json2_write_is_refused():
    runtime = OdooRuntime(transport=httpx.MockTransport(lambda request: pytest.fail("must not call Odoo")))
    result = await runtime.call(
        ConnectorOperation("odoo_write", "write", "POST", "/json/2", {"type": "object"}),
        {"model": "res.partner", "id": 1, "values": {"name": "Acme"}},
        credential=_credential(),
        approval_id="approval-1",
        autonomous=True,
    )
    assert result.is_error is True
    assert "unattended" in result.text
