"""Wipe EWA blob uploads and Azure Search documents.

This is a convenience wrapper around reset-uploaded-data.py.

Examples:
  python infrastructure/scripts/wipe_blob_and_search.py --dry-run
  python infrastructure/scripts/wipe_blob_and_search.py --confirm
  python infrastructure/scripts/wipe_blob_and_search.py --customer-id TBS --confirm
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Wipe blob and search data for EWA")
    parser.add_argument("--customer-id", help="Optional customer_id scope")
    parser.add_argument("--dry-run", action="store_true", help="Preview delete counts")
    parser.add_argument("--confirm", action="store_true", help="Execute deletion")
    args = parser.parse_args()

    if args.dry_run == args.confirm:
        print("ERROR: Choose exactly one: --dry-run or --confirm")
        return 1

    script_path = Path(__file__).resolve().parent / "reset-uploaded-data.py"
    cmd = [sys.executable, str(script_path)]

    if args.customer_id:
        cmd.extend(["--customer-id", args.customer_id])
    if args.dry_run:
        cmd.append("--dry-run")
    if args.confirm:
        cmd.append("--confirm")

    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
