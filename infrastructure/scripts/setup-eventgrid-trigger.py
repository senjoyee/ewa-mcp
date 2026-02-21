#!/usr/bin/env python3
"""
setup-eventgrid-trigger.py

Creates (or updates) the Event Grid System Topic on the EWA blob storage account
and wires an Event Subscription to the Azure Function HTTP endpoint.

Run this AFTER deploying the Azure Function so the webhook URL is reachable.

Usage:
    python infrastructure/scripts/setup-eventgrid-trigger.py

Required env vars (or pass as CLI args):
    AZURE_SUBSCRIPTION_ID   – Azure subscription ID
    RESOURCE_GROUP          – Resource group name  (default: ewa-mcp-rg)
    STORAGE_ACCOUNT_NAME    – Storage account name (default: ewastgw2gtkdzdemu7s)
    FUNCTION_APP_NAME       – Function App name    (default: ewa-processor-prod)
    FUNCTION_NAME           – HTTP function name   (default: ProcessEwaBlob)

The script retrieves the function-level host key automatically via the Azure CLI.
"""

import argparse
import json
import subprocess
import sys


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run an az CLI command and return the result."""
    print("  »", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        print("ERROR:", result.stderr or result.stdout)
        sys.exit(result.returncode)
    return result


def main():
    parser = argparse.ArgumentParser(description="Wire Event Grid blob trigger to Azure Function")
    parser.add_argument("--subscription", default=None)
    parser.add_argument("--resource-group", default="ewa-mcp-rg")
    parser.add_argument("--storage-account", default="ewastgw2gtkdzdemu7s")
    parser.add_argument("--function-app", default="ewa-processor-prod")
    parser.add_argument("--function-name", default="ProcessEwaBlob")
    parser.add_argument("--container", default="ewa-uploads")
    parser.add_argument("--topic-name", default="ewa-blob-events")
    parser.add_argument("--subscription-name", default="ewa-blob-trigger")
    args = parser.parse_args()

    rg = args.resource_group
    storage = args.storage_account
    func_app = args.function_app
    func_name = args.function_name
    container = args.container
    topic_name = args.topic_name
    sub_name = args.subscription_name

    # ── Set subscription if provided ────────────────────────────────────────
    if args.subscription:
        print(f"\n[1/5] Setting subscription to {args.subscription}...")
        run(["az", "account", "set", "--subscription", args.subscription])
    else:
        print("\n[1/5] Using current subscription")

    # ── Get storage account resource ID ─────────────────────────────────────
    print(f"\n[2/5] Fetching storage account resource ID for '{storage}'...")
    result = run([
        "az", "storage", "account", "show",
        "--name", storage,
        "--resource-group", rg,
        "--query", "id",
        "--output", "tsv",
    ])
    storage_id = result.stdout.strip()
    print(f"       Storage ID: {storage_id}")

    # ── Create / update Event Grid System Topic ──────────────────────────────
    print(f"\n[3/5] Creating Event Grid System Topic '{topic_name}'...")
    result = run([
        "az", "eventgrid", "system-topic", "create",
        "--name", topic_name,
        "--resource-group", rg,
        "--source", storage_id,
        "--topic-type", "microsoft.storage.storageaccounts",
        "--location", "uksouth",   # must match storage account location
        "--output", "json",
    ], check=False)

    if result.returncode != 0:
        if "already exists" in (result.stderr + result.stdout).lower():
            print("       System Topic already exists — continuing.")
        else:
            print("ERROR:", result.stderr or result.stdout)
            sys.exit(result.returncode)
    else:
        print("       System Topic created ✓")

    # ── Retrieve function host key ───────────────────────────────────────────
    print(f"\n[4/5] Fetching function key for '{func_name}'...")
    result = run([
        "az", "functionapp", "function", "keys", "list",
        "--name", func_app,
        "--resource-group", rg,
        "--function-name", func_name,
        "--output", "json",
    ])
    keys = json.loads(result.stdout)
    # Prefer 'default' key
    func_key = keys.get("default") or next(iter(keys.values()), "")
    if not func_key:
        print("ERROR: Could not retrieve function key. Deploy the function first.")
        sys.exit(1)

    webhook_url = (
        f"https://{func_app}.azurewebsites.net/api/{func_name}?code={func_key}"
    )
    print(f"       Webhook URL: https://{func_app}.azurewebsites.net/api/{func_name}?code=***")

    # ── Create / update Event Subscription ──────────────────────────────────
    print(f"\n[5/5] Creating Event Subscription '{sub_name}'...")
    subject_prefix = f"/blobServices/default/containers/{container}/"

    result = run([
        "az", "eventgrid", "system-topic", "event-subscription", "create",
        "--name", sub_name,
        "--system-topic-name", topic_name,
        "--resource-group", rg,
        "--endpoint-type", "webhook",
        "--endpoint", webhook_url,
        "--included-event-types", "Microsoft.Storage.BlobCreated",
        "--subject-begins-with", subject_prefix,
        "--subject-ends-with", ".pdf",
        "--event-delivery-schema", "EventGridSchema",
        "--max-delivery-attempts", "5",
        "--event-ttl", "60",
        "--output", "json",
    ], check=False)

    if result.returncode != 0:
        if "already exists" in (result.stderr + result.stdout).lower():
            # Update existing subscription
            print("       Subscription exists — updating...")
            run([
                "az", "eventgrid", "system-topic", "event-subscription", "update",
                "--name", sub_name,
                "--system-topic-name", topic_name,
                "--resource-group", rg,
                "--endpoint", webhook_url,
            ])
            print("       Subscription updated ✓")
        else:
            print("ERROR:", result.stderr or result.stdout)
            sys.exit(result.returncode)
    else:
        print("       Subscription created ✓")

    print("\n✅  Event Grid trigger wiring complete!")
    print(f"    Upload a PDF to container '{container}' to test.")
    print(f"    Monitor: az functionapp function show --name {func_app} "
          f"--resource-group {rg} --function-name {func_name}")


if __name__ == "__main__":
    main()
