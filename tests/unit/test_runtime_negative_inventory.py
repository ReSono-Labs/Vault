from pathlib import Path
import re


PROHIBITED_AGENT_MARKERS = (
    "agent_foundry", "agent_hub", "agent_package", "build_agent",
    "specialist_agent", "generated_agent", "marketplace_agent", "delegate_task",
)

PROHIBITED_CLOUD_AUTH_MARKERS = (
    "resono_api_base_url", "service_api_key", "vault_route_grant",
    "resono_subscription", "hosted_auth",
)


def test_runtime_source_contains_no_prohibited_agent_registration_or_cloud_authority() -> None:
    app_root = Path(__file__).resolve().parents[2] / "app"
    findings = []
    for path in sorted(app_root.rglob("*.py")):
        relative = path.relative_to(app_root).as_posix().lower()
        source = path.read_text(encoding="utf-8").lower()
        for marker in (*PROHIBITED_AGENT_MARKERS, *PROHIBITED_CLOUD_AUTH_MARKERS):
            # Match prohibited identifiers, not a harmless formatting helper
            # such as build_agent_path_areas that cannot register an agent.
            present = bool(re.search(r"(?<![a-z0-9_])"+re.escape(marker)+r"(?![a-z0-9_])", source))
            if marker in relative or present:
                findings.append(f"{relative}:{marker}")
    assert findings == []
