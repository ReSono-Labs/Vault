# Phase 6B Donor Closure Evidence

Date: 2026-08-29  
Donor: `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace`  
Donor state: read-only inspection; pre-existing owner changes preserved

## Frozen implementation hashes

| Donor relative path | SHA-256 |
|---|---|
| `app/vault_runtime/email_provider.py` | `24b86d4d44355da1ab0adc9dccbffef1e197f40a9ae8d0589060bd69e8ede4ab` |
| `app/vault_runtime/email_service.py` | `285c1bb19089e31133cfd37f54b1a810f073138f5769e5485781407858628d5f` |
| `app/vault_runtime/email_store.py` | `7ff067e98c6efbe1888a68303471c1abb8bd800e288aa057a4d19d0543fecc85` |
| `app/vault_runtime/signals/email/session_tools.py` | `0ffa9574d532a9c06aa2128feb31255e1d6f2d97d9970fddfc038cc108065ae1` |
| `app/vault_runtime/session_tools/brokers/contacts.py` | `527c93b0355a7c3ebcff0dca5fe895a7dcd4e31bd5e087a47ab729f75a241766` |
| `app/vault_runtime/calendar_provider.py` | `0422a1811ebae2ae54b747f01c735c5baaaaffa1725ba304ba3d6a26eb4a7e06` |
| `app/vault_runtime/calendar_sync.py` | `b8a5a7fa27ce3f7b68d3109e82d87288fbbd51120ea98490d489c7fa6859b7a4` |
| `app/modules/integrations/calendar_ics_provider.py` | `1491073a704eca1cd2da8fd41c4e243523eb3d38bd56af7310c771f12037c3e8` |
| `app/modules/integrations/caldav_calendar_provider.py` | `14b129a3738fb3489d6622565f5328aa6ef44da70ffa463f7f14bd4a325acf65` |
| `app/vault_runtime/session_tools/brokers/provider_cache.py` | `2b5610596052cff2e5de8cadca6074f0b476eb23376a9c5991cf163de84bffe5` |
| `app/core/security/outbound.py` | `19c58f20fe1d0e40a1f373a764ba46fd15f762bef1c3df70c21eabdf42e35e34` |

## Frozen behavioral/UI hashes

| Donor relative path | SHA-256 |
|---|---|
| `tests/unit/test_custom_email_provider.py` | `6e6edc83ee1cfb813966f8ab8ca418df5600568df90c160bf828a907447d09da` |
| `tests/unit/test_vault_email_service.py` | `c7c27e245ee9ca2d655cd45d613b6eae12f0dcbd93e8e40ddeafdb21496d21dd` |
| `tests/integration/test_contacts_c3_postgres.py` | `208cab456423c15759097901cdb4500f9cddbd3cceb62f5768bd104aaba132c9` |
| `tests/unit/test_vault_calendar_sync.py` | `a0fe2b1db702709436d04b38a8e031ca35b23e6b2e8c33e63cc76d9a7d05db09` |
| `frontend/src/browser-voice/BrowserVoiceConnectionsPanel.tsx` | `08f6741c964f7bc73daddb4be84ed96baf00192ab073e3b794754430648f0336` |
| `frontend/src/browser-voice/BrowserVoicePanels.tsx` | `621b24557cf462cebefc2f7c1a4fca404d805f57b76ed0c82ef30fe636893672` |

## Integrity baseline

- Voice commit: `0f3b34223f745920e79d1d9db301f3b639d08393`
- Voice tracked diff SHA-256:
  `0d9a4ce77e3707940c4f3becc5ecbfb641eb50f4df975c7e971f52e14e6942da`
- R1 commit: `91d9e70bbe156f03c79399a458416f0bebd20210`
- R1 tracked diff SHA-256:
  `90f9c55912d93683e5e3dea53688b6190c2685c6437259d418520fc6be7551ff`

The donor contains extensive pre-existing owner changes. This evidence records
their state; it does not claim a clean worktree. No command in the closure wrote
to either donor.

## Bounded carry status

- Mail provider/service/store and its signal tools were copied; local changes
  remove Agent Mail and replace cloud scope/credentials with local membership
  checks and AES-GCM protected credentials.
- Contacts broker was copied. Its canonical adapter uses the same broker and
  preserves prepare/confirm semantics; no second Contacts implementation exists.
- Calendar provider, sync, ICS client, CalDAV client and the four donor sync
  tests were copied byte-for-behavior into the target. Only the two Calendar
  datastore constants were recreated locally to avoid importing excluded donor
  domains.
- Local Calendar composition adds only account/workspace authorization,
  AES-GCM credential ownership, API wiring and persistence for the donor's
  pending-confirmation create protocol. The provider side effect cannot run on
  the first tool call and a confirmed action cannot be replayed.
- No External AI, social-post, recipe, local-event, market, weather, news or
  non-system-agent module was admitted by this carry.
