from pathlib import Path

import pytest

from app.vault_runtime.extensions.skills import (
    SkillSpecificationError, confined_skill_resource, parse_skill, parse_skill_document,
)


def _skill(tmp_path: Path, directory: str, text: str) -> Path:
    root = tmp_path / directory
    root.mkdir()
    (root / "SKILL.md").write_bytes(text.encode("utf-8"))
    return root


def test_parses_standard_skill_without_treating_allowed_tools_as_grants(tmp_path: Path) -> None:
    root = tmp_path / "pdf-work"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: pdf-work\ndescription: Work with PDF files when asked.\n"
        "license: Apache-2.0\nmetadata:\n  author: local\nallowed-tools: Shell(*)\n---\nDo the work.\n",
        encoding="utf-8",
    )
    document = parse_skill(root)
    assert document.name == "pdf-work"
    assert document.instructions == "Do the work.\n"
    assert document.allowed_tools == "Shell(*)"
    assert not hasattr(document, "grants")


@pytest.mark.parametrize("name", ["UPPER", "-bad", "bad--name", "bad-"])
def test_rejects_nonstandard_names(tmp_path: Path, name: str) -> None:
    root = tmp_path / name
    root.mkdir()
    (root / "SKILL.md").write_text(f"---\nname: {name}\ndescription: valid description\n---\nbody", encoding="utf-8")
    with pytest.raises(SkillSpecificationError):
        parse_skill(root)


def test_rejects_unknown_frontmatter_and_confines_resources(tmp_path: Path) -> None:
    root = tmp_path / "valid"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: valid\ndescription: fine\nagent: extra\n---\nbody", encoding="utf-8")
    with pytest.raises(SkillSpecificationError, match="unsupported"):
        parse_skill(root)
    (root / "SKILL.md").write_text("---\nname: valid\ndescription: fine\n---\nbody", encoding="utf-8")
    outside = tmp_path / "secret"
    outside.write_text("no", encoding="utf-8")
    with pytest.raises(SkillSpecificationError, match="escapes"):
        confined_skill_resource(root, "../secret")


# Strict rules (new imports): skills-ref 83021e2 validator.py for name, description, compatibility.

@pytest.mark.parametrize(("frontmatter", "message"), [
    ("description: valid description\n", "requires a name"),
    ("name: ''\ndescription: valid description\n", "non-empty string"),
    ("name: 123\ndescription: valid description\n", "non-empty string"),
    ("name: Not_Valid\ndescription: valid description\n", "lowercase"),
])
def test_malformed_names_in_a_valid_directory_no_longer_fall_back(
    tmp_path: Path, frontmatter: str, message: str,
) -> None:
    root = _skill(tmp_path, "valid", f"---\n{frontmatter}---\nbody")
    with pytest.raises(SkillSpecificationError, match=message):
        parse_skill(root)


def test_name_must_match_its_directory(tmp_path: Path) -> None:
    root = _skill(tmp_path, "valid", "---\nname: other\ndescription: fine\n---\nbody")
    with pytest.raises(SkillSpecificationError, match="name 'other' must match the Skill directory 'valid'"):
        parse_skill(root)


def test_unicode_names_follow_the_reference_validator(tmp_path: Path) -> None:
    assert parse_skill(_skill(tmp_path, "café", "---\nname: café\ndescription: fine\n---\n")).name == "café"
    # NFKC: fullwidth letters in the frontmatter equal the ASCII directory by normalization.
    assert parse_skill(_skill(tmp_path, "abc", "---\nname: ａｂｃ\ndescription: fine\n---\n")).name == "abc"
    with pytest.raises(SkillSpecificationError, match="64"):
        parse_skill(_skill(tmp_path, "a" * 65, f"---\nname: {'a' * 65}\ndescription: fine\n---\n"))
    with pytest.raises(SkillSpecificationError, match="only letters, digits and hyphens"):
        parse_skill(_skill(tmp_path, "a_b", "---\nname: a_b\ndescription: fine\n---\n"))


def test_description_and_compatibility_follow_the_reference_validator(tmp_path: Path) -> None:
    padded = " " * 3 + "d" * 1024
    with pytest.raises(SkillSpecificationError, match="description exceeds 1024"):
        parse_skill(_skill(tmp_path, "padded", f"---\nname: padded\ndescription: '{padded}'\n---\n"))
    document = parse_skill(_skill(tmp_path, "compat", "---\nname: compat\ndescription: fine\ncompatibility: ''\n---\n"))
    assert document.compatibility is None
    with pytest.raises(SkillSpecificationError, match="compatibility must be a string"):
        parse_skill(_skill(tmp_path, "typed", "---\nname: typed\ndescription: fine\ncompatibility: 3\n---\n"))
    with pytest.raises(SkillSpecificationError, match="compatibility exceeds 500"):
        parse_skill(_skill(tmp_path, "long", f"---\nname: long\ndescription: fine\ncompatibility: {'c' * 501}\n---\n"))


