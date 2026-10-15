from pathlib import Path

from app.vault_runtime.email_tools import register_email_tools
from app.vault_runtime.signals.email.session_tools import EMAIL_SIGNAL_CACHE_TOOLS, EMAIL_SIGNAL_SIDE_EFFECT_TOOLS
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog


EXCLUDED_MODULE_MARKERS = (
    "external_ai", "social_posts", "signals/recipes", "signals\\recipes",
    "signals/workouts", "signals/weather", "signals/news",
)


def test_unadmitted_donor_feature_families_are_absent_from_runtime() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    relative_files = [path.relative_to(root).as_posix().casefold() for path in root.rglob("*.py")]
    findings = [
        f"{path}:{marker}" for path in relative_files for marker in EXCLUDED_MODULE_MARKERS
        if marker.replace("\\", "/") in path
    ]
    assert findings == []


def test_mail_tools_use_only_the_two_existing_fixed_agent_identities() -> None:
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    register_email_tools(catalog=catalog, runtime=object())  # type: ignore[arg-type]
    expected = EMAIL_SIGNAL_CACHE_TOOLS | EMAIL_SIGNAL_SIDE_EFFECT_TOOLS
    voice = {item.name for item in catalog.definitions_for(AgentKind.VOICE)}
    background = {item.name for item in catalog.definitions_for(AgentKind.BACKGROUND)}
    assert expected <= voice
    # Current Mail and Agent Mail handlers are shared capabilities of the two
    # fixed agents; grants remain a separate invocation-time requirement.
    assert expected <= background
    assert all(d.audiences <= frozenset({AgentKind.VOICE,AgentKind.BACKGROUND})
               for d in catalog.definitions_for(AgentKind.VOICE))
