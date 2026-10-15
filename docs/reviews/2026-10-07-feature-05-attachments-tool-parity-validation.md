# Feature 05 — Chat attachments and tool parity validation

Read COMPLETE chat-attachments-and-tool-parity-plan r2 (including Phase02
prerequisites) before disposition. Actual sources: workspace_files manager/service/
store/access/local_operations/tools; BrowserWorkspaceFileBrowser upload UI;
ToolInvocationContext/catalog, VoiceToolRuntime/LocalToolAuthority, memory pending
actions, current SDK string input and HTTP response/Permissions-Policy.

Verdict: existing file upload/storage/tools/grants are IMPLEMENTED. Chat-private
staging/model-input attachments and conversation-scoped tool execution/confirmation
are NOT IMPLEMENTED. A document preview/file upload is not model file processing.

| Planned obligation | Actual implementation compared | Status / missing delta |
|---|---|---|
| Reuse scoped file service/managed storage/authorized Save to Workspace | WorkspaceFileManagerService uploads128MB bounds; service resolves access and require_write; browser file UI | DONE baseline; not another filesystem |
| Chat attach picker/paste/drop/screen snapshot/camera and tray | No Chat surface or staging client; server camera=() | NOT DONE; camera conditional, no blanket policy weakening |
| Private staged object not silent shared-workspace upload | Existing files are workspace/file-service objects, no Chat staging namespace/adapter | NOT DONE adapter/data ownership, existing store reused |
| Attachment IDs/idempotent ready/failed progress/removal/retry | No conversation attachment/turn mapping/derivative/ref schemas or runtime | NOT DONE |
| MIME/path/decode/pixel/page/request/model limits | Existing file extension/path/size policy implemented, not selected-model part/extraction limits | PARTIAL security primitive, required model limits missing |
| Typed image/file parts to actual selected model | Existing Help/SDK use text strings; no Chat model attachment adapter | NOT DONE; no capability claim from previews |
| Format/extraction coverage/citations/oversized chunked read | Existing file previews/read, no submitted attachment extraction/reviewer map | NOT DONE planned analysis coverage |
| Provider/account scoped refs/expiry/no silent model swap | Credential authority exists; no attachment remote-ref owner | NOT DONE required adapter |
| Add/remove/hash/readiness invalidates same live revision | No live controller or attachment preparation | NOT DONE |
| Final refs/derivative fingerprints/source authority to existing factual review | C03A text-only hash, legacy transcript types; no attachment evidence loader | NOT DONE integration, no new canonical memory store |
| Stage cleanup/expiry/private blob/provider deletion on user erase | Existing file erasure paths, no staged attachment owner | NOT DONE new lifecycle duties; CASCADE alone insufficient |
| General interactive catalog parity/current scope | Actual catalog/authorizer/ToolDefinition fixed audiences exist | DONE baseline; dynamically reuse, not cloned tools |
| Durable conversation/turn/call claims without fake Voice session | prepare_voice_invocation checks current Voice session; no ConversationToolRuntime/context claims | NOT DONE channel adapter; existing algorithm/authority reused |
| Same-call arg conflict/result replay/effect_unknown | Existing Voice claims/results/fail recovery | DONE Voice foundation, NOT text-channel wiring |
| Current confirmation and later final user entry for memory correction/forget | Existing MemoryService.confirm_action/repository pending action refer to Voice session/entry | NOT DONE Chat confirmation adapter; no bypass/direct writes |
| Composed observer preserves Voice plus Chat evidence | Catalog one observer setter exists; no set_invocation_observer in composition | NOT DONE production evidence composition; class existence not mounted proof |
| No Background identity/grant union or tool duplication | Existing fixed-agent audience/grants remain; no new Chat executor | Preserve invariant; new adapter must prove current authorization |
| Real provider attachment and authorized-write/unknown-effect tests | Baseline file/catalog tests, no actual Chat attachment/tool path | NOT DONE end-to-end tests; mock adapter success not endpoint capability |

No new upload/provider call or destructive fixture executed. Existing catalog unit
tests checked with Feature04 focused32-case run; no new attachment/model capability
test exists to run. Required new work is staging/model input and channel-context
adapters, not replacement storage, grant engine or filesystem. Exact model/input
limits and any extra persistence require bounded reviewed contract; plan proposals
are not an applied schema or permission to invent default retention.
