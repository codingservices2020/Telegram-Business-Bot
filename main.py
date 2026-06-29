import os
import json
import logging
# from locale import currency

import requests
import httpx
import uuid
import asyncio
import fitz  # PyMuPDF
from PyPDF2 import PdfReader, PdfWriter  # Required for sign_pdf
from firebase_db import save_report_links, load_report_links, remove_report_links, save_user_data, load_user_data, get_latest_users, remove_user_data
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyParameters
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler#, CallbackContext, TypeHandler
from google_drive_files import upload_and_get_link


import warnings
from keep_alive import keep_alive
keep_alive()

from dotenv import load_dotenv
load_dotenv()

warnings.filterwarnings("ignore", category=DeprecationWarning)
# Enable logging to both console and a file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_log.txt", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
TOKEN = os.getenv("TOKEN")
SHORTIO_LINK_API_KEY = os.getenv("SHORTIO_LINK_API_KEY")
SHORTIO_DOMAIN = os.getenv("SHORTIO_DOMAIN")
PDF_PASSWORD = os.getenv("PDF_PASSWORD")
SIGN_TEXT_1 = os.getenv("SIGN_TEXT_1")
URL = f'https://api.telegram.org/bot{TOKEN}/getUpdates'
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
RAZORPAY_PAYMENT_URL = os.getenv('RAZORPAY_PAYMENT_URL')
RAZORPAY_USD_PAYMENT_URL = os.getenv('RAZORPAY_USD_PAYMENT_URL') or os.getenv('RAZORPAY_PAYMENT_URL')
PAYMENT_CAPTURED_DETAILS_URL = os.getenv('PAYMENT_CAPTURED_DETAILS_URL')


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
# Define states for conversation handler
WAITING_FOR_UPLOAD_OPTION, WAITING_FOR_MULTIPLE_FILES, COLLECTING_FILES = range(100, 103)
WAITING_FOR_PAYMENT, WAITING_FOR_USER = range(103, 105)
WAITING_FOR_DELETE_ID = 105
WAITING_FOR_SEARCH_INPUT = 106  # 🔍 New state for search
WAITING_FOR_NAME = 107  # add this line
WAITING_FOR_DELETE_USER_ID = 108  # for /show_users command
WAITING_FOR_SIGN_CONFIRMATION = 109
WAITING_FOR_REGION = 110  # Update the states to include region selection




# Load existing file data or initialize an empty dictionary
DATA_FILE = "file_data.json"
report_links = {}
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
UPLOAD_BUTTON = "⬆️ Upload"
SHOW_REPORTS_BUTTON = "📜 Show Reports"
SHOW_USERS_BUTTON = "👥 Show Users"


def is_valid_url(url):
    """Check if the URL is non-empty, a string, and starts with a valid protocol."""
    return isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))
try:
    report_links = load_report_links()
except Exception as e:
    print(f"Error loading report links from Firebase at startup: {e}")
    report_links = {}

def save_data():
    """Save the file data to JSON."""
    with open(DATA_FILE, "w") as f:
        json.dump(report_links, f, indent=4)

def edit_pdf(input_pdf, output_pdf, output_pdf_name, selected_text, do_sign):
    doc = fitz.open(input_pdf)
    page = doc[0]

    # ================= VISUAL SIGNATURE (ONLY IF YES) =================
    if do_sign:
        # Hide original area
        hide_rect = fitz.Rect(30.0, 304.0, 600, 410)
        page.draw_rect(hide_rect, color=(1, 1, 1), fill=(1, 1, 1))

        # Big visual name/signature
        rect = fitz.Rect(36, 329, 600, 400)
        page.insert_textbox(
            rect,
            selected_text,
            fontsize=23,
            fontname="helvetica-bold",
            color=(0, 0, 0),
            align=0
        )

        # File name text
        page.insert_text(
            (36, 383),
            output_pdf_name,
            fontsize=17,
            fontname="helvetica-bold",
            color=(0, 0, 0)
        )

    # ================= FOOTER TEXT (ALWAYS EXECUTE) =================
    if selected_text != SIGN_TEXT_1:
        page.insert_text(
            (402, 560),
            f"Digitally signed by {selected_text}",
            fontsize=8,
            fontname="times-italic",
            color=(1, 0, 0)
        )
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

