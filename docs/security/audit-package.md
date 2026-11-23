# Security audit readiness package

This package prepares an external review of Shade's [merchant](../glossary.md#merchant) payment gateway contracts. It records the code scope, architecture, documented residual risks, and reproducible build and test commands; it is not a security certification or a substitute for checking the source at the audit revision.

## Audit scope

The scope below reflects the tracked Rust source at commit `f80d0e137a5b9efc853f623a058b81d8f1165032` (the source baseline used to prepare this package). Counts are physical lines in tracked `.rs` files, including blank lines, with production and test code separated. This documentation change does not change contract code. Before an audit starts, agree on and record the exact commit being audited; refresh the counts if the source changes.

| Crate | Path | Production Rust lines | Test Rust lines | Total Rust lines |
|---|---|---:|---:|---:|
| `shade` | [`contracts/shade`](../../contracts/shade/) | 5,577 | 13,299 | 18,876 |
| `account` | [`contracts/account`](../../contracts/account/) | 647 | 1,172 | 1,819 |

These are the only members of the root Cargo workspace and the only supported gateway contracts in `contracts/`. The gateway scope and rationale are documented in [ADR 0007](../architecture/decisions/0007-core-gateway-scope.md).

### Out of scope

- The standalone and legacy examples under [`example/`](../../example/), which are excluded from the workspace and CI.
- Soroban SDK/runtime internals, Stellar network consensus, RPC providers, and upstream dependency implementations. Review Shade's interactions with these trust boundaries, but do not treat their implementations as part of this source audit.
- Wallets, merchant backends, indexers, client libraries, and deployment infrastructure not present in the two contract crates.
- Production deployment configuration and operational key custody, except where needed to understand contract trust assumptions and privileged actions.

`SECURITY.md` contains an older contract inventory that lists example contracts under `contracts/`; use the current workspace and ADR 0007 above to determine this audit's code scope.

## Architecture, trust assumptions, and invariants

