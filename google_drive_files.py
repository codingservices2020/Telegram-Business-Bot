# google_drive_files.py
import os
import mimetypes
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

# ============================================================
# GOOGLE DRIVE SETTINGS
# ============================================================

ROOT_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
SHARED_DRIVE_ID = os.getenv("GDRIVE_SHARED_DRIVE_ID")

if not ROOT_FOLDER_ID:
    raise ValueError("GDRIVE_FOLDER_ID is missing from .env")


# ================= GOOGLE DRIVE INITIALIZATION =================
def clean_env(val):
    """Strip whitespace and surrounding quotes from environment variable values."""
    if not val:
        return ""
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()
    return val


# ================= GOOGLE DRIVE INITIALIZATION =================
def get_drive_service():
    """
    Initialize Google Drive service.
    First tries OAuth 2.0 credentials (via token.json, GOOGLE_TOKEN_JSON, or .env variables),
    falling back to Firebase Service Account if OAuth is not configured.
    """
    import json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(script_dir, "token.json")

    oauth_refresh_token = clean_env(os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN"))
    oauth_client_id = clean_env(os.getenv("GOOGLE_OAUTH_CLIENT_ID"))
    oauth_client_secret = clean_env(os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"))
    google_token_json = clean_env(os.getenv("GOOGLE_TOKEN_JSON"))

    creds = None

    # 1. Try OAuth 2.0 credentials from token.json
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, scopes=SCOPES)
            if creds and not creds.valid:
                if creds.refresh_token:
                    creds.refresh(Request())
                    with open(token_path, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
            print("Google Drive: Loaded credentials from token.json")
        except Exception as e:
            print(f"Warning: Failed loading token.json: {e}")
            creds = None

    # 2. Try OAuth 2.0 from raw GOOGLE_TOKEN_JSON environment variable
    if not creds and google_token_json:
        try:
            token_data = json.loads(google_token_json)
            creds = Credentials.from_authorized_user_info(token_data, scopes=SCOPES)
            if creds and not creds.valid and creds.refresh_token:
                creds.refresh(Request())
            print("Google Drive: Authenticated via GOOGLE_TOKEN_JSON environment variable")
        except Exception as e:
            print(f"Warning: Failed loading GOOGLE_TOKEN_JSON: {e}")
            creds = None

    # 3. Try OAuth 2.0 credentials from environment variables
    if not creds and oauth_refresh_token and oauth_client_id and oauth_client_secret:
        try:
            token_uri = clean_env(os.getenv("GOOGLE_OAUTH_TOKEN_URI")) or "https://oauth2.googleapis.com/token"
            creds = Credentials(
                token=None,
                refresh_token=oauth_refresh_token,
                token_uri=token_uri,
                client_id=oauth_client_id,
                client_secret=oauth_client_secret,
                scopes=SCOPES
            )
            creds.refresh(Request())
            print("Google Drive: Authenticated via OAuth 2.0 environment variables")
        except Exception as e:
            raise RuntimeError(
                f"Google Drive OAuth authentication failed from environment variables: {e}.\n"
                "Please verify that GOOGLE_OAUTH_REFRESH_TOKEN, GOOGLE_OAUTH_CLIENT_ID, and "
                "GOOGLE_OAUTH_CLIENT_SECRET are set correctly in Render without surrounding quotes."
            ) from e

    # 4. If no OAuth credentials were found, fail fast with a clear error message
    if not creds:
        raise RuntimeError(
            "❌ Google Drive authentication failed: No valid OAuth 2.0 user credentials found.\n\n"
            "Personal Google Drive accounts require OAuth 2.0 user credentials to upload files "
            "(Firebase Service Accounts have 0 storage quota and will fail with HttpError 403).\n\n"
            "To fix this, please ensure one of the following is configured:\n"
            "1. token.json is present in the project directory, OR\n"
            "2. GOOGLE_TOKEN_JSON environment variable contains the contents of token.json, OR\n"
            "3. GOOGLE_OAUTH_REFRESH_TOKEN, GOOGLE_OAUTH_CLIENT_ID, and GOOGLE_OAUTH_CLIENT_SECRET are set in your environment variables."
        )

    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        # Verify access to the configured root folder
        folder_info = service.files().get(
            fileId=ROOT_FOLDER_ID,
            supportsAllDrives=True,
            fields="id,name"
        ).execute()

        print("Google Drive authentication successful!")
        print(f"Target Root Folder: {folder_info.get('name')} ({ROOT_FOLDER_ID})")
        return service

    except Exception as e:
        print(f"Google Drive initialization failed: {e}")
        raise


# Initialize Google Drive once when this module is imported.
drive_service = get_drive_service()


# ================= FUNCTIONS =================

def create_folder(folder_name, parent_id=ROOT_FOLDER_ID):
    """Create a folder inside Google Drive under parent_id."""
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }

    folder = drive_service.files().create(
        body=metadata,
        fields="id,name",
        supportsAllDrives=True
    ).execute()

    print(f"Created Google Drive folder: {folder['name']} ({folder['id']})")
    return folder["id"]


def find_folder(folder_name, parent_id=ROOT_FOLDER_ID):
    """Find an existing folder inside parent_id."""
    query = (
        f"name = '{folder_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents "
        f"and trashed = false"
    )

    response = drive_service.files().list(
        q=query,
        spaces="drive",
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()

    folders = response.get("files", [])
    if folders:
        return folders[0]["id"]
    return None


def get_or_create_folder(folder_name):
    """Return existing folder or create it."""
    folder_id = find_folder(folder_name)
    if folder_id:
        print(f"Using existing folder: {folder_name} ({folder_id})")
        return folder_id

    return create_folder(folder_name)


def upload_file(folder_id, file_path):
    """Upload a file to Google Drive under folder_id."""
    file_name = os.path.basename(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)

    if not mime_type:
        mime_type = "application/octet-stream"

    metadata = {
        "name": file_name,
        "parents": [folder_id]
    }

    media = MediaFileUpload(
        file_path,
        mimetype=mime_type,
        resumable=True
    )

    print("=" * 60)
    print("GOOGLE DRIVE UPLOAD")
    print(f"File: {file_path}")
    print(f"Folder ID: {folder_id}")
    print("=" * 60)

    file = drive_service.files().create(
        body=metadata,
        media_body=media,
        fields="id,name,webViewLink",
        supportsAllDrives=True
    ).execute()

    print(f"Upload successful: {file['name']} ({file['id']})")
    return file["id"]


def generate_download_link(file_id):
    """Make file accessible via link and return direct download URL."""
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            supportsAllDrives=True
        ).execute()
    except Exception as e:
        print(f"Warning: Could not set public permission on {file_id}: {e}")

    return f"https://drive.google.com/uc?export=download&id={file_id}"


def upload_and_get_link(file_path, folder_name):
    """Upload report to Google Drive and return direct download link."""
    try:
        folder_id = get_or_create_folder(folder_name)
        file_id = upload_file(folder_id, file_path)
        link = generate_download_link(file_id)
        print(f"Google Drive link: {link}")
        return link

    except Exception as e:
        print("=" * 60)
        print("GOOGLE DRIVE UPLOAD FAILED")
        print(f"Error type: {type(e).__name__}")
        print(f"Error: {e}")
        print("=" * 60)
        raise


def upload_private_file(file_path, folder_name):
    """
    Upload report to Google Drive privately without creating public sharing links.
    Returns:
        dict: {"file_id": file_id, "file_name": file_name, "provider": "google_drive"}
    """
    folder_id = get_or_create_folder(folder_name)
    file_id = upload_file(folder_id, file_path)
    file_name = os.path.basename(file_path)
    return {
        "file_id": file_id,
        "file_name": file_name,
        "provider": "google_drive"
    }


def download_file_bytes(file_id):
    """
    Download raw file bytes from Google Drive using the authenticated service.
    """
    return drive_service.files().get_media(fileId=file_id).execute()