async def verify_payment(chat_id, payment_amount):
    max_retries = 3
    retry_delay = 2.0  # seconds
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Verifying payment for chat_id={chat_id}, amount={payment_amount} (attempt {attempt + 1}/{max_retries})")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(PAYMENT_CAPTURED_DETAILS_URL)
                response.raise_for_status()
                data = response.json()
                
                if isinstance(data, list):
                    for entry in data:
                        if entry.get('user_id') == str(chat_id):
                            if entry.get('amount') == str(payment_amount):
                                logger.info(f"Payment verified for user {chat_id}")
                                return True
                logger.info("No matching payment details found in SheetDB.")
                return False
        except httpx.HTTPStatusError as err:
            logger.warning(f"HTTP error during payment verification (attempt {attempt + 1}/{max_retries}): {err}")
        except httpx.RequestError as err:
            logger.warning(f"Request error / SSL error during payment verification (attempt {attempt + 1}/{max_retries}): {err}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)
            
    logger.error("Max retries exceeded or error occurred during payment verification.")
    return False

def shorten_url(long_url):
    BASE_URL="https://api.short.io/links/"     # Short.io API Endpoint
    # Headers
    headers = {
        "Authorization": SHORTIO_LINK_API_KEY,
        "Content-Type": "application/json"
    }
    # Payload
    data = {"domain": SHORTIO_DOMAIN,
            "originalURL": long_url,
            "title": "Test Link"
            }
    try:
        response = requests.post(BASE_URL, json=data, headers=headers, timeout=5)
        return response.json()["shortURL"]
    except Exception as e:
        print(f"Error shortening URL: {e}")
        return long_url


def process_all_files(context, do_sign):
    """Process all raw files with the given signing preference"""
    raw_files = context.user_data.get("raw_files", [])
    file_names = context.user_data.get("file_names", [])
    processed_files = []

    selected_text = os.getenv("SIGN_TEXT_1", "Default Signature Text")

    for i, (raw_file_path, original_name) in enumerate(zip(raw_files, file_names)):
        # Check if the file exists
        if not os.path.exists(raw_file_path):
            logger.error(f"File not found: {raw_file_path}")
            continue

        # Prepare filenames
        file_base, _ = os.path.splitext(original_name)
        edited_file_name = f"{file_base}{uuid.uuid4().hex[:1]}.pdf"
        edited_file_path = f"downloads/{edited_file_name}"

        # Edit the PDF
        edit_pdf(
            raw_file_path,
            edited_file_path,
            edited_file_name,
            selected_text,
            do_sign=do_sign
        )

        # Sign the edited PDF
        signed_file_path = sign_pdf(edited_file_path)
        signed_file_name = os.path.basename(signed_file_path)

        processed_files.append((signed_file_path, signed_file_name))

        # Clean up intermediate files
        for path in [raw_file_path, edited_file_path]:
            if os.path.exists(path):
                os.remove(path)

    # Clean up the raw files list since they've been processed
    context.user_data.pop("raw_files", None)
    context.user_data.pop("file_names", None)

    return processed_files

def build_reply_keyboard(buttons, one_time_keyboard=False, is_persistent=False):
    """Create a reply keyboard while staying compatible with older PTB versions."""
    try:
        return ReplyKeyboardMarkup(
            buttons,
            resize_keyboard=True,
            one_time_keyboard=one_time_keyboard,
            is_persistent=is_persistent
        )
    except TypeError:
        return ReplyKeyboardMarkup(
            buttons,
            resize_keyboard=True,
            one_time_keyboard=one_time_keyboard
        )


def get_admin_keyboard():
    return build_reply_keyboard(
        [
            [UPLOAD_BUTTON, SHOW_REPORTS_BUTTON],
            [SHOW_USERS_BUTTON, CANCEL_BUTTON],
        ],
        is_persistent=True
    )


def get_cancel_keyboard():
    return build_reply_keyboard([[CANCEL_BUTTON]], is_persistent=True)


def get_start_keyboard():
    return build_reply_keyboard([[START_BUTTON]], one_time_keyboard=True)


def inline_button(text, style=None, **kwargs):
    if style:
        kwargs["api_kwargs"] = {**kwargs.get("api_kwargs", {}), "style": style}
    return InlineKeyboardButton(text, **kwargs)


def remove_temp_file(file_path):
    if not file_path:
        return

    safe_roots = [
        os.path.abspath("downloads"),
        os.path.abspath(INPUT_FOLDER),
        os.path.abspath(OUTPUT_FOLDER),
    ]
    abs_path = os.path.abspath(file_path)
    if any(abs_path == root or abs_path.startswith(root + os.sep) for root in safe_roots):
        try:
            if os.path.exists(abs_path):
                os.remove(abs_path)
        except OSError as e:
            logger.warning(f"Failed to remove temporary file {abs_path}: {e}")


def cleanup_conversation_state(context):
    raw_files = context.user_data.get("raw_files", [])
    processed_files = context.user_data.get("files", [])
    single_file = context.user_data.get("file_path")

    for file_path in raw_files:
        remove_temp_file(file_path)
    for file_path, _ in processed_files:
        remove_temp_file(file_path)
    remove_temp_file(single_file)

    context.user_data.clear()


async def restore_admin_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    chat_id = update.effective_chat.id if update.effective_chat else ADMIN_ID
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_admin_keyboard()
    )


