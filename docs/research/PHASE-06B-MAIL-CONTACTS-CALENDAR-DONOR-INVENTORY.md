# Phase 6B Mail, Contacts and Calendar Donor Inventory

Status: donor closure complete; candidate accepted for bounded copy  
Authority: `GROUNDING.md` built-in personal-capability boundary  
Primary donor: ReSono Labs Voice, read-only

## Outcome and boundary

Vault will port exactly three modular built-in personal domains: Mail, Contacts
and Calendar. Mail is the complete local multi-account mail client already in
Voice, not a newly designed send-mail tool. No other Voice signal/tool family
enters this slice. The fixed Voice Agent and Background Agent may consume
authorized tools; these modules do not create agent identities.

## Exact primary donor files

### Mail

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/email_provider.py`
  — bounded IMAP/SMTP connection, folder discovery, paged fetch/search/read,
  attachment handling, send, archive and move behavior.
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/email_service.py`
  — multiple mailbox connect/list/status/sync lifecycle, cached message client,
  confirmation-protected send and local mailbox removal.
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/email_store.py`
  — mailbox/folder/message/send-request/sync-run persistence.
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/signals/email/session_tools.py`
  — identity-neutral Mail tool behavior.
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/session_tools/email_adapters.py`
  — canonical Voice tool adapter geometry. The `agent_mail` dependency is
  excluded because it represents a separate feature surface.

Direct donor dependency candidates requiring bounded extraction are
`app/core/security/outbound.py`, `app/vault_runtime/datastore/scope.py`,
`app/vault_runtime/session_tools/{adapters,errors,primitives,records}.py` and
the relevant schema statements. They are not authorization to copy unrelated
datastore or signal code.

### Contacts

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/session_tools/brokers/contacts.py`
  — contact import/list/search/get/create/update/delete and scoped records.
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/session_tools/contacts_adapters.py`
  — canonical tool adapter.

Only identity-neutral contact behavior is admissible. The similarly named
`agent_packages/brokers/contacts.py` is prohibited package-agent code.

### Calendar

- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/calendar_provider.py`
  — local ICS and CalDAV provider abstraction.
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/calendar_sync.py`
  — scoped credential/event sync behavior.
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/session_tools/calendar_adapters.py`
  — canonical Calendar tool adapter.
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/integrations/calendar_ics_provider.py`
- `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/integrations/caldav_calendar_provider.py`
  — direct provider clients used by the Vault abstraction.

## Required local adaptations

- Replace donor account/workspace identifiers with Phase 2 local principals and
  enforce scope in repositories, not UI filtering.
- Store Mail/Calendar secrets with the established local AES-GCM owner and
  never return stored secrets to Browser Voice.
- Preserve outbound-host validation, TLS verification, timeouts and bounded
  message/attachment/page sizes.
- Preserve Mail confirmation and idempotency boundaries for sends and unsafe
  mutations.
- Project tools only through the canonical Phase 4 catalog and fixed-agent
  audiences.
- Compose management screens only from admitted Browser Voice visual patterns.
- Keep each service importable and testable without importing another signal
  family.

## Automatic rejection cases

- any import from External AI, social posts, recipes, local events, markets,
  workouts, weather, news, Agent Mail or agent packages;
- a single-account shortcut that removes donor mailbox identity/lifecycle;
- plaintext secrets or secrets included in memory/model context;
- a new agent identity, agent registry or package-agent delegation route;
- cloud authentication, ReSono service keys or hosted provider control;
- copying the whole donor datastore/tool registry instead of the required
  dependency slice.

## Closed schema and test evidence

- Mail schema is the bounded statement slice at donor
  `app/vault_runtime/datastore/schema.py:181` through the compatibility columns
  ending near line 368, plus indexes near lines 1811–1842. Port these statements
  to Phase 2 `local_users`/`local_workspaces`; do not copy the full donor schema.
- Contacts and Calendar use the donor private-record contract at
  `app/vault_runtime/datastore/schema.py:160` and identity-neutral record helpers
  in `session_tools/records.py`; Vault will give these domains a smaller scoped
  repository rather than import the donor's full cloud migration datastore.
- Mail behavioral sources are `tests/unit/test_custom_email_provider.py` and
  `tests/unit/test_vault_email_service.py`. The latter's Agent Mail assertions
  are excluded; multi-mailbox, sync/cache, confirmation, mutation and no-delete
  assertions are carried/adapted.
- Contacts isolation/query-before-limit evidence is
  `tests/integration/test_contacts_c3_postgres.py`. Package publication/recovery
  tests are excluded because they prove a prohibited agent package, not Contacts.
- Calendar provider/cache/failure/cadence evidence is
  `tests/unit/test_vault_calendar_sync.py`; cloud-route retirement tests are
  negative evidence only.

## Closed transitive dependency classification

| Dependency | Decision |
|---|---|
| `app/core/security/outbound.py` | Copy bounded public-host/URL/redirect safety; adapt donor HTTP exception to local error |
| `datastore/scope.py` | Do not copy; Phase 2 already owns local user/workspace scope |
| `session_tools/errors.py`, `primitives.py`, `records.py`, `types.py` | Copy only identity-neutral functions/types actually imported by Contacts/Calendar |
| `session_tools/adapters.py`, `tool_registry.py` | Do not copy wholesale; translate admitted tools into Phase 4 `ToolDefinition` |
| `modules/integrations/calendar_ics_provider.py`, `caldav_calendar_provider.py` | Copy bounded provider clients with outbound safety dependency |
| `datastore/domains.py` | Copy only admitted Calendar/provider constants into the local module |
| `agent_mail`, agent-package contacts, external/coordinator routers | Reject |

## Closed Browser Voice surface

The donor `BrowserVoiceConnectionsPanel.tsx` contains the exact ICS, CalDAV and
Mail credential form geometry, but also social/weather/External AI content.
Extract only the three admitted forms into Vault's existing Connections panel.
The donor `BrowserVoicePanels.tsx` contains Contacts and Calendar data-card CRUD
geometry mixed with reminders, notifications and Agent Mail. Extract only the
Contacts/Calendar card/editor patterns; do not copy the component wholesale.
File hashes and test hashes are frozen in
`docs/evidence/PHASE-06B-DONOR-CLOSURE.md`.

License/notice treatment remains the independent public-release blocker. It
does not prevent local bounded extraction but does prevent a public artifact.
