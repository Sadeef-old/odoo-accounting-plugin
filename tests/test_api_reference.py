import json
from pathlib import Path


def test_api_reference_skill_is_present_and_officially_grounded():
    skill = Path(__file__).parents[1] / "skills" / "odoo-api-reference" / "SKILL.md"
    text = skill.read_text()
    assert "odoo_discover_models" in text
    assert "search_read" in text
    assert "documentation/19.0/developer/reference/external_api.html" in text


def test_manifest_declares_discovery_operations():
    manifest = json.loads((Path(__file__).parents[1] / ".claude-plugin" / "plugin.json").read_text())
    ids = {operation["id"] for operation in manifest["connectors"][0]["operations"]}
    assert {"odoo_discover_models", "odoo_discover_fields", "odoo_read"}.issubset(ids)
