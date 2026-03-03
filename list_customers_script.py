import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv

load_dotenv()

endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
key = os.environ.get("AZURE_SEARCH_API_KEY")
index_name = os.environ.get("INDEX_DOCS", "ewa-docs")

if not endpoint or not key:
    print("Environment variables AZURE_SEARCH_ENDPOINT or AZURE_SEARCH_API_KEY not set.")
    exit(1)

client = SearchClient(endpoint=endpoint, index_name=index_name, credential=AzureKeyCredential(key))

try:
    results = client.search(search_text="*", select="customer_id")
    customers = set()
    for result in results:
        customers.add(result["customer_id"])
    
    if not customers:
        print("No customers found.")
    else:
        print("Available Customers:")
        for customer in sorted(list(customers)):
            print(f"- {customer}")
except Exception as e:
    print(f"Error: {e}")
