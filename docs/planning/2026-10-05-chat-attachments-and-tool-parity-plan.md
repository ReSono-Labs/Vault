# Chat attachments, capture and existing tool parity

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

Revision LMD-CHAT-INPUTS-r2. Phase01 candidate; grounding r11 R36/R37.
Research: [current overlap and primary sources](../research/2026-10-05-chat-history-attachments-and-tools-research.md).
New `conversation_attachments/` owns staged inputs/extraction/model conversion;
new `conversation_tools/` owns final-turn invocation/correlation/idempotency adapter.
Neither owns a new agent, grant store or filesystem implementation.

## Capture/import and storage

Provide attach menu/file picker, paste image, drag/drop and one-shot capture with
preview/removal before Send. Capture port supports browser screen/window snapshot
and camera where available; user starts explicit permission flow, reviews result,
tracks stop after snapshot/cancel. Unsupported/denied capture leaves file import
available. User intent didn't pick a single capture kind: screen/camera are
candidate mechanisms to validate, not silent continuous surveillance. Import supports
images and documents via format allowlist/capability matrix. Reuse file service
through opaque attachment storage port, not filename-keyed workspace upload.

Staged attachment is scope-owned, not published memory or automatic workspace
file. Store in private namespace under existing managed storage; access checks
apply to upload/preview/download/extraction/provider submission. Explicit Save to
Workspace uses current authorized file tool rather than silently uploading into
shared workspace. Existing storage128MB limit is NOT model limit. Pin per-file,
request/count/pixel/page/extraction CPU/time/token limits to selected provider and
storage constraints; reject before Send with exact actionable message. Formats
include supported images, PDF, text/Markdown and DOCX; spreadsheets/presentations
require actual extraction capability and truthful coverage (not assume all formats).

Proposed tables under vault_private:
- `vault_conversation_attachments`: attachment_id PK, user/workspace FKs, optional
  conversation/draft association, storage object key, original display filename,
  detected MIME, byte size/hash, width/height/page count optional, state staged/
  processing/ready/failed/deleted, created/expires_at, error_code. Unique scope/
  upload-idempotency; never global hash exposes another user's possession.
- `vault_turn_attachments`: turn_id FK, attachment_id FK, ordinal, frozen content
  fingerprint, input purpose; unique(turn,attachment). Submitted mapping immutable.
- `vault_attachment_derivatives`: derivative_id PK, attachment FK, extractor/version,
  source hash, pages/spans, coverage complete/partial/failed, bounded content/blob
  reference, fingerprint/status/error. Unique attachment/source/contract.
- `vault_attachment_provider_refs`: scope, attachment/source hash, provider/account
  identity, remote file ID, expiry/state; separate credential store owns auth.

Detect actual MIME/format, validate filename/path boundaries and decode image
size safely; no arbitrary archive extraction or unsafe document macros/scripts.
Preview user content safely, revoke blob URLs on teardown. Local/provider staged
cleanup on remove/expiry; submitted references retain according to same history
retention/deletion policy. Session list omits private previews until authorized.
Large asynchronous upload status survives retry; stable attachment ID/hash avoids
reupload duplicates. Hash identifies bytes, not permission or memory ingestion.

## Model processing and shared live search

Server builds typed input parts from submitted scoped attachment IDs only; no
client arbitrary file path/provider ID authority. Supported image → actual image
part; supported document → actual file part or bounded extraction preserving page/
section citations. Selected provider/model/SDK/OAuth capability matrix determines
path. Missing capability shows explicit status or owner-selectable supported model;
no silent model/provider switch, ignored files or thumbnail-only fake support.
PDF page vision, DOCX embedded charts and spreadsheet row coverage differ by
endpoint; track exact extraction/source coverage. Unsupported/partial inputs do
not yield claims of complete document analysis. Files larger than direct model
budget require chunked document read/retrieval port; don't index raw attachments
as canonical memories or replace the memory store with hosted File Search.

While drafting, shared live-memory pipeline can use text and READY extracted
hints under same revision contract; no expensive provider image analysis triggered
for every keystroke. Attachment add/remove/hash/readiness change increments context
revision and invalidates preparation. Full required attachment interpretation
happens on submitted final turn unless separately scoped experiment allows earlier.
Provider draft permission from grounding covered text experiments, not an assumed
policy to upload every removed file to cloud before Send.

