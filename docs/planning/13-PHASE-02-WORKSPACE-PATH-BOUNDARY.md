# Phase 2 Workspace Path Boundary

Status: accepted Phase 2 closure slice, revised for filesystem-backed workspace files

Voice donor:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/workspace_files/repository.py`  
SHA-256: `3244a2bfead1c9dd9a9f59213b795d2c35d72aa03a37a514352d89d5993f9ae0`

Carried test donor:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/tests/unit/test_workspace_file_keys.py`

The exact `PurePosixPath` relative-key normalization behavior is ported without
the donor's hosted SQLAlchemy repository. Workspace file bytes now live on disk
under each provisioned workspace `files/` root. PostgreSQL retains folder-share
authorization only. Legacy projection rows migrate to disk once at startup, then
the projections table is removed.

The Phase 2 contract additionally requires traversal and symlink denial for
local staging/materialization. The smallest adaptation resolves an already
normalized key beneath an explicit workspace files root and rejects a symlinked root,
any existing symlink component, or a resolved escape. It performs no file write
and grants no access; callers must first prove active workspace membership.
