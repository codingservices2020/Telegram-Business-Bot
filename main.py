import os
import json
import logging
import requests
import uuid
import fitz  # PyMuPDF
from PyPDF2 import PdfReader, PdfWriter  # Required for sign_pdf
from firebase_db import save_report_links, load_report_links, remove_report_links, save_user_data, load_user_data, get_latest_users, remove_user_data
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, CallbackContext, TypeHandler
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import warnings
from keep_alive import keep_alive
keep_alive()

# from dotenv import load_dotenv
# load_dotenv()

warnings.filterwarnings("ignore", category=DeprecationWarning)
# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
TOKEN = os.getenv("TOKEN")
PDF_PASSWORD = os.getenv("PDF_PASSWORD")
SIGN_TEXT_1 = os.getenv("SIGN_TEXT_1")
URL = f'https://api.telegram.org/bot{TOKEN}/getUpdates'
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PAYMENT_URL = os.getenv('PAYMENT_URL')
PAYMENT_CAPTURED_DETAILS_URL= os.getenv("PAYMENT_CAPTURED_DETAILS_URL")
SHORTIO_LINK_API_KEY = os.getenv("SHORTIO_LINK_API_KEY")
SHORTIO_LINK_URL = os.getenv("SHORTIO_LINK_URL")    # Short.io API Endpoint
SHORTIO_DOMAIN = os.getenv("SHORTIO_DOMAIN")  # Example: "example.short.io"

# Load Google Drive API Credentials from environment variables
SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY", "").replace('\\n', '\n'),  # Convert \n into real newlines
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL"),
}

# ✅ Debugging: Check if private key is loaded correctly
if not SERVICE_ACCOUNT_INFO["private_key"].startswith("-----BEGIN PRIVATE KEY-----"):
    print("❌ ERROR: Private key is not correctly formatted.")
    exit(1)

# Authenticate with Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']
creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# Authenticate with Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']
creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# Define states for conversation handler
WAITING_FOR_UPLOAD_OPTION, WAITING_FOR_MULTIPLE_FILES, COLLECTING_FILES = range(100, 103)
WAITING_FOR_PAYMENT, WAITING_FOR_USER = range(103, 105)
WAITING_FOR_DELETE_ID = 105
WAITING_FOR_SEARCH_INPUT = 106  # 🔍 New state for search
WAITING_FOR_NAME = 107  # add this line
WAITING_FOR_DELETE_USER_ID = 108  # for /show_users command



# Load existing file data or initialize an empty dictionary
DATA_FILE = "file_data.json"
report_links = {}
active_conversations = {}
# Define folders for input and edited PDFs
INPUT_FOLDER = "input_pdfs"
OUTPUT_FOLDER = "edited_pdfs"

# Ensure both folders exist
os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Global variable to store the code fetched from the API.
code = None
# Define the cancel button
CANCEL_BUTTON = "🚫 Cancel"
START_BUTTON = "🤖 Start the Bot"



if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r") as f:
            file_content = f.read().strip()  # Remove any accidental empty spaces
            report_links = json.loads(file_content) if file_content else {}
    except json.JSONDecodeError:
        print("Warning: JSON file is corrupted. Resetting data.")
        report_links = {}
else:
    report_links = {}

def save_data():
    """Save the file data to JSON."""
    with open(DATA_FILE, "w") as f:
        json.dump(report_links, f, indent=4)