[`shade`](../../contracts/shade/) is the gateway hub. Its feature components manage merchants, [invoices](../glossary.md#invoice), payment routing, fees, refunds, and administration while sharing the hub's isolated Soroban storage. It calls SEP-41 token contracts, configured price oracles for fiat-priced invoices, and merchant-specific [`account`](../../contracts/account/) vault contracts. The account factory deploys one vault per merchant, separating their balances. See the [architecture overview](../architecture/overview.md), [component pattern](../architecture/component-pattern.md), and [cross-contract call model](../architecture/cross-contract-calls.md).

The principal trust assumptions are:

- The current admin key is controlled by an honest operator. The admin can change protocol configuration, assign roles, pause the hub, set the account WASM hash, and upgrade the hub.
- Configured price oracles return accurate and sufficiently current prices; accepted tokens behave as expected under SEP-41.
- Soroban enforces authorization, storage isolation, and transaction rollback as specified.
- Merchants protect their signing keys and use unique nonces for signed invoices.

The [`threat model`](threat-model.md) lists assets, attacker classes, attack surfaces, and residual risks. The [access-control model](access-control.md) documents the permission matrix: `Admin` has full authority, while `Manager` and `Operator` are currently reserved roles. Merchants authorize merchant-owned operations; [payers](../glossary.md#payer) authorize payments; the proposed new admin must authorize acceptance of an admin transfer. See [admin ownership](admin-and-ownership.md) for the two-step transfer model.

Review at least these documented invariants and their enforcement in the agreed source revision:

- Invoice payment and status transitions preserve the amount due and accepted-token checks; signed-invoice nonces cannot be reused. See [invoice lifecycle](../concepts/invoice-lifecycle.md) and [signature verification](signatures.md).
- Cumulative refunds cannot exceed an invoice's amount. See [refunds and voids](../concepts/refunds-and-voids.md).
- A merchant account isolates that merchant's balances; cross-contract operations and transaction rollback must preserve accounting consistency. See [architecture](../architecture/overview.md) and [storage model](../architecture/storage-model.md).
- Authorization, pause checks, fee calculations, and storage compatibility are security boundaries. See [access control](access-control.md), [pausing](pausable.md), [fees](../concepts/fees.md), and [upgradeability](../architecture/upgradeability.md).

## Known issues and accepted risks

The following are documented design limitations or review questions, not a confirmed vulnerability list. No separate, current findings or formally accepted-risk register was found in the repository at the source baseline. Confirm each item against the audit revision and agree its disposition with the team.

| Area | Documented limitation or risk | Reference |
|---|---|---|
| Admin authority | A compromised admin can change configuration and upgrade the hub. Fee configuration has no on-chain maximum; `set_fee` takes effect immediately even though `propose_fee` offers a time-locked path. | [Threat model](threat-model.md#fee-configuration), [access control](access-control.md), [time-locked fee ADR](../architecture/decisions/0003-time-locked-fee-changes.md) |
| Oracle data | Fiat-priced invoices depend on admin-configured oracle values, and the threat model documents no freshness requirement. | [Threat model](threat-model.md#attack-surfaces), [fiat pricing](../concepts/fiat-pricing-and-oracles.md) |
| Resource limits | Collection getters return unbounded vectors, and large payment batches may exceed Soroban resource limits. | [Threat model](threat-model.md#known-limitations), [storage model](../architecture/storage-model.md) |
| External contracts | Accepted token and oracle behavior is trusted. The `Swap` route validates route data but does not execute a swap in this repository. | [Threat model](threat-model.md#trust-assumptions), [payment routing](../concepts/payment-payloads-and-routing.md) |
| Reentrancy | Guard use is selective, not a blanket wrapper. The architecture overview specifically notes that `pay_invoice` does not call the guard; inspect every token and cross-contract call path rather than assuming all fund-moving paths are guarded. | [Architecture overview](../architecture/overview.md), [reentrancy](reentrancy.md) |
| Documentation consistency | `SECURITY.md` lists example contracts as if they were under `contracts/`, although ADR 0007 moved them to `example/`. The threat model and `SECURITY.md` also list different security email domains; verify the active contact before an audit or disclosure. | [ADR 0007](../architecture/decisions/0007-core-gateway-scope.md), [`SECURITY.md`](../../SECURITY.md) |

These items are starting points for auditor verification, not a claim that the code is safe or that the team has formally accepted every risk.

## Build, tests, and coverage

Use the stable Rust toolchain and the `wasm32v1-none` target. From the repository root, reproduce CI's native test setup and run the complete workspace suite:

```bash
rustup target add wasm32v1-none
make fixtures
cargo test --workspace --all-features
```

`make fixtures` rebuilds the account WASM fixture used by Shade tests. To build deployable contract WASM, run:

```bash
cargo build --workspace --target wasm32v1-none --release
```

CI also runs formatting and lint checks:

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-features -- -D warnings
```

For focused runs, use `cargo test -p shade` or `cargo test -p account`. `make test` runs `cargo test --workspace --all-features`; run `make fixtures` first when you need the same fixture rebuild as CI. See [running tests](../getting-started/running-tests.md) and the [CI workflow](../../.github/workflows/ci.yml).

At the source baseline, the two crates contain **476 unit tests**: 427 in `shade` and 49 in `account`. This is a test count, not a code-coverage percentage. **Coverage is not currently measured or published:** the repository has no checked-in coverage configuration or report, so a coverage percentage is not available. No fuzzing or property-testing harness or configuration was found; there is no project fuzz/property-test command to run.

## Findings tracking template

Record each finding with enough detail to reproduce it, assess impact, and verify remediation. Use the team's private channel for sensitive findings; do not put exploit details in a public issue.

| Field | Details |
|---|---|
| Finding ID / title | |
| Severity and rationale | |
| Affected crate, function, and source revision | |
| Preconditions and attack path | |
| Impact and affected assets | |
| Reproduction steps / proof of concept | |
| Recommended remediation | |
| Team disposition (fix, mitigate, accept, or dispute) and rationale | |
| Owner, status, and target date | |
| Fix commit / regression test / retest result | |
| Disclosure constraints and report reference | |

## Audit report publication

1. Agree with the auditor on the engagement scope, source commit, exclusions, severity definitions, and report format before testing.
2. Triage findings privately with the auditor and team. Track remediation and retesting against the agreed source revision.
3. Coordinate publication timing with the auditor and affected parties. Do not publicly disclose exploitable details before the team has addressed the issue and approved disclosure.
4. Publish or link the final report only after the team and auditor agree it is ready. Record the report URL, publication date, audited commit, scope, exclusions, and remediation status in the audit history below.

For vulnerability reports outside an audit, follow [`SECURITY.md`](../../SECURITY.md): use GitHub's private vulnerability reporting or the security email listed there rather than a public issue. Verify the email address with maintainers before relying on it because the threat-model page currently lists a different domain.

## Past audits

No past audit report or public report link is recorded in this repository at the source baseline. Add each completed engagement here when its report is available.

| Auditor | Date | Audited commit | Scope | Report |
|---|---|---|---|---|
| None recorded | — | — | — | — |
