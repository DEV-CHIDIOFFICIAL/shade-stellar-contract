# 0008. Storage TTL Strategy

- **Status:** Accepted
- **Date:** 2026-11-24

## Context

Under Soroban's state archival and rent model, both contract instance storage and persistent storage entries have a finite Time-To-Live (TTL) measured in ledgers. If an entry's TTL expires without being renewed, validators archive the entry into cold storage. Once archived, the entry cannot be read or modified by smart contracts until an explicit restoration footprint and transaction fee are submitted to restore it.

Prior to Issue 348, as documented in [Storage model](../storage-model.md), no contract in the Shade workspace (`contracts/shade` or `contracts/account`) invoked `extend_ttl` or related host functions. All core state—including contract instance configuration (`Admin`, `Paused`, `AcceptedTokens`), merchant metadata (`Merchant`, `MerchantId`, `MerchantAccount`), and invoices (`Invoice`)—relied exclusively on the initial write-time TTL allocated by the network.

This created an operational and availability hazard:
- If the `shade` or `account` contract instances archive due to inactivity, all invoice creation, settlement, and administrative calls fail immediately.
- If persistent entries for an active merchant or pending invoice archive, customer payments and merchant sweeps revert with entry-not-found errors.
- On Stellar Soroban networks, ledgers close approximately every 5 seconds (~17,280 ledgers per day), and the network enforces maximum TTL boundaries (typically 518,400 ledgers, or ~30 days, up to network limits).

A storage TTL strategy is required to balance guaranteed availability for active contracts and payment flows, predictable caller fees, zero-cost read operations, and state sustainability without unbounded rent costs.

## Decision

We adopt an automated, in-contract TTL extension strategy with the following constants, rules, and operational boundaries:

### 1. TTL Constants

We define standard TTL extension parameters based on a 5-second ledger close rate:
- **`TTL_THRESHOLD` = `276,480` ledgers (~16 days):** The remaining lifetime watermark below which an entry's TTL is extended.
- **`TTL_EXTEND_TO` = `518,400` ledgers (~30 days):** The target lifetime to which the entry is extended upon crossing the threshold.

**Rationale:**
- Stellar caps the maximum entry TTL (e.g. `max_entry_ttl` of 518,400 ledgers). Setting `TTL_EXTEND_TO` to 518,400 ledgers maximizes the validity window while staying safely within network protocol limits.
- The threshold of 276,480 ledgers ensures that an entry is only renewed when less than ~16 days remain. Because Soroban's `extend_ttl` is idempotent and only acts when current TTL is below the threshold, high-frequency transactions during the first 14 days do not repeatedly bump the entry or incur redundant rent write charges. Active entries are guaranteed to always maintain between 16 and 30 days of lifetime.

### 2. Contract Instance TTL Extension

Both `shade` and per-merchant `account` contracts automatically extend their instance storage TTL (`env.storage().instance().extend_ttl(TTL_THRESHOLD, TTL_EXTEND_TO)`) on every state-changing call:
- Handled through a shared helper in `core` triggered on mutating entry points (e.g. invoice creation, payments, admin configuration, sweeps, and withdrawals).
- Ensures that contract code instances, manager references, pause states, and global administration keys stay live as long as the protocol experiences regular usage.

### 3. Persistent Entry Extension on Hot Paths

Persistent storage entries accessed along active execution paths are renewed during read or write operations on hot paths:
- **Merchant records:** `DataKey::Merchant(id)`, `DataKey::MerchantId(address)`, and `DataKey::MerchantAccount(id)` extended during registration, status updates, fee configuration, and payment routing.
- **Invoices:** `DataKey::Invoice(id)` extended upon creation, settlement (`pay_invoice`, batch payments), cancellation, voiding, and refunding.
- **Fee and token configurations:** `DataKey::TokenFee(token)`, `DataKey::MerchantPlatformFee(id, token)`, and `DataKey::MerchantTokens(address)` extended during fee evaluation and payment routing.

### 4. Read Paths Do Not Extend TTLs

Read-only entry points (such as `get_invoice`, `get_merchant`, `get_fee`, `get_merchants`, `get_invoices`, and paginated list queries) **must not invoke `extend_ttl`**:
- Invoking `extend_ttl` alters transaction semantics from a pure view query to a state-modifying transaction that requires transaction signatures and incurs base network fees.
- Keeping read paths non-mutating preserves zero-fee, read-only Stellar RPC simulations (`simulateTransaction`) used by frontends, explorers, and indexers.

## Consequences

### Positive Consequences
- **Automated Availability:** Active merchants, open invoices, and the contract instances stay live automatically without requiring constant manual intervention or reliance on centralized off-chain keepers.
- **Zero Read-Only Overhead:** Integrators and dashboards can query contract state via standard RPC calls without signing transactions or paying gas.
- **Efficient Rent Consumption:** The ~16-day threshold avoids redundant TTL extensions on consecutive transactions, minimizing rent fees.

### Negative Consequences and Trade-offs
- **Extra Fee Per Write Call:** Mutating calls that trigger an extension incur a small, bounded additional rent fee assessed by Soroban to pay for ledger lifetime extension. When the remaining TTL is already above `276,480` ledgers, `extend_ttl` is a no-op that consumes negligible CPU instructions and zero additional rent.
- **Natural Archival of Inactive Historical Records:** Completed, voided, or refunded invoices that are never touched again, as well as abandoned merchant accounts, will eventually exhaust their TTL and be archived by validators.
- **Operator Remaining Responsibilities:**
  - Operators must run monitoring scripts to detect if the contract instances approach expiration during prolonged platform-wide inactivity (>16 days without any transactions) and submit maintenance bump calls if necessary.
  - Operators must maintain a runbook and funded utility accounts to execute Soroban `restore` footprint transactions if historical, archived invoices need to be recovered for off-chain auditing or dispute resolution.

## Alternatives considered

- **Operator-only extension:**
  - *Why rejected:* Relying entirely on external operator keeper bots to bump instance and entry TTLs introduces a single point of failure. If the keeper bot crashes, runs out of funds, or experiences network downtime, the payment gateway contract instance or active merchant records could be archived, causing user checkout transactions to fail catastrophically.
- **Extending on every access (including read-only queries):**
  - *Why rejected:* Calling `extend_ttl` inside read functions converts read-only queries into state-modifying transactions. Callers, indexers, and wallets would need to sign every query with an account private key and pay transaction fees just to inspect an invoice or check merchant verification status, breaking standard Web3 client integration patterns.
- **Leaving archived invoices to be restored on demand:**
  - *Why rejected:* Allowing pending or actively transacting invoices to expire without in-contract extension shifts the burden of archival restoration onto payers. Customers attempting to pay an expired invoice would encounter failed transactions with cryptic Soroban host errors, requiring complex, multi-transaction restoration pre-flights before checkout could succeed.
