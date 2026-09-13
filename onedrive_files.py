# onedrive_files.py
import os
import time
import mimetypes
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

logger = logging.getLogger(__name__)

# ============================================================
# ONEDRIVE (MICROSOFT GRAPH) SETTINGS
# ============================================================

def clean_env(val):
    """Strip whitespace and surrounding quotes from environment variable values."""
    if not val:
        return ""
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()
    return val

def reload_env_if_needed():
    """Reload environment variables if any are empty."""
    global AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, ONEDRIVE_USER_EMAIL, ONEDRIVE_ROOT_FOLDER
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    if not AZURE_TENANT_ID:
        AZURE_TENANT_ID = clean_env(os.getenv("AZURE_TENANT_ID"))
    if not AZURE_CLIENT_ID:
        AZURE_CLIENT_ID = clean_env(os.getenv("AZURE_CLIENT_ID"))
    if not AZURE_CLIENT_SECRET:
        AZURE_CLIENT_SECRET = clean_env(os.getenv("AZURE_CLIENT_SECRET"))
    if not ONEDRIVE_USER_EMAIL:
        ONEDRIVE_USER_EMAIL = clean_env(os.getenv("ONEDRIVE_USER_EMAIL"))
    if not ONEDRIVE_ROOT_FOLDER:
        ONEDRIVE_ROOT_FOLDER = clean_env(os.getenv("ONEDRIVE_ROOT_FOLDER")) or "TelegramBotReports"

AZURE_TENANT_ID = clean_env(os.getenv("AZURE_TENANT_ID"))
AZURE_CLIENT_ID = clean_env(os.getenv("AZURE_CLIENT_ID"))
AZURE_CLIENT_SECRET = clean_env(os.getenv("AZURE_CLIENT_SECRET"))
ONEDRIVE_USER_EMAIL = clean_env(os.getenv("ONEDRIVE_USER_EMAIL"))
ONEDRIVE_ROOT_FOLDER = clean_env(os.getenv("ONEDRIVE_ROOT_FOLDER")) or "TelegramBotReports"

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# In-memory token cache
_cached_token = None
_token_expires_at = 0


# ================= AUTHENTICATION =================