def edit_pdf(input_pdf, output_pdf, output_pdf_name, selected_text):
    doc = fitz.open(input_pdf)
    page = doc[0]

    hide_rect = fitz.Rect(30.0, 304.0, 600, 410)
    page.draw_rect(hide_rect, color=(1, 1, 1), fill=(1, 1, 1))

    rect = fitz.Rect(36, 329, 600, 400)
    page.insert_textbox(rect, selected_text, fontsize=23, fontname="helvetica-bold", color=(0, 0, 0), align=0)

    page.insert_text((36, 383), output_pdf_name, fontsize=17, fontname="helvetica-bold", color=(0, 0, 0))

    if selected_text != SIGN_TEXT_1:
        page.insert_text((402, 560), f"Digitally signed by {selected_text}", fontsize=8,
                         fontname="times-italic", color=(1, 0, 0))
    else:
        rect = fitz.Rect(382, 680, 580, 740)
        page.draw_rect(rect, color=(1, 0, 0))
        page.insert_textbox(
            rect,
            f"\n  \t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\tDigitally signed by {selected_text}\n\n"
            f" Contact to Coding Services for Plagiarism and AI checking report on telegram @coding_services.",
            fontsize=8,
            fontname="times-italic",
            color=(0, 0, 0),
            align=0
        )

    doc.save(output_pdf)
    doc.close()


def sign_pdf(pdf_file_path):
    reader = PdfReader(pdf_file_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    signed_pdf_path = os.path.join("edited_pdfs", os.path.basename(pdf_file_path))

    writer.encrypt(user_password="", owner_pwd=PDF_PASSWORD, permissions_flag=3)

    with open(signed_pdf_path, "wb") as f_out:
        writer.write(f_out)

    return signed_pdf_path

def verify_payment(chat_id,payment_amount):
    response = requests.get(url=PAYMENT_CAPTURED_DETAILS_URL)
    try:
        response.raise_for_status()
        data = response.json()
        for entry in data:
            if entry['user_id'] == str(chat_id):
                if entry['amount'] == str(payment_amount):
                    return True
        print("No payment details found! ")
    except requests.exceptions.HTTPError as err:
        print("HTTP Error:", err)

def short_link(long_url, title):
    # Headers
    headers = {
        "Authorization": SHORTIO_LINK_API_KEY,
        "Content-Type": "application/json"
    }
    # Payload
    data = {"domain": SHORTIO_DOMAIN,
            "originalURL": long_url,
            "title": title
            }
    response = requests.post(SHORTIO_LINK_URL, json=data, headers=headers)
    try:
        response_data = response.json()
        if "shortURL" in response_data:
            return response_data["shortURL"]
        else:
            return long_url
    except Exception as e:
        return long_url


# Function to create a reply keyboard with a Cancel button
def get_cancel_keyboard():
    return ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True, one_time_keyboard=True)

# Function to create a reply keyboard with a Cancel button
def get_start_keyboard():
    return ReplyKeyboardMarkup([[START_BUTTON]], resize_keyboard=True, one_time_keyboard=True)


async def handle_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.business_message and update.business_message.document:
        bm = update.business_message
        global BUSINESS_CONNECTION_ID
        BUSINESS_CONNECTION_ID = bm.business_connection_id
        print(f"bm: {bm}")
        if bm.document:
            print("document")
            try:
                logger.info(f"📨 Business document received: {bm.document.file_name}")
                print(f"bm.chat.id: {bm.chat.id}; type: {type(bm.chat.id)}")

                user_id = str(bm.chat.id)
                name = bm.chat.full_name if hasattr(bm.chat, 'full_name') else "Unknown"
                username = bm.chat.username or "unknown"
                await bm.reply_text(
                    "🤖*Thank you for submitting your article*🙏\n\n"
                    "✅Kindly wait while your report is being prepared. I will notify you as soon as it is ready for download.",
                    parse_mode="Markdown",
                )

                save_user_data(
                    user_id=user_id,
                    name=name,
                    username=username,
                    business_chat_id=bm.chat.id,
                    # business_connection_id=bm.business_connection_id
                )

                # await context.bot.send_message(
                #     business_connection_id=bm.business_connection_id,
                #     chat_id=bm.chat.id,
                #     text=f"🤖*Thank you for submitting your article*🙏\n\n"
                #          f"✅Kindly wait while your report is being prepared. I will notify you as soon as it is ready for download.",
                #     parse_mode="Markdown",
                # )
            except Exception as e:
                logger.error(f"Error replying to document upload: {e}")
            return


