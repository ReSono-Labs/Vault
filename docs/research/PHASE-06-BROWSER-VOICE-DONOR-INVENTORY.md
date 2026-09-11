# Phase 6 Browser Voice Donor Inventory

Date: 2026-08-29  
Status: donor freeze; no visual redesign authority  
Primary donor root:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend`

## Owner visual decision

The standalone Vault web application is Browser Voice visually. Preserve its
current navy shell, logo, type scale, spacing, card geometry, microphone state,
navigation placement, responsive breakpoints, mobile safe areas, overlays and
management-panel visual language. Do not make an approximation or alternate
dashboard.

Functional/cloud subtraction is required even when it changes text or removes
a prohibited destination. Visual fidelity does not authorize cloud auth,
subscriptions, billing, browser-device trust, tunnels, route grants, Agent
Foundry or non-system agents.

## Exact admitted presentation files

| Donor path | SHA-256 | Use |
|---|---|---|
| `browser-voice.html` | `88906d728af483b866a4860c97de4e69a10815a2a9105c523b8d4b6e4c97618f` | Document/PWA entry structure |
| `src/browser-voice/main.tsx` | `65baecc59315d79c57ec3f187609d1be7d9a461a092aa7d286cb5a8d95c342d0` | React entry |
| `src/browser-voice/browser-voice.css` | `d33c0516172c35ee2d230eadf025f60a9cca3542f54bf73a9da5e71aff11fa44` | Exact style import order |
| `src/browser-voice/styles/browser-voice-foundation.css` | `08da4e9ba327f42c3dfb5b4a9939c701e203257b7c54009ddca502466ac2a5ad` | Shell/tokens/core geometry |
| `src/browser-voice/styles/browser-voice-responsive.css` | `d5d637e36ec1cc4abc70c46e2a787d540d116b130937d6d701626b0ee18869c4` | Desktop/mobile behavior |
| `src/browser-voice/styles/browser-voice-landing-retry.css` | `56812d91799950081719dcd3ebcdffa3a3a77c4b905443d1858fe3da134095c1` | Voice landing/state visuals |
| `src/browser-voice/styles/browser-voice-login-overhaul.css` | `b107da8b0f358fe73709cb7b34e0d86d34d99993d5e0784ce4cab6c99909a2e5` | Login/onboarding visual system |
| `src/browser-voice/styles/browser-voice-panels.css` | `1ade2c1243b72ac6c4bf00ebf8759b8c550113de36bc37739db4d9e1422dd4fb` | Shared panel/overlay geometry |
| `src/browser-voice/styles/browser-voice-cards-overhaul.css` | `5f0363b18f4a9130d5968034bd117903997da722ac287fd113cfdf7b28be8012` | Retained local-data cards visuals |
| `src/browser-voice/styles/browser-voice-workspace-overhaul.css` | `2cc27a868ac02eca9ce00c4a5722daf500462e1efbb844efa64209fdd12c7394` | Workspace visual composition |
| `src/browser-voice/styles/browser-voice-files.css` | `8bda34247f851c88dce0264f0c2bb893e81c81171c75e4a6bdb141be342fe30e` | Workspace file rows/previews |
| `src/browser-voice/styles/browser-voice-connections.css` | `03e033254650e1b50b70b033bb423e1728c13abb07acdf4023578b2520193c29` | Capability/provider panel language |
| `src/browser-voice/styles/browser-voice-devices-account.css` | `456058ed1ab94f4a2e429590a0672f14c8a721873ee24e84e41df19b545e3f77` | Local account/settings rows |
| `src/browser-voice/styles/browser-voice-agents.css` | `2b0105cb89e09378eaea8496213cc9e703d111b39403acb15ddd449dee534610` | Visual row language only; no donor agent behaviors/text |
| `src/browser-voice/presentation/BrowserVoiceIcons.tsx` | `ec492fd0c0319ff0ecd3046a221b9bfd66cd598e83cd94b150bef376853748f0` | Exact SVG icon geometry; agent label becomes Capabilities |
| `src/browser-voice/BrowserVoicePanels.tsx` | `621b24557cf462cebefc2f7c1a4fca404d805f57b76ed0c82ef30fe636893672` | Retained transcript/presentation/shared panels only |
| `src/browser-voice/BrowserWorkspaceFileBrowser.tsx` | `f197d624ac0a4a39b3425756f693452818f9afe459b2b7e4985c20a13bb83261` | Workspace file-browser presentation, gated by local API availability |
| `src/browser-voice/browserVoiceTypes.ts` | `4b6aa0e8173f6f5ad0a3a270a5d0db590ab65dd2be163af2a62847c86ce6f381` | Retained presentation/transcript types only |
| `public/resono-logo.svg` | `5fb1d8c00fe3827126a3b6fa321ec212518222cd91217d562c8412c493ef5540` | Exact header mark |
| `public/resono-voice-icon.svg` | `5e89301dc28b9959097fec4b82b8b10bbf28eb95a9e1032755d2f178d2a74eca` | Exact app icon |
| `public/resono-voice-icon-192.png` | `cb299ead221fd4ea40870beee61df4917967322024c3e390ee2eec95779e1dcb` | PWA icon |
| `public/resono-voice-icon-512.png` | `c51949bde4e36c8180fb7898223214b946b95175d1a0804cbbc03c9f63ebf3d8` | PWA icon |
| `public/apple-touch-icon.png` | `9897698568e3e7806a2372e4cd8de8f6573aac0c8bd76454702e1b873edaed33` | Apple touch icon |

`src/browser-voice/styles/browser-voice-handoff.css` is deferred with remote
handoff. It is not needed merely to preserve the core UI.

## Donor files requiring bounded adaptation

| Donor path | Classification | Standalone adaptation |
|---|---|---|
| `BrowserVoiceApp.tsx` (`6f522e...`) | Visual composition authority, cloud-coupled behavior | Preserve DOM/class/state visual composition; replace API/session logic with local identity/Voice APIs |
| `api.ts` (`8b6acc...`) | Cloud/remoting evidence | Do not copy wholesale; create a small local API adapter with same UI-facing concepts only where Phase 1–5 endpoints exist |
| `session.ts` (`e65502...`) | Hosted token/session assumptions | Replace with local opaque-cookie/CSRF session state; never persist bearer credentials in browser storage |
| `useBrowserVoiceSessionLifecycle.ts` (`c3d5f8...`) | Voice WebRTC behavior plus cloud/vault routing | Retain direct provider/WebRTC behavior; remove cloud plane, route grants, opaque relay and tunnel selection |
| `useBrowserVoiceRealtimeEvents.ts` (`b9294b...`) | Realtime presentation behavior | Retain provider event/transcript state; remove platform credit/subscription behavior |
| `useBrowserVoiceToolBridge.ts` (`351f26...`) | Voice tool bridge | Retain only Phase 4 canonical local tool calls |
| `useBrowserVoicePresentation.ts` (`affcca...`) | Presentation overlay | Retain only if supported by existing local tools; otherwise hide, never fake |
| `BrowserVoiceConnectionsPanel.tsx` (`08f674...`) | Visual row/form donor | Adapt to local provider credentials and Phase 5 MCP connections |
| `BrowserVoiceDevicesPanel.tsx` (`a8b5be...`) | Cloud device/trust UI | Exclude from core release; remote device management is deferred |
| `BrowserVoiceAccountPanel.tsx` (`065a48...`) | Account visual donor | Adapt to local `/me`, workspace selection and logout; remove plan/usage/MFA/cloud email claims |
| `BrowserVoiceAgentsPanel.tsx` (`663b4d...`) | Prohibited behavior, reusable row geometry | Do not port component behavior or agent API; use row CSS geometry for a Capabilities panel showing Plugins/Skills/MCP only |

## Explicit removals

- hosted login/MFA/account challenge, access/refresh JWT handling;
- subscription, plan, usage credits and platform exhaustion copy;
- cloud/vault plane switching, tunnel health, route grants and opaque relay;
- browser-device authorization/trust and remote device management;
- Agent catalog, installable agents, Foundry, specialist/package agents and
  Build Agent;
- External AI, social posting, recipes, local events and every other
  unadmitted signal/tool family; Mail, Contacts and Calendar are the only
  owner-admitted built-in personal domains;
- cloud push/autonomy proposal services;
- Gym and other ungrounded domain features;
- Link/A2A/remote handoff in the core build.

Removal is not permission to redesign the remaining screen. Empty or unavailable
features are hidden rather than represented by fake controls.

## Visual reference evidence

The donor contains signed-out desktop/mobile captures at:

`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/phases/2026-08-10_consumer_dashboard_simplicity_overhaul/browser-voice-consolidation-grounding-v2/evidence/screenshots/`

Authenticated reference harness and review evidence are under the same phase
directory. These are visual references only; their mock/cloud data is not donor
authority for standalone behavior.

Required target viewports are 1440×1000 desktop and 390×844 mobile, matching the
donor evidence. Phase 6 must also test keyboard focus, labels, reduced motion,
safe-area behavior and absence of horizontal overflow.