async def cancel_current_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    cleanup_conversation_state(context)
    await update.message.reply_text(
        "🚫 Current process cancelled.",
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END


async def handle_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received update: {update.to_dict()}")
    bm = None
    is_business = False
    if update.business_message:
        bm = update.business_message
        is_business = True
    elif update.message:
        bm = update.message

    if bm and bm.document:
        # Ignore documents sent by the admin (from_user.id is ADMIN_ID) or in the admin's private chat
        if (bm.from_user and bm.from_user.id == ADMIN_ID) or bm.chat.id == ADMIN_ID:
            logger.info("Ignoring document sent by ADMIN or in ADMIN chat")
            return

        # Check if the document is a Word or PDF file
        file_name = bm.document.file_name or ""
        is_word_or_pdf = file_name.lower().endswith(('.pdf', '.doc', '.docx'))
        if not is_word_or_pdf:
            logger.info(f"Ignoring document of unsupported type: {file_name}")
            return

        try:
            logger.info(f"📨 Document received (is_business={is_business}): {bm.document.file_name}")
            user_id = str(bm.chat.id)
            name = bm.chat.full_name if hasattr(bm.chat, 'full_name') and bm.chat.full_name else "Unknown"
            username = bm.chat.username or "unknown"

            # Save user data to Firestore first
            save_user_data(
                user_id=user_id,
                name=name,
                username=username,
                business_chat_id=bm.chat.id,
                business_connection_id=bm.business_connection_id if is_business else None
            )
            logger.info(f"Successfully saved user data for {name} ({user_id})")

            # Reply parameters MUST NOT contain chat_id for business connections
            # To be 100% safe, we do not quote business messages to avoid any Telegram API validation/quoting limitations.
            reply_params = None if is_business else ReplyParameters(message_id=bm.message_id)

            try:
                await context.bot.send_message(
                    chat_id=bm.chat.id,
                    text=(
                        "🤖*Thank you for submitting your article*🙏\n\n"
                        "✅Kindly wait while your report is being prepared. I will notify you as soon as it is ready for download."
                    ),
                    parse_mode="Markdown",
                    business_connection_id=bm.business_connection_id if is_business else None,
                    reply_parameters=reply_params
                )
                logger.info("Sent thank-you message via business connection")
            except Exception as conn_err:
                logger.warning(f"Failed to reply via business connection, attempting direct send: {conn_err}")
                # Fallback to direct send (only works if user has started the bot)
                await context.bot.send_message(
                    chat_id=bm.chat.id,
                    text=(
                        "🤖*Thank you for submitting your article*🙏\n\n"
                        "✅Kindly wait while your report is being prepared. I will notify you as soon as it is ready for download."
                    ),
                    parse_mode="Markdown",
                    reply_parameters=None
                )
                logger.info("Sent thank-you message directly (fallback)")

        except Exception as e:
            logger.error(f"Error replying to document upload: {e}")
            # Real-time error notification to the Admin with troubleshooting tip
            err_msg = str(e)
            admin_advice = ""
            if "business_peer_invalid" in err_msg.lower():
                admin_advice = "\n\n💡 *Tip:* Please check if your bot has 'Can Reply' toggled ON in your Telegram app: *Settings -> Business -> Chatbots*."
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ *Error in document handler:*\n`{err_msg}`{admin_advice}\n\nUser ID: `{bm.chat.id}`",
                    parse_mode="Markdown"
                )
            except Exception as notify_err:
                logger.error(f"Failed to notify admin of error: {notify_err}")



async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current admin conversation and reset state."""
    return await cancel_current_conversation(update, context)


async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return ConversationHandler.END

    await update.message.reply_text(
        "♻️ Upload Process has Started...",
        reply_markup=get_cancel_keyboard()
    )
    # Clear any old data from previous sessions
    cleanup_conversation_state(context)
    # Ask for region first
    keyboard = [
        [InlineKeyboardButton("🇮🇳 Indian", callback_data="region_indian")],
        [InlineKeyboardButton("🌍 Non-Indian", callback_data="region_non_indian")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🌍 *Select your region:*\n\n"
        "1. 🇮🇳 Indian - Use Razorpay (INR) for payment\n"
        "2. 🌍 Non-Indian - Use Razorpay (USD) for payment",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return WAITING_FOR_REGION


# Add region selection handler
async def handle_region_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "region_indian":
        context.user_data["region"] = "indian"
        context.user_data["payment_url"] = RAZORPAY_PAYMENT_URL
        region_text = "🇮🇳 Indian (Razorpay INR)"
    else:
        context.user_data["region"] = "non_indian"
        context.user_data["payment_url"] = RAZORPAY_USD_PAYMENT_URL
        region_text = "🌍 Non-Indian (Razorpay USD)"

    await query.edit_message_text(f"✅ Region selected: {region_text}", parse_mode="Markdown")

    # Now show file upload options
    keyboard = [
        [inline_button("📁 One File", callback_data="upload_1", style="success")],
        [inline_button("📂 Two Files", callback_data="upload_2", style="primary")],
        [inline_button("📦 More than Two Files", callback_data="upload_more", style="danger")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=query.message.chat.id,
        text="How many files do you want to upload?",
        reply_markup=reply_markup
    )

    return WAITING_FOR_UPLOAD_OPTION

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the admin Cancel button."""
    return await cancel_current_conversation(update, context)

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
    if not user_input.isdigit() or int(user_input) <= 2:
        await update.message.reply_text("❌ Please enter a number greater than 2.")
        return WAITING_FOR_MULTIPLE_FILES

    context.user_data["upload_limit"] = int(user_input)
    await update.message.reply_text(f"📤 Please send {user_input} files one by one.")
    return COLLECTING_FILES