Model-derived observations preserve image/document source authority and citations;
attachment contents are untrusted data, not instructions/permission. Record final
attachment refs, analysis/extraction coverage, actual response/tool outcomes in
session evidence. Memory agent receives relevant retained evidence through bounded
windows, references original content, and distinguishes user assertion from file/
model inference. Store accepted durable candidates through existing reconciliation,
not blanket auto-memory ingest of all file text. History fingerprints include
submitted attachment/derivative identities; old text-only fingerprint insufficient.

## Full existing tool functionality without new identity

Inventory existing catalog dynamically for current interactive fixed identity:
read/search/list/write/save/edit/move/delete/upload files; memory lookup/explain/
remember/confirmed correct/forget; contacts/personal data; web/tools; installed
plugin/MCP capabilities. The exact available set is current catalog+scope+grants,
not hardcoded cloned functions. Chat should use all generally applicable tools,
including writes; transport-only Voice start/mode/audio controls retain their
owner and explicit UI routing, not blindly executed by model Chat calls.

Existing VoiceToolRuntime requires open Voice session, so do NOT call it with a
fake transport or call ToolCatalog directly bypassing durable claims. New
ConversationToolRuntime accepts conversation/turn/call ID, current LocalPrincipal,
arguments hash and fixed interactive audience. Reuse shared authorizer/catalog
and add conversation-scoped durable invocation claims: unique(scope,turn,call),
argument fingerprint, definition/tool/version/effect, state running/succeeded/
failed/effect_unknown, result reference, timestamps. Publication/evidence attached
to Chat turn, not currently open Voice session. Same call changed arguments rejects.
No retry of unknown write/delete effects. Current scope/availability/confirmation
rechecked immediately before effect, despite prior prepared context.

Initial identity proposal: interactive Chat is another channel of existing Voice
agent identity, not third Chat agent. Current grants separate Voice/Background;
never union them or execute under Background just to gain a tool. Inventory tools
only available to Background and distinguish execution-lifecycle-specific tools
from generally usable capabilities. True missing common capability gets explicit
audience projection reviewed under owner parity request; grants still explicit.
Background goal orchestration remains unchanged/outside feature. UI tells user
unavailable/ungranted and uses existing enable/confirmation flow; no automatic grant.

Memory pending-action contract currently requires Voice session/later user entry.
Add channel-neutral conversation-confirmation adapter with exact action ID/target/
proposed change, subsequent final user entry, current scope and atomic consume+
apply; don't send Chat memory edit to fake Voice transcript. Other tool-specific
confirmation policies remain current authority. Catalog single observer must
compose evidence routing by invocation context, preserving existing Voice observer;
new observer cannot overwrite existing session learning.

## Replaceable filesystem boundary and tests

Expose current handlers through same stable semantic capability IDs/catalog
source. Future reputable filesystem donor can replace handler implementation via
existing replace_capability_source mechanism after its own research/contract;
Chat/history/attachments must depend on port, not donor. Read and write path/
workspace/share permissions remain authoritative. Don't delay working Chat writes
until future donor, or put new filesystem engine in Chat UI/backend.

Positive tests: image/file reaches actual selected model; paste/capture/remove,
PDF citations, upload retry/resume by reference; authorized write/edit returns
scoped downloadable result; history continuation does not replay tools. Negative:
unsupported model/MIME, wrong scoped attachment, huge image/corrupt document,
provider file expired, removed attachment late extraction, capture denied, stale
hash, tool revocation, duplicate call/different args, unknown write effect, missing
confirmation, observer misrouting. Real provider capability test required before
claiming actual multimodal/OAuth support; mocks prove only adapter behavior.

Delivery O4-A after shared final turn/evidence/storage ports; tool parity adapter
is O4 core prerequisite. Rollback unmounts attachment capture and new tool runtime,
retains submitted references/accepted memory, leaves existing Voice/Background
execution and filesystem unchanged. New attachment expiry/retention/limits are
conditional until contracted; no paid upload or implementation performed now.

## Phase02 verified integration prerequisites

Existing static server Permissions-Policy disables camera; camera capture is
conditional on explicit reviewed self-only header/browser capability adapter.
File/paste/screen input support is independent. Existing API buffers complete
responses; new stream emission/cancel/replay is not available until owned adapter
contract. Attachment/evidence metadata isn't projected by legacy TranscriptEntry;
explicit authorized metadata loader/type adapter is mandatory. User erasure must
remove all new rows/private blobs/provider references/checkpoints/cache under each
owner, with failure retry; cascade alone isn't complete cleanup. None of these
changes is authorized inline in Chat or as global server-policy weakening.
