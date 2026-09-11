# Phase 6 Exact Browser Voice Contract

Status: accepted build contract  
Entry: Phase 5 anti-drift exit complete  
Authority: owner exact-visual decision and Phase 6 donor inventory

## Outcome

Vault serves a loopback web application visually identical to the admitted
Browser Voice donor surfaces at desktop and mobile sizes. It uses local
authentication, workspaces, Voice sessions and extension APIs only. It never
contacts or requires ReSono Labs.

## Retained destinations

1. **Home** — exact Voice landing/microphone/status/transcript composition.
2. **Capabilities** — occupies the donor Agents navigation position and exact
   row/panel visual language, but contains only Plugins, Skills and MCP tools.
3. **Connections** — existing visual language for local Voice provider keys and
   Phase 5 MCP connections.
4. **Account** — local profile, workspace selector and logout in the donor
   account visual language.

The donor Devices destination is hidden in Phase 6 because remote devices are
deferred. The navigation spacing may not be filled with an invented feature.
The donor External AI connection is not a Vault feature. The owner-entered
Realtime credential configures infrastructure for the one fixed Voice Agent
only and must not expose External AI tools or destinations.

## Onboarding and authentication

- Uninitialized Vault shows the same Browser Voice signed-out shell and asks
  only for name and experience style. Installer/bootstrap supplies the one-time
  setup proof without another product question. Vault derives local login
  identity and generates recovery authentication material; the owner can manage
  it later from Account. Local credentials are security machinery, not an
  onboarding questionnaire or cloud authentication.
- Initialized Vault shows local username/password login in the exact donor form
  geometry.
- Session auth uses secure HttpOnly cookies and CSRF from Phase 2. No bearer or
  refresh token is stored in `localStorage`/`sessionStorage`.
- At most four users are supported; only the device owner can create another.

## Voice behavior

- Microphone permission is requested only after a user gesture.
- Start calls the local Voice endpoint, then completes the donor direct WebRTC
  offer/answer flow with the returned ephemeral provider credential.
- Stop closes media/data-channel/peer connection and local Voice session.
- Provider events/transcript/tool calls use existing Phase 4 endpoints only.
- Provider API keys are owner-entered local secrets and never returned to the
  browser after storage; session client secrets are ephemeral.
- No cloud plane, route grant, tunnel or opaque relay fallback exists.

## Visual lock

Copy admitted CSS, icons and assets without aesthetic edits. Preserve class
names and DOM hierarchy where functionality remains. Allowed visual changes are
only those forced by grounded local semantics:

- `Agents` label/content becomes `Capabilities`;
- cloud status becomes truthful `Local Vault` status;
- cloud account/plan/usage/MFA content is removed;
- Devices and other deferred/unavailable destinations are hidden;
- local onboarding and workspace fields replace hosted login challenges.

Do not change colors, gradients, shadows, radii, type sizes, spacing,
microphone artwork, logo sizing, breakpoints or responsive stacking to express
personal preference.

## Security and CSP

- Static files and API share the loopback origin in release.
- CSP defaults to self, permits only required provider WebRTC/media behavior,
  forbids framing and object embedding, and avoids inline script.
- No third-party analytics, fonts, CDN assets, telemetry or service worker
  network caching outside the local origin.
- HTML/API responses use no-store for authenticated/private data.
- All mutations use strict JSON and CSRF. UI output is React-escaped; uploaded
  names/descriptions are never injected as HTML.

## Required tests

1. Carried/adapted donor component and state tests.
2. Onboarding, login/logout, workspace switch and four-user limit UI flows.
3. Start/stop/error/retry Voice state transitions with mocked media/WebRTC and
   real local HTTP contract tests.
4. Capabilities shows no Agents/Foundry/Build Agent/package-agent controls and
   cannot create another agent identity.
5. No source/runtime request references ReSono endpoints, hosted auth, cloud
   plane, billing, subscription, route grants, Link or Tailscale.
6. No browser storage contains credentials or session tokens.
7. Production build succeeds from the lockfile with no required network at
   runtime.
8. Automated accessibility checks for names, focus, keyboard activation and
   reduced motion.
9. Screenshots at 1440×1000 and 390×844 for onboarding/login, idle Home,
   active/error Home, Capabilities, Connections and Account.
10. Element-by-element comparison against donor reference; differences outside
    the explicit semantic substitutions are blockers.
11. Horizontal overflow and mobile safe-area checks.
12. Full Python/PostgreSQL suite remains green.
13. Excluded External AI, social-post, recipe and local-event modules and UI
    destinations remain absent.

## Exit

Phase 6 exits only after behavior/build/accessibility tests, desktop/mobile
screenshots, visual comparison, cloud/agent negative scans, donor integrity and
the anti-drift review pass. Phase 7 packaging cannot begin earlier.
