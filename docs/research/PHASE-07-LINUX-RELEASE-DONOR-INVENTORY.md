# Phase 7 Linux Release Donor Inventory

Status: research complete; implementation entry blocked by Phase 6 visual gate and D-07  
Date: 2026-08-29

## Grounding review

Vault requires one simple Linux-first installer for a non-developer. The
portable runtime must not fork product behavior by operating system. Phase 7
may package and operate the existing two-agent local Vault only; it cannot add
remote routing, Link, Tailscale, hosted authentication, another agent, or an
installer agent.

Phase 7 has not entered. `GROUNDING.md`, `INDEX.md`, `SKILLS.md`, the anti-drift
protocol, the Phase 6 contract and D-07 were reread before this inventory.

## R1 donor boundary

R1 contributes installer safety patterns, not its device installer behavior.

| Donor path | SHA-256 | Reusable pattern |
|---|---|---|
| `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/installer/linux-macos/install.sh` | `3078fe5328c3f48c22b083eb8348e06254bad2fc4fb85e2cf7030f8df36d35e0` | Resolve package root, fail closed on missing artifacts, narrow privilege boundary |
| `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/installer/cli/src/release.rs` | `4ac1c4cac2cd0f80186f59fb818f9e0b6822ebf99835f87fe1dee87432e88755` | Closed artifact inventory, size/hash verification before mutation |
| `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/installer/cli/src/command.rs` | `7cd77687b482cdd43f765bb1927391f7dd7aec46a8f8ccd935375999fba7683f` | Closed commands, stable support-safe errors, exact arguments |
| `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/installer/cli/src/main.rs` | `9836808b3e944176a73a3685311e6359d1288afe2cadd8e774fac73178827694` | Small ordinary CLI entrypoint; no agent identity |

## Explicitly prohibited R1 copy

Do not copy fastboot, flashing, Android images, device discovery, USB/udev,
preloader, bootloader unlocking, physical-device prompts or JackRabbit release
identities. Those are R1-device behavior and cannot enter standalone Vault.

## Voice donor boundary

Voice remains the authority for the runtime, database data and Browser Voice
assets being packaged. Hosted backup scripts are deployment-specific and are
not copied wholesale. Phase 7 must back up the standalone data root and local
PostgreSQL database using a newly bounded local operations adapter.

## Required target closure

The eventual package must contain a pinned runtime without a developer
toolchain; production Browser Voice assets; an explicit PostgreSQL/pgvector
strategy; loopback service and launcher; local setup-secret generation;
verified upgrade/rollback; backup/restore; uninstall with data choice; artifact
manifest/checksums/SBOM/signature; and clean-host/offline evidence.

## Entry blockers

- Phase 6 screenshot and element comparison is not proved because this host
  currently exposes no browser-control surface.
- D-07 requires owner/licensor confirmation of the public license and copied
  donor notice treatment before a public artifact can be released.

Research and private packaging tests may continue, but the Phase 7 contract
forbids implementation entry or a public-release claim until those gates pass.
