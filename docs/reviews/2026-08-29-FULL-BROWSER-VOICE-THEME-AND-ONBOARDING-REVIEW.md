# Full Browser Voice Theme and Onboarding Review

Date: 2026-08-29  
Status: correction in progress; owner screenshot rejected the first rendered pass

## Controlling decision

Vault has no independent visual design. Voice Home retains Browser Voice. The
management surfaces—onboarding, login, Library, Connections and Accounts—use
the current R1 management-console structure, spacing, typography, dividers,
forms, lists, modal geometry and responsive behavior. Vault semantics may
replace device/cloud wording but do not authorize an invented visual system.

This review adds no feature. It restates and audits the existing Phase 6
contract against the current code and primary Voice donor.

## Primary donor

`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend/src/browser-voice/`

Vault comparison root:

`/home/christian/Documents/Projects/ReSono-Labs-Vault/frontend/src/browser-voice/`

## Theme findings

The original source-parity findings below record the starting point. Owner
review found that parity insufficient for management UX. The corrective layer
is now `styles/browser-voice-r1-console.css`, sourced from the current R1
management tokens and CSS. It constrains content/forms, removes the stretched
connection form, gives Library and Accounts explicit management structure,
keeps onboarding/password panels within the viewport, and changes the mobile
shell to a four-item non-overflowing navigation grid.

- `browser-voice.css` is byte-identical to the donor import graph.
- Eleven of the twelve imported `styles/browser-voice-*.css` modules are
  byte-identical to Voice.
- `browser-voice-connections.css` differs only by deleting four selectors for
  excluded `external_ai`, `news`, `social` and `weather` categories. No retained
  visual value changed.
- The Browser Voice icon source differs only where excluded category icons and
  prohibited Agents/Devices navigation were removed, and where the donor
  Agents position was relabeled Capabilities/Tools. Retained artwork is donor
  code.
- The current application is a bounded local-semantic composition, not a
  byte-for-byte copy of the cloud-coupled 1,968-line donor application. The
  Phase 6 visual lock therefore depends on preserved donor DOM classes and
  rendered comparison, not application-file equality.

## Onboarding finding

First-run onboarding is part of the Browser Voice visual lock. The current
local onboarding surface correctly reuses these donor classes and assets:

- `browser-voice-shell`;
- `browser-voice-card is-login-page`;
- `browser-voice-header` and `browser-voice-login-brand`;
- `browser-voice-login-panel`;
- `browser-voice-form`;
- `browser-voice-submit`; and
- the donor ReSono logo and byte-identical login/foundation/responsive CSS.

The fields are grounded local substitutions: master name/style, optional local
users with age classification and setup/temporary/managed access, and optional
shared provider configuration. Cloud email, MFA, subscription, device-intent
and hosted onboarding questions must not return. Temporary-password users are
forced to replace that password on first login.

The one-time setup credential is intentionally not another visible product
question. It must arrive in the installer/test setup URL as `#setup=...`.
Opening the bare URL and attempting onboarding cannot succeed; documentation
must provide the prepared setup link rather than instructing the user to type
the credential into a field that does not exist.

## Surface-by-surface visual authority

| Vault surface | Browser Voice authority | Permitted semantic substitution |
|---|---|---|
| First-run onboarding | Signed-out card, brand, login panel/form and responsive CSS | Name and experience fields; one-time local recovery result |
| Login | Donor login geometry and controls | Local username replaces cloud email; MFA removed |
| Home | Donor landing, microphone, status, transcript and responsive composition | Truthful local runtime/privacy labels |
| Library | R1 management tabs, configured-item rows and restrained actions | Plugins, Skills, MCP and tools only; no additional agent |
| Connections | R1 management sections, bounded fields and add-account dialogs/forms | Shared Voice provider, Mail, Calendar and MCP only |
| Accounts | R1 management headings, lists and restrained actions | Master profile, password, private workspace and at-most-four concurrent users |

## Acceptance still required

Owner review of the first running correction found the Accounts page opening at
a retained scroll offset, clipping its heading, and exposed unstructured profile,
workspace, password and sign-out geometry. That pass is rejected and may not be
used as Phase 6 evidence. Navigation now resets document scroll, and Accounts
has explicit R1-style section geometry, three-column desktop facts, bounded
workspace/password controls and a restrained sign-out action. Fresh owner
desktop/mobile review is still required.

Mail and Calendar addition forms now follow the R1 management `dialog.modal`
pattern rather than expanding inline. The donor geometry, backdrop, header,
actions, responsive field stacking and viewport-bounded scrolling are retained;
Vault field names and local encrypted-storage semantics replace R1 wording.

Source and automated DOM/build proof are not rendered proof. The browser-control
runtime was unavailable during this review. Phase 6 therefore remains open until screenshots at
1440×1000 and 390×844 cover onboarding, login, Home states, Capabilities,
Connections and Account, followed by element-by-element donor comparison,
overflow, focus, keyboard and responsive checks.

No packaging phase may claim the visual gate passed from this review alone.
