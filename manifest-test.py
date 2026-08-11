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
    "search_invoices",
    "list_vendor_bills",
    "list_partners",
    "list_payments",
    "list_journal_entries",
    "list_accounts",
}
assert all(operation.mode == "read" for operation in connector.operations)
assert connector.is_bound("odoo-accounting", "search_invoices")
assert connector.is_bound("odoo-accounting", "list_accounts")
assert {field.id for field in connector.credentials} == {"base_url", "database", "username", "api_key"}
print("manifest and connector definition: OK")