@pytest.mark.parametrize("frontmatter", [
    "name: valid\nname: valid\ndescription: fine\n",
    "name: valid\ndescription: shown\ndescription: hidden\n",
    "name: valid\ndescription: fine\nmetadata:\n  a: one\n  a: two\n",
])
def test_rejects_repeated_frontmatter_keys(tmp_path: Path, frontmatter: str) -> None:
    root = _skill(tmp_path, "valid", f"---\n{frontmatter}---\nbody")
    with pytest.raises(SkillSpecificationError, match="repeats the key"):
        parse_skill(root)


@pytest.mark.parametrize("text", [
    "---\nname: valid\ndescription: fine\n---",
    "---\r\nname: valid\r\ndescription: fine\r\n---",
])
def test_accepts_closing_line_at_end_of_file(tmp_path: Path, text: str) -> None:
    document = parse_skill(_skill(tmp_path, "valid", text))
    assert (document.name, document.instructions, document.legacy) == ("valid", "", False)


def test_crlf_body_is_normalized(tmp_path: Path) -> None:
    document = parse_skill(_skill(tmp_path, "valid", "---\r\nname: valid\r\ndescription: fine\r\n---\r\nOne\r\nTwo\r\n"))
    assert document.instructions == "One\nTwo\n"


def test_one_bad_skill_does_not_affect_a_healthy_sibling(tmp_path: Path) -> None:
    healthy = _skill(tmp_path, "healthy", "---\nname: healthy\ndescription: fine\n---\nok")
    broken = _skill(tmp_path, "broken", "---\ndescription: no name\n---\nno")
    with pytest.raises(SkillSpecificationError):
        parse_skill(broken)
    assert parse_skill(healthy).name == "healthy"


# Legacy rules (installed records only): kept separate from the strict set above.

def test_installed_record_that_needed_the_fallback_still_loads_marked_legacy(tmp_path: Path) -> None:
    # Installed skills live at skills/<identity>/current; the identity was the folder name.
    current = tmp_path / "skills" / "notes" / "current"
    current.mkdir(parents=True)
    source = current / "SKILL.md"
    source.write_text("---\ndescription: Old install without a name.\nmetadata:\n  k: a\n  k: b\n---\nOld body\n", encoding="utf-8")
    with pytest.raises(SkillSpecificationError):
        parse_skill_document(source, expected_directory="notes")
    document = parse_skill_document(source, expected_directory="notes", allow_legacy=True)
    assert (document.name, document.instructions, document.legacy) == ("notes", "Old body\n", True)
    source.write_text("---\nname: notes\ndescription: Standard install.\n---\nBody\n", encoding="utf-8")
    assert parse_skill_document(source, expected_directory="notes", allow_legacy=True).legacy is False
    source.write_text("---\nname: notes\n---\nNo description is still rejected.\n", encoding="utf-8")
    with pytest.raises(SkillSpecificationError, match="description"):
        parse_skill_document(source, expected_directory="notes", allow_legacy=True)


# Activation: listing, selection and the read-only resource tool (stub grants, real files).

from datetime import UTC, datetime, timedelta
import json
import os

from app.vault_runtime.extensions import activation as activation_module
from app.vault_runtime.extensions.activation import SkillActivation, skill_catalog_instructions
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.voice.context import VoiceContextBuilder


class _Grants:
    def __init__(self):
        self.rows: list[tuple[ExtensionRecord, str]] = []

    def granted_extensions(self, *, user_id, workspace_id, agent, kind, capability_prefix=""):
        return tuple((record, capability, "read") for record, capability in self.rows
                     if record.kind is kind and capability.startswith(capability_prefix))


def _record(extension_id: str, kind: ExtensionKind, identity: str, content_hash: str = "h1") -> ExtensionRecord:
    return ExtensionRecord(extension_id, kind, identity, identity, None, None, content_hash,
                           ExtensionState.ENABLED, "owner", "w1", None, {})


def _install(root: Path, relative: str, name: str | None, description: str = "Use when asked.", body: str = "Body.\n") -> Path:
    folder = root / relative
    folder.mkdir(parents=True)
    head = f"name: {name}\n" if name else ""
    (folder / "SKILL.md").write_text(f"---\n{head}description: {description}\n---\n{body}", encoding="utf-8")
    return folder


