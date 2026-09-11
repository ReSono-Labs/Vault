# Donor Code Porting Rule

Status: controlling owner decision  
Authority: owner direction dated 2026-08-28

## Decision

Vault uses the working donor code already written in other projects on this
computer. It does not recreate donor features from planning documents, observed
behavior, screenshots, summaries, or developer preference.

Donor projects are immutable inputs to Vault work. Do not modify them. Copy
only what an accepted phase needs, and make adaptations exclusively in the
Vault copy.

For each feature, the build record must contain:

1. exact absolute donor file paths;
2. the donor commit or content hashes when available;
3. code and tests copied;
4. behavior intentionally preserved;
5. each grounded adaptation and why it is necessary;
6. private endpoints, secrets, branding, or cloud coupling removed;
7. licensing and required notices; and
8. evidence that the resulting behavior still matches the donor contract.

The port record must also show that the donor path was unchanged by the work,
using Git status/diff evidence where available. Existing donor changes belong
to their owner and must not be reset, overwritten, or included in Vault.

## Allowed adaptation classes

- local-only replacement for a ReSono-operated cloud dependency;
- user/workspace/integration authorization required by Vault grounding;
- OS-neutral boundary needed for Linux, Windows, and macOS;
- API wiring needed by the exact Browser Voice front end;
- packaging and filesystem-path adaptation; or
- a demonstrated security defect with a regression test.

## Prohibited substitutions

- rewriting because another language, framework, or pattern is preferred;
- modifying, formatting, upgrading, deleting, or generating files inside a
  donor repository;
- copying entire donor trees when the phase needs only a bounded subset;
- replacing code with an approximation derived from documentation;
- redesigning UI or interaction behavior;
- adding features because they are common in similar products;
- hiding an unresolved donor or license gap behind newly written code; or
- claiming parity without carrying over or replacing donor tests with equivalent
  acceptance evidence.

## Exception gate

A rewrite exception is `BLOCKED` until the record identifies the exact donor,
why extraction cannot meet a grounded requirement, the smallest replacement,
affected behavior, migration/reversal path, and owner authority. A developer or
AI cannot approve its own exception merely to continue.