def get_access_token():
    """
    Acquire Microsoft Graph OAuth 2.0 access token using Client Credentials.
    Tries msal if available, falling back to direct HTTP request.
    Caches token in memory until 60 seconds before expiration.
    """
    global _cached_token, _token_expires_at

    # Return cached token if still valid
    if _cached_token and time.time() < (_token_expires_at - 60):
        return _cached_token

    if not AZURE_TENANT_ID or not AZURE_CLIENT_ID or not AZURE_CLIENT_SECRET:
        reload_env_if_needed()

    if not AZURE_TENANT_ID or not AZURE_CLIENT_ID or not AZURE_CLIENT_SECRET:
        raise ValueError(
            "Missing Microsoft Entra ID credentials in .env.\n"
            "Please ensure AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET are set."
        )

    # 1. Try MSAL library if available
    try:
        import msal
        app = msal.ConfidentialClientApplication(
            client_id=AZURE_CLIENT_ID,
            client_credential=AZURE_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
        )
        result = app.acquire_token_silent(scopes=["https://graph.microsoft.com/.default"], account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" in result:
            _cached_token = result["access_token"]
            expires_in = result.get("expires_in", 3600)
            _token_expires_at = time.time() + expires_in
            return _cached_token
        else:
            err_desc = result.get("error_description") or result.get("error")
            raise RuntimeError(f"MSAL authentication failed: {err_desc}")
    except ImportError:
        pass  # Fall back to standard requests below

    # 2. Fallback: Direct OAuth2 POST request
    token_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token"
    payload = {
        "client_id": AZURE_CLIENT_ID,
        "client_secret": AZURE_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    resp = requests.post(token_url, data=payload, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Microsoft Graph token request failed [{resp.status_code}]: {resp.text}"
        )

    data = resp.json()
    _cached_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    _token_expires_at = time.time() + expires_in
    return _cached_token


def _get_headers(content_type="application/json"):
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}"
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _get_drive_endpoint():
    """Returns the base drive endpoint for the configured user."""
    if not ONEDRIVE_USER_EMAIL:
        reload_env_if_needed()

    if not ONEDRIVE_USER_EMAIL:
        raise ValueError(
            "ONEDRIVE_USER_EMAIL is missing in .env.\n"
            "Please specify the user email whose OneDrive will store the reports."
        )
    return f"{GRAPH_BASE_URL}/users/{ONEDRIVE_USER_EMAIL}/drive"


# ================= FOLDER MANAGEMENT =================

def get_root_folder_id():
    """
    Get or create the top-level folder (e.g. 'TelegramBotReports') in OneDrive root.
    """
    drive_url = _get_drive_endpoint()
    headers = _get_headers()

    # 1. Try direct path lookup
    url = f"{drive_url}/root:/{ONEDRIVE_ROOT_FOLDER}"
    resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code == 200:
        return resp.json()["id"]

    # 2. Check root children manually without relying on OData $filter
    list_url = f"{drive_url}/root/children"
    list_resp = requests.get(list_url, headers=headers, timeout=20)
    if list_resp.status_code == 200:
        for item in list_resp.json().get("value", []):
            if item.get("name") == ONEDRIVE_ROOT_FOLDER and "folder" in item:
                return item["id"]

    # 3. Create root folder if not found
    create_url = f"{drive_url}/root/children"
    payload = {
        "name": ONEDRIVE_ROOT_FOLDER,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "rename"
    }
    create_resp = requests.post(create_url, headers=headers, json=payload, timeout=20)
    if create_resp.status_code in (200, 201):
        folder_info = create_resp.json()
        print(f"Created OneDrive root folder: {folder_info.get('name')} ({folder_info.get('id')})")
        return folder_info["id"]

    raise RuntimeError(f"Failed to create root folder '{ONEDRIVE_ROOT_FOLDER}': {create_resp.text}")


def find_folder(folder_name, parent_id):
    """Find an existing folder inside parent_id."""
    drive_url = _get_drive_endpoint()
    headers = _get_headers()

    # 1. Try direct item path lookup
    url = f"{drive_url}/items/{parent_id}:/{folder_name}"
    resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code == 200:
        return resp.json()["id"]

    # 2. Check parent's children manually
    list_url = f"{drive_url}/items/{parent_id}/children"
    list_resp = requests.get(list_url, headers=headers, timeout=20)
    if list_resp.status_code == 200:
        for item in list_resp.json().get("value", []):
            if item.get("name") == folder_name and "folder" in item:
                return item["id"]

    return None


def create_folder(folder_name, parent_id):
    """Create a folder inside parent_id."""
    drive_url = _get_drive_endpoint()
    headers = _get_headers()

    url = f"{drive_url}/items/{parent_id}/children"
    payload = {
        "name": folder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "rename"
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=20)
    if resp.status_code in (200, 201):
        folder = resp.json()
        print(f"Created OneDrive folder: {folder.get('name')} ({folder.get('id')})")
        return folder["id"]

    raise RuntimeError(f"Failed to create folder '{folder_name}': {resp.text}")


def get_or_create_folder(folder_name):
    """Return existing folder under the root reports folder or create it."""
    root_id = get_root_folder_id()
    folder_id = find_folder(folder_name, root_id)
    if folder_id:
        print(f"Using existing OneDrive folder: {folder_name} ({folder_id})")
        return folder_id

    return create_folder(folder_name, root_id)


# ================= FILE UPLOADS =================

def upload_file(folder_id, file_path):
    """
    Upload a file to OneDrive under folder_id.
    Uses simple PUT upload for files <= 4MB, and upload session for larger files.
    """
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    drive_url = _get_drive_endpoint()

    print("=" * 60)
    print("MICROSOFT ONEDRIVE UPLOAD")
    print(f"File: {file_path} ({file_size} bytes)")
    print(f"Folder ID: {folder_id}")
    print("=" * 60)

    # 1. Simple upload (files <= 4MB)
    if file_size <= 4 * 1024 * 1024:
        upload_url = f"{drive_url}/items/{folder_id}:/{file_name}:/content"
        headers = _get_headers(content_type=mime_type)

        with open(file_path, "rb") as f:
            resp = requests.put(upload_url, headers=headers, data=f, timeout=60)

        if resp.status_code in (200, 201):
            item = resp.json()
            print(f"Upload successful: {item.get('name')} ({item.get('id')})")
            return item["id"]

        raise RuntimeError(f"Simple upload failed [{resp.status_code}]: {resp.text}")

    # 2. Resumable Upload Session (files > 4MB)
    session_url = f"{drive_url}/items/{folder_id}:/{file_name}:/createUploadSession"
    session_headers = _get_headers()
    session_payload = {
        "item": {
            "@microsoft.graph.conflictBehavior": "replace",
            "name": file_name
        }
    }
    session_resp = requests.post(session_url, headers=session_headers, json=session_payload, timeout=30)
    if session_resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create upload session [{session_resp.status_code}]: {session_resp.text}")

    upload_url = session_resp.json()["uploadUrl"]
    chunk_size = 320 * 1024 * 10  # 3.2 MB chunks (must be multiple of 320 KiB)

    with open(file_path, "rb") as f:
        start = 0
        while start < file_size:
            chunk = f.read(chunk_size)
            end = start + len(chunk) - 1
            chunk_headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{file_size}"
            }
            chunk_resp = requests.put(upload_url, headers=chunk_headers, data=chunk, timeout=60)

            if chunk_resp.status_code in (200, 201):
                item = chunk_resp.json()
                print(f"Large file upload successful: {item.get('name')} ({item.get('id')})")
                return item["id"]
            elif chunk_resp.status_code != 202:
                raise RuntimeError(f"Chunk upload failed [{chunk_resp.status_code}]: {chunk_resp.text}")

            start = end + 1

    raise RuntimeError("Upload session ended without completion response.")


# ================= LINK GENERATION =================

