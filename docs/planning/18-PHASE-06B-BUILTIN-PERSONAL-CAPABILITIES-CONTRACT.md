# Phase 6B Built-in Personal Capabilities Contract

Status: accepted bounded build contract; donor closure complete  
Entry: Phases 1–5 complete, Phase 6 underway, owner admission recorded

## Scenario and owner outcome

Up to four local users manage multiple Mail accounts plus local Contacts and
Calendar through Vault. The two fixed system agents can use only explicitly
authorized domain tools. Vault remains useful without these optional account
connections and has no required ReSono service.

## In scope

- exact Voice multi-account Mail client behavior and persistence;
- Mail folder/message/search/read/sync, attachment, draft/send confirmation,
  archive/move and mailbox lifecycle supported by the admitted donor;
- Contacts import/list/search/get/create/update/delete under local scope;
- ICS/CalDAV Calendar connection, event cache/sync and admitted mutations;
- encrypted local credentials, owner management and revocation;
- modular service/repository/tool boundaries and Browser Voice visual patterns.

## Out of scope

External AI, Agent Mail, social posting, recipes, local events, markets,
workouts, weather, news, documents, package agents, remote routing and every
other donor signal/tool family. A future Plugin possibility is not current
scope.

## Entry gate before implementation

1. `PHASE-06B-MAIL-CONTACTS-CALENDAR-DONOR-INVENTORY.md` closure: complete.
2. Exact schema/test paths and file hashes: complete in donor map/evidence.
3. Before each copy, record the file/hash and minimal adaptation.
4. Re-read Grounding, Index, Skills and anti-drift and verify donors unchanged:
   required at implementation start and exit.

## Acceptance evidence

- two or more Mail accounts coexist, synchronize and remain independently
  addressable;
- send requires the donor confirmation/idempotency boundary;
- Mail/Contact/Calendar data cannot cross user/workspace membership;
- credentials are ciphertext at rest, never echoed and immediately revoked;
- provider/network failures preserve local cache and return support-safe errors;
- only the Voice and Background fixed audiences can receive granted tools;
- negative source/import tests reject every excluded feature family;
- exact Browser Voice visual comparison at desktop/mobile;
- full PostgreSQL/frontend regression suite and donor-integrity proof.

## Stop and rollback

Stop if the dependency closure requires copying a prohibited agent/signal or
cloud authority. Extract the identity-neutral helper only when the donor path
and behavior are proven. Roll back the Phase 6B copy without modifying donors;
do not invent a replacement feature.

## Exit

Mail is demonstrably a multi-account client, Contacts and Calendar meet donor
behavior under local authority, excluded families remain absent, and the
anti-drift exit passes. Phase 7 cannot claim a complete product artifact before
this owner-required built-in slice exits.

## Implementation note

Calendar's local adaptation stores provider secrets as AES-GCM ciphertext and
projects the copied provider/cache behavior into the canonical tool catalog.
The donor `calendar_create` two-call rule is retained: preparation persists a
15-minute pending action without provider work; only a later exact approval
claims it atomically and invokes CalDAV once. This adaptation adds local scope
and persistence only; it does not introduce a new Calendar feature.
