import sys
import os
from pathlib import Path
from pcloud_client import PyCloud

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

PCLOUD_EMAIL = os.getenv("PCLOUD_EMAIL")
PCLOUD_PASSWORD = os.getenv("PCLOUD_PASSWORD")
PCLOUD_ROOT_FOLDER = os.getenv("PCLOUD_ROOT_FOLDER") or "Telegram-Bot-Reports"

_pc_client = None

def get_pcloud_client():
    global _pc_client
    if _pc_client is None:
        email = os.getenv("PCLOUD_EMAIL")
        password = os.getenv("PCLOUD_PASSWORD")
        if not email or not password:
            load_dotenv(dotenv_path=ENV_PATH, override=True)
            email = os.getenv("PCLOUD_EMAIL")
            password = os.getenv("PCLOUD_PASSWORD")
        _pc_client = PyCloud(email, password)
    return _pc_client



# 1. List all files/folders in root
def list_root():
    print("📂 Files in your root folder:")
    client = get_pcloud_client()
    result = client.listfolder(folderid=0)
    files = result.get('metadata', {}).get('contents', [])
    for item in files:
        if not item.get('isfolder'):
            print(f" - {item['name']} (fileid: {item['fileid']})")
        else:
            print(f" 📁 {item['name']} (folder)")
    return files


# 2. Create folder (or return existing)
def create_folder(folder_name):
    """
    Creates a folder in pCloud (or returns the existing folder ID).
    Supports nested paths like '/Telegram-Bot-Reports/John Doe (123456)'
    and creates parent directories automatically.
    """
    client = get_pcloud_client()
    folder_path = folder_name if folder_name.startswith('/') else f"/{folder_name}"
    
    # Try direct creation first
    response = client.createfolder(path=folder_path)
    if response.get('result') == 0 and 'metadata' in response:
        folder_id = response['metadata']['folderid']
        print(f"📁 Folder created: {folder_path} (ID: {folder_id})")
        return folder_id

    elif response.get('result') == 2004:  # Folder already exists
        list_resp = client.listfolder(path=folder_path)
        if list_resp.get("result") == 0 and "metadata" in list_resp:
            folder_id = list_resp['metadata']['folderid']
            print(f"📁 Folder already exists: {folder_path} (ID: {folder_id})")
            return folder_id

    # Handle missing parent components (2002 / 2005) or any nested path creation
    parts = [p.strip() for p in folder_path.strip('/').split('/') if p.strip()]
    curr_id = 0
    current_acc_path = ""
    for part in parts:
        current_acc_path += f"/{part}"
        res = client.createfolder(path=current_acc_path)
        if res.get('result') == 0 and 'metadata' in res:
            curr_id = res['metadata']['folderid']
            print(f"📁 Created folder segment: {current_acc_path} (ID: {curr_id})")
        elif res.get('result') == 2004:  # Already exists
            list_res = client.listfolder(path=current_acc_path)
            if list_res.get('result') == 0 and 'metadata' in list_res:
                curr_id = list_res['metadata']['folderid']
            else:
                raise Exception(f"❌ Failed to inspect existing segment '{current_acc_path}': {list_res}")
        else:
            raise Exception(f"❌ Failed to create folder segment '{current_acc_path}': {res}")

    return curr_id



# 3. Upload file to a folder
def upload_file(folder_id, local_file_path):
    if not os.path.exists(local_file_path):
        raise FileNotFoundError(f"Local file not found: {local_file_path}")

    client = get_pcloud_client()
    result = client.uploadfile(files=[local_file_path], folderid=folder_id)
    if result.get('result') == 0 and 'metadata' in result and len(result['metadata']) > 0:
        file_info = result['metadata'][0]
        print(f"✅ Uploaded: {file_info['name']} (fileid: {file_info['fileid']})")
        return file_info['fileid']
    else:
        raise Exception(f"❌ Failed to upload file: {result}")


# 4. Generate public + short link
def generate_share_link(file_id):
    client = get_pcloud_client()
    data = client.getfilepublink(fileid=file_id, shortlink=1)
    if data.get("result") == 0:
        link = data.get("link")
        linkid = data.get("linkid")
        shortlink = data.get("shortlink")
        if not shortlink:
            resp = client.changepublink(linkid=linkid, shortlink=1)
            shortlink = resp.get("shortlink")
        link_data = {
            "link": link,
            "shortlink": shortlink or link,
            "linkid": linkid
        }
        return link_data
    else:
        raise Exception(f"❌ Failed to create public link: {data}")


# 5. Force shortlink creation for an existing link
def force_shortlink(linkid):
    client = get_pcloud_client()
    resp = client.changepublink(linkid=linkid, shortlink=1)
    return resp.get("shortlink")


# 6. Delete a file by ID
def delete_file(file_id):
    client = get_pcloud_client()
    resp = client.deletefile(fileid=file_id)
    if resp.get('result') == 0:
        print(f"🗑️ File deleted: fileid={file_id}")
    else:
        print(f"❌ Failed to delete: {resp}")
    return resp


def get_or_create_folder(folder_name):
    """
    Get or create subfolder under PCLOUD_ROOT_FOLDER.
    """
    root_folder = os.getenv("PCLOUD_ROOT_FOLDER") or "Telegram-Bot-Reports"
    clean_root = root_folder.strip("/")
    clean_sub = folder_name.strip("/")
    full_path = f"/{clean_root}/{clean_sub}"
    return create_folder(full_path)


def upload_private_file(file_path, folder_name):
    """
    Upload report to pCloud privately.
    Returns:
        dict: {"file_id": file_id, "file_name": file_name, "provider": "pcloud"}
    """
    folder_id = get_or_create_folder(folder_name)
    file_id = upload_file(folder_id, file_path)
    file_name = os.path.basename(file_path)
    return {
        "file_id": file_id,
        "file_name": file_name,
        "provider": "pcloud"
    }


def download_file_bytes(file_id):
    """
    Download raw file bytes from pCloud by file_id.
    """
    import requests
    client = get_pcloud_client()
    res = client._request("getfilelink", params={"fileid": file_id})
    if res.get("result") == 0 and res.get("hosts") and res.get("path"):
        host = res["hosts"][0]
        path = res["path"]
        download_url = f"https://{host}{path}"
        r = requests.get(download_url, timeout=60)
        if r.status_code == 200:
            return r.content
        raise RuntimeError(f"Failed to download pCloud file {file_id} [{r.status_code}]: {r.text}")
    raise RuntimeError(f"pCloud getfilelink failed for file {file_id}: {res}")


def upload_and_get_link(file_path, folder_name):
    """
    Upload report to pCloud and return a public/short share link.
    """
    folder_id = get_or_create_folder(folder_name)
    file_id = upload_file(folder_id, file_path)
    link_info = generate_share_link(file_id)
    return link_info.get("shortlink") or link_info.get("link")


if __name__ == "__main__":
    folder_id = create_folder("WebUploads")
    print(f"Target Folder ID: {folder_id}")