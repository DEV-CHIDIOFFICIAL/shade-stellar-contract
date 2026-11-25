# How to Read Contract State Directly via Stellar RPC

Read current Shade contract storage from Stellar RPC with `getLedgerEntries`, construct keys from the contract's `DataKey` types, and decode the returned XDR.

> **Warning — storage layout is an internal, version-dependent detail.** These keys and value shapes are not part of Shade's stable public interface and may change in a contract upgrade. Pin your reader to the deployed WASM hash, verify the live version before relying on a key, and update your decoder after upgrades. See [Upgradeability: storage compatibility and versioning](../architecture/upgradeability.md#storage-compatibility-rules) and [identifying a deployed build](../architecture/upgradeability.md#versioning-and-identifying-a-deployed-build).

## Choose the right read method

| Method | Best for | Trade-offs |
|---|---|---|
| Contract view function via `simulateTransaction` | Reading values through Shade's public interface, with the contract's own lookup and validation behavior. | Runs contract code and uses simulation resources. It only returns what the contract exposes; it is not a general query language. Read-only simulations do not submit a transaction. |
| `getLedgerEntries` | Inspecting known keys in current ledger state, debugging, or reading internal values not exposed by a getter. | Requires constructing the exact XDR key and understanding the stored XDR value. It exposes implementation details, not a stable API; it provides no event history. Each request accepts at most 200 keys. |
| Event indexer | Historical activity, event-driven projections, and queries across transactions. | Events are only the facts the contract emitted; they are not a complete snapshot of storage. An indexer must handle pagination, cursors, and recovery/backfill. See the [event indexing guide](indexing-events.md). |

Prefer a view function when one provides the data you need. Use direct ledger reads when you need a specific current storage entry or are diagnosing contract state. Use an indexer for history; a ledger read cannot reconstruct prior values.

## Prerequisites