# Add a new function to handle cancellation of the upload process
async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the upload process and reset the conversation state."""
    active_conversations[update.message.chat_id] = False
    await update.message.reply_text("⬆️ Upload process cancelled. You can start over with /upload.")
    return ConversationHandler.END

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return ConversationHandler.END
    await update.message.reply_text("♻️ Upload Process has Started...", reply_markup=get_cancel_keyboard(),parse_mode="Markdown")
    active_conversations[update.message.chat_id] = True
    keyboard = [
        [InlineKeyboardButton("📁 One File", callback_data="upload_1")],
        [InlineKeyboardButton("📂 Two Files", callback_data="upload_2")],
        [InlineKeyboardButton("📦 More than Two Files", callback_data="upload_more")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("How many files do you want to upload?", reply_markup=reply_markup)
    return WAITING_FOR_UPLOAD_OPTION

# Handle the Cancel button
async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Cancel button press."""
    active_conversations[update.message.chat_id] = False
    await update.message.reply_text(
        "Upload process cancelled.",
        reply_markup=ReplyKeyboardRemove()  # Remove the custom keyboard
    )
    return ConversationHandler.END

async def upload_option_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["files"] = []
    if query.data == "upload_1":
        context.user_data["upload_limit"] = 1
        await query.edit_message_text("📤 Please send 1 file.")
        return COLLECTING_FILES
    elif query.data == "upload_2":
        context.user_data["upload_limit"] = 2
        await query.edit_message_text("📤 Please send 2 files.")
        return COLLECTING_FILES
    else:
        await query.edit_message_text("✳️ Please enter how many files you want to upload (must be a number > 2):")
        return WAITING_FOR_MULTIPLE_FILES

async def ask_file_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    active_conversations[update.message.chat_id] = True
    if not user_input.isdigit() or int(user_input) <= 2:
        await update.message.reply_text("❌ Please enter a number greater than 2.")
        return WAITING_FOR_MULTIPLE_FILES

    context.user_data["upload_limit"] = int(user_input)
    await update.message.reply_text(f"📤 Please send {user_input} files one by one.")
    return COLLECTING_FILES


async def handle_multiple_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    active_conversations[update.message.chat_id] = True

    if not document:
        await update.message.reply_text("Please send a valid file.")
        return COLLECTING_FILES

    file = await context.bot.get_file(document.file_id)
    os.makedirs("downloads", exist_ok=True)

    # Step 1: Download original file
    original_file_path = f"downloads/{document.file_name}"
    await file.download_to_drive(original_file_path)

    # Step 2: Prepare filenames
    file_base, _ = os.path.splitext(document.file_name)
    edited_file_name = f"{file_base}{uuid.uuid4().hex[:1]}.pdf"
    edited_file_path = f"downloads/{edited_file_name}"

    # Step 3: Edit the PDF using SIGN_TEXT_1 from .env
    selected_text = os.getenv("SIGN_TEXT_1", "Default Signature Text")
    edit_pdf(original_file_path, edited_file_path, edited_file_name, selected_text)

    # Step 4: Sign the edited PDF
    signed_file_path = sign_pdf(edited_file_path)
    signed_file_name = os.path.basename(signed_file_path)

    # Step 5: Store the final signed PDF path and name
    context.user_data["files"].append((signed_file_path, signed_file_name))

    # Step 6: Clean up intermediate files
    for path in [original_file_path, edited_file_path]:
        if os.path.exists(path):
            os.remove(path)

    # Step 7: Check if all files are received
    if len(context.user_data["files"]) >= context.user_data["upload_limit"]:
        await update.message.reply_text("✅ All files received. Now enter payment amount:")
        return WAITING_FOR_PAYMENT

    await update.message.reply_text(
        f"📒 File *{document.file_name}* received and signed. Send next file...",
        parse_mode="Markdown"
    )
    return COLLECTING_FILES



