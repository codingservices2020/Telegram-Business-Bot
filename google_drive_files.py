# google_drive_files.py
import os
import mimetypes
from dotenv import load_dotenv

load_dotenv()

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
def get_drive_service():
    """
    Initialize Google Drive service.
    First tries OAuth 2.0 credentials (via token.json or .env variables),
    falling back to Firebase Service Account if OAuth is not configured.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(script_dir, "token.json")

    oauth_refresh_token = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")
    oauth_client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    oauth_client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

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

    # 2. Try OAuth 2.0 credentials from .env
    if not creds and oauth_refresh_token and oauth_client_id and oauth_client_secret:
        try:
            creds = Credentials(
                token=None,
                refresh_token=oauth_refresh_token,
                token_uri=os.getenv("GOOGLE_OAUTH_TOKEN_URI", "https://oauth2.googleapis.com/token"),
                client_id=oauth_client_id,
                client_secret=oauth_client_secret,
                scopes=SCOPES
            )
            creds.refresh(Request())
            print("Google Drive: Authenticated via OAuth 2.0 environment variables")
        except Exception as e:
            print(f"Warning: Failed OAuth authentication from .env: {e}")
            creds = None

    # 3. Fallback to Service Account credentials from .env
    if not creds:
        service_account_info = {
            "type": os.getenv("FIREBASE_TYPE", "service_account"),
            "project_id": os.getenv("FIREBASE_PROJECT_ID"),
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
            "client_id": os.getenv("FIREBASE_CLIENT_ID"),
            "auth_uri": os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": os.getenv(
                "FIREBASE_AUTH_PROVIDER_CERT_URL",
                "https://www.googleapis.com/oauth2/v1/certs"
            ),
            "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL", ""),
            "universe_domain": os.getenv("FIREBASE_UNIVERSE_DOMAIN", "googleapis.com"),
        }

        required = ["project_id", "private_key_id", "private_key", "client_email", "client_id"]
        missing = [key for key in required if not service_account_info.get(key)]
        if missing:
            raise ValueError(
                "Neither valid OAuth 2.0 credentials nor complete Firebase Service Account credentials found. "
                f"Missing keys: {', '.join(missing)}"
            )

        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES
        )
        print("Google Drive: Authenticated via Service Account")

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