async def handle_multiple_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document

    if not document:
        await update.message.reply_text("Please send a valid file.")
        return COLLECTING_FILES

    file = await context.bot.get_file(document.file_id)
    os.makedirs("downloads", exist_ok=True)

    # Step 1: Download original file
    original_file_path = f"downloads/{document.file_name}"
    await file.download_to_drive(original_file_path)

    # Store the raw file path instead of processing it immediately
    context.user_data.setdefault("raw_files", []).append(original_file_path)
    context.user_data.setdefault("file_names", []).append(document.file_name)

    if context.user_data["region"] == "indian":
        currency = "Rs"
    else:
        currency = "$"
    # Step 7: Check if all files are received
    if len(context.user_data.get("raw_files", [])) >= context.user_data["upload_limit"]:
        await update.message.reply_text(f"✅ All files received. \n"
                                        f"Now enter payment amount (in {currency}):")
        return WAITING_FOR_PAYMENT

    await update.message.reply_text(
        f"📒 File *{document.file_name}* received. Send next file...",
        parse_mode="Markdown"
    )
    return COLLECTING_FILES



async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handle file upload from users """
    document = update.message.document
    if not document:
        await update.message.reply_text("No document detected. Please try again.")
        return WAITING_FOR_UPLOAD_OPTION
    await update.message.reply_text(
        "♻️ Uploading Report ....",
        reply_markup=get_cancel_keyboard()
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
    suggestions = get_latest_users()

    logger.info(
        f"Suggestions loaded: {suggestions}"
    )
    context.user_data["amount"] = amount
    buttons = [[InlineKeyboardButton(f"{name} ({uid})", callback_data=f"user_select|{uid}|{name}")]
               for uid, name in suggestions]

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

    await update.message.reply_text(
        "✍️ Please enter the name of the user (or tap below):",
        reply_markup=reply_markup
    )
    return WAITING_FOR_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["name"] = name

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data="sign_yes"),
            InlineKeyboardButton("❌ No", callback_data="sign_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🖊️ *Do you want to Sign this report?*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return WAITING_FOR_SIGN_CONFIRMATION


async def handle_sign_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    do_sign = (query.data == "sign_yes")  # True if "Yes", False if "No"
    context.user_data["do_sign"] = do_sign

    # DEBUGGING: Log the choice
    logger.info(f"DEBUG: User chose {'YES' if do_sign else 'NO'} for signing")

    await query.edit_message_text(
        "✅ Report will be signed." if do_sign
        else "❌ Report will NOT be signed."
    )

    # Process all files with the signing preference
    try:
        processed_files = process_all_files(context, do_sign)

        if not processed_files:
            cleanup_conversation_state(context)
            await query.edit_message_text("❌ No files could be processed.")
            await restore_admin_keyboard(update, context, "Admin keyboard restored.")
            return ConversationHandler.END

        context.user_data["files"] = processed_files
        logger.info(f"DEBUG: Processed {len(processed_files)} files with do_sign={do_sign}")
    except Exception as e:
        logger.error(f"Error processing files: {e}")
        cleanup_conversation_state(context)
        await query.edit_message_text("❌ Error processing files.")
        await restore_admin_keyboard(update, context, "Admin keyboard restored.")
        return ConversationHandler.END

    # 🔥 DIRECTLY CONTINUE (NO USER ID QUESTION)
    return await receive_user(update, context)


async def handle_user_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, uid, name = query.data.split('|')

    context.user_data["name"] = name
    context.user_data["user_id_from_button"] = uid

    # Retrieve and cache the user's business connection ID before they are deleted
    users = load_user_data()
    user_info = users.get(str(uid), {})
    business_conn_id = user_info.get("business_connection_id")
    context.user_data["business_connection_id"] = business_conn_id

    # Immediately delete the user from the Firestore suggestions list
    try:
        remove_user_data(uid)
        logger.info(f"User {name} ({uid}) removed from suggestions list.")
    except Exception as e:
        logger.error(f"Error removing user {uid} from suggestions list: {e}")

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data="sign_yes"),
            InlineKeyboardButton("❌ No", callback_data="sign_no"),
        ]
    ]

    await query.edit_message_text(
        f"👤 Selected: {name} ({uid})\n\n"
        "🖊️ *Do you want to Sign this report?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    return WAITING_FOR_SIGN_CONFIRMATION


async def receive_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # 🔥 User ID ALWAYS comes from suggestion
    user_id = context.user_data.get("user_id_from_button")

    if not user_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ User ID not found.",
            reply_markup=get_admin_keyboard()
        )
        cleanup_conversation_state(context)
        return ConversationHandler.END

    # Use the cached business connection ID first; fallback to database lookup if not cached
    business_conn_id = context.user_data.get("business_connection_id")
    if not business_conn_id:
        users = load_user_data()
        business_conn_id = users.get(str(user_id), {}).get("business_connection_id")
        context.user_data["business_connection_id"] = business_conn_id

    amount = context.user_data.get("amount")
    name = context.user_data.get("name", "Unknown")
    region = context.user_data.get("region", "indian")
    payment_url = context.user_data.get("payment_url", RAZORPAY_PAYMENT_URL)

    if "files" not in context.user_data or not context.user_data["files"]:
        await context.bot.send_message(
            chat_id=chat_id,
            text="🚫 No files found.",
            reply_markup=get_admin_keyboard()
        )
        cleanup_conversation_state(context)
        return ConversationHandler.END

    await context.bot.send_message(
        chat_id=chat_id,
        text="♻️ Uploading file to Google Drive...",
        reply_markup=get_cancel_keyboard()
    )

    links = []
    for path, _ in context.user_data["files"]:
        link = await upload_to_drive(path, name, user_id)
        if link:
            links.append(link)

    if not links:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Upload failed.",
            reply_markup=get_admin_keyboard()
        )
        cleanup_conversation_state(context)
        return ConversationHandler.END

    # short_links =
    short_links = []

    for link in links:
        short = shorten_url(link)

        if short and not short.lower().startswith("error"):
            short_links.append(short)
        else:
            print(f"URL shortener failed: {short}")
            short_links.append(link)  # use original Google Drive link

    save_report_links(user_id, amount, short_links, region, business_connection_id=business_conn_id)  # Update this function to store region

    global report_links
    report_links = load_report_links()

    links_formatted = "\n".join(
        [f"📥 File {i + 1}: {link}" for i, link in enumerate(report_links[user_id]["links"])]
    )

    if region == "indian":
        payment_amount = f"Rs {amount}/-"
    else:
        payment_amount = f"${amount}"

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"<b>🔰REPORT UPLOADED SUCCESSFULLY!🔰</b>\n\n"
            f"👤 <b>Name:</b> <a href='tg://user?id={user_id}'>{name}</a>\n"
            f"💰 <b>Amount:</b> {payment_amount}\n\n"
            f"<b>⬇️ Report Download Links:</b>\n{links_formatted}"
        ),
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )

    # Unify payment flow using Razorpay (INR or USD)
    payment_button = inline_button(
        f"🚀Click here to Pay {payment_amount}🚀",
        callback_data=f"start_{user_id}",
        style="success"
    )

    reply_markup = InlineKeyboardMarkup([[payment_button]])

    try:
        await context.bot.send_message(
            business_connection_id=business_conn_id,
            chat_id=user_id,
            text=f"<b>🔰REPORT IS READY🔰</b>\n\n"
                 f"Please, click on the button below and make the payment of"
                 f" <b>{payment_amount}</b> to download your report.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.info(f"Sent report ready message to {user_id} via business connection")
    except Exception as conn_err:
        logger.warning(f"Failed sending report ready message to {user_id} via business connection: {conn_err}. Attempting direct send.")
        # Fallback to direct send
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<b>🔰REPORT IS READY🔰</b>\n\n"
                 f"Please, click on the button below and make the payment of"
                 f" <b>{payment_amount}</b> to download your report.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.info(f"Sent report ready message to {user_id} directly (fallback)")
    # remove_user_data(user_id)
    cleanup_conversation_state(context)
    return ConversationHandler.END

async def upload_to_drive(file_path, user_name, user_id):
    """
    Upload file to Google Drive and return direct download link
    """
    try:
        folder_name = f"{user_name} ({user_id})"

        # One-step upload + link
        drive_link = upload_and_get_link(
            file_path=file_path,
            folder_name=folder_name
        )

        return drive_link

    except Exception as e:
        logger.error(f"❌ Error uploading file to Google Drive: {e}")
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

    # Refresh report links from Firebase to ensure persistent data on Render/restarts
    global report_links
    report_links = load_report_links()

    # Check if there's any user's report
    if user_id in report_links:
        # Get region from report_links
        region = report_links[user_id].get('region', 'indian')
        amount = report_links[user_id].get('amount')
        business_conn_id = report_links[user_id].get("business_connection_id")

        if region == "indian":
            payment_amount = f"Rs {amount}/-"
            razorpay_url = RAZORPAY_PAYMENT_URL
            payment_method = "Razorpay (INR)"
        else:
            payment_amount = f"${amount}"
            razorpay_url = RAZORPAY_USD_PAYMENT_URL
            payment_method = "Razorpay (USD)"

        # Fallback to alternative env url if the selected one is invalid
        if not is_valid_url(razorpay_url):
            if is_valid_url(RAZORPAY_PAYMENT_URL):
                razorpay_url = RAZORPAY_PAYMENT_URL
            elif is_valid_url(RAZORPAY_USD_PAYMENT_URL):
                razorpay_url = RAZORPAY_USD_PAYMENT_URL
            else:
                razorpay_url = None

        download_button_text = "📥 Download Report"
        download_button = inline_button(
            download_button_text,
            callback_data=f"download_{user_id}",
            style="primary"
        )
        
        keyboard = []
        if is_valid_url(razorpay_url):
            payment_button = inline_button(
                f"🚀Make Payment of {payment_amount}🚀",
                url=razorpay_url,
                style="success"
            )
            keyboard.append([payment_button])
        keyboard.append([download_button])
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_message(
                business_connection_id=business_conn_id,
                chat_id=user_id,
                text=(
                    f"*🔰Report Downloader Bot🔰*\n\n"
                    f"To download your report, follow these two steps:\n"
                    f" 1️⃣ First click on the button below and make the payment of {payment_amount}.\n"
                    f" 2️⃣ After payment download the report.\n\n"
                    f" Your User ID: `{user_id}` (tap to copy)\n\n"
                    f"✅ Use this User ID on {payment_method} Payment Gateway."
                ),
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            logger.info(f"Sent report downloader message to {user_id} via business connection")
        except Exception as conn_err:
            logger.warning(f"Failed sending report downloader message to {user_id} via business connection: {conn_err}. Attempting direct send.")
            await message.reply_text(
                f"*🔰Report Downloader Bot🔰*"
                f"\n\nTo download your report, follow these two steps:"
                f"\n 1️⃣ First click on the button below and make the payment of {payment_amount}."
                f"\n 2️⃣ After payment download the report."
                f"\n\n Your User ID: `{user_id}` (tap to copy)\n\n"
                f"✅ Use this User ID on {payment_method} Payment Gateway.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    else:
        if chat_id == ADMIN_ID:
            await message.reply_text(
                "Admin keyboard is ready.",
                reply_markup=get_admin_keyboard()
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

    # Retrieve business connection ID to allow editing messages sent via business connection
    business_conn_id = None
    if query.message:
        business_conn_id = getattr(query.message, 'business_connection_id', None)
    if not business_conn_id:
        report_links = load_report_links()
        business_conn_id = report_links.get(str(user_id), {}).get("business_connection_id")
    if not business_conn_id:
        user_info = load_user_data().get(str(user_id), {})
        business_conn_id = user_info.get("business_connection_id")

    current_message_id = query.message.message_id if query.message else None

    # Helper function to edit message text, passing business_connection_id
    async def edit_msg(text, **kwargs):
        nonlocal current_message_id
        if query.message and current_message_id:
            extra_args = {}
            if business_conn_id:
                extra_args["business_connection_id"] = business_conn_id
            try:
                return await context.bot.edit_message_text(
                    chat_id=query.message.chat.id,
                    message_id=current_message_id,
                    text=text,
                    **extra_args,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"Failed to edit message {current_message_id} with error: {e}. Falling back to send + delete.")
                # Send the new message instead
                new_msg = await context.bot.send_message(
                    chat_id=query.message.chat.id,
                    text=text,
                    **extra_args,
                    **kwargs
                )
                # Attempt to delete the old message to clean up the chat
                try:
                    await context.bot.delete_message(
                        chat_id=query.message.chat.id,
                        message_id=current_message_id,
                        **extra_args
                    )
                except Exception as del_err:
                    logger.warning(f"Failed to delete old message {current_message_id}: {del_err}")
                
                if new_msg:
                    current_message_id = new_msg.message_id
                return new_msg
        else:
            return await query.edit_message_text(
                text=text,
                **kwargs
            )

    await edit_msg(f"♻️  Payment verifying. Please wait...")
    report_links = load_report_links() # Refresh from Firebase
    if user_id in report_links:
        region = report_links[user_id].get('region', 'indian')
        amount = report_links[user_id].get('amount')

        if region == "indian":
            payment_amount = f"Rs {amount}/-"
            razorpay_url = RAZORPAY_PAYMENT_URL
        else:
            payment_amount = f"${amount}"
            razorpay_url = RAZORPAY_USD_PAYMENT_URL

        # Fallback to alternative env url if the selected one is invalid
        if not is_valid_url(razorpay_url):
            if is_valid_url(RAZORPAY_PAYMENT_URL):
                razorpay_url = RAZORPAY_PAYMENT_URL
            elif is_valid_url(RAZORPAY_USD_PAYMENT_URL):
                razorpay_url = RAZORPAY_USD_PAYMENT_URL
            else:
                razorpay_url = None

        download_button = inline_button(
            "📥 Download Report",
            callback_data=f"download_{user_id}",
            style="primary"
        )
        keyboard = []
        if is_valid_url(razorpay_url):
            payment_button = inline_button(
                f"🚀Make Payment of {payment_amount}🚀",
                url=razorpay_url,
                style="success"
            )
            keyboard.append([payment_button])
        keyboard.append([download_button])
        reply_markup = InlineKeyboardMarkup(keyboard)

        invoice_amount = int(amount)
        # Both INR and USD regions are verified via the Razorpay payment gateway
        paid = await verify_payment(user_id, invoice_amount)

        if paid:
            links_formatted = "\n".join(
                [f"📥 File {i + 1}: {link}" for i, link in enumerate(report_links[user_id]["links"])])
            await edit_msg(
                f"<b>🔰PAYMENT VERIFIED🔰</b>\n\n"
                f"🙏Thank you for making the payment.\n\n"
                f"✅ Download your report by clicking on the link below.\n\n"
                f"<b>⬇️ Report Download Links:</b>\n{links_formatted}",
                parse_mode="HTML"
            )
            
            try:
                DELETED_CODES_URL = f"{PAYMENT_CAPTURED_DETAILS_URL}/amount/{invoice_amount}"
                response_del = requests.delete(url=DELETED_CODES_URL, timeout=5)
                response_del.raise_for_status()
                logger.info(f"Successfully deleted sheet entry for user {user_id}")
            except Exception as del_err:
                logger.warning(f"Failed to delete verified entry from SheetDB: {del_err}")

            # Get the business connection ID from the report data (which we saved in Firestore)
            business_conn_id = report_links.get(str(user_id), {}).get("business_connection_id")
            if not business_conn_id:
                user_info = load_user_data().get(str(user_id), {})
                business_conn_id = user_info.get("business_connection_id")

            try:
                await context.bot.send_message(
                    business_connection_id=business_conn_id,
                    chat_id=user_id,
                    text=f"*🔰JOIN & SHARE🔰*\n\n"
                         f"✅Please share and join our Telegram channel with your friends to stay updated "
                         f"about our products and services and also for weekly giveaways🎁\n\n"
                         f"❤️ Join our Telegram channel: https://t.me/+66qt38tocAI0ZWI1",
                    parse_mode="Markdown"
                )
                logger.info(f"Sent join & share message to {user_id} via business connection")
            except Exception as conn_err:
                logger.warning(f"Failed sending join & share message to {user_id} via business connection: {conn_err}. Attempting direct send.")
                # Fallback to direct send
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"*🔰JOIN & SHARE🔰*\n\n"
                         f"✅Please share and join our Telegram channel with your friends to stay updated "
                         f"about our products and services and also for weekly giveaways🎁\n\n"
                         f"❤️ Join our Telegram channel: https://t.me/+66qt38tocAI0ZWI1",
                    parse_mode="Markdown"
                )
                logger.info(f"Sent join & share message to {user_id} directly (fallback)")
            remove_user_data(user_id)
            remove_report_links(user_id)
            load_report_links()  # Refresh from Firebase

        else:
            await edit_msg(
                f"<b>❌ PAYMENT NOT VERIFIED YET ❌</b>\n\n"
                f"We could not verify your payment of <b>{payment_amount}</b> at this moment.\n\n"
                f"1️⃣ If you have not paid yet, please make the payment first using the button below.\n"
                f"2️⃣ If you have already paid, it may take 1-2 minutes to register. Please try clicking <b>📥 Download Report</b> again in a few moments.\n\n"
                f"✅ Need help? Contact Admin @coding_services.",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
    else:
        await edit_msg("⭕️ Your report is not ready. Please wait for some time!")


# ------------------ Admin Command: Show Reports ------------------ #
async def show_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return ConversationHandler.END

    report_links = load_report_links()  # Refresh from Firebase
    if not report_links:
        await update.message.reply_text(
            "📭 No pending reports found.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END

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
        disable_web_page_preview=True,
        reply_markup=get_admin_keyboard()
    )
    return WAITING_FOR_DELETE_ID

async def delete_user_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.text.strip()
    report_links = load_report_links()  # Refresh from Firebase
    if user_id in report_links:
        remove_report_links(user_id)
        load_report_links()  # Refresh from Firebase
        await update.message.reply_text(
            f"🗑️ Report data for user ID {user_id} has been deleted.",
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            f"⚠️ No data found for user ID {user_id}.",
            reply_markup=get_admin_keyboard()
        )
    return ConversationHandler.END

# ------------------ Admin Command: Show Users ------------------ #
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return ConversationHandler.END

    users = load_user_data()
    if not users:
        await update.message.reply_text(
            "📭 No users found in the database.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END

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
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )

    return WAITING_FOR_DELETE_USER_ID

async def delete_user_by_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_to_delete = update.message.text.strip()
    users = load_user_data()

    for uid, info in users.items():
        if str(info.get("business_chat_id")) == chat_id_to_delete:
            remove_user_data(uid)
            await update.message.reply_text(
                f"🗑️ User with business_chat_id {chat_id_to_delete} has been deleted.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END

    await update.message.reply_text(
        f"⚠️ No user found with business_chat_id {chat_id_to_delete}.",
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END

# ------------------ Help Command ------------------ #
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = get_admin_keyboard() if update.effective_user and update.effective_user.id == ADMIN_ID else None
    await update.message.reply_text(
        """
