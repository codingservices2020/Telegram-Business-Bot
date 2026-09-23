import sys
import subprocess
import os

# Auto-install dependencies if running in an environment that lacks them
try:
    import requests
    import httpx
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    import PyPDF2
    import telegram
    import firebase_admin
    import dotenv
except ModuleNotFoundError:
    print("Warning: Missing required packages. Installing dependencies...")
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        req_path = os.path.join(script_dir, "requirements.txt")
        try:
            # Try with --break-system-packages (for uv and PEP 668 managed environments)
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path, "--break-system-packages"])
        except subprocess.CalledProcessError:
            # Fallback for older python/pip versions
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])
    except Exception as e:
        print(f"Error installing dependencies: {e}", file=sys.stderr)
        sys.exit(1)

from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*The `fitz` API is deprecated.*")
warnings.filterwarnings("ignore", category=UserWarning, module="fitz")

import json
import logging

# Enable logging to both console and a file immediately
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_log.txt", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# from locale import currency

import io
import requests
import httpx
import uuid
import asyncio
try:
    import pymupdf as fitz
except ImportError:
    import fitz
from PyPDF2 import PdfReader, PdfWriter  # Required for sign_pdf
from firebase_db import save_report_links, load_report_links, remove_report_links, save_user_data, load_user_data, \
    get_latest_users, remove_user_data
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyParameters, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, \
    CallbackQueryHandler  # , CallbackContext, TypeHandler

# Cloud Storage Providers (Google Drive primary, pCloud fallback)
google_drive_files = None
try:
    import google_drive_files
    logger.info("✅ Google Drive module initialized successfully.")
except Exception as e:
    logger.error(f"❌ Failed to load google_drive_files: {e}", exc_info=True)

pcloud_utils = None
try:
    import pcloud_utils
    logger.info("✅ pCloud module initialized successfully.")
except Exception as e:
    logger.error(f"❌ Failed to load pcloud_utils: {e}", exc_info=True)


from keep_alive import keep_alive

keep_alive()

# Load environment variables
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
PDF_PASSWORD = os.getenv("PDF_PASSWORD")
SIGN_TEXT_1 = os.getenv("SIGN_TEXT_1")
URL = f'https://api.telegram.org/bot{TOKEN}/getUpdates'
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
RAZORPAY_PAYMENT_URL = os.getenv('RAZORPAY_PAYMENT_URL')
RAZORPAY_USD_PAYMENT_URL = os.getenv('RAZORPAY_USD_PAYMENT_URL') or os.getenv('RAZORPAY_PAYMENT_URL')
PAYMENT_CAPTURED_DETAILS_URL = os.getenv('PAYMENT_CAPTURED_DETAILS_URL')
admin_id = os.getenv("ADMIN_ID")
if not admin_id:
    raise RuntimeError("ADMIN_ID is missing from .env")
ADMIN_ID = int(admin_id)

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

# Custom Emoji HTML strings for messages
UPLOAD_EMOJI = '<tg-emoji emoji-id="6109429315990981798">⬆️</tg-emoji>'
REPORTS_EMOJI = '<tg-emoji emoji-id="5282843764451195532">📜</tg-emoji>'
USERS_EMOJI = '<tg-emoji emoji-id="5461117441612462242">👥</tg-emoji>'
CANCEL_EMOJI = '<tg-emoji emoji-id="5240241223632954241">🚫</tg-emoji>'
CROSS_EMOJI = '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji>'
RECYCLE_EMOJI = '<tg-emoji emoji-id="4967897119760319376">♻️</tg-emoji>'
BOT_EMOJI = '<tg-emoji emoji-id="5372981976804366741">🤖</tg-emoji>'
GREEN_TICK_EMOJI = '<tg-emoji emoji-id="6003394583566749782">✅</tg-emoji>'
RED_TICK_EMOJI = '<tg-emoji emoji-id="6006039858219324431">✅</tg-emoji>'
NAMASTE_EMOJI = '<tg-emoji emoji-id="5472189549473963781">🙏</tg-emoji>'
WARNING_EMOJI = '<tg-emoji emoji-id="5420323339723881652">⚠️</tg-emoji>'
FIRE_EMOJI = '<tg-emoji emoji-id="5424972470023104089">🔥</tg-emoji>'
CRACKER_EMOJI = '<tg-emoji emoji-id="5276032951342088188">💥</tg-emoji>'
MSWORD_EMOJI = '<tg-emoji emoji-id="5370845518337416649">📝</tg-emoji>'
GOOGLE_DRIVE_EMOJI = '<tg-emoji emoji-id="5372878055775683161">📄</tg-emoji>'
PDF_SYMBOL_EMOJI = '<tg-emoji emoji-id="5316632894939093711">📄</tg-emoji>'
PDF_FILE_EMOJI = '<tg-emoji emoji-id="5280652918813374349">📄</tg-emoji>'
SEND_FILE_EMOJI = '<tg-emoji emoji-id="5445355530111437729">📄</tg-emoji>'
MONEY_EMOJI = '<tg-emoji emoji-id="5224257782013769471">💸</tg-emoji>'
WORLD_EMOJI = '<tg-emoji emoji-id="5399898266265475100">🌍</tg-emoji>'
INDIA_EMOJI = '<tg-emoji emoji-id="6109380284644329775">🇮🇳</tg-emoji>'
TELEGRAM_EMOJI = '<tg-emoji emoji-id="5165976888283234815">Telegram</tg-emoji>'


# Button texts and KeyboardButton definitions with Telegram Custom Emojis
CANCEL_BUTTON_TEXT = "Cancel"
CANCEL_BUTTON = KeyboardButton(CANCEL_BUTTON_TEXT, icon_custom_emoji_id="5240241223632954241")

START_BUTTON = f"{BOT_EMOJI} Start the Bot"

