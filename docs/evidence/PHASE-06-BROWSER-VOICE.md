# Phase 6 Browser Voice Evidence

Date: 2026-08-29; visual exit accepted 2026-09-02  
Status: COMPLETE — behavior/build evidence green; owner visual QA accepted

## Proved

- Production frontend build from the pinned lockfile succeeds.
- Seven frontend tests prove minimal master onboarding, optional secondary
  accounts with age classification, optional encrypted API-key AI setup, local login shell, retained
  navigation, no Agents/Devices/Foundry destination, same-origin cookie/CSRF
  use, no browser token storage, and the admitted Mail/Calendar connection
  surface without excluded feature labels, plus owner four-user/password management.
- Static files and local API share the loopback server; traversal and security
  header tests pass.
- Runtime/frontend source scans contain no hosted endpoint, cloud authority,
  route grant, Link/Tailscale, prohibited agent implementation, External AI,
  social-post, recipe or local-event runtime surface. Test assertions may name
  excluded terms to prove absence.
- The current complete PostgreSQL-enabled Python suite passes `204 passed`;
  Browser Voice passes `7` tests and its production build passes.

## Visual evidence

Automated 1440×1000 and 390×844 screenshot capture was never available on the
agent host. Owner live visual QA on 2026-09-02 covered every public-facing
page at desktop and phone sizes and accepted the UI.

Two mobile defects were found in that pass and corrected before acceptance:

- Documents Back/Next stay compact on one row (`repeat(2, minmax(0, 1fr))`,
  reduced padding, page titles hidden on narrow widths).
- Vault Help uses a column flex panel with a dedicated `flex: 1 1 auto`
  scroll region; message bubbles are `flex: 0 0 auto` with `height: auto` so
  full text is visible.

The live deployed image was grepped for those CSS rules after rebuild.
Formal screenshot files are not required to keep this gate open; owner
acceptance closes it.

Visible product gaps that are not visual defects: no dedicated Background
Agent submission page, no standalone Contacts page, and no Mail-account
removal control.

## Donor integrity

- Voice commit: `0f3b34223f745920e79d1d9db301f3b639d08393`
- Voice tracked diff SHA-256:
  `0d9a4ce77e3707940c4f3becc5ecbfb641eb50f4df975c7e971f52e14e6942da`
- R1 commit: `91d9e70bbe156f03c79399a458416f0bebd20210`
- R1 tracked diff SHA-256:
  `90f9c55912d93683e5e3dea53688b6190c2685c6437259d418520fc6be7551ff`

These match the frozen pre-copy baselines. Donors remain unchanged.
