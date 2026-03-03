import os
import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

endpoint = "https://ewa-search.search.windows.net"
key = os.environ.get("AZURE_SEARCH_KEY") # Removed hardcoded key
index_name = "ewa-check-overview"

client = SearchClient(endpoint=endpoint, index_name=index_name, credential=AzureKeyCredential(key))

try:
    results = client.search(
        search_text="*",
        filter="customer_id eq 'TBS' and doc_id eq 'TBS_32cccac4f856d495' and severity eq 'very_high'",
        select="severity"
    )
    count = len(list(results))
    print(f"Very High (Red) Alerts found: {count}")
    
except Exception as e:
    print(f"Error: {e}")