UPLOAD_BUTTON_TEXT = "Upload"
UPLOAD_BUTTON = KeyboardButton(UPLOAD_BUTTON_TEXT, icon_custom_emoji_id="6109429315990981798")

SHOW_REPORTS_BUTTON_TEXT = "Show Reports"
SHOW_REPORTS_BUTTON = KeyboardButton(SHOW_REPORTS_BUTTON_TEXT, icon_custom_emoji_id="5282843764451195532")

SHOW_USERS_BUTTON_TEXT = "Show Users"
SHOW_USERS_BUTTON = KeyboardButton(SHOW_USERS_BUTTON_TEXT, icon_custom_emoji_id="5461117441612462242")



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


async def is_user_subscribed(context: ContextTypes.DEFAULT_TYPE, channel_id, user_id) -> bool:
    """Check if a user is already a member/admin/owner of the specified channel."""
    target_channel = channel_id or os.getenv("CHANNEL_ID")
    if not target_channel:
        try:
            load_dotenv(dotenv_path=ENV_PATH, override=True)
            target_channel = os.getenv("CHANNEL_ID")
        except Exception:
            pass

    if not target_channel:
        target_channel = "-1001884223394"

    if isinstance(target_channel, str):
        target_channel = target_channel.strip().strip("'\"")

    # If it's a URL like https://t.me/username, extract @username
    if isinstance(target_channel, str) and "t.me/" in target_channel:
        part = target_channel.split("t.me/")[-1].strip("/")
        if not part.startswith("+"):
            target_channel = f"@{part}"

    try:
        user_id_int = int(str(user_id).strip())
    except (ValueError, TypeError):
        logger.warning(f"Invalid user_id for subscription check: {user_id}")
        return False

    # Candidate representations for Telegram channel ID
    channel_candidates = []
    if isinstance(target_channel, int):
        channel_candidates.append(target_channel)
        if target_channel > 0:
            channel_candidates.append(int(f"-100{target_channel}"))
    elif isinstance(target_channel, str):
        if target_channel.startswith("@"):
            channel_candidates.append(target_channel)
        elif target_channel.lstrip("-").isdigit():
            val = int(target_channel)
            channel_candidates.append(val)
            if val > 0:
                channel_candidates.append(int(f"-100{val}"))
            elif not target_channel.startswith("-100"):
                channel_candidates.append(int(f"-100{target_channel.lstrip('-')}"))
        else:
            channel_candidates.append(target_channel)

    member = None
    last_err = None
    successful_channel = None

    for cand in channel_candidates:
        try:
            member = await context.bot.get_chat_member(chat_id=cand, user_id=user_id_int)
            successful_channel = cand
            break
        except Exception as e:
            last_err = e
            logger.debug(f"get_chat_member failed with candidate {cand}: {e}")

    if member is None:
        logger.warning(f"⚠️ Error checking channel membership for user {user_id} in channel {target_channel}: {last_err}")
        return False

    status = getattr(member, 'status', None)
    if hasattr(status, 'value'):
        status_val = str(status.value).lower()
    else:
        status_val = str(status).lower() if status else ""

    type_name = type(member).__name__.lower()
    logger.info(f"Channel membership check: user_id={user_id}, channel={successful_channel}, status='{status_val}', type='{type_name}'")

    if any(k in status_val for k in ["member", "administrator", "creator", "owner"]) or any(k in type_name for k in ["member", "administrator", "owner"]):
        if "left" not in status_val and "kicked" not in status_val and "banned" not in status_val:
            return True

    if "restricted" in status_val:
        return getattr(member, 'is_member', True)

    return False


async def verify_payment(chat_id, payment_amount):
    max_retries = 3
    retry_delay = 2.0  # seconds

    def _matches_user(entry, target_id):
        target_str = str(target_id).strip()
        # 1. Check known keys that may hold user ID / chat ID / telegram ID
        for key in ('user_id', '.', 'chat_id', 'telegram_id', 'userid', 'Telegram ID', 'User ID', 'telegram', 'id'):
            val = entry.get(key)
            if val is not None and str(val).strip() == target_str:
                return True
        # 2. Case-insensitive / whitespace-stripped key check
        for k, v in entry.items():
            k_clean = str(k).strip().lower().replace('_', '').replace(' ', '')
            if k_clean in ('userid', '.', 'chatid', 'telegramid', 'telegram', 'id'):
                if str(v).strip() == target_str:
                    return True
        # 3. Value check: Does any field contain target_id? (excluding non-ID fields like email, name, service)
        for k, v in entry.items():
            if str(k).lower() in ('email', 'service', 'name'):
                continue
            if str(v).strip() == target_str:
                return True
        return False

    def _matches_amount(entry, expected_amt):
        amt_val = entry.get('amount')
        if amt_val is None:
            return False
        s_entry = str(amt_val).strip()
        s_expected = str(expected_amt).strip()
        if s_entry == s_expected:
            return True
        # Float comparison if string contains currency or decimals (e.g. 2.00 vs 2)
        try:
            clean_entry = ''.join(c for c in s_entry if c.isdigit() or c == '.')
            clean_exp = ''.join(c for c in s_expected if c.isdigit() or c == '.')
            if clean_entry and clean_exp:
                return float(clean_entry) == float(clean_exp)
        except Exception:
            pass
        return False

    for attempt in range(max_retries):
        try:
            logger.info(
                f"Verifying payment for chat_id={chat_id}, amount={payment_amount} (attempt {attempt + 1}/{max_retries})")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(PAYMENT_CAPTURED_DETAILS_URL)
                response.raise_for_status()
                data = response.json()

                if isinstance(data, list):
                    for entry in data:
                        if _matches_user(entry, chat_id) and _matches_amount(entry, payment_amount):
                            logger.info(f"Payment verified for user {chat_id} (amount {payment_amount})")
                            return True
                logger.info(f"No matching payment details found in SheetDB (attempt {attempt + 1}/{max_retries}).")
        except httpx.HTTPStatusError as err:
            logger.warning(f"HTTP error during payment verification (attempt {attempt + 1}/{max_retries}): {err}")
        except httpx.RequestError as err:
            logger.warning(
                f"Request error / SSL error during payment verification (attempt {attempt + 1}/{max_retries}): {err}")
        except Exception as err:
            logger.warning(
                f"Unexpected error during payment verification (attempt {attempt + 1}/{max_retries}): {err}")

        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)

    logger.error("Max retries exceeded or error occurred during payment verification.")
    return False


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
    if update.effective_message:
        await update.effective_message.reply_text(
            f"{CANCEL_EMOJI} Current process cancelled.",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
        )
    return ConversationHandler.END


