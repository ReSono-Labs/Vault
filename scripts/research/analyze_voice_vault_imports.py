"""Read-only import inventory for the Voice Vault donor.

This script never writes inside the donor. It emits JSON to stdout so evidence
can be reviewed before a bounded file subset is copied into Vault.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


REMOVE_PREFIXES = (
    "app.vault_runtime.agent_packages",
    "app.vault_runtime.handlers.agent_foundry",
    "app.vault_runtime.handlers.agent_package_sync",
    "app.vault_runtime.session_tools.brokers.agent_hub",
    "app.vault_runtime.session_tools.brokers.agent_package_router",
    "app.modules.agent_packages",
    "app.contracts.internal.agent_foundry",
)
DEFER_PREFIXES = (
    "app.vault_runtime.a2a",
    "app.vault_runtime.edge_connector",
    "app.vault_runtime.r1_tunnel",
    "app.vault_runtime.remote_management",
    "app.vault_runtime.tunnel",
)
CLOUD_EDGE_PREFIXES = (
    "app.vault_runtime.client",
    "app.vault_runtime.config",
    "app.vault_runtime.platform_provider",
    "app.vault_runtime.route_grants",
    "app.vault_runtime.worker",
)


def module_for(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            imports.add(node.module)
    return imports


def classification(module: str) -> str:
    if module.startswith(REMOVE_PREFIXES):
        return "REMOVE_AGENT"
    if module.startswith(DEFER_PREFIXES):
        return "DEFER_ADAPTER"
    if module.startswith(CLOUD_EDGE_PREFIXES):
        return "LOCALIZE_CLOUD_EDGE"
    return "PRESERVE"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("donor_root", type=Path)
    args = parser.parse_args()
    root = args.donor_root.resolve()
    app_root = root / "app"
    records = []
    known_modules: dict[str, str] = {}
    for path in sorted(app_root.rglob("*.py")):
        module = module_for(root, path)
        known_modules[module] = str(path)
    for module, raw_path in sorted(known_modules.items()):
        if not module.startswith("app.vault_runtime"):
            continue
        path = Path(raw_path)
        imports = sorted(imported_modules(path))
        internal = sorted(item for item in imports if item in known_modules)
        records.append(
            {
                "module": module,
                "path": raw_path,
                "classification": classification(module),
                "internalImports": internal,
                "externalAppImports": sorted(item for item in imports if item not in known_modules),
            }
        )
    counts: dict[str, int] = {}
    for record in records:
        key = record["classification"]
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"donorRoot": str(root), "counts": counts, "modules": records}, indent=2))


if __name__ == "__main__":
    main()
