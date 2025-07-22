from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
import traceback
import os
import httpx
from datetime import datetime
from dotenv import load_dotenv
from msal import ConfidentialClientApplication
from bs4 import BeautifulSoup
import pytz
import json
from filelock import FileLock

from functions.document_chunking import DocumentChunker
from functions.embedding_model import EmbeddingModelFactory
from functions.vectorstore import VectorStore
from config import CHUNKING_METHOD, EMBEDDING_MODEL_TYPE

load_dotenv()

AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")

router = APIRouter(prefix="/email", tags=["Email Webhook Processing"])

async def get_graph_api_token():
    authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    scope = ["https://graph.microsoft.com/.default"]
    app = ConfidentialClientApplication(
        client_id=AZURE_CLIENT_ID,
        authority=authority,
        client_credential=AZURE_CLIENT_SECRET,
    )
    result = app.acquire_token_silent(scopes=scope, account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=scope)
    return result.get("access_token")

async def fetch_email_from_graph_api(resource: str):
    token = await get_graph_api_token()
    if not token:
        print("[FETCH]  Auth token missing.")
        return None
    graph_url = f"https://graph.microsoft.com/v1.0/{resource}"
    params = {
        "$select": "id,subject,bodyPreview,body,from,toRecipients,ccRecipients,sentDateTime,internetMessageId,hasAttachments"
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(graph_url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[FETCH]  Error: {e}")
            traceback.print_exc()
            return None

@router.api_route("/graph-webhook", methods=["GET", "POST"])
async def handle_graph_webhook(request: Request, background_tasks: BackgroundTasks):
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        local_time = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[VALIDATION] Token received via GET: {validation_token} at {local_time} IST\n")

        return PlainTextResponse(content=validation_token, status_code=200)

    if request.method == "POST":
        try:
            body = await request.json()
            print("New email notification received:")
            print(body)
            notifications = body.get("value", [])
            for notification in notifications:
                resource = notification.get("resource", "")
                print(f"Resource: {resource}")
                background_tasks.add_task(trigger_email_processing, resource)
            return JSONResponse(content={"status": "Notification received"}, status_code=202)
        except Exception as e:
            print(f"Failed to parse JSON: {e}")
            return JSONResponse(content={"error": "Invalid JSON"}, status_code=400)

    return PlainTextResponse(status_code=405)

async def trigger_email_processing(resource: str):
    email_data = await fetch_email_from_graph_api(resource)
    if email_data:
        await process_and_store_email(email_data)
    else:
        print("[BACKGROUND]  Email not fetched.")

async def process_and_store_email(email_data: dict):
    uid = email_data.get("id")
    subject = email_data.get("subject", "No Subject")
    sender = email_data.get("from", {}).get("emailAddress", {}).get("address", "unknown")
    sender_name = email_data.get("from", {}).get("emailAddress", {}).get("name", "Unknown")
    sent_time = email_data.get("sentDateTime", "unknown")
    cc_list = [r.get("emailAddress", {}).get("address", "") for r in email_data.get("ccRecipients", [])]
    has_attachments = email_data.get("hasAttachments", False)

    html_body = email_data.get("body", {}).get("content", "")
    plain_body = BeautifulSoup(html_body, "html.parser").get_text()

    if not plain_body.strip():
        print(f"[PROCESS EMAIL]  Email {uid} has no body content. Skipping.")
        return

    print(f"[PROCESS EMAIL]  Storing {uid} from {sender} | Subject: {subject}")

    base_path = "vector_stores/email_data"
    os.makedirs(base_path, exist_ok=True)

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    temp_file_path = os.path.join(base_path, f"email_{uid}_{timestamp}.txt")
    index_path = os.path.join(base_path, "index_email.faiss")
    metadata_path = os.path.join(base_path, "metadata.json")
    metadata_lock_path = os.path.join(base_path, "metadata.json.lock")

    with open(temp_file_path, "w", encoding="utf-8") as f:
        f.write(plain_body)

    chunker = DocumentChunker(
        file_path=temp_file_path,
        method=CHUNKING_METHOD,
        source_type="email",
        accessType="private"
    )
    chunks = await chunker.chunk()

    for chunk in chunks:
        chunk["metadata"].update({
            "email_id": uid,
            "subject": subject,
            "sender": sender,
            "sender_name": sender_name,
            "timestamp": timestamp,
            "cc": cc_list,
            "hasAttachments": has_attachments
        })

    embedding_model = EmbeddingModelFactory.get_embedding_model(EMBEDDING_MODEL_TYPE)
    vector_store = VectorStore(embedding_model, EMBEDDING_MODEL_TYPE)
    vector_store.build_or_append_index(chunks, index_path)

    metadata_entry = {
        "email_id": uid,
        "subject": subject,
        "sender": sender,
        "sender_name": sender_name,
        "timestamp": timestamp,
        "cc": cc_list,
        "hasAttachments": has_attachments,
        "chunk_count": len(chunks),
        "index_path": index_path,
        "uploadDate": datetime.utcnow().isoformat()
    }

    lock = FileLock(metadata_lock_path)
    with lock:
        metadata_list = []
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as f:
                try:
                    metadata_list = json.load(f)
                except json.JSONDecodeError:
                    metadata_list = []

        if not any(m.get("email_id") == uid for m in metadata_list):
            metadata_list.append(metadata_entry)
            with open(metadata_path, "w") as f:
                json.dump(metadata_list, f, indent=4)
        else:
            print(f"[PROCESS EMAIL]  Duplicate email ID {uid} found. Skipping metadata append.")

    os.remove(temp_file_path)
    print(f"[PROCESS EMAIL]  Email {uid} stored successfully.")
