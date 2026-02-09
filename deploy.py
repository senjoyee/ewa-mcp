#!/usr/bin/env python3
"""Unified deployment script for EWA MCP system on Azure.

This script orchestrates the deployment of:
1. Azure resources via Bicep (Search, OpenAI, Storage, Event Grid, Container Apps)
2. Azure AI Search indexes (ewa-docs, ewa-chunks, ewa-alerts)
3. Azure Function (document processor)
4. MCP Server (Container App)

Usage:
    python deploy.py --subscription <id> --resource-group <name> --location <region>

Prerequisites:
    - Azure CLI installed and logged in
    - Python 3.9+ with azure-search-documents package
    - Docker installed (for MCP server build)
    - func CLI installed (for Azure Functions)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def run_cmd(cmd: list, cwd: Optional[str] = None, capture: bool = True) -> tuple:
    """Run shell command and return (stdout, stderr, returncode)."""
    print(f"Running: {' '.join(cmd)}")
    
    if capture:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            cwd=cwd,
            shell=False
        )
        return result.stdout, result.stderr, result.returncode
    else:
        result = subprocess.run(cmd, cwd=cwd)
        return "", "", result.returncode


def check_prerequisites():
    """Check that all required tools are installed."""
    print("Checking prerequisites...")
    
    tools = {
        "az": "Azure CLI",
        "docker": "Docker",
        "func": "Azure Functions Core Tools",
        "python": "Python 3.9+"
    }
    
    for cmd, name in tools.items():
        result = subprocess.run([cmd, "--version"], capture_output=True)
        if result.returncode != 0:
            print(f"❌ {name} not found. Please install {name}.")
            sys.exit(1)
        print(f"✅ {name} found")
    
    # Check Azure login
    result = subprocess.run(["az", "account", "show"], capture_output=True)
    if result.returncode != 0:
        print("❌ Not logged into Azure. Run: az login")
        sys.exit(1)
    print("✅ Logged into Azure")


def deploy_bicep(
    subscription: str,
    resource_group: str,
    location: str,
    environment: str,
    person_responsible: str,
    deploy_openai: bool,
    existing_openai_endpoint: str,
    existing_openai_key: str,
    bicep_dir: Path
) -> dict:
    """Deploy Azure resources via Bicep."""
    print(f"\n{'='*60}")
    print("Step 1: Deploying Azure Resources via Bicep")
    print(f"{'='*60}")
    
    # Create resource group if it doesn't exist
    stdout, stderr, code = run_cmd([
        "az", "group", "create",
        "--name", resource_group,
        "--location", location,
        "--subscription", subscription
    ])
    
    if code != 0:
        print(f"Warning: Could not create resource group: {stderr}")
    
    # Deploy Bicep template
    deployment_name = f"ewa-deploy-{int(time.time())}"
    
    # Build parameters
    bicep_params = [
        "--parameters", f"environment={environment}",
        "--parameters", f"personResponsible={person_responsible}",
        "--parameters", f"deployOpenAI={str(deploy_openai).lower()}",
    ]
    
    # Add existing OpenAI params if not deploying new one
    if not deploy_openai:
        bicep_params.extend([
            "--parameters", f"existingOpenAIEndpoint={existing_openai_endpoint}",
            "--parameters", f"existingOpenAIKey={existing_openai_key}",
        ])
    
    stdout, stderr, code = run_cmd([
        "az", "deployment", "group", "create",
        "--resource-group", resource_group,
        "--template-file", str(bicep_dir / "main.bicep"),
        "--name", deployment_name,
        "--subscription", subscription,
        "--output", "json"
    ] + bicep_params)
    
    if code != 0:
        print(f"❌ Bicep deployment failed: {stderr}")
        sys.exit(1)
    
    print("✅ Bicep deployment completed")
    
    # Parse outputs
    try:
        deployment = json.loads(stdout)
        outputs = deployment.get("properties", {}).get("outputs", {})
        
        return {
            "search_endpoint": outputs.get("searchEndpoint", {}).get("value", ""),
            "search_name": outputs.get("searchName", {}).get("value", ""),
            "openai_endpoint": outputs.get("openaiEndpoint", {}).get("value", ""),
            "storage_connection": outputs.get("storageConnectionString", {}).get("value", ""),
            "eventgrid_endpoint": outputs.get("eventgridEndpoint", {}).get("value", ""),
            "container_env_id": outputs.get("containerAppEnvironmentId", {}).get("value", "")
        }
    except json.JSONDecodeError:
        print("Warning: Could not parse deployment outputs")
        return {}


def get_resource_keys(resource_group: str, subscription: str, environment: str = "") -> dict:
    """Get API keys for deployed resources."""
    print(f"\n{'='*60}")
    print("Step 2: Retrieving Resource API Keys")
    print(f"{'='*60}")
    
    keys = {}
    env_suffix = f"-{environment}" if environment else ""
    
    # Search admin key
    stdout, stderr, code = run_cmd([
        "az", "search", "admin-key", "show",
        "--service-name", f"ewa-search{env_suffix}",
        "--resource-group", resource_group,
        "--subscription", subscription,
        "--output", "json"
    ])
    
    if code == 0:
        search_keys = json.loads(stdout)
        keys["search_api_key"] = search_keys.get("primaryKey", "")
        print("✅ Retrieved Search API key")
    else:
        print(f"⚠️ Could not get Search key: {stderr}")
    
    # OpenAI key
    stdout, stderr, code = run_cmd([
        "az", "cognitiveservices", "account", "keys", "list",
        "--name", f"ewa-openai{env_suffix}",
        "--resource-group", resource_group,
        "--subscription", subscription,
        "--output", "json"
    ])
    
    if code == 0:
        openai_keys = json.loads(stdout)
        keys["openai_api_key"] = openai_keys.get("key1", "")
        print("✅ Retrieved OpenAI API key")
    else:
        print(f"⚠️ Could not get OpenAI key: {stderr}")
    
    # Storage key
    stdout, stderr, code = run_cmd([
        "az", "storage", "account", "keys", "list",
        "--account-name", f"ewastg{env_suffix}",
        "--resource-group", resource_group,
        "--subscription", subscription,
        "--output", "json"
    ])
    
    if code == 0:
        storage_keys = json.loads(stdout)
        if storage_keys:
            keys["storage_key"] = storage_keys[0].get("value", "")
            print("✅ Retrieved Storage key")
    else:
        print(f"⚠️ Could not get Storage key: {stderr}")
    
    # Event Grid key
    stdout, stderr, code = run_cmd([
        "az", "eventgrid", "topic", "key", "list",
        "--name", f"ewa-events{env_suffix}",
        "--resource-group", resource_group,
        "--subscription", subscription,
        "--output", "json"
    ])
    
    if code == 0:
        eg_keys = json.loads(stdout)
        keys["eventgrid_key"] = eg_keys.get("key1", "")
        print("✅ Retrieved Event Grid key")
    else:
        print(f"⚠️ Could not get Event Grid key: {stderr}")
    
    return keys


def setup_search_indexes(
    endpoint: str,
    api_key: str,
    scripts_dir: Path
):
    """Setup Azure AI Search indexes."""
    print(f"\n{'='*60}")
    print("Step 3: Setting up Azure AI Search Indexes")
    print(f"{'='*60}")
    
    # Check if azure-search-documents is installed
    result = subprocess.run(
        [sys.executable, "-c", "import azure.search.documents"],
        capture_output=True
    )
    
    if result.returncode != 0:
        print("Installing azure-search-documents...")
        run_cmd([sys.executable, "-m", "pip", "install", "azure-search-documents>=11.4.0"])
    
    # Run setup script
    stdout, stderr, code = run_cmd([
        sys.executable,
        str(scripts_dir / "setup-indexes.py"),
        "--endpoint", endpoint,
        "--api-key", api_key
    ])
    
    if code != 0:
        print(f"❌ Index setup failed: {stderr}")
        sys.exit(1)
    
    print("✅ Search indexes created")


def deploy_function_app(
    resource_group: str,
    function_name: str,
    processor_dir: Path,
    env_vars: dict,
    environment: str = ""
):
    """Deploy Azure Function."""
    print(f"\n{'='*60}")
    print("Step 4: Deploying Azure Function")
    print(f"{'='*60}")
    
    env_suffix = f"-{environment}" if environment else ""
    
    # Create local.settings.json
    local_settings = {
        "IsEncrypted": False,
        "Values": {
            "AzureWebJobsStorage": env_vars.get("storage_connection", ""),
            "FUNCTIONS_WORKER_RUNTIME": "python",
            "BLOB_CONNECTION_STRING": env_vars.get("storage_connection", ""),
            "BLOB_CONTAINER_NAME": "ewa-uploads",
            "AZURE_OPENAI_ENDPOINT": env_vars.get("openai_endpoint", ""),
            "AZURE_OPENAI_API_KEY": env_vars.get("openai_api_key", ""),
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
            "AZURE_OPENAI_VISION_DEPLOYMENT": "gpt-5.2",
            "AZURE_SEARCH_ENDPOINT": env_vars.get("search_endpoint", ""),
            "AZURE_SEARCH_API_KEY": env_vars.get("search_api_key", ""),
            "EVENTGRID_ENDPOINT": env_vars.get("eventgrid_endpoint", ""),
            "EVENTGRID_KEY": env_vars.get("eventgrid_key", "")
        }
    }
    
    settings_path = processor_dir / "local.settings.json"
    with open(settings_path, "w") as f:
        json.dump(local_settings, f, indent=2)
    
    print("✅ Created local.settings.json")
    
    # Create function app if it doesn't exist
    stdout, stderr, code = run_cmd([
        "az", "functionapp", "create",
        "--name", function_name,
        "--resource-group", resource_group,
        "--storage-account", f"ewastg{env_suffix}",
        "--consumption-plan-location", "eastus",
        "--runtime", "python",
        "--runtime-version", "3.11",
        "--functions-version", "4",
        "--output", "json"
    ])
    
    if code != 0 and "already exists" not in stderr.lower():
        print(f"⚠️ Function app creation issue: {stderr}")
    else:
        print("✅ Function app ready")
    
    # Deploy function
    print("Deploying function code...")
    stdout, stderr, code = run_cmd(
        ["func", "azure", "functionapp", "publish", function_name],
        cwd=str(processor_dir),
        capture=False
    )
    
    if code != 0:
        print(f"❌ Function deployment failed")
        sys.exit(1)
    
    print("✅ Azure Function deployed")


def deploy_mcp_server(
    resource_group: str,
    container_app_name: str,
    acr_name: str,
    mcp_server_dir: Path,
    env_vars: dict
):
    """Build and deploy MCP server to Container Apps."""
    print(f"\n{'='*60}")
    print("Step 5: Deploying MCP Server to Container Apps")
    print(f"{'='*60}")
    
    # Build Docker image
    print("Building Docker image...")
    stdout, stderr, code = run_cmd([
        "az", "acr", "build",
        "--registry", acr_name,
        "--image", "ewa-mcp:latest",
        "--file", str(mcp_server_dir / "Dockerfile"),
        str(mcp_server_dir)
    ])
    
    if code != 0:
        print(f"❌ Docker build failed: {stderr}")
        sys.exit(1)
    
    print("✅ Docker image built")
    
    # Create or update container app
    # Note: This requires the Container App to exist, which should be created by Bicep
    # Here we're just updating the image
    
    stdout, stderr, code = run_cmd([
        "az", "containerapp", "update",
        "--name", container_app_name,
        "--resource-group", resource_group,
        "--image", f"{acr_name}.azurecr.io/ewa-mcp:latest"
    ])
    
    if code != 0:
        # Try to create if update failed
        stdout, stderr, code = run_cmd([
            "az", "containerapp", "create",
            "--name", container_app_name,
            "--resource-group", resource_group,
            "--environment", f"ewa-env{env_suffix}",
            "--image", f"{acr_name}.azurecr.io/ewa-mcp:latest",
            "--target-port", "8000",
            "--ingress", "external",
            "--min-replicas", "1",
            "--max-replicas", "10"
        ])
        
        if code != 0:
            print(f"❌ Container app deployment failed: {stderr}")
            sys.exit(1)
    
    print("✅ MCP Server deployed")
    
    # Get FQDN
    stdout, stderr, code = run_cmd([
        "az", "containerapp", "show",
        "--name", container_app_name,
        "--resource-group", resource_group,
        "--query", "properties.configuration.ingress.fqdn",
        "--output", "tsv"
    ])
    
    if code == 0:
        fqdn = stdout.strip()
        print(f"✅ MCP Server URL: https://{fqdn}/mcp")
        return fqdn
    
    return None


def save_deployment_info(
    resource_group: str,
    env_vars: dict,
    fqdn: Optional[str],
    output_file: str
):
    """Save deployment information to file."""
    info = {
        "resource_group": resource_group,
        "search_endpoint": env_vars.get("search_endpoint"),
        "openai_endpoint": env_vars.get("openai_endpoint"),
        "eventgrid_endpoint": env_vars.get("eventgrid_endpoint"),
        "mcp_server_url": f"https://{fqdn}/mcp" if fqdn else None,
        "api_key": env_vars.get("api_key", "<set your API key>")
    }
    
    with open(output_file, "w") as f:
        json.dump(info, f, indent=2)
    
    print(f"\nDeployment info saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Deploy EWA MCP system to Azure"
    )
    parser.add_argument(
        "--subscription",
        required=True,
        help="Azure Subscription ID"
    )
    parser.add_argument(
        "--resource-group",
        required=True,
        help="Azure Resource Group name"
    )
    parser.add_argument(
        "--location",
        default="eastus",
        help="Azure region (default: eastus)"
    )
    parser.add_argument(
        "--environment",
        default="",
        help="Environment suffix (default: empty for cleaner names)"
    )
    parser.add_argument(
        "--person-responsible",
        required=True,
        help="Person responsible for the resources (mandatory tag)"
    )
    parser.add_argument(
        "--use-existing-openai",
        action="store_true",
        help="Use existing OpenAI deployment instead of creating new one"
    )
    parser.add_argument(
        "--openai-endpoint",
        help="Existing OpenAI endpoint (required with --use-existing-openai)"
    )
    parser.add_argument(
        "--openai-key",
        help="Existing OpenAI API key (required with --use-existing-openai)"
    )
    parser.add_argument(
        "--skip-bicep",
        action="store_true",
        help="Skip Bicep deployment (use existing resources)"
    )
    parser.add_argument(
        "--skip-indexes",
        action="store_true",
        help="Skip search index setup"
    )
    parser.add_argument(
        "--skip-function",
        action="store_true",
        help="Skip Azure Function deployment"
    )
    parser.add_argument(
        "--skip-mcp",
        action="store_true",
        help="Skip MCP server deployment"
    )
    
    args = parser.parse_args()
    
    # Validate OpenAI arguments
    if args.use_existing_openai and (not args.openai_endpoint or not args.openai_key):
        print("❌ --openai-endpoint and --openai-key are required when using --use-existing-openai")
        sys.exit(1)
    
    # Paths
    script_dir = Path(__file__).parent.absolute()
    bicep_dir = script_dir / "infrastructure" / "bicep"
    scripts_dir = script_dir / "infrastructure" / "scripts"
    processor_dir = script_dir / "processor"
    mcp_server_dir = script_dir / "mcp-server"
    
    # Check prerequisites
    check_prerequisites()
    
    # Collect all environment variables
    env_vars = {}
    
    # Step 1: Deploy Bicep
    if not args.skip_bicep:
        bicep_outputs = deploy_bicep(
            args.subscription,
            args.resource_group,
            args.location,
            args.environment,
            args.person_responsible,
            not args.use_existing_openai,  # deploy_openai
            args.openai_endpoint or "",
            args.openai_key or "",
            bicep_dir
        )
        env_vars.update(bicep_outputs)
        
        # Get resource keys (skip OpenAI if using existing)
        if not args.use_existing_openai:
            resource_keys = get_resource_keys(args.resource_group, args.subscription, args.environment)
            env_vars.update(resource_keys)
        else:
            print("\n⚡ Using existing OpenAI deployment, skipping key retrieval")
            env_vars["openai_api_key"] = args.openai_key
    else:
        print("\n⚡ Skipping Bicep deployment")
        # Load from existing or prompt
        print("Please provide the following values:")
        env_vars["search_endpoint"] = input("Search endpoint: ")
        env_vars["search_api_key"] = input("Search API key: ")
        env_vars["openai_endpoint"] = input("OpenAI endpoint: ")
        env_vars["openai_api_key"] = input("OpenAI API key: ")
        env_vars["eventgrid_endpoint"] = input("Event Grid endpoint: ")
        env_vars["eventgrid_key"] = input("Event Grid key: ")
        env_vars["storage_connection"] = input("Storage connection string: ")
    
    # Step 2: Setup Search Indexes
    if not args.skip_indexes and env_vars.get("search_endpoint") and env_vars.get("search_api_key"):
        setup_search_indexes(
            env_vars["search_endpoint"],
            env_vars["search_api_key"],
            scripts_dir
        )
    else:
        print("\n⚡ Skipping search index setup")
    
    # Step 3: Deploy Azure Function
    if not args.skip_function:
        env_suffix = f"-{args.environment}" if args.environment else ""
        function_name = f"ewa-processor{env_suffix}"
        deploy_function_app(
            args.resource_group,
            function_name,
            processor_dir,
            env_vars,
            args.environment
        )
    else:
        print("\n⚡ Skipping Azure Function deployment")
    
    # Step 4: Deploy MCP Server
    mcp_fqdn = None
    if not args.skip_mcp:
        env_suffix = f"-{args.environment}" if args.environment else ""
        env_suffix_clean = args.environment if args.environment else ""
        acr_name = f"ewaacr{env_suffix_clean}"
        container_app_name = f"ewa-mcp{env_suffix}"
        
        # Create Dockerfile if it doesn't exist
        dockerfile_path = mcp_server_dir / "Dockerfile"
        if not dockerfile_path.exists():
            dockerfile_content = '''FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
'''
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
            print("✅ Created Dockerfile")
        
        mcp_fqdn = deploy_mcp_server(
            args.resource_group,
            container_app_name,
            acr_name,
            mcp_server_dir,
            env_vars
        )
    else:
        print("\n⚡ Skipping MCP server deployment")
    
    # Save deployment info
    output_suffix = f"-{args.environment}" if args.environment else ""
    save_deployment_info(
        args.resource_group,
        env_vars,
        mcp_fqdn,
        f"deployment{output_suffix}.json"
    )
    
    print(f"\n{'='*60}")
    print("🎉 DEPLOYMENT COMPLETE!")
    print(f"{'='*60}")
    
    if mcp_fqdn:
        print(f"\nMCP Server URL: https://{mcp_fqdn}/mcp")
        print(f"Add to Claude Desktop config:")
        print(json.dumps({
            "mcpServers": {
                "ewa": {
                    "url": f"https://{mcp_fqdn}/mcp",
                    "headers": {
                        "Authorization": "Bearer <your-api-key>"
                    }
                }
            }
        }, indent=2))
    
    print(f"\nTo upload EWA PDFs:")
    print(f"  az storage blob upload --container-name ewa-uploads --file <pdf> --name <customer_id>/<filename>")
    
    print(f"\nResource Group: {args.resource_group}")
    print(f"Location: {args.location}")
    if args.environment:
        print(f"Environment: {args.environment}")


if __name__ == "__main__":
    main()
