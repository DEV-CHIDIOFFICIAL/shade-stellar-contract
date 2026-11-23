#!/usr/bin/env python3
"""Idempotent Shade deployment/configuration runner (Python 3.11+)."""
from __future__ import annotations

import argparse
import json
import hashlib
import os
import shlex
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_DIR = ROOT / ".stellar" / "deployments"


def run(command: list[str], *, dry_run: bool, capture: bool = False) -> str:
    printable = shlex.join(command)
    if dry_run:
        print(f"[dry-run] {printable}")
        return ""
    print(f"+ {printable}", flush=True)
    result = subprocess.run(command, cwd=ROOT, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if result.returncode:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed ({result.returncode}): {printable}")
    return result.stdout.strip() if capture else ""


def invoke(network: str, contract_id: str, method: str, args: list[str] = (),
           *, dry_run: bool, read: bool = False) -> str:
    command = ["stellar", "contract", "invoke", "--id", contract_id,
               "--network", network]
    if not read:
        command += ["--source-account", os.environ.get("STELLAR_SOURCE_ACCOUNT", "default")]
    command += ["--", method, *args]
    return run(command, dry_run=dry_run, capture=read)


def normalize(value: str) -> str:
    return "".join(value.lower().replace('"', "").split())


def ensure_equal(actual: str, expected: str, label: str) -> None:
    if normalize(actual) != normalize(expected):
        raise RuntimeError(f"Verification failed for {label}: expected {expected!r}, got {actual!r}")


def save_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", required=True, choices=("testnet", "mainnet"))
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()
    network = options.network
    dry_run = options.dry_run
    config_path = ROOT / "deploy" / f"{network}.toml"
    if not config_path.is_file():
        raise RuntimeError(f"Missing network configuration: {config_path}")
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)

    admin = config.get("admin", "").strip()
    platform_account = config.get("platform_account", admin).strip()
    tokens = config.get("tokens", [])
    if not admin:
        raise RuntimeError(f"Set admin in {config_path} before deploying")
    if not tokens:
        raise RuntimeError(f"Configure at least one accepted token in {config_path}")
    for token in tokens:
        if not token.get("address") or "fee_bps" not in token:
            raise RuntimeError("Every token needs address and fee_bps")
        if not 0 <= int(token["fee_bps"]) <= 10_000:
            raise RuntimeError(f"Invalid fee_bps for {token['address']}")
    if not platform_account:
        raise RuntimeError("Set platform_account (or admin) in the network config")

    record_path = RECORD_DIR / f"{network}.json"
    record = {}
    if record_path.exists() and not dry_run:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("network") != network:
            raise RuntimeError("Existing deployment record belongs to a different network")

    def checkpoint(**values):
        record.update(values)
        record.update(network=network, updated_at=datetime.now(timezone.utc).isoformat())
        if not dry_run:
            save_record(record_path, record)

    shade_wasm = "target/wasm32v1-none/release/shade.wasm"
    account_wasm = "target/wasm32v1-none/release/account.wasm"
    shade_opt = "target/wasm32v1-none/release/shade.optimized.wasm"
    account_opt = "target/wasm32v1-none/release/account.optimized.wasm"

    run(["cargo", "build", "--workspace", "--target", "wasm32v1-none", "--release"],
        dry_run=dry_run)
    run(["stellar", "contract", "optimize", "--wasm", shade_wasm], dry_run=dry_run)
    run(["stellar", "contract", "optimize", "--wasm", account_wasm], dry_run=dry_run)

    account_hash = record.get("account_wasm_hash")
    if not account_hash:
        account_hash = run(["stellar", "contract", "install", "--wasm", account_opt,
                            "--network", network, "--source-account",
                            os.environ.get("STELLAR_SOURCE_ACCOUNT", "default")],
                           dry_run=dry_run, capture=not dry_run)
        if dry_run:
            account_hash = "<account-wasm-hash>"
        checkpoint(account_wasm_hash=account_hash)
    else:
        print(f"Account WASM already installed: {account_hash}")

    shade_wasm_hash = (hashlib.sha256((ROOT / shade_opt).read_bytes()).hexdigest()\n                       if not dry_run else "<shade-wasm-sha256>")\n    checkpoint(shade_wasm_hash=shade_wasm_hash)\n\n    shade_wasm_hash = (hashlib.sha256((ROOT / shade_opt).read_bytes()).hexdigest()
                       if not dry_run else "<shade-wasm-sha256>")
    checkpoint(shade_wasm_hash=shade_wasm_hash)

    shade_id = record.get("shade_contract_id")
    if not shade_id:
        shade_id = run(["stellar", "contract", "deploy", "--wasm", shade_opt,
                        "--network", network, "--source-account",
                        os.environ.get("STELLAR_SOURCE_ACCOUNT", "default")],
                       dry_run=dry_run, capture=not dry_run)
        if dry_run:
            shade_id = "<shade-contract-id>"
        checkpoint(shade_contract_id=shade_id)
    else:
        print(f"Using recorded Shade contract: {shade_id}")

    if not dry_run:
        try:
            current_admin = invoke(network, shade_id, "get_admin", dry_run=False, read=True)
        except RuntimeError:
            # A fresh contract has no admin until initialize succeeds.
            invoke(network, shade_id, "initialize", ["--admin", admin], dry_run=False)
            current_admin = invoke(network, shade_id, "get_admin", dry_run=False, read=True)
        ensure_equal(current_admin, admin, "Shade admin")
    else:
        invoke(network, shade_id, "initialize", ["--admin", admin], dry_run=True)

    # The contract initializes PlatformAccount to admin. Change only when requested.
    if not dry_run:
        current_platform = invoke(network, shade_id, "get_platform_account",
                                  dry_run=False, read=True)
        if normalize(current_platform) != normalize(platform_account):
            invoke(network, shade_id, "set_platform_account",
                   ["--admin", admin, "--account", platform_account], dry_run=False)
        ensure_equal(invoke(network, shade_id, "get_platform_account",
                            dry_run=False, read=True), platform_account, "platform account")
    else:
        invoke(network, shade_id, "set_platform_account",
               ["--admin", admin, "--account", platform_account], dry_run=True)

    # Register the account WASM hash on Shade, then verify it by comparing the
    # deployment record on reruns. The contract currently exposes no getter.
    if record.get("registered_account_wasm_hash") != account_hash:
        invoke(network, shade_id, "set_account_wasm_hash",
               ["--admin", admin, "--wasm-hash", account_hash], dry_run=dry_run)
        checkpoint(registered_account_wasm_hash=account_hash)

    for token in tokens:
        address = token["address"]
        if not dry_run:
            accepted = invoke(network, shade_id, "is_accepted_token",
                              ["--token", address], dry_run=False, read=True)
            if normalize(accepted) not in ("true", "1"):
                invoke(network, shade_id, "add_accepted_token",
                       ["--admin", admin, "--token", address], dry_run=False)
            ensure_equal(invoke(network, shade_id, "is_accepted_token",
                                ["--token", address], dry_run=False, read=True),
                         "true", f"accepted token {address}")
            current_fee = invoke(network, shade_id, "get_fee",
                                 ["--token", address], dry_run=False, read=True)
            if normalize(current_fee) != normalize(str(token["fee_bps"])):
                invoke(network, shade_id, "set_fee",
                       ["--admin", admin, "--token", address,
                        "--fee", str(token["fee_bps"])], dry_run=False)
            ensure_equal(invoke(network, shade_id, "get_fee", ["--token", address],
                                dry_run=False, read=True),
                         str(token["fee_bps"]), f"fee for {address}")
        else:
            invoke(network, shade_id, "add_accepted_token",
                   ["--admin", admin, "--token", address], dry_run=True)
            invoke(network, shade_id, "set_fee",
                   ["--admin", admin, "--token", address,
                    "--fee", str(token["fee_bps"])], dry_run=True)

        oracle = token.get("oracle")
        if oracle:
            oracle_args = ["--admin", admin, "--token", address, "--oracle",
                           json.dumps({"contract": oracle["contract"],
                                       "price_decimals": int(oracle["price_decimals"]),
                                       "token_decimals": int(oracle["token_decimals"])},
                                      separators=(",", ":"))]
            if dry_run:
                invoke(network, shade_id, "set_token_oracle", oracle_args, dry_run=True)
            else:
                current = invoke(network, shade_id, "get_token_oracle",
                                 ["--token", address], dry_run=False, read=True)
                expected = (oracle["contract"], str(oracle["price_decimals"]),
                            str(oracle["token_decimals"]))
                if not all(normalize(part) in normalize(current) for part in expected):
                    invoke(network, shade_id, "set_token_oracle", oracle_args, dry_run=False)
                verified = invoke(network, shade_id, "get_token_oracle",
                                  ["--token", address], dry_run=False, read=True)
                if not all(normalize(part) in normalize(verified) for part in expected):
                    raise RuntimeError(f"Oracle verification failed for {address}")

    if not dry_run:
        checkpoint(verified=True, admin=admin, platform_account=platform_account,
                   tokens=tokens, shade_wasm=shade_opt, account_wasm=account_opt,
                   shade_wasm_hash=shade_wasm_hash, account_wasm_hash=account_hash)
        try:
            info = run(["stellar", "network", "info", "--network", network],
                       dry_run=False, capture=True)
            record["network_info"] = info
            # CLI output varies by version; retain the full output and extract
            # a ledger only when an unambiguous sequence is present.
            import re
            match = re.search(r"(?:latest_ledger|ledger|sequence)\D+(\d+)", info, re.I)
            record["ledger"] = int(match.group(1)) if match else None
        except RuntimeError:
            record["ledger"] = None
        checkpoint()
        print(f"Deployment complete. Record: {record_path.relative_to(ROOT)}")
    else:
        print("[dry-run] No network requests or files were changed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"deploy: error: {error}", file=sys.stderr)
        raise SystemExit(1)