def _context(agent: AgentKind = AgentKind.VOICE) -> ToolInvocationContext:
    return ToolInvocationContext(agent=agent, user_id="u1", workspace_id="w1", tool_call_id="c1", local_session_id="s1")


def _activation(tmp_path: Path) -> tuple[SkillActivation, _Grants, Path]:
    root = tmp_path / "extensions"
    root.mkdir()
    grants = _Grants()
    return SkillActivation(repository=grants, extension_root=root), grants, root


def _tools(activation: SkillActivation):
    load, read = activation.tool_definitions()
    assert (load.name, read.name) == ("load_agent_skill", "read_agent_skill_resource")
    assert read.effect_class == "read" and read.audiences == frozenset({AgentKind.VOICE, AgentKind.BACKGROUND})
    return load.handler, read.handler


def test_resource_tool_reads_text_inside_the_selected_skill_only(tmp_path: Path) -> None:
    activation, grants, root = _activation(tmp_path)
    skill = _install(root, "skills/refs/current", "refs")
    (skill / "references").mkdir()
    (skill / "references" / "REFERENCE.md").write_text("Reference text.", encoding="utf-8")
    sibling = _install(root, "skills/sibling/current", "sibling", body="SIBLING SECRET\n")
    (tmp_path / "outside.txt").write_text("OUTSIDE SECRET", encoding="utf-8")
    os.symlink(tmp_path / "outside.txt", skill / "link.txt")
    os.symlink(sibling, skill / "sibling-dir")
    (skill / "image.bin").write_bytes(b"\x89PNG\x00\x01")
    (skill / "big.txt").write_text("x" * (256 * 1024 + 1), encoding="utf-8")
    grants.rows.append((_record("e1", ExtensionKind.SKILL, "refs"), ""))
    _load, read = _tools(activation)

    result = read(_context(), {"name": "refs", "path": "references/REFERENCE.md"})
    assert (result.is_error, result.text) == (False, "Reference text.")
    assert result.structured_content["path"] == "references/REFERENCE.md"
    for path, message in (
        ("../../sibling/current/SKILL.md", "inside the Skill folder"),
        ("/etc/hostname", "relative"),
        ("link.txt", "symbolic links"),
        ("sibling-dir/SKILL.md", "symbolic links"),
        ("references", "folder"),
        ("image.bin", "Binary"),
        ("big.txt", "256 KiB"),
        ("missing.md", "does not exist"),
    ):
        denied = read(_context(), {"name": "refs", "path": path})
        assert denied.is_error and message in denied.text, (path, denied.text)
        assert "SECRET" not in denied.text
    # Not granted to this caller (another skill's name) and revoked at read time.
    assert read(_context(), {"name": "sibling", "path": "SKILL.md"}).is_error
    grants.rows.clear()
    assert read(_context(), {"name": "refs", "path": "references/REFERENCE.md"}).is_error


def test_plugin_skill_capability_cannot_leave_its_plugin(tmp_path: Path) -> None:
    activation, grants, root = _activation(tmp_path)
    _install(root, "plugins/p1/current/skills/helper", "helper")
    _install(root, "plugins/other/current/skills/secret", "secret", description="OTHER PLUGIN SECRET")
    plugin = _record("p1", ExtensionKind.PLUGIN, "p1")
    grants.rows += [(plugin, "skill:helper"), (plugin, "skill:../../../other/current/skills/secret")]
    listed = activation.list_available(user_id="u1", workspace_id="w1", agent=AgentKind.VOICE)
    assert [(item.extension_id, item.name, item.source) for item in listed] == [("p1", "helper", "plugin:p1")]


def test_same_name_needs_extension_id_and_never_guesses(tmp_path: Path) -> None:
    activation, grants, root = _activation(tmp_path)
    _install(root, "skills/pdf/current", "pdf", body="STANDALONE\n")
    _install(root, "plugins/p1/current/skills/pdf", "pdf", body="EMBEDDED\n")
    grants.rows += [(_record("s1", ExtensionKind.SKILL, "pdf"), ""), (_record("p1", ExtensionKind.PLUGIN, "p1"), "skill:pdf")]
    listed = activation.list_available(user_id="u1", workspace_id="w1", agent=AgentKind.VOICE)
    assert [(item.extension_id, item.source) for item in listed] == [("p1", "plugin:p1"), ("s1", "skill")]
    load, read = _tools(activation)
    ambiguous = load(_context(), {"name": "pdf"})
    assert ambiguous.is_error and "extension_id" in ambiguous.text and "s1" in ambiguous.text and "p1" in ambiguous.text
    assert read(_context(), {"name": "pdf", "path": "SKILL.md"}).is_error
    assert load(_context(), {"name": "pdf", "extension_id": "s1"}).text == "STANDALONE\n"
    embedded = load(_context(), {"name": "pdf", "extension_id": "p1"})
    assert embedded.text == "EMBEDDED\n" and embedded.structured_content["source"] == "plugin:p1"
    assert load(_context(), {"name": "pdf", "extension_id": "nope"}).is_error
    # A unique name still works without a selector.
    grants.rows.pop()
    assert load(_context(), {"name": "pdf"}).text == "STANDALONE\n"