def generate_download_link(item_id):
    """
    Generate an anonymous, shareable direct-download link for the file.
    Uses Microsoft Graph createLink API and adds direct-download parameters.
    """
    drive_url = _get_drive_endpoint()
    headers = _get_headers()

    # 1. Try creating an anonymous view link
    link_url = f"{drive_url}/items/{item_id}/createLink"
    payload = {
        "type": "view",
        "scope": "anonymous"
    }

    resp = requests.post(link_url, headers=headers, json=payload, timeout=20)
    if resp.status_code in (200, 201):
        link_data = resp.json()
        raw_url = link_data.get("link", {}).get("webUrl")
        if raw_url:
            # Ensure direct download query parameter
            separator = "&" if "?" in raw_url else "?"
            download_url = f"{raw_url}{separator}download=1"
            return download_url

    # 2. Fallback: If tenant blocks anonymous links, try organization link or webUrl
    print(f"Notice: Anonymous link creation returned status {resp.status_code}. Attempting fallback...")
    item_url = f"{drive_url}/items/{item_id}?$select=id,name,webUrl,@microsoft.graph.downloadUrl"
    item_resp = requests.get(item_url, headers=headers, timeout=20)
    if item_resp.status_code == 200:
        item_data = item_resp.json()
        direct_url = item_data.get("@microsoft.graph.downloadUrl")
        if direct_url:
            return direct_url
        web_url = item_data.get("webUrl")
        if web_url:
            separator = "&" if "?" in web_url else "?"
            return f"{web_url}{separator}download=1"

    raise RuntimeError(f"Could not generate sharing link for item {item_id}: {resp.text}")


# ================= MAIN ENTRY POINT =================

def upload_and_get_link(file_path, folder_name):
    """
    Upload report to OneDrive and return direct download link.
    Drop-in replacement for google_drive_files.upload_and_get_link.
    """
    try:
        folder_id = get_or_create_folder(folder_name)
        file_id = upload_file(folder_id, file_path)
        link = generate_download_link(file_id)
        print(f"OneDrive download link: {link}")
        return link

    except Exception as e:
        print("=" * 60)
        print("ONEDRIVE UPLOAD FAILED")
        print(f"Error type: {type(e).__name__}")
        print(f"Error: {e}")
        print("=" * 60)
        raise


def upload_private_file(file_path, folder_name):
    """
    Upload report to OneDrive privately without creating anonymous sharing links.
    Returns:
        dict: {"file_id": item_id, "file_name": file_name, "provider": "onedrive"}
    """
    folder_id = get_or_create_folder(folder_name)
    file_id = upload_file(folder_id, file_path)
    file_name = os.path.basename(file_path)
    return {
        "file_id": file_id,
        "file_name": file_name,
        "provider": "onedrive"
    }


def download_file_bytes(item_id):
    """
    Download raw file bytes from OneDrive using Microsoft Graph API.
    """
    drive_url = _get_drive_endpoint()
    download_url = f"{drive_url}/items/{item_id}/content"
    resp = requests.get(download_url, headers=_get_headers(), timeout=60)
    if resp.status_code == 200:
        return resp.content
    raise RuntimeError(f"Failed to download OneDrive item {item_id} [{resp.status_code}]: {resp.text}")



# ================= STANDALONE DIAGNOSTIC TEST =================

def test_connection():
    """Verify Microsoft Graph credentials and OneDrive functionality."""
    print("\n🔍 Running Microsoft OneDrive Connection Test...")
    print(f"- Tenant ID: {AZURE_TENANT_ID[:6]}...{AZURE_TENANT_ID[-4:] if AZURE_TENANT_ID else 'MISSING'}")
    print(f"- Client ID: {AZURE_CLIENT_ID[:6]}...{AZURE_CLIENT_ID[-4:] if AZURE_CLIENT_ID else 'MISSING'}")
    print(f"- User Email: {ONEDRIVE_USER_EMAIL or 'MISSING'}")
    print(f"- Root Folder: {ONEDRIVE_ROOT_FOLDER}")

    # 1. Test Token
    print("\n1️⃣ Requesting OAuth token...")
    token = get_access_token()
    print("✅ Token acquired successfully!")

    # 2. Test User Drive Access
    print("\n2️⃣ Checking OneDrive access for user...")
    drive_url = _get_drive_endpoint()
    resp = requests.get(drive_url, headers=_get_headers(), timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"Drive access failed [{resp.status_code}]: {resp.text}")
    drive_data = resp.json()
    print(f"✅ OneDrive accessible! Drive Type: {drive_data.get('driveType')}, ID: {drive_data.get('id')}")

    # 3. Test Root Folder
    print("\n3️⃣ Verifying root folder...")
    root_id = get_root_folder_id()
    print(f"✅ Root folder verified (ID: {root_id})")

    # 4. Test File Upload & Link
    print("\n4️⃣ Testing temporary file upload & link generation...")
    test_file = "onedrive_test.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("Telegram Bot OneDrive Connection Test - OK")

    try:
        test_link = upload_and_get_link(test_file, "Diagnostic_Test")
        print(f"✅ Upload successful! Link: {test_link}")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

    print("\n🎉 ALL TESTS PASSED! OneDrive is fully configured and ready for the bot.")


if __name__ == "__main__":
    test_connection()