async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handle file upload from users """
    document = update.message.document
    active_conversations[update.message.chat_id] = True
    if not document:
        await update.message.reply_text("No document detected. Please try again.")
        return WAITING_FOR_UPLOAD_OPTION
    await update.message.reply_text(
        "♻️ Uploading Report ....",
        reply_markup=ReplyKeyboardRemove()  # Remove the keyboard
    )
    logger.info(f"Received file: {document.file_name}")  # Debugging log

    file = await context.bot.get_file(document.file_id)
    file_path = f"downloads/{document.file_name}"

    # Create folder if not exists
    os.makedirs("downloads", exist_ok=True)

    # Download file
    await file.download_to_drive(file_path)
    logger.info(f"File saved locally: {file_path}")  # Debugging log

    # Store file path for later use
    context.user_data["file_path"] = file_path
    context.user_data["file_name"] = document.file_name
    # context.job_queue.run_once(delete_message, 0, data=(sent_message.chat.id, sent_message.message_id))
    await update.message.reply_text("💵 Now, enter the payment amount:")

    return WAITING_FOR_PAYMENT

async def receive_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global code
    """ Receive payment amount and prompt for user ID """
    amount = update.message.text
    active_conversations[update.message.chat_id] = True
    context.user_data["amount"] = amount
    suggestions = get_latest_users()
    buttons = [[InlineKeyboardButton(f"{name} ({uid})", callback_data=f"user_select|{uid}|{name}")]
               for uid, name in suggestions]

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

    await update.message.reply_text(
        "✍️ Please enter the name of the user (or tap below):",
        reply_markup=reply_markup
    )
    return WAITING_FOR_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive name after amount"""
    name = update.message.text.strip()
    active_conversations[update.message.chat_id] = True
    context.user_data["name"] = name
    await update.message.reply_text("👤 Enter the User ID:")
    return WAITING_FOR_USER

async def handle_user_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, uid, name = query.data.split('|')
    context.user_data["name"] = name
    context.user_data["user_id_from_button"] = uid

    await query.edit_message_text(f"✅ Selected: {name} ({uid})")

    # Call receive_user with user_id directly
    return await receive_user(update, context, uid)


