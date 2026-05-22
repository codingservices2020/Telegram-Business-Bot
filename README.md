# 🤖 Telegram Business Bot (Auto-Sign & Report Upload)

A premium, enterprise-grade Telegram Business Chatbot that automates report generation, PDF signing, Google Drive storage management, payment gateway routing, and client notifications.

This bot integrates directly with your **Telegram Business Connection**, allowing you to automate customer interactions inline in your business chats, with a built-in fallback to direct private messaging.

---

## 🌟 Key Features

*   **Telegram Business Connection Integration**: Communicates inline with customers in the business connection chat, with an automatic direct-message fallback mechanism.
*   **Automatic PDF Editing & Signing**: Automatically edits and signs PDF reports (`PyMuPDF` & `PyPDF2`) before delivering them to users.
*   **Google Drive Storage Automation**: Auto-creates customer-specific folders, uploads processed files, and retrieves direct, shareable download links.
*   **Dual Payment Gateway Support**:
    *   🇮🇳 **Indian Region**: Razorpay payment integration.
    *   🌍 **Non-Indian Region**: PayPal payment link generation and order verification.
*   **Firestore Database Integration**: Real-time customer data tracking, user suggestions for admin uploads, and payment/report status synchronization.
*   **Keep-Alive Flask Server**: Built-in background Flask server to satisfy Render/hosting service health checks and prevent server sleep.

---

## 🛠️ Project Structure

```bash
├── main2.py                 # Core bot application and update handlers
├── firebase_db.py           # Firestore database CRUD operations and user tracking
├── google_drive_files.py    # Google Drive API helper for folders & uploads
├── paypal.py / paypal2.py   # PayPal API order generation & payment capturing
├── keep_alive.py            # Flask background thread for uptime maintenance
├── requirements.txt         # Project dependencies
└── runtime.txt              # Render runtime python version specification
```

---

## 🚀 Admin Commands

The following commands are restricted to the configured `ADMIN_ID`:

*   `/upload` - Initiates the interactive multi-file report upload flow:
    1. Select user region (Indian / Non-Indian).
    2. Select the number of files to upload.
    3. Upload the documents.
    4. Enter the payment amount.
    5. Choose the customer from the quick suggestion list (top 4 latest active users).
    6. Choose whether to auto-sign the PDFs.
    7. Automatically processes, uploads to Google Drive, and sends the payment links to the customer.
*   `/show_reports` - Displays all reports that have not yet been downloaded/paid for by customers (with options to delete).
*   `/show_users` - Lists all users who have sent documents recently (with options to delete).
*   `/cancel` - Cancels the current `/upload` conversation flow.

---

## ⚙️ Configuration & Environment Variables

Create a `.env` file in the root directory (or configure these in your Render environment variables dashboard):

```env
# --- Telegram Configuration ---
TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_admin_user_id

# --- Firestore Credentials ---
FIREBASE_TYPE=service_account
FIREBASE_PROJECT_ID=your_firebase_project_id
FIREBASE_PRIVATE_KEY_ID=your_firebase_private_key_id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
FIREBASE_CLIENT_EMAIL=your_firebase_client_email
FIREBASE_CLIENT_ID=your_firebase_client_id
FIREBASE_AUTH_URI=https://accounts.google.com/o/oauth2/auth
FIREBASE_TOKEN_URI=https://oauth2.googleapis.com/token
FIREBASE_AUTH_PROVIDER_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
FIREBASE_CLIENT_CERT_URL=your_firebase_client_cert_url
FIREBASE_UNIVERSE_DOMAIN=googleapis.com

# --- Payment Gateways ---
RAZORPAY_PAYMENT_URL=your_razorpay_payment_page_url
PAYPAL_PAYMENT_URL=your_paypal_payment_url
# PayPal API credentials (for automated non-Indian invoicing)
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret
PAYPAL_MODE=live_or_sandbox

# --- Google Drive Configuration ---
# Service account or OAuth JSON credentials configured within google_drive_files.py
```

---

## 📦 Local Installation & Setup

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/telegram-business-bot.git
    cd telegram-business-bot
    ```

2.  **Create and Activate a Virtual Environment**:
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # macOS/Linux:
    source .venv/bin/activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables**:
    Create your `.env` file using the configuration template above.

5.  **Run the Bot**:
    ```bash
    python main2.py
    ```

---

## 🌐 Deploying to Render

This repository is optimized for deployment as a **Render Web Service**:

1.  Create a new **Web Service** on Render and link your GitHub repository.
2.  Set the following settings:
    *   **Runtime**: `Python` (Render reads `runtime.txt` to install Python 3.10.13 automatically).
    *   **Build Command**: `pip install -r requirements.txt`
    *   **Start Command**: `python main2.py`
3.  Add all variables from your local `.env` file to the **Environment Variables** section in Render.
4.  Once deployed, the `keep_alive` background web service will start on the Render-allocated port (preventing the service from sleeping due to inactivity).

---

## ⚠️ Telegram Business Connection Requirement

To ensure the bot can reply directly inside the business connection chats:
1. Open the Telegram app on your mobile phone or desktop client.
2. Navigate to **Settings > Telegram Business > Chatbots**.
3. Select your bot (`@Testing233535Bot`).
4. Ensure the **"Can Reply"** / **"Reply to messages"** permission toggle is turned **ON**. 
*(If this setting is turned off, the bot will automatically fall back to sending direct messages to the customer in their private bot chat).*
