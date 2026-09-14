# 🤖 Telegram Business Bot: Auto-Signing & Cloud Report Delivery

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot_API-v22.8-2CA5E0?logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Firebase Firestore](https://img.shields.io/badge/Database-Firebase_Firestore-FFCA28?logo=firebase&logoColor=black)](https://firebase.google.com/)
[![Google Drive](https://img.shields.io/badge/Storage-Google_Drive-34A853?logo=googledrive&logoColor=white)](https://developers.google.com/drive)
[![Microsoft OneDrive](https://img.shields.io/badge/Storage-OneDrive_Graph_API-0078D4?logo=microsoftonedrive&logoColor=white)](https://learn.microsoft.com/en-us/graph/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](#)

A high-performance, automated **Telegram Business Bot** designed for plagiarism and AI-checking report businesses (e.g., `@coding_services`). The bot seamlessly connects to Telegram Business accounts, collects student/client document submissions, automates report signing/watermarking, encrypts PDFs, securely uploads files to **Google Drive** with automatic failover to **Microsoft OneDrive**, manages orders via **Firebase Firestore**, and verifies payments in real-time before delivering final reports directly inside Telegram.

---

## 📑 Table of Contents

- [Key Features](#-key-features)
- [Architecture & Data Flow](#-architecture--data-flow)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Cloud & API Setup Guide](#-cloud--api-setup-guide)
  - [1. Telegram Bot & Business Connection](#1-telegram-bot--business-connection)
  - [2. Firebase Firestore Database](#2-firebase-firestore-database)
  - [3. Google Drive API (OAuth 2.0)](#3-google-drive-api-oauth-20)
  - [4. Microsoft OneDrive (Microsoft Graph API)](#4-microsoft-onedrive-microsoft-graph-api)
  - [5. Payment Verification (SheetDB / Webhook)](#5-payment-verification-sheetdb--webhook)
- [Environment Variables (.env)](#-environment-variables-env)
- [Installation & Setup](#-installation--setup)
- [Bot Commands & Usage](#-bot-commands--usage)
  - [Admin Workflow](#admin-workflow-uploading-and-signing)
  - [Customer Experience](#customer-experience)
  - [Admin Management Commands](#admin-management-commands)
- [Deployment (Render / Cloud PaaS)](#-deployment-render--cloud-paas)
- [Troubleshooting & FAQs](#-troubleshooting--faqs)

---

## 🚀 Key Features

- **Telegram Business Account Integration**:
  - Intercepts document submissions (.pdf, .doc, .docx) directly sent to your Telegram Business account.
  - Automatically acknowledges document receipt via `business_connection_id` and records client metadata in Firestore.
- **Automated PDF Processing & Digital Watermarking**:
  - Uses [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) to dynamically draw signature boxes, client report metadata, and service contact disclaimers.
  - Applies owner-password protection and strict permission flags via [PyPDF2](https://pypdf2.readthedocs.io/).
- **Dual Cloud Storage with Graceful Fallback**:
  - **Primary**: Google Drive via OAuth 2.0 user credentials.
  - **Secondary (Automatic Failover)**: Microsoft OneDrive via Microsoft Graph REST API & MSAL.
  - If Google Drive hits rate limits, expired tokens, or service downtime, the bot automatically switches to Microsoft OneDrive without failing the upload.
- **Private & Secure File Delivery**:
  - Files are stored privately in individual client folders—no public download links are leaked.
  - Once payment is verified, the bot pulls the raw binary file from cloud storage and streams it as a native Telegram document.
- **Multi-Region & Multi-Currency Payment Processing**:
  - Supports **Indian (INR ₹)** and **International (USD $)** billing.
  - Dynamic payment button generation using Razorpay payment links.
  - Real-time automated payment verification and record cleanup using SheetDB / Webhook API.
- **Persistent Cloud Database (Firebase Firestore)**:
  - Tracks user queues, active business connections, and pending deliveries.
  - Data survives dyno/container restarts when deployed on cloud providers.
- **Built-in Flask Keep-Alive Server**:
  - Embedded HTTP server (`keep_alive.py`) running on port `8080` to keep the bot alive 24/7 on free-tier cloud platforms (Render, Koyeb, etc.).

---

## 🔄 Architecture & Data Flow

```mermaid
sequenceDiagram
    autonumber
    actor Client as 👤 Client
    participant Bot as 🤖 Telegram Bot (main.py)
    actor Admin as 👨‍💼 Admin (@coding_services)
    participant Cloud as ☁️ Google Drive / OneDrive
    participant DB as 🔥 Firebase Firestore
    participant Gateway as 💳 Razorpay / SheetDB

    Client->>Bot: Sends document (.pdf / .docx) via Telegram Business Chat
    Bot->>DB: Saves client metadata & business_connection_id
    Bot-->>Client: Sends automated "Report is being prepared" message

    Admin->>Bot: /upload (Selects Region: INR / USD, file count)
    Admin->>Bot: Uploads completed report file(s)
    Admin->>Bot: Enters amount & selects client from recent suggestions
    Admin->>Bot: Selects whether to Sign & Watermark PDF
    
    alt Watermark Enabled
        Bot->>Bot: PyMuPDF draws signature & PyPDF2 sets owner password
    end

    Bot->>Cloud: Uploads file privately (Google Drive -> Fallback: OneDrive)
    Bot->>DB: Stores report metadata & cloud file IDs
    Bot-->>Admin: Confirms upload success with storage info
    Bot-->>Client: Sends "Report is Ready" with Razorpay payment button

    Client->>Gateway: Completes payment
    Client->>Bot: Clicks "📥 Download Report"
    Bot->>Gateway: Checks payment verification via SheetDB API
    
    alt Payment Verified
        Bot->>Cloud: Downloads private file binary
        Bot-->>Client: Delivers report PDF document in chat
        Bot->>Gateway: Deletes payment entry from SheetDB
        Bot->>DB: Cleans up pending report record & user queue
        Bot-->>Client: Sends channel invitation link
    else Payment Not Verified
        Bot-->>Client: Alerts client that payment has not registered yet
    end
```

---

## 📁 Project Structure

```text
├── downloads/                  # Temporary cache for incoming & processing files
├── edited_pdfs/                # Output folder for watermarked & signed PDFs
├── input_pdfs/                 # Buffer folder for incoming PDF files
├── firebase_db.py              # Firestore database interactions & user queue manager
├── google_drive_files.py       # Google Drive API integration (OAuth 2.0 upload/download)
├── onedrive_files.py           # Microsoft OneDrive integration (Microsoft Graph API & MSAL)
├── keep_alive.py               # Lightweight Flask server for 24/7 uptime
├── main.py                     # Core Telegram bot application & conversation handlers
├── main2.py                    # Backup / secondary application instance
├── requirements.txt            # Python package dependencies
├── runtime.txt                 # Specifies Python runtime (python-3.10.13)
├── .env.example                # Sample environment variables configuration
└── README.md                   # Project documentation
```

---

## 🛠️ Prerequisites

- **Python**: `3.10.x` or higher
- **Telegram Bot Token**: Created via [@BotFather](https://t.me/BotFather)
- **Telegram Business Account**: Required for business chat integration
- **Firebase Project**: With Cloud Firestore enabled
- **Google Cloud Console Project**: With Google Drive API enabled and OAuth 2.0 credentials
- **Microsoft Azure Entra ID**: App Registration with `Files.ReadWrite.All` permissions
- **Payment Gateway**: Razorpay account with Payment Links & SheetDB / Webhook integration

---

## 🔑 Cloud & API Setup Guide

### 1. Telegram Bot & Business Connection
1. Open Telegram and talk to [@BotFather](https://t.me/BotFather) to create a bot (`/newbot`).
2. Copy your **Bot Token**.
3. In your Telegram Business account:
   - Go to **Settings** ➡️ **Telegram Business** ➡️ **Chatbots**.
   - Connect your newly created bot.
   - **Important**: Ensure the **"Can Reply"** permission is toggled **ON**.
4. Retrieve your numerical Telegram user ID using [@userinfobot](https://t.me/userinfobot) to set as `ADMIN_ID`.

### 2. Firebase Firestore Database
1. Go to the [Firebase Console](https://console.firebase.google.com/) and create a project.
2. In the sidebar, navigate to **Build** ➡️ **Firestore Database** and create a database.
3. Go to **Project Settings** ➡️ **Service Accounts** ➡️ **Generate New Private Key**.
4. Open the downloaded JSON key and populate the `FIREBASE_*` variables in `.env`.

### 3. Google Drive API (OAuth 2.0)
> [!IMPORTANT]
> Standard Firebase/GCP Service Accounts have **0 GB storage quota** for personal Google Drives. You must authenticate using **OAuth 2.0 User Credentials** (Refresh Token).

1. In the [Google Cloud Console](https://console.cloud.google.com/), enable the **Google Drive API**.
2. Configure your **OAuth Consent Screen** (add your Google account as a Test User).
3. Create **OAuth 2.0 Client IDs** (Application Type: *Desktop App* or *Web Application*).
4. Obtain an OAuth refresh token with scope `https://www.googleapis.com/auth/drive`.
5. Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and `GOOGLE_OAUTH_REFRESH_TOKEN` in `.env`.
6. Create a folder in Google Drive to store reports, copy its ID from the URL (`https://drive.google.com/drive/folders/<FOLDER_ID>`), and set it as `GDRIVE_FOLDER_ID`.

### 4. Microsoft OneDrive (Microsoft Graph API)
OneDrive acts as the seamless automatic fallback if Google Drive fails:
1. Go to the [Microsoft Entra Admin Center](https://entra.microsoft.com/) (Azure AD).
2. Navigate to **App registrations** ➡️ **New registration**.
3. Under **Certificates & secrets**, create a new **Client Secret** and copy its value.
4. Under **API permissions**, add:
   - `Microsoft Graph` ➡️ Application permissions: `Files.ReadWrite.All`
   - Click **Grant admin consent for <your-tenant>**.
5. Fill `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, and `ONEDRIVE_USER_EMAIL` in `.env`.
6. Verify your connection anytime by running:
   ```bash
   python onedrive_files.py
   ```

### 5. Payment Verification (SheetDB / Webhook)
The bot checks completed payments against a SheetDB REST API endpoint:
- `PAYMENT_CAPTURED_DETAILS_URL`: Endpoint returning an array of verified payments:
  ```json
  [
    {
      "user_id": "123456789",
      "amount": "150"
    }
  ]
  ```
- When payment is confirmed and the report delivered, the bot sends a `DELETE` request to `{PAYMENT_CAPTURED_DETAILS_URL}/amount/{amount}` to prevent replay attacks.

---

## ⚙️ Environment Variables (.env)

Copy the `.env.example` file to create your `.env`:

```bash
cp .env.example .env
```

| Variable | Description | Example |
| :--- | :--- | :--- |
| `TOKEN` | Telegram Bot API Token | `123456789:ABCdefGHIjklMNO` |
| `ADMIN_ID` | Numeric Telegram ID of the admin | `987654321` |
| `PDF_PASSWORD` | Owner password for encrypted output PDFs | `SuperSecret123!` |
| `SIGN_TEXT_1` | Digital signature watermark label | `Coding Services` |
| `RAZORPAY_PAYMENT_URL` | Payment link for Indian users (INR) | `https://rzp.io/l/inr_pay` |
| `RAZORPAY_USD_PAYMENT_URL` | Payment link for non-Indian users (USD) | `https://rzp.io/l/usd_pay` |
| `PAYMENT_CAPTURED_DETAILS_URL` | SheetDB / Webhook verification URL | `https://sheetdb.io/api/v1/xyz` |
| `FIREBASE_PROJECT_ID` | Firebase Project ID | `plagiarism-bot-prod` |
| `FIREBASE_PRIVATE_KEY` | Firebase Service Account Private Key | `"-----BEGIN PRIVATE KEY-----\n..."` |
| `FIREBASE_CLIENT_EMAIL` | Firebase Client Service Account Email | `bot@project.iam.gserviceaccount.com` |
| `GDRIVE_FOLDER_ID` | Google Drive target folder ID | `1a2b3c4d5e6f7g8h9i` |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth 2.0 Client ID | `xxxx.apps.googleusercontent.com` |
| `GOOGLE_OAUTH_CLIENT_SECRET`| Google OAuth 2.0 Client Secret | `GOCSPX-xxxx` |
| `GOOGLE_OAUTH_REFRESH_TOKEN`| Google OAuth 2.0 Refresh Token | `1//04xxxx` |
| `AZURE_TENANT_ID` | Microsoft Azure Entra Tenant ID | `uuid-xxxx-xxxx` |
| `AZURE_CLIENT_ID` | Azure App Registration Client ID | `uuid-xxxx-xxxx` |
| `AZURE_CLIENT_SECRET` | Azure App Client Secret Value | `~xxxx` |
| `ONEDRIVE_USER_EMAIL` | Target Microsoft 365 User Email | `reports@yourdomain.com` |
| `ONEDRIVE_ROOT_FOLDER` | Root folder name in OneDrive | `TelegramBotReports` |
| `PORT` | Flask keep-alive webserver port | `8080` |

---

## 💻 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/telegram-business-bot.git
cd "With auto sign and report upload - Google and One Drive - Non-Indian"
```

### 2. Set Up Virtual Environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Test Cloud Connections
Before running the bot, verify your Microsoft OneDrive integration:
```bash
python onedrive_files.py
```
*You should see `🎉 ALL TESTS PASSED! OneDrive is fully configured and ready for the bot.`*

### 5. Start the Bot
```bash
python main.py
```

---

## 📱 Bot Commands & Usage

### Customer Experience
1. The client sends a document (.pdf, .doc, or .docx) to your Telegram Business account.
2. The bot automatically replies:
   > *"🤖 Thank you for submitting your article 🙏. Kindly wait while your report is being prepared."*
3. Once the admin finishes analyzing and uploads the report, the client receives:
   > *"🔰 REPORT IS READY 🔰 Please click on the button below to pay [Amount] to receive your report."*
4. The client clicks the payment button, pays via Razorpay, and clicks **📥 Download Report**.
5. The bot verifies the payment and delivers the PDF document directly into the chat!

### Admin Workflow (Uploading and Signing)
1. In the admin chat, tap **`⬆️ Upload`** or send `/upload`.
2. **Select Region**:
   - `🇮🇳 Indian` (Currency: INR `Rs`)
   - `🌍 Non-Indian` (Currency: USD `$`)
3. **Select File Count**:
   - `📁 One File`, `📂 Two Files`, or `📦 More than Two Files`.
4. Send the generated report PDF file(s).
5. Enter the **Payment Amount**.
6. Select the client from the **interactive suggested users list** (populated in real-time from submissions).
7. Choose whether to **Sign & Watermark** the report:
   - `✅ Yes`: Adds visual stamp box, name text, and page footers.
   - `❌ No`: Leaves report formatting as original.
8. The bot uploads the file to **Google Drive** (or fails over to **OneDrive**), saves records in Firestore, and pings the customer.

### Admin Management Commands

| Command | Button | Description |
| :--- | :--- | :--- |
| `/upload` | `⬆️ Upload` | Launches report upload, signing, and billing wizard |
| `/show_reports` | `📜 Show Reports` | Lists all pending reports that customers haven't downloaded yet (allows deletion by User ID) |
| `/show_users` | `👥 Show Users` | Displays recent users who submitted documents (allows deletion by Chat ID) |
| `/cancel` | `🚫 Cancel` | Cancels any ongoing conversation and restores the main admin keyboard |
| `/help` | — | Shows the command reference cheat sheet |

---

## ☁️ Deployment (Render / Cloud PaaS)

This project includes configuration files optimized for cloud deployment (such as [Render](https://render.com)):

- `runtime.txt`: Pins Python version `python-3.10.13`.
- `keep_alive.py`: Starts a Flask web server on port `8080` in a background daemon thread.
- `main.py`: Automatically initializes `keep_alive()` and drops any stale webhooks before polling.

### Steps to Deploy on Render:
1. Create a **New Web Service** linked to your Git repository.
2. Select **Python** as the runtime.
3. Configure Build and Start commands:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
4. Add all environment variables from `.env` in the **Environment** tab.
5. Set up an uptime monitor (such as [UptimeRobot](https://uptimerobot.com/)) to ping your Render URL (`https://<service-name>.onrender.com/`) every 5 minutes to prevent sleep on free tiers.

---

## ❓ Troubleshooting & FAQs

### 1. `business_peer_invalid` or unable to reply to business chats
- **Cause**: Telegram Business chatbot permissions are restricted.
- **Fix**: Open Telegram ➡️ **Settings** ➡️ **Telegram Business** ➡️ **Chatbots** ➡️ Select your bot ➡️ Toggle **"Can Reply"** to **ON**.

### 2. Google Drive returns `HttpError 403: The user's Drive storage quota has been exceeded`
- **Cause**: Using a GCP Service Account to upload to a standard Gmail/personal Google Drive (Service accounts have 0 GB quota).
- **Fix**: Configure user OAuth 2.0 credentials (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`).

### 3. Google Drive upload fails with `invalid_grant`
- **Cause**: The OAuth 2.0 refresh token expired or was revoked.
- **Fix**: Regenerate the OAuth refresh token in Google Cloud Console or allow the bot to fail over to Microsoft OneDrive.

### 4. Temporary files cluttering storage
- **Fix**: The bot includes automatic file garbage collection in `remove_temp_file` and `cleanup_conversation_state` to clean up downloaded files from `downloads/`, `input_pdfs/`, and `edited_pdfs/` after delivery or cancellation.

---

## 🤝 Support & Contact

For assistance, custom features, or inquiries:
- **Telegram Admin**: [@coding_services](https://t.me/coding_services)
- **Telegram Channel**: [Join Here](https://t.me/+66qt38tocAI0ZWI1)