Commands available:
/start - Check whether your report is ready or not
/upload - Upload report (Admin only)
/cancel - Cancel the current process (Admin only)
/show_reports - Show list of all reports not downloaded by users (Admin only)
/show_users - Show all users who sent their articles recently (Admin only)
/help - Show this help message
""",
        reply_markup=reply_markup
    )

async def main():
    """ Main function to start the bot """
    application = Application.builder().token(TOKEN).build()
    admin_button_filter = filters.Text([
        UPLOAD_BUTTON,
        SHOW_REPORTS_BUTTON,
        SHOW_USERS_BUTTON,
        CANCEL_BUTTON,
    ])

    # Attach business update handler in a separate group so it doesn’t block others
    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_all_updates
        ),
        group=1
    )

    # Upload file conversation handler
    conv_handler_upload = ConversationHandler(
        entry_points=[
            CommandHandler("upload", upload),
            MessageHandler(filters.Text([UPLOAD_BUTTON]), upload),
        ],
        states={
            WAITING_FOR_REGION: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                CallbackQueryHandler(handle_region_selection, pattern="^region_"),
            ],
            WAITING_FOR_UPLOAD_OPTION: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                CallbackQueryHandler(upload_option_handler),
            ],
            WAITING_FOR_MULTIPLE_FILES: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_file_count),
            ],
            COLLECTING_FILES: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                MessageHandler(filters.Document.ALL, handle_multiple_files),
            ],
            WAITING_FOR_PAYMENT: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_payment),
            ],
            WAITING_FOR_NAME: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                CallbackQueryHandler(handle_user_suggestion, pattern=r'^user_select\|'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
            ],
            WAITING_FOR_SIGN_CONFIRMATION: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                CallbackQueryHandler(handle_sign_confirmation, pattern="^sign_"),
            ],
            WAITING_FOR_USER: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", handle_cancel),
            CommandHandler("start", start),  # Reset conversation if /start is issued
            CommandHandler("upload", upload),  # Reset conversation if /upload is issued again
            CommandHandler("help", help_command),  # Reset conversation if /help is issued
            # CommandHandler("admin_commands", admin_commands),  # Reset conversation if /admin_commands is issued
            MessageHandler(filters.COMMAND, cancel_upload),  # Reset conversation on any other command
        ],
    )

    # Delete links conversation handler
    conv_handler_delete = ConversationHandler(
        entry_points=[
            CommandHandler("show_reports", show_reports),
            MessageHandler(filters.Text([SHOW_REPORTS_BUTTON]), show_reports),
        ],
        states={
            WAITING_FOR_DELETE_ID: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~admin_button_filter, delete_user_report)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", handle_cancel),
            CommandHandler("start", start),  # Reset conversation if /start is issued
            CommandHandler("upload", upload),  # Reset conversation if /upload is issued again
            CommandHandler("help", help_command),  # Reset conversation if /help is issued
            # CommandHandler("admin_commands", admin_commands),  # Reset conversation if /admin_commands is issued
            MessageHandler(filters.COMMAND, cancel_upload),  # Reset conversation on any other command
        ],
    )

    conv_handler_show_users = ConversationHandler(
        entry_points=[
            CommandHandler("show_users", show_users),
            MessageHandler(filters.Text([SHOW_USERS_BUTTON]), show_users),
        ],
        states={
            WAITING_FOR_DELETE_USER_ID: [
                MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~admin_button_filter, delete_user_by_chat_id)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", handle_cancel),
            CommandHandler("start", start),
            CommandHandler("upload", upload),
            CommandHandler("help", help_command),
            MessageHandler(filters.COMMAND, cancel_upload),
        ],
    )

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Exception while handling an update:", exc_info=context.error)

    application.add_error_handler(error_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    # CallbackQueryHandler(handle_cancel, pattern="^cancel_upload$")
    application.add_handler(conv_handler_upload)
    application.add_handler(conv_handler_delete)
    application.add_handler(conv_handler_show_users)
    application.add_handler(CommandHandler("cancel", handle_cancel))
    application.add_handler(MessageHandler(filters.Text([CANCEL_BUTTON]), handle_cancel))
    application.add_handler(CallbackQueryHandler(button_handler))


    # application.run_polling()

    await application.initialize()
    await application.bot.delete_webhook(
        drop_pending_updates=True
    )
    await application.start()
    await application.updater.start_polling(
        allowed_updates=[
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
            "inline_query",
            "chosen_inline_result",
            "callback_query",
            "shipping_query",
            "pre_checkout_query",
            "poll",
            "poll_answer",
            "my_chat_member",
            "chat_member",
            "chat_join_request",
            "chat_boost",
            "removed_chat_boost",
            "message_reaction",
            "message_reaction_count",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
            "purchased_paid_media"
        ]
    )  # 🔥 KEEP RUNNING

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
