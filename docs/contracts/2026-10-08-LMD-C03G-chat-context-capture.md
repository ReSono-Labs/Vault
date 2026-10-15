# C03G — original Chat context/capability supply capture

NEW necessary metadata only over actual Vault
`app/vault_runtime/conversation/{runtime,runtime_store,contracts}.py` and
`conversation_tools/runtime.py`; REUSE canonical history assembly and ToolCatalog.
No copied transcript/history payload ledger, new provider or grants owner.

Decision CONTINUE: capture bounded history turn IDs and canonical hash of the
actual server-owned history supplied, alongside exact tool definitions supplied to
the same SDK invocation. Freeze that supply once; dispatch still rechecks current
catalog/grants. Original schema/effect/tool identity is evidence, not permission.
Existing context event stores this metadata; selected model/memory versions already
captured there. Do not retrospectively populate legacy events.

Extract existing pure canonical history assembly into a shared helper, preserving
output shape and ordering. Subsequent source qualification must reconstruct and
verify actual input history from canonical rows, never assume timestamps or completed
status prove it. Old events remain unknown. Missing/oversized source stays blocked.
Tests: unchanged canonical history, frozen supplied tools, actual captured metadata,
catalog change still denied at dispatch. Internal prebuild review CONTINUE bounded
producer; no complete-source or activation claim before consumer verification.