async def handle_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # logger.info(f"Received update: {update.to_dict()}")
    async def handle_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):

        logger.info("=" * 80)
        logger.info("🔥 handle_all_updates() CALLED")
        logger.info(f"Update ID: {update.update_id}")

        if update.business_message:
            logger.info("✅ THIS IS A BUSINESS MESSAGE")
            logger.info(f"Business connection ID: {update.business_message.business_connection_id}")
            logger.info(f"Chat ID: {update.business_message.chat.id}")
            logger.info(f"User: {update.business_message.chat.full_name}")
            logger.info(f"Username: {update.business_message.chat.username}")
            logger.info(f"Document: {update.business_message.document}")

        elif update.message:
            logger.info("📨 THIS IS A NORMAL MESSAGE")
            logger.info(f"Chat ID: {update.message.chat.id}")
            logger.info(f"Document: {update.message.document}")

        else:
            logger.info("⚠️ No message/business_message found")

        logger.info("=" * 80)

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
                # await context.bot.send_message(
                #     chat_id=bm.chat.id,
                #     text=(
                #         f"{BOT_EMOJI} <b>Thank you for submitting your article</b> {NAMASTE_EMOJI}\n\n"
                #         "✅Kindly wait while your report is being prepared. I will notify you as soon as it is ready for download."
                #     ),
                #     parse_mode="HTML",
                #     business_connection_id=bm.business_connection_id if is_business else None,
                #     reply_parameters=reply_params
                # )
                if is_business:
                    logger.info(
                        f"📩 BUSINESS MESSAGE RECEIVED | "
                        f"user_id={bm.chat.id} | "
                        f"name={bm.chat.full_name} | "
                        f"business_connection_id={bm.business_connection_id}"
                    )

                    try:
                        await context.bot.send_message(
                            business_connection_id=bm.business_connection_id,
                            chat_id=bm.chat.id,
                            text=(
                                f"{BOT_EMOJI} <b>Thank you for submitting your article</b> {NAMASTE_EMOJI}\n\n"
                                f"{GREEN_TICK_EMOJI} Kindly wait while your report is being prepared. "
                                "I will notify you as soon as it is ready for download."
                            ),
                            parse_mode="HTML"
                        )

                        logger.info(
                            f"✅ THANK-YOU MESSAGE SENT TO USER {bm.chat.id}"
                        )

                    except Exception as e:
                        logger.error(
                            f"❌ FAILED TO SEND THANK-YOU MESSAGE | "
                            f"user={bm.chat.id} | "
                            f"business_connection_id={bm.business_connection_id} | "
                            f"error={e}",
                            exc_info=True
                        )

                logger.info("Sent thank-you message via business connection")
            except Exception as conn_err:
                logger.warning(f"Failed to reply via business connection, attempting direct send: {conn_err}")
                # Fallback to direct send (only works if user has started the bot)
                # await context.bot.send_message(
                #     chat_id=bm.chat.id,
                #     text=(
                #         f"{BOT_EMOJI} <b>Thank you for submitting your article</b> {NAMASTE_EMOJI}\n\n"
                #         f"{GREEN_TICK_EMOJI} Kindly wait while your report is being prepared. I will notify you as soon as it is ready for download."
                #     ),
                #     parse_mode="HTML",
                #     reply_parameters=None
                # )
                if is_business:
                    logger.info(
                        f"📩 BUSINESS MESSAGE RECEIVED | "
                        f"user_id={bm.chat.id} | "
                        f"name={bm.chat.full_name} | "
                        f"business_connection_id={bm.business_connection_id}"
                    )

                    try:
                        await context.bot.send_message(
                            business_connection_id=bm.business_connection_id,
                            chat_id=bm.chat.id,
                            text=(
                                f"{BOT_EMOJI} <b>Thank you for submitting your article</b> {NAMASTE_EMOJI}\n\n"
                                f"{GREEN_TICK_EMOJI} Kindly wait while your report is being prepared. "
                                "I will notify you as soon as it is ready for download."
                            ),
                            parse_mode="HTML"
                        )

                        logger.info(
                            f"✅ THANK-YOU MESSAGE SENT TO USER {bm.chat.id}"
                        )

                    except Exception as e:
                        logger.error(
                            f"❌ FAILED TO SEND THANK-YOU MESSAGE | "
                            f"user={bm.chat.id} | "
                            f"business_connection_id={bm.business_connection_id} | "
                            f"error={e}",
                            exc_info=True
                        )

                logger.info("Sent thank-you message directly (fallback)")

        except Exception as e:
            logger.error(f"Error replying to document upload: {e}")
            # Real-time error notification to the Admin with troubleshooting tip
            err_msg = str(e)
            admin_advice = ""
            if "business_peer_invalid" in err_msg.lower():
                admin_advice = f"\n\n{BULB_EMOJI} <b>Tip:</b> Please check if your bot has 'Can Reply' toggled ON in your Telegram app: <b>Settings -> Business -> Chatbots</b>."
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"{WARNING_EMOJI} <b>Error in document handler:</b>\n{err_msg}{admin_advice}\n\nUser ID: `{bm.chat.id}`",
                    parse_mode="HTML"
                )
            except Exception as notify_err:
                logger.error(f"Failed to notify admin of error: {notify_err}")