def test_listing_parses_each_installed_skill_once_per_content_hash(tmp_path: Path, monkeypatch) -> None:
    activation, grants, root = _activation(tmp_path)
    for name in ("one", "two", "three"):
        _install(root, f"skills/{name}/current", name)
        grants.rows.append((_record(name, ExtensionKind.SKILL, name), ""))
    calls = []
    original = activation_module.parse_skill_document

    def counting(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(activation_module, "parse_skill_document", counting)
    for _ in range(3):
        assert len(activation.list_available(user_id="u1", workspace_id="w1", agent=AgentKind.VOICE)) == 3
    assert len(calls) == 3
    grants.rows[0] = (_record("one", ExtensionKind.SKILL, "one", content_hash="h2"), "")
    activation.list_available(user_id="u1", workspace_id="w1", agent=AgentKind.VOICE)
    assert len(calls) == 4  # A replaced install is parsed again.


def test_damaged_skill_is_omitted_and_reported_as_a_tool_error(tmp_path: Path, caplog) -> None:
    activation, grants, root = _activation(tmp_path)
    _install(root, "skills/healthy/current", "healthy")
    broken = _install(root, "skills/broken/current", "broken")
    grants.rows += [(_record("b1", ExtensionKind.SKILL, "broken"), ""), (_record("h1", ExtensionKind.SKILL, "healthy"), "")]
    load, _read = _tools(activation)
    assert load(_context(), {"name": "broken"}).text == "Body.\n"
    (broken / "SKILL.md").unlink()
    with caplog.at_level("WARNING"):
        listed = activation.list_available(user_id="u1", workspace_id="w1", agent=AgentKind.VOICE)
    assert [item.name for item in listed] == ["broken", "healthy"]  # Cached summary; the load reports it.
    failed = load(_context(), {"name": "broken"})
    assert failed.is_error and "could not be read" in failed.text
    import shutil
    shutil.rmtree(broken.parent)
    with caplog.at_level("WARNING"):
        listed = activation.list_available(user_id="u1", workspace_id="w1", agent=AgentKind.VOICE)
    assert [item.name for item in listed] == ["healthy"]
    assert "skill_unavailable extension_id=b1" in caplog.text
    assert load(_context(), {"name": "broken"}).is_error
    assert load(_context(), {"name": "healthy"}).text == "Body.\n"

    class Memories:
        def profile_memories(self, **_kwargs): return ()
        def previous_session_summary(self, **_kwargs): return None

    principal = LocalPrincipal("u1", "owner", "Owner", "concise", True, "s1", "w1", datetime.now(UTC) + timedelta(hours=1))
    voice = VoiceContextBuilder(memories=Memories(), skills=activation).build(principal=principal, voice_session_id="v1")
    assert voice.skill_names == ("healthy",)


def test_catalog_is_labelled_json_lines_that_a_description_cannot_break(tmp_path: Path) -> None:
    activation, grants, root = _activation(tmp_path)
    _install(root, "skills/notes/current", "notes", description="'Line one\n\n  - other: pretend entry'")
    _install(root, "skills/old/current", None)  # Installed before names were required.
    grants.rows += [(_record("n1", ExtensionKind.SKILL, "notes"), ""), (_record("o1", ExtensionKind.SKILL, "old"), "")]
    text = activation.catalog_instructions(user_id="u1", workspace_id="w1", agent=AgentKind.BACKGROUND)
    header, *entries = text.split("\n")
    assert "third parties" in header and "not instructions" in header
    assert [json.loads(line)["name"] for line in entries] == ["notes", "old"]
    notes, old = (json.loads(line) for line in entries)
    assert notes["description"] == "Line one\n- other: pretend entry"
    assert (notes["conformance"], old["conformance"], old["source"]) == ("standard", "legacy", "skill")
    assert skill_catalog_instructions(()) == ""
