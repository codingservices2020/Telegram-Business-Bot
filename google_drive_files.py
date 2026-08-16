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

# ================= SERVICE / OAUTH CLIENT INITIALIZATION =================
def get_drive_service():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials as OAuthCredentials

    creds = None
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(script_dir, "token.json")
    creds_path = os.path.join(script_dir, "credentials.json")

    # 1. Try to load OAuth2 user credentials from environment variables (.env)
    refresh_token = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    project_id = os.getenv("GOOGLE_OAUTH_PROJECT_ID")

    if refresh_token and client_id and client_secret:
        try:
            print("Initializing Google Drive credentials from environment variables...")
            creds = OAuthCredentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES
            )
            # Refresh to fetch the active access token
            creds.refresh(Request())
            print("Google Drive credentials successfully loaded and authenticated from env variables!")
        except Exception as oauth_env_err:
            print(f"Warning: OAuth authentication from environment variables failed: {oauth_env_err}")
            creds = None

    # 2. Try to load existing OAuth2 user credentials from token.json file
    if not creds and os.path.exists(token_path):
        try:
            creds = OAuthCredentials.from_authorized_user_file(token_path, SCOPES)
            print("Loaded existing Google Drive user credentials from token.json")
        except Exception as token_err:
            print(f"Warning: Failed to load token.json: {token_err}")

    # 3. If no valid OAuth2 user credentials exist, try to authorize
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("Refreshing expired user credentials...")
                creds.refresh(Request())
                if os.path.exists(token_path):
                    with open(token_path, "w") as token:
                        token.write(creds.to_json())
            except Exception as refresh_err:
                print(f"Warning: Failed to refresh user credentials: {refresh_err}. Starting full login flow...")
                creds = None
        
        if not creds:
            flow = None
            if client_id and client_secret and project_id:
                try:
                    client_config = {
                        "installed": {
                            "client_id": client_id,
                            "project_id": project_id,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "client_secret": client_secret,
                            "redirect_uris": ["http://localhost"]
                        }
                    }
                    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                except Exception as config_err:
                    print(f"Warning: Failed to load OAuth client config from environment: {config_err}")
            
            if not flow and os.path.exists(creds_path):
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                except Exception as file_err:
                    print(f"Warning: Failed to load credentials.json file: {file_err}")

            if flow:
                try:
                    print("Prompting Google login browser for Drive authorization...")
                    creds = flow.run_local_server(port=0)
                    with open(token_path, "w") as token:
                        token.write(creds.to_json())
                    print("Drive authorization successful! Saved user credentials to token.json")
                except Exception as oauth_err:
                    print(f"Error during OAuth authentication: {oauth_err}")
            else:
                print("Warning: Neither environment OAuth variables nor credentials.json found. OAuth2 user authentication skipped.")

    # 3. If OAuth2 user credentials succeeded, build and return the service
    if creds and creds.valid:
        try:
            service = build("drive", "v3", credentials=creds)
            # Test list call
            service.files().list(pageSize=1, fields="files(id)").execute()
            return service
        except Exception as build_err:
            print(f"Warning: User credential Drive service build/test failed: {build_err}")

    # 4. Fallback: Try Firebase Service Account
    print("Trying Firebase service account as fallback...")
    info_firebase = {
        "type": "service_account",
        "project_id": os.getenv("FIREBASE_PROJECT_ID"),
        "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
        "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
        "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
        "client_id": os.getenv("FIREBASE_CLIENT_ID"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL"),
    }
    if info_firebase.get("client_email") and info_firebase.get("private_key"):
        try:
            from google.oauth2.service_account import Credentials as ServiceAccountCredentials
            creds_fb = ServiceAccountCredentials.from_service_account_info(info_firebase, scopes=SCOPES)
            service = build("drive", "v3", credentials=creds_fb)
            service.files().list(pageSize=1, fields="files(id)").execute()
            return service
        except Exception as fb_err:
            print(f"Warning: Firebase service account connect failed: {fb_err}")

    # 5. Raise exception if all authentication attempts failed
    raise Exception("All Google Drive authentication attempts failed (OAuth User credentials and Firebase Service Account credentials).")

drive_service = get_drive_service()

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
        q=query, 
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()

    if result["files"]:
        return result["files"][0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id] if parent_id else []
    }

    folder = drive_service.files().create(
        body=metadata, 
        fields="id",
        supportsAllDrives=True
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
        fields="id",
        supportsAllDrives=True
    ).execute()

    return file["id"]


def generate_download_link(file_id):
    drive_service.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
        supportsAllDrives=True
    ).execute()

    return f"https://drive.google.com/uc?id={file_id}&export=download"


def upload_to_free_host(file_path):
    import requests
    # 1. Try Catbox (Permanent file hosting)
    try:
        url = "https://catbox.moe/user/api.php"
        with open(file_path, "rb") as f:
            data = {"reqtype": "fileupload"}
            files = {"fileToUpload": f}
            response = requests.post(url, data=data, files=files, timeout=60)
        if response.status_code == 200:
            direct_url = response.text.strip()
            if direct_url.startswith("https://"):
                print(f"Fallback Upload to Catbox success: {direct_url}")
                return direct_url
    except Exception as e:
        print(f"Catbox upload fallback failed: {e}")
        
    # 2. Try Tmpfiles (Direct link, expires in 60 mins)
    try:
        url = "https://tmpfiles.org/api/v1/upload"
        with open(file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(url, files=files, timeout=30)
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get("status") == "success":
                upload_url = res_data["data"]["url"]
                download_url = upload_url.replace("https://tmpfiles.org/", "https://tmpfiles.org/dl/")
                print(f"Fallback Upload to Tmpfiles success: {download_url}")
                return download_url
    except Exception as e:
        print(f"Tmpfiles upload fallback failed: {e}")
        
    raise Exception("Both Google Drive upload and fallback file hosts (Catbox, Tmpfiles) failed.")


def upload_and_get_link(file_path, folder_name):
    try:
        folder_id = create_folder(folder_name)
        file_id = upload_file(folder_id, file_path)
        return generate_download_link(file_id)
    except Exception as e:
        print(f"Warning: Google Drive upload failed: {e}. Falling back to anonymous hosting...")
        return upload_to_free_host(file_path)