- The Shade contract ID and the RPC URL for the same network. This guide's examples use Stellar testnet: `https://soroban-testnet.stellar.org`.
- The `@stellar/stellar-sdk` package for the TypeScript examples.
- The deployed contract version or WASM hash, so you can verify that the storage layout described here matches the code running at that contract ID. Shade has no semantic version stored on chain; see the [versioning policy](../architecture/upgradeability.md#versioning-and-identifying-a-deployed-build).

## Build a Shade contract-data ledger key

A contract-data key identifies the contract address, an `ScVal` key, and the storage durability. Soroban `#[contracttype]` enums encode their variant name as a symbol; tuple variants encode their arguments after that symbol in an `ScVal` vector.

In the current `shade` implementation, `DataKey::Merchant(u64)`, `DataKey::Invoice(u64)`, and `DataKey::TokenFee(Address)` are persistent-storage keys. Their `ScVal` keys are:

| Rust storage key | `ScVal` key |
|---|---|
| `DataKey::Merchant(merchant_id)` | `vec![symbol("Merchant"), u64(merchant_id)]` |
| `DataKey::Invoice(invoice_id)` | `vec![symbol("Invoice"), u64(invoice_id)]` |
| `DataKey::TokenFee(token_address)` | `vec![symbol("TokenFee"), address(token_address)]` |

The variant names and argument types must match the deployed contract exactly. The durability is part of the ledger key too; use the durability actually used by that contract version.

### TypeScript: construct keys and decode entries

Replace the example contract ID and addresses with values from your testnet deployment. IDs are `bigint` because the stored key arguments are Soroban `u64`s.

```typescript
import {
  Address,
  nativeToScVal,
  rpc,
  scValToNative,
  xdr,
} from "@stellar/stellar-sdk";

const rpcServer = new rpc.Server("https://soroban-testnet.stellar.org");
const shadeContractId = "<testnet-shade-contract-id>";
const tokenAddress = "<testnet-token-contract-address>";
const merchantId = 1n;
const invoiceId = 1n;

function dataKey(variant: string, ...args: xdr.ScVal[]): xdr.ScVal {
  return xdr.ScVal.scvVec([
    xdr.ScVal.scvSymbol(variant),
    ...args,
  ]);
}

function persistentKey(key: xdr.ScVal): xdr.LedgerKey {
  return xdr.LedgerKey.contractData(
    new xdr.LedgerKeyContractData({
      contract: new Address(shadeContractId).toScAddress(),
      key,
      durability: xdr.ContractDataDurability.persistent,
    }),
  );
}

const entriesToRead = [
  [
    "merchant",
    persistentKey(
      dataKey("Merchant", nativeToScVal(merchantId, { type: "u64" })),
    ),
  ],
  [
    "invoice",
    persistentKey(
      dataKey("Invoice", nativeToScVal(invoiceId, { type: "u64" })),
    ),
  ],
  [
    "token fee",
    persistentKey(
      dataKey(
        "TokenFee",
        new Address(tokenAddress).toScVal(),
      ),
    ),
  ],
] as const;

for (const [label, key] of entriesToRead) {
  // Save this value if you also want to query the same key with curl.
  console.log(`${label} LedgerKey XDR:`, key.toXDR("base64"));

  const response = await rpcServer.getLedgerEntries(key);
  const entry = response.entries[0];
  if (!entry) {
    console.log(`${label}: no live ledger entry returned`);
    continue;
  }

  const { contractData } = xdr.expectUnionVariant(entry.val, "contractData");
  const value = scValToNative(contractData.val);
  console.log(`${label}:`, value);
  console.log("latest ledger:", response.latestLedger);
  console.log("live until ledger:", entry.liveUntilLedgerSeq);
}
```

`getLedgerEntries` returns the decoded XDR union in `entry.val` when using the SDK's `rpc.Server`. `scValToNative` converts the stored `ScVal` to JavaScript values; for example, the fee is an `i128` and is represented as a `bigint`. Merchant and invoice values are contracttype structs. Match their fields by name, and decode against the struct definition from the exact deployed version rather than assuming a permanent shape.

### Decode the raw base64 XDR

If you call RPC with `fetch` or `curl` rather than `rpc.Server`, the response's `entries[].xdr` is a base64-encoded `LedgerEntryData`. Parse that XDR first, then convert the contract value:

```typescript
import { scValToNative, xdr } from "@stellar/stellar-sdk";

const rawLedgerEntryDataXdr = "<entries[0].xdr from the RPC response>";
const ledgerEntryData = xdr.LedgerEntryData.fromXDR(
  rawLedgerEntryDataXdr,
  "base64",
);
const { contractData } = xdr.expectUnionVariant(
  ledgerEntryData,
  "contractData",
);
const value = scValToNative(contractData.val);
console.log(value);
```

The `key` and `xdr` fields in the raw RPC response are different XDR types: `key` is a `LedgerKey`; `xdr` is the corresponding `LedgerEntryData`. If you want a human-readable representation while debugging, request `"xdrFormat": "json"` or use Stellar CLI's `stellar xdr decode`.

## Query the same key with curl

Copy the base64 value printed as `LedgerKey XDR` by the TypeScript example into `LEDGER_KEY`. The testnet RPC expects a JSON-RPC `getLedgerEntries` request whose `keys` values are base64 `LedgerKey` XDR:

```bash
LEDGER_KEY='<base64 LedgerKey XDR from the TypeScript example>'

curl --fail-with-body --silent --show-error \
  -H 'Content-Type: application/json' \
  --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getLedgerEntries\",\"params\":{\"keys\":[\"$LEDGER_KEY\"]}}" \
  https://soroban-testnet.stellar.org
```

The response includes `latestLedger` and, for each live result, `key`, `xdr`, `lastModifiedLedgerSeq`, and `liveUntilLedgerSeq`. Use the raw-XDR TypeScript example above to parse the response's `xdr`.

## Check TTL and archived entries

For a returned entry, compare `liveUntilLedgerSeq` with the response's `latestLedger`. The approximate remaining TTL in ledgers is `liveUntilLedgerSeq - latestLedger`. TTL is measured in ledgers, not seconds; the latest ledger can advance between requests. A low remaining TTL is a signal to investigate the contract's TTL-management plan, not evidence that a read will extend it. See [Shade's current storage and TTL behavior](../architecture/storage-model.md#ttl-and-rent).

`getLedgerEntries` returns live ledger entries. If a requested key is absent from `entries`, that alone does **not** tell you whether it never existed or its persistent entry has been archived. Direct reads do not restore entries. To investigate an expected archived entry, simulate a public contract read that accesses it; on Protocol 23 and later, simulation can identify archived entries in its restoration data. Simulation itself does not commit a restoration. See Stellar's [State Archival documentation](https://developers.stellar.org/docs/learn/fundamentals/contract-development/storage/state-archival) for the network's archival and restoration behavior.

Shade currently writes these keys in persistent storage and does not proactively extend their TTL in contract code, but this is an implementation detail that may change. Do not equate an absent direct read with deleted data, and do not assume that reading an entry extends its lifetime.

## Related pages

- [Storage model](../architecture/storage-model.md) — current `DataKey` variants, stored value types, and TTL behavior.
- [Upgradeability](../architecture/upgradeability.md) — storage compatibility and deployed WASM versioning.
- [Event indexing guide](indexing-events.md) — build a historical off-chain indexer.
- [Generating and using contract bindings](contract-bindings.md) — use the public typed interface instead of internal storage when possible.

← [Back to guides](README.md)
