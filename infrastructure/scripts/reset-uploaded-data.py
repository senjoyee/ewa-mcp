"""Reset uploaded EWA test data in Blob Storage and Azure AI Search.

Usage examples:
  python infrastructure/scripts/reset-uploaded-data.py --customer-id TBS --dry-run
  python infrastructure/scripts/reset-uploaded-data.py --customer-id TBS --confirm
  python infrastructure/scripts/reset-uploaded-data.py --confirm
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.storage.blob import BlobServiceClient


DEFAULT_DOCS_INDEX = "ewa-docs"
DEFAULT_CHUNKS_INDEX = "ewa-chunks"
DEFAULT_ALERTS_INDEX = "ewa-alerts"
DEFAULT_CONTAINER = "ewa-uploads"
BATCH_SIZE = 500


def _load_local_settings_fallback() -> None:
    """Load env vars from local.settings.json if present and env vars are missing."""
    repo_root = Path(__file__).resolve().parents[2]
    candidate_files = [
        repo_root / "processor" / "local.settings.json",
        repo_root / "local.settings.json",
    ]

    for candidate in candidate_files:
        if not candidate.exists():
            continue

        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            values = data.get("Values", {}) if isinstance(data, dict) else {}
            if not isinstance(values, dict):
                continue

            for key, value in values.items():
                if key not in os.environ and isinstance(value, str):
                    os.environ[key] = value

            print(f"Loaded fallback settings from: {candidate}")
            return
        except Exception as exc:
            print(f"WARNING: Could not parse {candidate}: {exc}")


@dataclass
class ResetSummary:
    blobs_deleted: int = 0
    docs_deleted: int = 0
    chunks_deleted: int = 0
    alerts_deleted: int = 0


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"ERROR: Missing required environment variable: {name}")
        sys.exit(1)
    return value


def _batch(iterable: List[str], batch_size: int) -> Iterable[List[str]]:
    for i in range(0, len(iterable), batch_size):
        yield iterable[i : i + batch_size]


def _collect_search_keys(client: SearchClient, key_field: str, filter_expression: str | None) -> List[str]:
    keys: List[str] = []
    results = client.search(search_text="*", filter=filter_expression, select=[key_field])
    for item in results:
        value = item.get(key_field)
        if value:
            keys.append(value)
    return keys


def _delete_search_docs(
    endpoint: str,
    api_key: str,
    index_name: str,
    key_field: str,
    filter_expression: str | None,
    confirm: bool,
) -> int:
    client = SearchClient(endpoint=endpoint, index_name=index_name, credential=AzureKeyCredential(api_key))
    keys = _collect_search_keys(client, key_field, filter_expression)

    if not keys:
        print(f"[{index_name}] no documents matched")
        return 0

    print(f"[{index_name}] matched {len(keys)} document(s)")
    if not confirm:
        return 0

    deleted = 0
    for key_batch in _batch(keys, BATCH_SIZE):
        payload = [{key_field: k} for k in key_batch]
        client.delete_documents(documents=payload)
        deleted += len(payload)

    print(f"[{index_name}] deleted {deleted} document(s)")
    return deleted


def _delete_blobs(connection_string: str, container_name: str, prefix: str | None, confirm: bool) -> int:
    blob_service = BlobServiceClient.from_connection_string(connection_string)
    container = blob_service.get_container_client(container_name)

    blob_names = [b.name for b in container.list_blobs(name_starts_with=prefix)]
    if not blob_names:
        print(f"[{container_name}] no blobs matched")
        return 0

    print(f"[{container_name}] matched {len(blob_names)} blob(s)")
    if not confirm:
        return 0

    deleted = 0
    for blob_name in blob_names:
        container.delete_blob(blob_name)
        deleted += 1

    print(f"[{container_name}] deleted {deleted} blob(s)")
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete uploaded files and related indexed data.")
    parser.add_argument("--customer-id", help="Only reset data for this customer ID (for blobs this means '<customer-id>/').")
    parser.add_argument("--container", default=DEFAULT_CONTAINER, help=f"Blob container name (default: {DEFAULT_CONTAINER})")
    parser.add_argument("--docs-index", default=os.getenv("INDEX_DOCS", DEFAULT_DOCS_INDEX))
    parser.add_argument("--chunks-index", default=os.getenv("INDEX_CHUNKS", DEFAULT_CHUNKS_INDEX))
    parser.add_argument("--alerts-index", default=os.getenv("INDEX_ALERTS", DEFAULT_ALERTS_INDEX))
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting.")
    parser.add_argument("--confirm", action="store_true", help="Actually perform deletion.")

    args = parser.parse_args()

    confirm = args.confirm and not args.dry_run
    if args.confirm and args.dry_run:
        print("ERROR: Use either --dry-run or --confirm, not both.")
        sys.exit(1)

    if not args.confirm and not args.dry_run:
        print("ERROR: choose one mode: --dry-run (preview) or --confirm (execute)")
        sys.exit(1)

    if args.customer_id:
        blob_prefix = f"{args.customer_id}/"
        search_filter = f"customer_id eq '{args.customer_id}'"
        print(f"Scoped reset: customer_id={args.customer_id}")
    else:
        blob_prefix = None
        search_filter = None
        print("Global reset: all customers")

    _load_local_settings_fallback()

    blob_connection_string = _require_env("BLOB_CONNECTION_STRING")
    search_endpoint = _require_env("AZURE_SEARCH_ENDPOINT")
    search_api_key = _require_env("AZURE_SEARCH_API_KEY")

    print("Mode:", "EXECUTE" if confirm else "DRY RUN")
    summary = ResetSummary()

    summary.blobs_deleted = _delete_blobs(
        connection_string=blob_connection_string,
        container_name=args.container,
        prefix=blob_prefix,
        confirm=confirm,
    )

    summary.docs_deleted = _delete_search_docs(
        endpoint=search_endpoint,
        api_key=search_api_key,
        index_name=args.docs_index,
        key_field="doc_id",
        filter_expression=search_filter,
        confirm=confirm,
    )

    summary.chunks_deleted = _delete_search_docs(
        endpoint=search_endpoint,
        api_key=search_api_key,
        index_name=args.chunks_index,
        key_field="chunk_id",
        filter_expression=search_filter,
        confirm=confirm,
    )

    summary.alerts_deleted = _delete_search_docs(
        endpoint=search_endpoint,
        api_key=search_api_key,
        index_name=args.alerts_index,
        key_field="alert_id",
        filter_expression=search_filter,
        confirm=confirm,
    )

    print("\nSummary")
    print(f"  blobs_deleted : {summary.blobs_deleted}")
    print(f"  docs_deleted  : {summary.docs_deleted}")
    print(f"  chunks_deleted: {summary.chunks_deleted}")
    print(f"  alerts_deleted: {summary.alerts_deleted}")


if __name__ == "__main__":
    main()
