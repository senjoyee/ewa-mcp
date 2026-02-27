#!/usr/bin/env python3
"""
Menu-driven maintenance helper for EWA Search + Blob cleanup and index recreation.

Options:
1) Delete all data (Search + Blob) for ALL customers
2) Delete all data (Search + Blob) for a specific customer
3) Delete and recreate indexes (docs, chunks, check-overview)

This script is intentionally thin: it shells out to the existing maintenance scripts
(reset-uploaded-data.py and setup-indexes.py) so behavior stays centralized.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESET_SCRIPT = REPO_ROOT / "infrastructure" / "scripts" / "reset-uploaded-data.py"
SETUP_SCRIPT = REPO_ROOT / "infrastructure" / "scripts" / "setup-indexes.py"


def _prompt_endpoint_key() -> tuple[str, str]:
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT") or input("Enter Azure Search endpoint (https://...search.windows.net): ").strip()
    api_key = os.getenv("AZURE_SEARCH_API_KEY") or input("Enter Azure Search ADMIN key: ").strip()
    if not endpoint or not api_key:
        print("ERROR: Endpoint and admin key are required.")
        sys.exit(1)
    return endpoint, api_key


def _run_cmd(cmd: list[str]) -> int:
    print("\n>>", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        print(f"Command failed with code {result.returncode}")
    return result.returncode


def delete_all_data():
    print("\nDeleting ALL data (blobs + search docs/chunks/check-overview) for ALL customers...")
    cmd = [
        sys.executable,
        str(RESET_SCRIPT),
        "--confirm",
        "--container", "ewa-uploads",
        "--docs-index", "ewa-docs",
        "--chunks-index", "ewa-chunks",
        "--alerts-index", "ewa-check-overview",
    ]
    return _run_cmd(cmd)


def delete_specific_customer():
    customer_id = input("Enter customer_id to delete: ").strip()
    if not customer_id:
        print("No customer_id provided; aborting.")
        return 1
    print(f"\nDeleting data for customer_id='{customer_id}' (blobs + search docs/chunks/check-overview)...")
    cmd = [
        sys.executable,
        str(RESET_SCRIPT),
        "--confirm",
        "--container", "ewa-uploads",
        "--docs-index", "ewa-docs",
        "--chunks-index", "ewa-chunks",
        "--alerts-index", "ewa-check-overview",
        "--customer-id", customer_id,
    ]
    return _run_cmd(cmd)


def recreate_indexes():
    print("\nRecreating indexes (ewa-docs, ewa-chunks, ewa-check-overview)...")
    endpoint, api_key = _prompt_endpoint_key()
    cmd = [
        sys.executable,
        str(SETUP_SCRIPT),
        "--endpoint", endpoint,
        "--api-key", api_key,
        "--delete-existing",
    ]
    return _run_cmd(cmd)


def main() -> int:
    menu = """
Select an option:
  1) Delete ALL data (Search + Blob) for ALL customers
  2) Delete ALL data (Search + Blob) for a specific customer
  3) Delete and recreate indexes (docs/chunks/check-overview)
  q) Quit
> """
    while True:
        choice = input(menu).strip().lower()
        if choice == "1":
            delete_all_data()
        elif choice == "2":
            delete_specific_customer()
        elif choice == "3":
            recreate_indexes()
        elif choice in {"q", "quit", "exit"}:
            print("Bye")
            return 0
        else:
            print("Invalid choice. Try again.")


if __name__ == "__main__":
    sys.exit(main())
