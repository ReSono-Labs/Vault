# Separate Chat: current overlap and implementation research

Revision LMD-CHAT-RESEARCH-r1,2026-10-05. Grounding r9. Read-only inspection;
no dependencies installed, provider calls, implementation or database mutation.
This record owns current overlap and source findings for this extension.

## Current code facts

`frontend/package.json`: React18/Vite/TypeScript; no chat UI/runtime library.
`BrowserVoiceApp.tsx`: voice refs/provider channels/audio and session live at host
level; destination changes reset document scroll but aren't a new Voice session.
`presentation/BrowserVoiceIcons.tsx`: desktop/mobile destination list has no Chat.
Screenshot shows persistent left navigation with Overview selected and Voice hero;
add navigation destination only, preserve hero/controller. Chat gets a bounded
inner scroll container so existing document scroll reset doesn't destroy reading.

`voice/repository.py`: sessions/events stored with user/workspace AND originating
local_session_id, transport/provider state; session read checks same login and
membership. There is no inspected general prior-conversation list/resume adapter.
Reopening an old provider connection is not continuing stored conversation history.
New history access must authenticate current login and authorize stable owner/
workspace; don't loosen old Voice session auth globally.

`memory/repository.py`: persisted transcript entries and session summaries;
completed ingestions keyed by scope/session/reviewer contract/full transcript
fingerprint. Fingerprint hashes index/role/event/text, not attachment content or
reasoning metadata. Summary+completed status can avoid identical-snapshot review.
A newly appended turn changes full fingerprint; current dedupe doesn't establish
incremental history coverage. Append conflict by entry_index returns original row
without verifying changed payload; new ingestion must reject same-id/different-data.
A single ingested boolean is insufficient for continuation and late corrections.

`tools/catalog.py` and `tools/definitions.py`: one catalog validates arguments,
fixed audience, scope and authorizer before dispatch. InvocationContext has local
session plus optional voice_session_id/execution_id, no generic conversation ID.
`voice/tools.py`: grants separate voice_enabled/background_enabled; durable Voice
invocation claim REQUIRES fixed Voice identity AND live Voice session. Directly
calling catalog from Chat skips durable claim/recovery. Need independent Chat
invocation adapter referencing conversation/turn, reusing grant/catalog policy,
with no microphone session fabricated. Single observer slot also needs safe
composition for Chat evidence without replacing existing Voice evidence observer.

`workspace_files/tools.py`: read/list/search/new-write/save/edit/move/delete/upload
etc. project to Voice and Background; writes already exist, not a future donor
prerequisite. `workspace_files/manager.py` upload128MB per request; text content
bound32MB. Those storage limits do not establish model ingestion limits. Existing
upload writes workspace paths; it is not a private temporary Chat attachment
service, can overwrite filenames, and doesn't prove image/PDF/DOCX model support.
Workspace browser image/PDF preview is display only. Keep attachment storage scoped
with opaque object IDs; do not duplicate Files service or use filename as key.

## Primary-source research and recommendation

[assistant-ui Thread](https://www.assistant-ui.com/docs/primitives/thread) offers
viewport/composer primitives with follow-output that yields to manual reading.
[Thread runtimes](https://www.assistant-ui.com/docs/runtimes/concepts/threads)
allow own-backend adapters and paginated history.
[Attachments](https://www.assistant-ui.com/docs/guides/attachments) provides an
adapter boundary; application still owns upload/model processing. These sources
prove suitable reusable UI mechanisms, not Vault authorization/persistence or
automatic polished layout. Recommend evaluating assistant-ui headless primitives
behind Vault-owned adapter/style modules instead of rushing custom chat mechanics.
No assistant-cloud or new Node inference backend. React18/version/peer dependency/
license/stream adapter compatibility must be pinned in an isolated contract before
adoption. If incompatible, implement the same explicit UX contract with existing
React, not silently replace the application framework.

[Vercel persistence](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-message-persistence)
describes stable message identity and loading server history while sending only
new input. Its file/Node example is a pattern, not Vault's store to import.
[Stream resumption](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams)
distinguishes client disconnect from actual generation cancellation. Reopening
conversation and reconnecting active stream are separate operations. Don't add
Redis/Node runtime merely to copy its example; Python server owns turn state and
bounded event replay/cancel ports. UI-library resume does not dedupe tool effects.

Official [OpenAI images](https://developers.openai.com/api/docs/guides/images-vision)
support model input image content, not just text descriptions. Official
[file inputs](https://developers.openai.com/api/docs/guides/file-inputs) distinguish
PDF text/page images, non-PDF text extraction and bounded spreadsheet processing.
These prove API formats, not support through Vault's selected SDK/OAuth/provider
path. Add provider capability/input conversion port and verify actual selected
transport before claiming attachment support. Missing diagrams/rows must be explicit.
[MDN screen capture](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia)
requires user-triggered browser permission and support detection. Use optional
one-shot capture, stop tracks after snapshot; camera, screen and paste/import
are distinct capture mechanisms. No silent ongoing screen capture.

No runtime/paid/provider/visual operating validation performed. Existing baseline
checks predate this new feature and do not prove it. UI screenshot is source
reference, not a Chat acceptance render. Filesystem donor research remains later,
with stable tool ports prepared now and no invented donor repository selection.

## License verification and selection update

2026-10-05: repository [LICENSE](https://github.com/assistant-ui/assistant-ui/blob/main/LICENSE)
verified MIT; copyright/permission notice must accompany distributed substantial
portions. Owner conditional approval is now satisfied (grounding r10 D23).
Select open-source primitives; retain pinned-package/React18/stream adapter
compatibility checks and existing Vault storage/backend. No install performed.
