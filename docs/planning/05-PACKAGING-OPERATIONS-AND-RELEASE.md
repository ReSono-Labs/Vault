# Packaging, Operations and Release

Status: conditional candidate v1; desktop/local packaging only

This plan does not deploy Vault to hardware devices. R1 appliance images,
Android/device firmware, flashing, fastboot, USB/udev installation, and
physical-device proof are excluded.

Linux is first. One installer installs an isolated runtime, web assets, local
service, data directories and launcher; opens onboarding; supports upgrade,
backup/restore and clean uninstall. It must not require a developer toolchain.

Runtime code stays portable. Platform launchers own service registration,
secret-store integration, paths and browser opening. Windows and macOS reuse
the same runtime/web artifacts later.

Release evidence: clean-machine install, offline launch, upgrade with data,
failed-upgrade rollback, backup/restore, uninstall data choice, checksum/signing
verification, dependency/SBOM record, and no unexpected outbound traffic.

Public distribution is blocked until ReSono Labs confirms the Vault license and
the compatibility/notice treatment for copied PolyForm Noncommercial donor
code. This does not authorize rewriting donor features.