async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current admin conversation and reset state."""
    return await cancel_current_conversation(update, context)


async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID:
        await update.message.reply_text(
            f"{CANCEL_EMOJI} You are not authorized to use this command.",
            parse_mode="HTML"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"{RECYCLE_EMOJI} Upload Process has Started...",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    # Clear any old data from previous sessions
    cleanup_conversation_state(context)
    # Ask for region first
    keyboard = [
        [inline_button("🇮🇳 Indian", callback_data="region_indian", style="primary")],
        [inline_button("🌍 Non-Indian", callback_data="region_non_indian", style="success")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"{WORLD_EMOJI} <b>Select your region:</b>\n\n"
        f"1. {INDIA_EMOJI} Indian - Use Razorpay (INR) for payment\n"
        f"2. {WORLD_EMOJI} Non-Indian - Use Razorpay (USD) for payment",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return WAITING_FOR_REGION


# Add region selection handler
async def handle_region_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "region_indian":
        context.user_data["region"] = "indian"
        context.user_data["payment_url"] = RAZORPAY_PAYMENT_URL
        region_text = f"{INDIA_EMOJI} Indian (Razorpay INR)"
    else:
        context.user_data["region"] = "non_indian"
        context.user_data["payment_url"] = RAZORPAY_USD_PAYMENT_URL
        region_text = f"{WORLD_EMOJI} Non-Indian (Razorpay USD)"

    await query.edit_message_text(f"{GREEN_TICK_EMOJI} <b>Region selected:</b> {region_text}", parse_mode="HTML")

    # Now show file upload options
    keyboard = [
        [inline_button("📁 One File", callback_data="upload_1", style="success")],
        [inline_button("📂 Two Files", callback_data="upload_2", style="primary")],
        [inline_button("📦 More than Two Files", callback_data="upload_more", style="danger")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=query.message.chat.id,
        text=f"<tg-emoji emoji-id=5461117441612462242>📁</tg-emoji> How many files do you want to upload?",
        reply_markup=reply_markup, parse_mode="HTML"
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
        await query.edit_message_text(f"{SEND_FILE_EMOJI} Please send 1 file.", parse_mode="HTML")
        return COLLECTING_FILES
    elif query.data == "upload_2":
        context.user_data["upload_limit"] = 2
        await query.edit_message_text(f"{SEND_FILE_EMOJI} Please send 2 files.", parse_mode="HTML")
        return COLLECTING_FILES
    else:
        await query.edit_message_text(f"{GREEN_TICK_EMOJI} Please enter how many files you want to upload (must be a number > 2):", parse_mode="HTML")
        return WAITING_FOR_MULTIPLE_FILES


async def ask_file_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input.isdigit() or int(user_input) <= 2:
        await update.message.reply_text(f"{CROSS_EMOJI} Please enter a number greater than 2.", parse_mode="HTML")
        return WAITING_FOR_MULTIPLE_FILES

    context.user_data["upload_limit"] = int(user_input)
    await update.message.reply_text(f"{SEND_FILE_EMOJI} Please send {user_input} files one by one.", parse_mode="HTML")
    return COLLECTING_FILES


async def handle_multiple_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document

    if not document:
        await update.message.reply_text(f"{CROSS_EMOJI} Please send a valid file.", parse_mode="HTML")
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
        await update.message.reply_text(f"{GREEN_TICK_EMOJI} All files received. \n"
                                        f"{MONEY_EMOJI} Now enter payment amount:", parse_mode="HTML")
        return WAITING_FOR_PAYMENT

    await update.message.reply_text(
        f"{PDF_SYMBOL_EMOJI} File <b>{document.file_name}</b> received. Send next file...",
        parse_mode="HTML"
    )
    return COLLECTING_FILES


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handle file upload from users """
    document = update.message.document
    if not document:
        await update.message.reply_text(f"{CROSS_EMOJI} No document detected. Please try again.", parse_mode="HTML")
        return WAITING_FOR_UPLOAD_OPTION
    await update.message.reply_text(
        f"{RECYCLE_EMOJI} Uploading Report ....",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
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
    await update.message.reply_text(f"{MONEY_EMOJI} Now, enter the payment amount:", parse_mode="HTML")

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
        f"<tg-emoji emoji-id='5458382591121964689'>✍️</tg-emoji> Please enter the name of the user (or tap below):",
        reply_markup=reply_markup, parse_mode="HTML"
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
        f"<tg-emoji emoji-id='5458382591121964689'>✍️</tg-emoji> *Do you want to Sign this report?*",
        reply_markup=reply_markup,
        parse_mode="HTML"
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
        f"{GREEN_TICK_EMOJI} Report will be signed." if do_sign
        else f"{CROSS_EMOJI} Report will NOT be signed.", parse_mode="HTML"
    )

    # Process all files with the signing preference
    try:
        processed_files = process_all_files(context, do_sign)

        if not processed_files:
            cleanup_conversation_state(context)
            await query.edit_message_text(f"{CROSS_EMOJI} No files could be processed.", parse_mode="HTML")
            await restore_admin_keyboard(update, context, "Admin keyboard restored.")
            return ConversationHandler.END

        context.user_data["files"] = processed_files
        logger.info(f"DEBUG: Processed {len(processed_files)} files with do_sign={do_sign}")
    except Exception as e:
        logger.error(f"Error processing files: {e}")
        cleanup_conversation_state(context)
        await query.edit_message_text(f"{CROSS_EMOJI} Error processing files.", parse_mode="HTML")
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
            text=f"{CROSS_EMOJI} User ID not found.",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
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
            text=f"{CROSS_EMOJI} No files found.",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
        )
        cleanup_conversation_state(context)
        return ConversationHandler.END

    if google_drive_files:
        initial_text = f"{RECYCLE_EMOJI} Uploading file to Google Drive..."
    elif pcloud_utils:
        initial_text = f"{RECYCLE_EMOJI} Uploading file to pCloud Storage..."
    else:
        initial_text = f"{RECYCLE_EMOJI} Uploading file to Cloud Storage..."

    await context.bot.send_message(
        chat_id=chat_id,
        text=initial_text,
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

    files_uploaded = []
    providers_used = []
    error_occurred = None
    preferred_provider = None

    for path, _ in context.user_data["files"]:
        try:
            file_info, provider, switched, prov_key = await upload_to_storage_with_fallback(
                file_path=path,
                user_name=name,
                user_id=user_id,
                preferred_provider=preferred_provider
            )
            if prov_key:
                preferred_provider = prov_key

            if switched and preferred_provider:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"{WARNING_EMOJI} Notice: Storing file via <b>{provider}</b>...",
                        parse_mode="HTML"
                    )
                except Exception as notify_err:
                    logger.debug(f"Could not send fallback switch notification: {notify_err}")

            if file_info:
                files_uploaded.append(file_info)
                if provider not in providers_used:
                    providers_used.append(provider)
        except Exception as e:
            error_occurred = e
            break

    if not files_uploaded:
        err_msg = str(error_occurred) if error_occurred else "Unknown error"
        admin_advice = ""
        if "invalid_grant" in err_msg.lower() or "account not found" in err_msg.lower():
            admin_advice = (
                "\n\n🔑 <b>Google Auth Issue:</b>\n"
                "Google OAuth credentials may have expired or need refreshing.\n"
                "Please verify token.json or GOOGLE_OAUTH_* in .env."
            )
        elif "pcloud" in err_msg.lower() and ("credentials" in err_msg.lower() or "password" in err_msg.lower()):
            admin_advice = (
                "\n\n🔑 <b>pCloud Auth Issue:</b>\n"
                "Please verify PCLOUD_EMAIL and PCLOUD_PASSWORD in .env."
            )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{CROSS_EMOJI} <b>Upload failed across cloud providers.</b>\n\nError Details:\n<code>{err_msg}</code>{admin_advice}",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
        )
        cleanup_conversation_state(context)
        return ConversationHandler.END

    save_report_links(
        user_id=user_id,
        amount=amount,
        links=[],
        region=region,
        business_connection_id=business_conn_id,
        files=files_uploaded
    )

    global report_links
    report_links = load_report_links()

    if region == "indian":
        payment_amount = f"Rs {amount}/-"
    else:
        payment_amount = f"${amount}"

    storage_display = ", ".join(providers_used) if providers_used else "Cloud Storage"
    files_formatted = "\n".join(
        [f"{PDF_FILE_EMOJI} File {i + 1}: <b>{f.get('file_name', 'Report')}</b> ({f.get('provider', 'cloud')})"
         for i, f in enumerate(files_uploaded)]
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"<b>{CRACKER_EMOJI}REPORT UPLOADED SUCCESSFULLY!{CRACKER_EMOJI}</b>\n\n"
            f"<tg-emoji emoji-id='5818715087237549366'>👤</tg-emoji> <b>Name:</b> <a href='tg://user?id={user_id}'>{name}</a>\n"
            f"<tg-emoji emoji-id='4947513368182260483'>☁️</tg-emoji> <b>Storage:</b> {storage_display} (Stored Privately)\n"
            f"{MONEY_EMOJI} <b>Amount:</b> {payment_amount}\n\n"
            f"<tg-emoji emoji-id='4947513368182260483'>📁</tg-emoji> <b>Stored Files:</b>\n{files_formatted}\n\n"
            f"<i>Files will be downloaded from cloud and delivered as PDF documents upon payment verification.</i>"
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
            text=f"<b>{CRACKER_EMOJI}REPORT IS READY{CRACKER_EMOJI}</b>\n\n"
                 f"Please, click on the button below and make the payment of"
                 f" <b>{payment_amount}</b> to receive your report.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.info(f"Sent report ready message to {user_id} via business connection")
    except Exception as conn_err:
        logger.warning(
            f"Failed sending report ready message to {user_id} via business connection: {conn_err}. Attempting direct send.")
        # Fallback to direct send
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<b>{CRACKER_EMOJI}REPORT IS READY{CRACKER_EMOJI}</b>\n\n"
                 f"Please, click on the button below and make the payment of"
                 f" <b>{payment_amount}</b> to receive your report.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.info(f"Sent report ready message to {user_id} directly (fallback)")

    # remove_user_data(user_id)
    cleanup_conversation_state(context)
    return ConversationHandler.END


async def upload_to_storage_with_fallback(file_path, user_name, user_id, preferred_provider=None):
    """
    Upload file privately to cloud storage with automatic fallback across providers:
    Google Drive -> pCloud
    Returns:
        tuple: (file_info_dict, provider_name, switched_to_fallback, actual_provider_key)
        file_info_dict format: {"file_id": ..., "file_name": ..., "provider": "google_drive" | "pcloud"}
    """
    global google_drive_files, pcloud_utils
    folder_name = f"{user_name} ({user_id})"
    errors = {}
    switched = False

    # Retry loading pcloud_utils dynamically if needed
    if pcloud_utils is None:
        try:
            import pcloud_utils as pcu
            pcloud_utils = pcu
        except Exception as pe:
            logger.debug(f"pcloud_utils import retry failed: {pe}")

    providers_order = ["google_drive", "pcloud"]
    if preferred_provider in providers_order:
        providers_order.remove(preferred_provider)
        providers_order.insert(0, preferred_provider)

    for prov in providers_order:
        if prov == "google_drive":
            if google_drive_files is None and preferred_provider == "google_drive":
                try:
                    import google_drive_files as gdf
                    google_drive_files = gdf
                except Exception:
                    pass
            if google_drive_files:
                try:
                    logger.info(f"Uploading '{file_path}' privately to Google Drive...")
                    file_info = google_drive_files.upload_private_file(
                        file_path=file_path,
                        folder_name=folder_name
                    )
                    if file_info:
                        prov_name = "Google Drive" if not errors else "Google Drive (Fallback)"
                        return file_info, prov_name, switched, "google_drive"
                except Exception as e:
                    errors["Google Drive"] = str(e)
                    logger.warning(f"⚠️ Google Drive upload failed for '{file_path}': {e}. Trying fallback...")
                    switched = True
            else:
                errors["Google Drive"] = "Google Drive is not initialized or configured"

        elif prov == "pcloud":
            if pcloud_utils is None:
                try:
                    import pcloud_utils as pcu
                    pcloud_utils = pcu
                except Exception:
                    pass
            if pcloud_utils:
                try:
                    logger.info(f"Uploading '{file_path}' privately to pCloud...")
                    file_info = pcloud_utils.upload_private_file(
                        file_path=file_path,
                        folder_name=folder_name
                    )
                    if file_info:
                        prov_name = "pCloud" if not errors else "pCloud (Fallback)"
                        return file_info, prov_name, switched, "pcloud"
                except Exception as e:
                    errors["pCloud"] = str(e)
                    logger.warning(f"⚠️ pCloud upload failed for '{file_path}': {e}.")
                    switched = True
            else:
                errors["pCloud"] = "pCloud is not initialized or configured"

    err_details = "\n".join([f"• {k}: {v}" for k, v in errors.items()])
    raise RuntimeError(f"Cloud storage upload failed across all providers!\n\n{err_details}")


def download_cloud_file_bytes(file_info):
    """
    Download file binary bytes from Google Drive or pCloud based on provider metadata.
    file_info format: {"file_id": ..., "file_name": ..., "provider": "google_drive" | "pcloud"}
    Returns: bytes
    """
    global google_drive_files, pcloud_utils
    provider = file_info.get("provider")
    file_id = file_info.get("file_id")

    if provider == "google_drive":
        if not google_drive_files:
            try:
                import google_drive_files as gdf
                google_drive_files = gdf
            except Exception:
                raise RuntimeError("Google Drive module not loaded.")
        return google_drive_files.download_file_bytes(file_id)
    elif provider == "pcloud":
        if not pcloud_utils:
            try:
                import pcloud_utils as pcu
                pcloud_utils = pcu
            except Exception:
                raise RuntimeError("pCloud module not loaded.")
        return pcloud_utils.download_file_bytes(file_id)
    else:
        raise ValueError(f"Unknown storage provider: {provider}")



async def upload_to_drive(file_path, user_name, user_id):
    """
    Upload file to cloud storage with automatic fallback.
    Maintained for backward compatibility.
    """
    file_info, _, _, _ = await upload_to_storage_with_fallback(file_path, user_name, user_id)
    return file_info



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

    async def reply(text, **kwargs):
        if message:
            await message.reply_text(text, **kwargs)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)

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
                    f"<b>{CRACKER_EMOJI}Report Downloader Bot{CRACKER_EMOJI}</b>\n\n"
                    f"To download your report, follow these two steps:\n"
                    f"<tg-emoji emoji-id='5461033346152804686'>1️⃣</tg-emoji> First click on the button below and make the payment of {payment_amount}.\n"
                    f"<tg-emoji emoji-id='5469622950032321924'>2️⃣</tg-emoji> After payment download the report.\n\n"
                    f" Your User ID: <code>{user_id}</code> (tap to copy)\n\n"
                    f"{GREEN_TICK_EMOJI} Use this User ID on {payment_method} Payment Gateway."
                ),
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            logger.info(f"Sent report downloader message to {user_id} via business connection")
        except Exception as conn_err:
            logger.warning(
                f"Failed sending report downloader message to {user_id} via business connection: {conn_err}. Attempting direct send.")
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"<b>{CRACKER_EMOJI}Report Downloader Bot{CRACKER_EMOJI}</b>\n\n"
                    f"To download your report, follow these two steps:\n"
                    f"<tg-emoji emoji-id='5461033346152804686'>1️⃣</tg-emoji> First click on the button below and make the payment of {payment_amount}.\n"
                    f"<tg-emoji emoji-id='5469622950032321924'>2️⃣</tg-emoji> After payment download the report.\n\n"
                    f" Your User ID: <code>{user_id}</code> (tap to copy)\n\n"
                    f"{GREEN_TICK_EMOJI} Use this User ID on {payment_method} Payment Gateway."
                ),
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

    else:
        if chat_id == ADMIN_ID:
            await reply(
                "Admin keyboard is ready.",
                reply_markup=get_admin_keyboard()
            )
        else:
            await reply(
                f"{CROSS_EMOJI} There is no information about your report. Please contact Admin @coding_services.",parse_mode="HTML")


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
                logger.warning(
                    f"Failed to edit message {current_message_id} with error: {e}. Falling back to send + delete.")
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

    await edit_msg(f"{RECYCLE_EMOJI}  Payment verifying. Please wait...", parse_mode="HTML")
    report_links = load_report_links()  # Refresh from Firebase
    target_user_key = str(user_id) if str(user_id) in report_links else user_id
    if target_user_key in report_links:
        region = report_links[target_user_key].get('region', 'indian')
        amount = report_links[target_user_key].get('amount')

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
            # Inform user we are fetching the report
            await edit_msg(
                f"<b>{CRACKER_EMOJI}PAYMENT VERIFIED!{CRACKER_EMOJI}</b>\n\n"
                f"{NAMASTE_EMOJI} Thank you for making the payment.\n"
                f"<tg-emoji emoji-id='5334885140147479028'>⏳</tg-emoji> Fetching your report from cloud storage...",
                parse_mode="HTML"
            )

            user_report = report_links.get(target_user_key, report_links.get(user_id, {}))
            stored_files = user_report.get("files", [])
            business_conn_id = user_report.get("business_connection_id")
            if not business_conn_id:
                user_info = load_user_data().get(str(user_id), {})
                business_conn_id = user_info.get("business_connection_id")

            delivery_success = True
            if stored_files:
                for idx, file_meta in enumerate(stored_files):
                    file_name = file_meta.get("file_name", f"Report_{idx + 1}.pdf")
                    try:
                        logger.info(f"Downloading {file_name} from {file_meta.get('provider')} for user {user_id}...")
                        file_bytes = download_cloud_file_bytes(file_meta)
                        doc_stream = io.BytesIO(file_bytes)
                        doc_stream.name = file_name

                        try:
                            await context.bot.send_document(
                                business_connection_id=business_conn_id,
                                chat_id=user_id,
                                document=doc_stream,
                                filename=file_name
                            )
                            logger.info(f"Sent {file_name} to {user_id} via business connection.")
                        except Exception as doc_conn_err:
                            logger.warning(
                                f"Failed sending document via business connection: {doc_conn_err}. Falling back to direct send."
                            )
                            doc_stream.seek(0)
                            await context.bot.send_document(
                                chat_id=user_id,
                                document=doc_stream,
                                filename=file_name
                            )
                            logger.info(f"Sent {file_name} to {user_id} directly (fallback).")
                    except Exception as dl_err:
                        logger.error(f"Failed to download/send file {file_name} to user {user_id}: {dl_err}", exc_info=True)
                        delivery_success = False

                if delivery_success:
                    await edit_msg(
                        f"<b>{CRACKER_EMOJI}PAYMENT VERIFIED{CRACKER_EMOJI}</b>\n\n"
                        f"{NAMASTE_EMOJI} Thank you for making the payment.\n\n"
                        f"{GREEN_TICK_EMOJI} <b>Your report has been sent above as a PDF document.</b>",
                        parse_mode="HTML"
                    )
                else:
                    await edit_msg(
                        f"<b>{CRACKER_EMOJI}PAYMENT VERIFIED{CRACKER_EMOJI}</b>\n\n"
                        f"{WARNING_EMOJI} There was an issue downloading one or more files.\n"
                        f"Please contact Admin @coding_services.",
                        parse_mode="HTML"
                    )
            elif user_report.get("links"):
                # Backward compatibility for any legacy records
                links_formatted = "\n".join(
                    [f"📥 File {i + 1}: {link}" for i, link in enumerate(user_report["links"])]
                )
                await edit_msg(
                    f"<b>{CRACKER_EMOJI}PAYMENT VERIFIED{CRACKER_EMOJI}</b>\n\n"
                    f"{NAMASTE_EMOJI} Thank you for making the payment.\n\n"
                    f"{GREEN_TICK_EMOJI} Download your report by clicking on the link below:\n\n"
                    f"<b>⬇️ Report Download Links:</b>\n{links_formatted}",
                    parse_mode="HTML"
                )

            try:
                deleted = False
                try:
                    del_user_url = f"{PAYMENT_CAPTURED_DETAILS_URL}/user_id/{user_id}"
                    resp_u = requests.delete(url=del_user_url, timeout=5)
                    if resp_u.status_code == 200:
                        deleted = True
                        logger.info(f"Successfully deleted sheet entry for user {user_id} via user_id column")
                except Exception:
                    pass

                if not deleted:
                    DELETED_CODES_URL = f"{PAYMENT_CAPTURED_DETAILS_URL}/amount/{invoice_amount}"
                    response_del = requests.delete(url=DELETED_CODES_URL, timeout=5)
                    response_del.raise_for_status()
                    logger.info(f"Successfully deleted sheet entry for user {user_id} via amount")
            except Exception as del_err:
                logger.warning(f"Failed to delete verified entry from SheetDB: {del_err}")

            # Get the business connection ID from the report data (which we saved in Firestore)
            business_conn_id = report_links.get(str(user_id), {}).get("business_connection_id")
            if not business_conn_id:
                user_info = load_user_data().get(str(user_id), {})
                business_conn_id = user_info.get("business_connection_id")

            # Send JOIN & SHARE message only if the user is not already subscribed to the channel
            try:
                is_subscribed = await is_user_subscribed(context, CHANNEL_ID, user_id)
            except Exception as sub_err:
                logger.warning(f"Failed to check channel subscription for {user_id}: {sub_err}")
                is_subscribed = False

            if not is_subscribed:
                try:
                    await context.bot.send_message(
                        business_connection_id=business_conn_id,
                        chat_id=user_id,
                        text=f"<b>{CRACKER_EMOJI}JOIN & SHARE{CRACKER_EMOJI}</b>\n\n"
                             f"{GREEN_TICK_EMOJI} Please share and join our Telegram channel with your friends to stay updated "
                             f"about our products and services and also for weekly giveaways🎁\n\n"
                             f"{TELEGRAM_EMOJI} Join our Telegram channel: https://t.me/+66qt38tocAI0ZWI1",
                        parse_mode="HTML"
                    )
                    logger.info(f"Sent join & share message to {user_id} via business connection")
                except Exception as conn_err:
                    logger.warning(
                        f"Failed sending join & share message to {user_id} via business connection: {conn_err}. Attempting direct send.")
                    # Fallback to direct send
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"<b>{CRACKER_EMOJI}JOIN & SHARE{CRACKER_EMOJI}</b>\n\n"
                                 f"{GREEN_TICK_EMOJI} Please share and join our Telegram channel with your friends to stay updated "
                                 f"about our products and services and also for weekly giveaways🎁\n\n"
                                 f"{TELEGRAM_EMOJI} Join our Telegram channel: https://t.me/+66qt38tocAI0ZWI1",
                            parse_mode="HTML"
                        )
                        logger.info(f"Sent join & share message to {user_id} directly (fallback)")
                    except Exception as direct_err:
                        logger.warning(f"Failed sending join & share message to {user_id} directly: {direct_err}")

            else:
                logger.info(f"User {user_id} is already subscribed to channel {CHANNEL_ID}. Skipping JOIN & SHARE message.")

            remove_user_data(user_id)
            remove_report_links(user_id)
            load_report_links()  # Refresh from Firebase

        else:
            await edit_msg(
                f"<b>{CROSS_EMOJI} PAYMENT NOT VERIFIED YET {CROSS_EMOJI}</b>\n\n"
                f"We could not verify your payment of <b>{payment_amount}</b> at this moment.\n\n"
                f"<tg-emoji emoji-id='5461033346152804686'>1️⃣</tg-emoji> If you have not paid yet, please make the payment first using the button below.\n"
                f"<tg-emoji emoji-id='5469622950032321924'>2️⃣</tg-emoji> If you have already paid, it may take 1-2 minutes to register. Please try clicking <b>📥 Download Report</b> again in a few moments.\n\n"
                f"{GREEN_TICK_EMOJI} Your User ID: <code>{user_id}</code> (tap to copy)\n"
                f"{TELEGRAM_EMOJI} Need help? Contact Admin @coding_services.",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
    else:
        await edit_msg(f"{CANCEL_EMOJI} Your report is not ready. Please wait for some time!", parse_mode="HTML")


# ------------------ Admin Command: Show Reports ------------------ #
async def show_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text(f"{CANCEL_EMOJI} You are not authorized to use this command.", parse_mode="HTML")
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
        files = details.get("files", [])
        links = details.get("links", [])
        amount = details.get("amount", "Unknown")
        region = details.get("region", "indian")
        payment_amount = f"Rs {amount}/-" if region == "indian" else f"${amount}"

        if files:
            file_lines = "\n".join(
                [f"📄 File {i + 1}: {f.get('file_name', 'Report')} ({f.get('provider', 'cloud')})"
                 for i, f in enumerate(files)]
            )
        elif links:
            file_lines = "\n".join([f"📥 File {i + 1}: {link}" for i, link in enumerate(links)])
        else:
            file_lines = "📁 No files found."

        messages.append(
            f"<b>👤 Name:</b> <a href='tg://user?id={chat_id}'> {name}</a>\n"
            f"<b>🆔 User ID:</b> <code>{chat_id}</code>\n"
            f"<b>💰 Amount:</b> {payment_amount}\n"
            f"{file_lines}\n"
        )

    final_report = "\n\n".join(messages)
    await update.message.reply_text(
        f"{REPORTS_EMOJI} <b>Not Downloaded Reports:</b>\n\n{final_report}\n"
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
            f"{WARNING_EMOJI} No data found for user ID {user_id}.",
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
        f"{USERS_EMOJI} <b>Users who sent their articles recently:</b>\n\n{final_msg}\n"
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
        f"{WARNING_EMOJI} No user found with business_chat_id {chat_id_to_delete}.",
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

    cancel_filter = filters.Text([CANCEL_BUTTON_TEXT, "🚫 Cancel", "Cancel"])
    upload_filter = filters.Text([UPLOAD_BUTTON_TEXT, "⬆️ Upload", "Upload"])
    show_reports_filter = filters.Text([SHOW_REPORTS_BUTTON_TEXT, "📜 Show Reports", "Show Reports"])
    show_users_filter = filters.Text([SHOW_USERS_BUTTON_TEXT, "👥 Show Users", "Show Users"])

    admin_button_filter = (
        upload_filter | show_reports_filter | show_users_filter | cancel_filter
    )

    # Attach business update handler in a separate group so it doesn’t block others
    # application.add_handler(
    #     MessageHandler(
    #         filters.Document.ALL,
    #         handle_all_updates
    #     ),
    #     group=1
    # )
    # Business account messages
    application.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGE & filters.Document.ALL,
            handle_all_updates
        ),
        group=1
    )

    # Normal bot messages
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.Document.ALL,
            handle_all_updates
        ),
        group=1
    )

    # Upload file conversation handler
    conv_handler_upload = ConversationHandler(
        entry_points=[
            CommandHandler("upload", upload),
            MessageHandler(upload_filter, upload),
        ],
        states={
            WAITING_FOR_REGION: [
                MessageHandler(cancel_filter, handle_cancel),
                CallbackQueryHandler(handle_region_selection, pattern="^region_"),
            ],
            WAITING_FOR_UPLOAD_OPTION: [
                MessageHandler(cancel_filter, handle_cancel),
                CallbackQueryHandler(upload_option_handler),
            ],
            WAITING_FOR_MULTIPLE_FILES: [
                MessageHandler(cancel_filter, handle_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_file_count),
            ],
            COLLECTING_FILES: [
                MessageHandler(cancel_filter, handle_cancel),
                MessageHandler(filters.Document.ALL, handle_multiple_files),
            ],
            WAITING_FOR_PAYMENT: [
                MessageHandler(cancel_filter, handle_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_payment),
            ],
            WAITING_FOR_NAME: [
                MessageHandler(cancel_filter, handle_cancel),
                CallbackQueryHandler(handle_user_suggestion, pattern=r'^user_select\|'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
            ],
            WAITING_FOR_SIGN_CONFIRMATION: [
                MessageHandler(cancel_filter, handle_cancel),
                CallbackQueryHandler(handle_sign_confirmation, pattern="^sign_"),
            ],
            WAITING_FOR_USER: [
                MessageHandler(cancel_filter, handle_cancel),
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
            MessageHandler(show_reports_filter, show_reports),
        ],
        states={
            WAITING_FOR_DELETE_ID: [
                MessageHandler(cancel_filter, handle_cancel),
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
            MessageHandler(show_users_filter, show_users),
        ],
        states={
            WAITING_FOR_DELETE_USER_ID: [
                MessageHandler(cancel_filter, handle_cancel),
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
    application.add_handler(MessageHandler(cancel_filter, handle_cancel))
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
