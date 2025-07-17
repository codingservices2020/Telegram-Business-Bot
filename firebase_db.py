from datetime import datetime, timedelta
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# DB_FILE_NAME = "testing_database"  # Define the firebase database file
DB_FILE_NAME = "Reports_Download_links"  # Define the firebase database file

# Build the Firebase credentials dictionary dynamically
firebase_config = {
    "type": os.getenv("FIREBASE_TYPE"),
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
    "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
    "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL"),
    "universe_domain": os.getenv("FIREBASE_UNIVERSE_DOMAIN"),
}

# Initialize Firebase app with loaded credentials
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)

# Firestore database instance
db = firestore.client()


def save_report_links(user_id, amount, links):
    """Save user subscription to Firestore with email & mobile"""
    doc_ref = db.collection(DB_FILE_NAME).document(str(user_id))
    doc_ref.set({
        "amount": amount,
        "links": links,
    })

def load_report_links():
    """Load all subscriptions from Firestore, safely handling errors"""
    try:
        users_ref = db.collection(DB_FILE_NAME).stream()
        return {
            user.id: {
                "amount": user.to_dict().get("amount", "Unknown"),
                "links": user.to_dict().get("links", "Unknown"),
            }
            for user in users_ref
        }
    except Exception as e:
        print(f"Firestore Error: {e}")
        return {}  # Return empty dict instead of crashing


def remove_report_links(user_id):
    """Remove expired subscriptions from Firestore"""
    users_ref = db.collection(DB_FILE_NAME).stream()
    for user in users_ref:
        if str(user_id) == user.id:
            db.collection(DB_FILE_NAME).document(user.id).delete()

###################################################################################

def save_user_data(user_id, name, username, business_chat_id=None):
    doc_ref = db.collection("users").document(str(user_id))
    data = {
        "name": name,
        "username": username,
        "business_chat_id": business_chat_id,
        "timestamp": datetime.utcnow().isoformat()  # 🔥 Add timestamp
    }
    doc_ref.set(data, merge=True)



def load_user_data():
    """Load all user info from Firestore"""
    try:
        users_ref = db.collection("users").stream()
        return {
            user.id: {
                "name": user.to_dict().get("name", "Unknown"),
                "username": user.to_dict().get("username", "Unknown"),
                "business_chat_id": user.to_dict().get("business_chat_id"),
                "timestamp": user.to_dict().get("timestamp")
            }
            for user in users_ref
        }
    except Exception as e:
        print(f"Firestore Error: {e}")
        return {}

def remove_user_data(user_id):
    """Remove expired subscriptions from Firestore"""
    users_ref = db.collection("users").stream()
    for user in users_ref:
        if str(user_id) == user.id:
            db.collection("users").document(user.id).delete()

def get_latest_users(limit=4):
    """Fetch the latest users sorted by timestamp"""
    try:
        users_ref = db.collection("users").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(
            limit).stream()
        return [(user.id, user.to_dict().get("name", "Unknown")) for user in users_ref]
    except Exception as e:
        print(f"Firestore Error: {e}")
        return []
