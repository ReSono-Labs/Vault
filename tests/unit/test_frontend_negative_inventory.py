from pathlib import Path


PROHIBITED_FRONTEND_MARKERS = (
    "foundry", "build agent", "agent package", "agent-package", "/agents",
    "vaultroutegrant", "opaque relay", "subscription", "billing",
    "resono.ai", "api.resono", "tailscale", "link runtime",
    "external_ai", "social_posts",
)


def test_browser_voice_runtime_has_no_cloud_or_non_system_agent_surface() -> None:
    root = Path(__file__).resolve().parents[2] / "frontend" / "src"
    findings = []
    for path in sorted((*root.rglob("*.ts"), *root.rglob("*.tsx"))):
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        source = path.read_text(encoding="utf-8").casefold()
        for marker in PROHIBITED_FRONTEND_MARKERS:
            if marker in source:
                findings.append(f"{path.relative_to(root)}:{marker}")
    assert findings == []
