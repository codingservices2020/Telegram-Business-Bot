# google_drive_files.py
import os
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

# ================= CONFIG =================
SCOPES = ["https://www.googleapis.com/auth/drive"]
GDRIVE_ROOT_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")

# ================= SERVICE ACCOUNT (ENV BASED) =================
SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL"),
}

# FIXED: Use from_service_account_info() instead of from_service_account_file()
credentials = Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO,
    scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=credentials)

# ================= FUNCTIONS =================

def create_folder(folder_name, parent_id=None):
    parent_id = parent_id or GDRIVE_ROOT_FOLDER_ID

    query = (
        f"name='{folder_name}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    result = drive_service.files().list(
        q=query, fields="files(id, name)"
    ).execute()

    if result["files"]:
        return result["files"][0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id] if parent_id else []
    }

    folder = drive_service.files().create(
        body=metadata, fields="id"
    ).execute()

    return folder["id"]


def upload_file(folder_id, file_path):
    media = MediaFileUpload(file_path, resumable=True)

    metadata = {
        "name": os.path.basename(file_path),
        "parents": [folder_id] if folder_id else []
    }

    file = drive_service.files().create(
        body=metadata,
        media_body=media,
        fields="id"
    ).execute()

    return file["id"]


def generate_download_link(file_id):
    drive_service.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"}
    ).execute()

    return f"https://drive.google.com/uc?id={file_id}&export=download"


def upload_and_get_link(file_path, folder_name):
    folder_id = create_folder(folder_name)
    file_id = upload_file(folder_id, file_path)
    return generate_download_link(file_id)