async def receive_user(update: Update, context: ContextTypes.DEFAULT_TYPE, prefilled_user_id=None):
    global code

    chat_id = update.effective_chat.id
    active_conversations[chat_id] = True

    # Safely determine the user ID
    if prefilled_user_id:
        user_id_text = prefilled_user_id
    elif update.message and update.message.text:
        user_id_text = update.message.text.strip()
    else:
        user_id_text = context.user_data.get("user_id_from_button")

    # Validate user ID
    if not user_id_text or not user_id_text.isdigit() or not (100000000 <= int(user_id_text) <= 9999999999):
        await context.bot.send_message(chat_id=chat_id, text="❌ Please enter a valid Telegram User ID (7–10 digits).")
        return WAITING_FOR_USER

    user_id = user_id_text
    file_path = context.user_data.get("file_path")
    file_name = context.user_data.get("file_name")
    amount = context.user_data.get("amount")

    if "files" not in context.user_data or not context.user_data["files"]:
        active_conversations[chat_id] = False
        await context.bot.send_message(chat_id=chat_id, text="🚫 No files found. Please restart with /upload.")
        return ConversationHandler.END

    await context.bot.send_message(chat_id=chat_id, text="♻️ Uploading file to Google Drive...", reply_markup=ReplyKeyboardRemove())

    # Upload to Google Drive
    links = []
    for path, name in context.user_data["files"]:
        gdrive_link = await upload_to_drive(path, name)
        if gdrive_link:
            links.append(gdrive_link)

    # Delete signed PDFs after upload
    for path, _ in context.user_data["files"]:
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"🧹 Deleted signed file: {path}")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete file {path}: {e}")

    if not links:
        await context.bot.send_message(chat_id=chat_id, text="❌ Error uploading files to Google Drive.")
        active_conversations[chat_id] = False
        return ConversationHandler.END

    short_links = [short_link(link, f"{user_id}-{i + 1}") for i, link in enumerate(links)]

    name = context.user_data.get("name", "Unknown")
    save_report_links(user_id, amount, short_links)
    global report_links
    report_links = load_report_links()

    links_formatted = "\n".join([f"📥 File {i + 1}: {link}" for i, link in enumerate(report_links[user_id]["links"])])

    await context.bot.send_message(chat_id=chat_id,
        text=f"<b>🔰REPORT UPLOADED SUCCESSFULLY!🔰</b>\n\n"
             f"👤 <b>Name:</b> <a href='tg://user?id={user_id}'>{name}</a>\n"
             f"💰 <b>Amount:</b> Rs {amount}/-\n\n"
             f"<b>⬇️ Report Download Links:</b>\n{links_formatted}",
        parse_mode="HTML"
    )

    start_button_text = "🚀Click here to Proceed🚀"
    start_button = InlineKeyboardButton(start_button_text, callback_data=f"start_{user_id}")
    reply_markup = InlineKeyboardMarkup([[start_button]])


    await context.bot.send_message(
        business_connection_id=BUSINESS_CONNECTION_ID,
        chat_id=user_id,
        text=f"<b>🔰REPORT IS READY🔰</b>\n\n"
             f"Please, click on the button below and make the payment of <b>Rs {amount}/-</b> to download your report.",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    remove_user_data(user_id)

    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    return ConversationHandler.END

async def upload_to_drive(file_path, file_name):
    """ Upload a file to Google Drive and return the shareable link """
    try:
        file_metadata = {'name': file_name, 'parents': [GDRIVE_FOLDER_ID]}
        media = MediaFileUpload(file_path, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

        # Make file public
        drive_service.permissions().create(fileId=file.get('id'), body={'role': 'reader', 'type': 'anyone'}).execute()

        return f"https://drive.google.com/uc?id={file.get('id')}&export=download"
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return None



# ------------------ Start Command ------------------ #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the update is from a callback query (button press)
    if update.callback_query:
        query = update.callback_query
        await query.answer()  # Acknowledge the button press
        chat_id = query.from_user.id
        user_id = str(chat_id)
        message = query.message  # Use the message from the callback query
    else:
        chat_id = update.message.from_user.id
        user_id = str(chat_id)
        message = update.message  # Use the message from the regular update


    #check is there any user's report
    if user_id in report_links:
        payment_button_text = f"🚀Make Payment of Rs {report_links[user_id]['amount']}/-🚀"
        download_button_text = "📥 Download Report"

        payment_button = InlineKeyboardButton(payment_button_text, url=PAYMENT_URL)
        download_button = InlineKeyboardButton(download_button_text, callback_data=f"download_{user_id}")
        keyboard = [[payment_button], [download_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            f"*🔰Report Downloader Bot🔰*"
            f"\n\nTo download your report, follow these two steps:"
            f"\n 1️⃣ First click on the button below and make the payment."
            f"\n 2️⃣ After payment download the report."
            f"\n\n Your User ID: `{user_id}` (tap to copy)\n\n"
            f"✅ Use this User ID on Razorpay Payment Gateway.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await message.reply_text("🚫 There is no information about your report. Please contact Admin @coding_services.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press
    # Check if the callback data starts with "start_"
    if query.data.startswith("start_"):
        user_id = query.data.replace("start_", "")
        await start(update, context)  # Call the start function
        return

    user_id = query.data.replace("download_", "")
    await query.edit_message_text(f"♻️  Payment verifying. Please wait...")
    report_links = load_report_links() # Refresh from Firebase
    if user_id in report_links:
        invoice_amount = int(report_links[user_id]['amount'])
        if verify_payment(user_id, invoice_amount):

            links_formatted = "\n".join(
                [f"📥 File {i + 1}: {link}" for i, link in enumerate(report_links[user_id]["links"])])
            await query.edit_message_text(
                f"<b>🔰PAYMENT VERIFIED🔰</b>\n\n"
                f"🙏Thank you for making the payment.\n\n"
                f"✅ Download your report by clicking on the link below.\n\n"
                f"<b>⬇️ Report Download Links:</b>\n{links_formatted}",
                parse_mode="HTML"
            )
            await context.bot.send_message(
                business_connection_id=BUSINESS_CONNECTION_ID,
                chat_id=user_id,
                text=f"*🔰JOIN & SHARE🔰*\n\n"
                     f"✅Please share and join our Telegram channel with your friends to stay updated "
                     f"about our products and services and also for weekly giveaways🎁\n\n"
                     f"❤️ Join our Telegram channel: https://t.me/+66qt38tocAI0ZWI1",

                parse_mode="Markdown"
            )


            DELETED_CODES_URL = f"{PAYMENT_CAPTURED_DETAILS_URL}/amount/{invoice_amount}"
            requests.delete(url=DELETED_CODES_URL)

            remove_report_links(user_id)
            load_report_links()  # Refresh from Firebase
        else:
            start_button_text = "🚀Click here to Pay🚀"
            start_button = InlineKeyboardButton(start_button_text, callback_data=f"start_{user_id}")
            keyboard = [[start_button]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("<b>🔰PAYMENT NOT RECEIVED🔰</b>\n\n"
                                           "We have not received your payment. Please first make the payment then click on Download Report button.\n\n"
                                           "✅ Need help? Please contact to Admin @coding_services.", parse_mode="HTML", reply_markup=reply_markup)
    else:
        await query.edit_message_text("⭕️ Your report is not ready. Please wait for some time!")


# ------------------ Admin Command: Show Reports ------------------ #
async def show_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    report_links = load_report_links()  # Refresh from Firebase
    if not report_links:
        await update.message.reply_text("📭 No pending reports found.")
        return

    messages = []
    users = load_user_data()
    for chat_id, details in report_links.items():
        name = users.get(chat_id, {}).get("name", "Unknown")
        # user_link = f"🆔 User ID:<a href='tg://user?id={chat_id}'>{chat_id}</a>"
        amount = details.get("amount", "N/A")
        links = details.get("links", [])

        if links:
            link_lines = "\n".join([f"📥 File {i + 1}: {link}" for i, link in enumerate(links)])
        else:
            link_lines = "🔗 No links found."

        messages.append(
            f"<b>👤 Name:</b> <a href='tg://user?id={chat_id}'> {name}</a>\n"
            f"<b>🆔 User ID:</b> <code>{chat_id}</code>\n"
            f"<b>💰 Amount:</b> Rs {amount}/-\n"
            f"{link_lines}\n"
        )

    final_report = "\n\n".join(messages)
    await update.message.reply_text(
        f"📜 <b>Not Downloaded Reports:</b>\n\n{final_report}\n"
        f"✂️ <b>To delete a report, send the User ID now.</b>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    return WAITING_FOR_DELETE_ID

async def delete_user_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.text.strip()
    report_links = load_report_links()  # Refresh from Firebase
    if user_id in report_links:
        remove_report_links(user_id)
        load_report_links()  # Refresh from Firebase
        await update.message.reply_text(f"🗑️ Report data for user ID {user_id} has been deleted.")
    else:
        await update.message.reply_text(f"⚠️ No data found for user ID {user_id}.")
    return ConversationHandler.END

# ------------------ Admin Command: Show Users ------------------ #
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    users = load_user_data()
    if not users:
        await update.message.reply_text("📭 No users found in the database.")
        return

    messages = []
    for uid, info in users.items():
        name = info.get("name", "Unknown")
        business_chat_id = info.get("business_chat_id", "None")
        messages.append(f"<b>👤 Name:</b> <a href='tg://user?id={business_chat_id}'> {name}</a>\n"
                        f"🆔 <b>business_chat_id:</b> <code>{business_chat_id}</code>\n")

    final_msg = "\n".join(messages)
    await update.message.reply_text(
        f"📋 <b>Users who sent their articles recently:</b>\n\n{final_msg}\n"
        f"✂️ <b>To delete a user, send their business_chat_id now.</b>",
        parse_mode="HTML"
    )

    return WAITING_FOR_DELETE_USER_ID

async def delete_user_by_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_to_delete = update.message.text.strip()
    users = load_user_data()

    for uid, info in users.items():
        if str(info.get("business_chat_id")) == chat_id_to_delete:
            remove_user_data(uid)
            await update.message.reply_text(f"🗑️ User with business_chat_id {chat_id_to_delete} has been deleted.")
            return ConversationHandler.END

    await update.message.reply_text(f"⚠️ No user found with business_chat_id {chat_id_to_delete}.")
    return ConversationHandler.END

# ------------------ Help Command ------------------ #
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """
Commands available:
/start - Check whether your report is ready or not
/upload - Upload report (Admin only)
/cancel - Cancel the current process (Admin only)
/show_reports - Show list of all reports not downloaded by users (Admin only)
/show_users - Show all users who sent their articles recently (Admin only)
/help - Show this help message
"""
    )

def main():
    """ Main function to start the bot """
    application = Application.builder().token(TOKEN).build()

    # Attach business update handler in a separate group so it doesn’t block others
    application.add_handler(
        MessageHandler(
            filters.Document.ALL & filters.UpdateType.BUSINESS_MESSAGE,
            handle_all_updates
        ),
        group=0
    )

    # Upload file conversation handler
    conv_handler_upload = ConversationHandler(
        entry_points=[CommandHandler("upload", upload)],
        states={
            WAITING_FOR_UPLOAD_OPTION: [
                CallbackQueryHandler(upload_option_handler),
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),  # Handle Cancel button
            ],
            WAITING_FOR_MULTIPLE_FILES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_file_count),
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),  # Handle Cancel button
            ],
            COLLECTING_FILES: [
                MessageHandler(filters.Document.ALL, handle_multiple_files),
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),  # Handle Cancel button
            ],
            WAITING_FOR_PAYMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_payment),
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),  # Handle Cancel button
            ],
            WAITING_FOR_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
                CallbackQueryHandler(handle_user_suggestion, pattern=r'^user_select\|'),
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
            ],
            WAITING_FOR_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user),
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),  # Handle Cancel button
            ],
        },
        fallbacks=[
            CommandHandler("start", start),  # Reset conversation if /start is issued
            CommandHandler("upload", upload),  # Reset conversation if /upload is issued again
            CommandHandler("help", help_command),  # Reset conversation if /help is issued
            # CommandHandler("admin_commands", admin_commands),  # Reset conversation if /admin_commands is issued
            MessageHandler(filters.COMMAND, cancel_upload),  # Reset conversation on any other command
        ],
    )

    # Delete links conversation handler
    conv_handler_delete = ConversationHandler(
        entry_points=[CommandHandler("show_reports", show_reports)],
        states={
            WAITING_FOR_DELETE_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_user_report)
            ]
        },
        fallbacks=[
            CommandHandler("start", start),  # Reset conversation if /start is issued
            CommandHandler("upload", upload),  # Reset conversation if /upload is issued again
            CommandHandler("help", help_command),  # Reset conversation if /help is issued
            # CommandHandler("admin_commands", admin_commands),  # Reset conversation if /admin_commands is issued
            MessageHandler(filters.COMMAND, cancel_upload),  # Reset conversation on any other command
        ],
    )

    conv_handler_show_users = ConversationHandler(
        entry_points=[CommandHandler("show_users", show_users)],
        states={
            WAITING_FOR_DELETE_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_user_by_chat_id)
            ]
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("upload", upload),
            CommandHandler("help", help_command),
            MessageHandler(filters.COMMAND, cancel_upload),
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler_upload)
    application.add_handler(conv_handler_delete)
    application.add_handler(conv_handler_show_users)
    application.add_handler(CallbackQueryHandler(button_handler))


    application.run_polling()

if __name__ == "__main__":
    main()
