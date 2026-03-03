import json
import os
import subprocess

with open(r'c:\GenAI\ewa-mcp\processor\local.settings.json') as f:
    settings = json.load(f)['Values']

# Note: The tool uses args --endpoint and --api-key
endpoint = settings['AZURE_SEARCH_ENDPOINT']
api_key = settings['AZURE_SEARCH_API_KEY']

cmd = [
    "python", 
    r"c:\GenAI\ewa-mcp\infrastructure\scripts\setup-indexes.py",
    "--endpoint", endpoint,
    "--api-key", api_key,
    "--delete-existing"
]

print("Running command:", " ".join([c if c != api_key else "********" for c in cmd]))
subprocess.run(cmd)
