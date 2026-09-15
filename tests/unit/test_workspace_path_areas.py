from __future__ import annotations

from pathlib import Path

import pytest

from app.vault_runtime.workspace_files.errors import WorkspaceFileConflictError
from app.vault_runtime.workspace_files.path_areas import (
    LOCAL_PATH_AREA,
    SHARED_PATH_AREA,
    VAULT_PATH_AREA,
    agent_tool_catalog,
    build_agent_path_areas,
    classify_workspace_path_area,
)
from app.vault_runtime.workspace_files.service import WorkspaceFileService
from app.vault_runtime.workspace_storage import WorkspaceStorage
from tests.unit.test_workspace_files_shares import FakeWorkspaceShareRepository, _principal


def test_classify_workspace_path_area() -> None:
    assert classify_workspace_path_area("notes/today.md") == VAULT_PATH_AREA
    assert classify_workspace_path_area("shared/alice/Reports") == SHARED_PATH_AREA
    assert classify_workspace_path_area("local/Documents") == LOCAL_PATH_AREA


def test_workspace_root_info_includes_path_areas(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-1")
    service = WorkspaceFileService(FakeWorkspaceShareRepository(), storage)  # type: ignore[arg-type]
    principal = _principal(user_id="owner-1", workspace_id="workspace-1")

    payload = service.workspace_root_info(principal=principal)

    assert "pathAreas" in payload
    assert set(payload["pathAreas"]) == {VAULT_PATH_AREA, SHARED_PATH_AREA, LOCAL_PATH_AREA}
    assert payload["pathAreas"][VAULT_PATH_AREA]["pathExample"] == "notes/today.md"
    assert payload["tools"]
    assert any(item["name"] == "workspace_patch_file" for item in payload["tools"])


def test_agent_tool_catalog_matches_hermes_openclaw_surface() -> None:
    names = {item["name"] for item in agent_tool_catalog()}
    assert {
        "workspace_root",
        "workspace_list_directory",
        "workspace_read_file",
        "workspace_search_files",
        "workspace_write_file",
        "workspace_save_file",
        "workspace_patch_file",
        "workspace_create_directory",
        "workspace_move_path",
        "workspace_delete_path",
        "workspace_upload_files",
    }.issubset(names)


def test_patch_file_requires_unique_match(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="owner-1", workspace_id="workspace-1")
    service = WorkspaceFileService(FakeWorkspaceShareRepository(), storage)  # type: ignore[arg-type]
    principal = _principal(user_id="owner-1", workspace_id="workspace-1")
    service.write_text_file(
        principal=principal,
        file_key="notes/sample.md",
        content_markdown="alpha beta alpha",
    )

    service.patch_file(
        principal=principal,
        file_key="notes/sample.md",
        old_string="beta",
        new_string="gamma",
    )
    read_back = service.read_file(principal=principal, file_key="notes/sample.md")
    assert read_back.contentMarkdown == "alpha gamma alpha"

    with pytest.raises(WorkspaceFileConflictError):
        service.patch_file(
            principal=principal,
            file_key="notes/sample.md",
            old_string="alpha",
            new_string="delta",
        )


def test_build_agent_path_areas_includes_mounts() -> None:
    areas = build_agent_path_areas(
        shared_mounts=[{"path": "shared/alice/Reports", "shareId": "share-1"}],
        local_enabled=True,
        local_mounts=[{"path": "local/Documents", "source": "helper", "agentAccessible": True}],
    )
    assert areas[SHARED_PATH_AREA]["mounts"][0]["path"] == "shared/alice/Reports"
    assert areas[SHARED_PATH_AREA]["pathExample"] == "shared/alice/Reports/..."
    assert areas[LOCAL_PATH_AREA]["enabled"] is True
    assert areas[LOCAL_PATH_AREA]["mounts"][0]["path"] == "local/Documents"
    assert areas[LOCAL_PATH_AREA]["pathExample"] == "local/Documents/..."
