from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.connections.connectors.manifest import parse_connector_manifest
from app.skills.packs import parse_manifest

root = Path(__file__).parent
plugin = (root / ".claude-plugin/plugin.json").read_bytes()
skill = (root / "skills/odoo-accounting/SKILL.md").read_bytes()

manifest = parse_manifest([
    (".claude-plugin/plugin.json", plugin),
    ("skills/odoo-accounting/SKILL.md", skill),
])
assert manifest.name == "odoo-accounting"
assert len(manifest.connectors) == 1
connector = parse_connector_manifest(manifest.connectors[0])
assert connector.id == "odoo"
assert {operation.id for operation in connector.operations} == {
    "odoo_discover_models",
    "odoo_discover_fields",
    "odoo_read",
    "odoo_create",
    "odoo_write",
    "odoo_action",
}
assert connector.is_bound("odoo-accounting", "odoo_read")
assert connector.is_bound("odoo-accounting", "odoo_create")
assert connector.is_bound("odoo-financial-analysis", "odoo_read")
assert connector.is_bound("odoo-tax-compliance", "odoo_write")
assert {field.id for field in connector.credentials} == {"base_url", "database", "username", "api_key"}
print("manifest and connector definition: OK")
