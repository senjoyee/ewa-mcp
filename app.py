import streamlit as st
import os
import time
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv

load_dotenv()  # Load from .env file if present

st.set_page_config(page_title="EWA Document Upload", page_icon="📄", layout="wide")

# Configuration — read from environment variables (never hardcode credentials)
BLOB_CONNECTION_STRING = os.environ["BLOB_CONNECTION_STRING"]
CONTAINER_NAME = os.environ.get("BLOB_CONTAINER_NAME", "ewa-uploads")
SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_API_KEY = os.environ["AZURE_SEARCH_API_KEY"]
DOCS_INDEX = os.environ.get("INDEX_DOCS", "ewa-docs")

st.title("📄 EWA Document Upload")
st.markdown("""
Upload SAP EarlyWatch Alert PDF reports here. Once uploaded, the Document Processor (Azure Function) will automatically:
1. Extract text and images
2. Use Kimi-K2.5 to find alerts in priority tables
3. Chunk and embed the document
4. Index everything into Azure AI Search for the MCP server
""")

# Setup clients
@st.cache_resource
def get_blob_client():
    return BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)

@st.cache_resource
def get_search_client():
    credential = AzureKeyCredential(SEARCH_API_KEY)
    return SearchClient(endpoint=SEARCH_ENDPOINT, index_name=DOCS_INDEX, credential=credential)

blob_service_client = get_blob_client()
search_client = get_search_client()

# Upload Section
st.header("1. Upload Report")
col1, col2 = st.columns([1, 2])

with col1:
    customer_id = st.text_input("Customer ID", value="CUST-001")

with col2:
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None and customer_id:
    if st.button("Upload & Process", type="primary"):
        with st.spinner("Uploading to Azure Blob Storage..."):
            try:
                # Create blob path: ewa-uploads/{customer_id}/{filename}
                blob_name = f"{customer_id}/{uploaded_file.name}"
                blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
                
                # Upload the file
                blob_client.upload_blob(uploaded_file, overwrite=True)
                st.success(f"Successfully uploaded: {uploaded_file.name}")
                
                # Set session state to start polling
                st.session_state['polling_file'] = uploaded_file.name
                st.session_state['polling_customer'] = customer_id
                st.session_state['upload_time'] = datetime.now()
                
            except Exception as e:
                st.error(f"Upload failed: {str(e)}")

# Status Polling Section
st.header("2. Processing Status")

if 'polling_file' in st.session_state:
    file_name = st.session_state['polling_file']
    cust_id = st.session_state['polling_customer']
    blob_name = f"{cust_id}/{file_name}"
    
    st.info(f"Tracking status for: **{file_name}** (Customer: {cust_id})")
    
    status_placeholder = st.empty()
    progress_bar = st.progress(0)
    
    # Simple polling loop
    if st.button("Refresh Status"):
        pass # Streamlit will rerun the script
        
    try:
        blob_exists = False
        try:
            debug_blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
            blob_exists = debug_blob_client.exists()
        except Exception as blob_exc:
            st.caption(f"Blob check warning: {blob_exc}")

        # Query Azure AI Search for this specific document
        # Wait a few seconds for the function to start and index the initial metadata
        time.sleep(2)
        
        # Search for the document.
        # file_name is neither searchable nor filterable in the current index schema,
        # so fetch latest docs for the customer and match filename client-side.
        results = search_client.search(
            search_text="*",
            filter=f"customer_id eq '{cust_id}'",
            order_by=["report_date desc"],
            top=20
        )

        # Narrow to exact filename client-side and take most recent doc_id
        customer_docs = list(results)
        docs = [d for d in customer_docs if d.get("file_name") == file_name]
        docs.sort(key=lambda d: d.get("doc_id", ""), reverse=True)

        with st.expander("Debug diagnostics", expanded=True):
            st.write(f"- Blob path: `{blob_name}`")
            st.write(f"- Blob exists: `{blob_exists}`")
            st.write(f"- Docs found for customer (top 20 scan): `{len(customer_docs)}`")
            st.write(f"- Docs matching filename: `{len(docs)}`")

        if not docs:
            status_placeholder.warning("⏳ Waiting for Azure Function to start processing... (Document not yet in search index)")
            progress_bar.progress(10)
            if blob_exists:
                st.warning("Blob upload succeeded but document metadata is not in search yet. This usually means the blob-triggered Function did not run or failed before indexing the document metadata.")
            else:
                st.warning("Blob was not found at expected path. Upload may have failed or used a different storage account/container.")
        else:
            doc = docs[0]
            status = doc.get("processing_status", "unknown")
            alerts = doc.get("alert_count", 0)
            doc_id = doc.get("doc_id", "unknown")
            
            if status in {"started", "processing", "extracting", "chunking", "embedding", "indexing"}:
                status_placeholder.info(f"🔄 **Processing In Progress** (Status: {status}) | Doc ID: {doc_id}")
                progress_bar.progress(50)
                # Auto-refresh suggestion
                st.markdown("*Click 'Refresh Status' above to check again.*")
                
            elif status == "completed":
                status_placeholder.success(f"✅ **Processing Complete!**")
                progress_bar.progress(100)
                st.balloons()
                
                st.subheader("Results summary:")
                st.write(f"- **Document ID:** `{doc_id}`")
                st.write(f"- **SAP System ID (SID):** `{doc.get('sid', 'N/A')}`")
                st.write(f"- **Alerts Extracted:** `{alerts}`")
                
                # Clear polling state
                if st.button("Clear tracking"):
                    del st.session_state['polling_file']
                    st.rerun()
                    
            elif status == "failed":
                status_placeholder.error(f"❌ **Processing Failed!** Check Azure Function logs for details.")
                progress_bar.progress(100)
                
    except Exception as e:
        status_placeholder.warning(f"Waiting for index to initialize: {str(e)}")

# View All Documents Section
st.header("3. All Processed Documents")
if st.button("Load Documents Database"):
    try:
        results = search_client.search(
            search_text="*",
            select="doc_id,customer_id,sid,file_name,processing_status,alert_count,report_date",
            order_by="report_date desc"
        )
        
        docs = list(results)
        if docs:
            st.dataframe(docs)
        else:
            st.info("No documents found in the index yet.")
    except Exception as e:
        st.error(f"Failed to query search index: {str(e)}")
