# telegram_bot.py
import os
import logging
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from keep_alive import keep_alive
keep_alive()

# from dotenv import load_dotenv
# load_dotenv()


admin_activity = {}  # {user_id: datetime}

# logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

indian_user_charges = """
*🤖 Charges for each article/document for:*

✅*Plagiarism Checking:*
1 to 5,000 words: *Rs 50/-*
5,000 to 10,000 words: *Rs 100/-*
 and so on...

✅*AI Checking:*
1 to 5,000 words: *Rs 100/-*
5,000 to 10,000 words: *Rs 150/-*
10,000 to 15,000 words: *Rs 200/-*
 and so on...

 🛑NOTE: We only use the "No Repository" setting, 
so your document is 💯% safe while checking the plagiarism 
because neither Turnitin nor our system will ever store your work.

"""

non_indian_user_charges = """
*🤖 Charges for each article/document for:*

✅*Plagiarism Checking:*
👉1 to 5,000 words: *$2/-*
👉5,000 to 10,000 words: *$3/-*
👉10,000 to 15,000 words: *$4/-*

✅*AI Checking:*
👉1 to 5,000 words: *$3/-*
👉5,000 to 10,000 words: *$4/-*
👉10,000 to 15,000 words: *$5/-*
 and so on...

🛑NOTE: We only use the "No Repository" setting, 
so your document is 💯% safe while checking the plagiarism 
because neither Turnitin nor our system will ever store your work.

"""


# --- start ---

async def start(update: Update, context) -> None:
    user = update.effective_user
    deep_link_payload = context.args[0] if context.args else None

    if deep_link_payload and deep_link_payload.startswith("bizChat"):
        user_chat_id = deep_link_payload[len("bizChat"):]
        response_text = (
            f"Welcome {user.mention_html()}! You've arrived from a business chat "
            f"(ID: `{user_chat_id}`). How can I help you?"
        )
        logger.info(
            f"User {user.id} ({user.first_name}) started bot via deep link from business chat {user_chat_id}."
        )
    else:
        response_text = (
            f"Hi {user.mention_html()}! Welcome to our business bot.\n"
            "How can I assist you today? Feel free to ask about our services or pricing."
        )
        logger.info(f"User {user.id} ({user.first_name}) started the bot.")

    await update.message.reply_html(response_text)


async def help_command(update: Update, context) -> None:
    await update.message.reply_text(
        "I am a business bot to help you with our services and pricing.\n"
        "Ask me about plagiarism reports, AI detection, or document checking."
    )


# --- handle updates ---

async def handle_all_updates(update: Update, context) -> None:
    if update.business_connection:
        bc = update.business_connection
        logger.info(
            f"Business Connection update: id={bc.id}, user_chat_id={bc.user_chat_id}, is_enabled={bc.is_enabled}"
        )
        try:
            await context.bot.send_message(
                chat_id=bc.user.id,
                text=(
                    f"Your business connection (ID: `{bc.id}`) is "
                    f"{'enabled' if bc.is_enabled else 'disabled'}.\n"
                    f"We {'can' if bc.can_reply else 'cannot'} reply on your behalf."
                ),
            )
        except Exception as e:
            logger.error(f"Business connection reply failed: {e}")

    if update.business_message:
        bm = update.business_message
        bc = update.business_connection
        can_reply = True
        if bc:
            can_reply = bc.can_reply
            logger.info(f"Business connection status: id={bc.id}, can_reply={can_reply}")

        logger.info(
            f"New Business Message: connection_id={bm.business_connection_id}, chat={bm.chat.id}, text={bm.text}"
        )

        if bm.from_user.id == ADMIN_CHAT_ID:
            # ✅ Admin replied to a user
            admin_activity[bm.chat.id] = datetime.now()
            logger.info("Message from admin, bot stays silent.")
            return

        # ⏱ Check if admin replied in last 60 seconds — independent of can_reply
        last_active = admin_activity.get(bm.chat.id)
        if last_active and datetime.now() - last_active < timedelta(minutes=5):
            logger.info("Admin recently replied, bot stays silent.")
            return

        # Only then fall back to can_reply check
        if not can_reply:
            logger.info("Admin is online (can_reply=False), bot stays silent.")
            return

        if bm.document:
            try:
                await context.bot.send_message(
                    business_connection_id=bm.business_connection_id,
                    chat_id=bm.chat.id,
                    text=f"🤖*Thank you for submitting your article*🙏\n\n"
                         f'🚀Plz send a msg "hi" or "Hi" to our bot @ReportDownloaderBot\n\n'
                         f"✅When your report is ready, our bot will notify you to download it.",
                    parse_mode="Markdown",
                )
                logger.info(f"Received document from user {bm.from_user.id}")
            except Exception as e:
                logger.error(f"Error replying to document upload: {e}")
            return

        text_lower = bm.text.lower() if bm.text else ""

        if "hi" in text_lower or "hello" in text_lower:
            reply = "🤖 Hello! How may I help you?"
        elif "plag" in text_lower or "plagiarism" in text_lower or "ai" in text_lower:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes", callback_data=f"charges_yes|{bm.business_connection_id}"),
                    InlineKeyboardButton("❌ No", callback_data=f"charges_no|{bm.business_connection_id}"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await context.bot.send_message(
                    business_connection_id=bm.business_connection_id,
                    chat_id=bm.chat.id,
                    text="🤖 Do you know our report charges?",
                    reply_markup=reply_markup,
                )
                logger.info("Sent yes/no charges buttons")
            except Exception as e:
                logger.error(f"Error sending yes/no charges buttons: {e}")
            return
        elif "thank" in text_lower or "thanks" in text_lower:
            reply = "🤖 You're welcome! Let me know if there’s anything else."
        elif text_lower.strip() != "":
            reply = (f"🤖 *Hello!*\nI'm an AI-assistant to help you when my master is offline.\n\n"
                     f'Plz send a msg "hi" or "Hi" here to start the chat with me.')
        else:
            reply = (
                f"🤖 I received: '{bm.text}'. Feel free to ask about our services or pricing."
            )

        try:
            await context.bot.send_message(
                business_connection_id=bm.business_connection_id,
                chat_id=bm.chat.id,
                text=reply,
                parse_mode="Markdown",
            )
            logger.info(f"Replied business text to {bm.business_connection_id}:{bm.chat.id}")
        except Exception as e:
            logger.error(f"Error sending business reply: {e}")

    # # if someone send a to this bot
    # if update.message and update.message.text:
    #     text = update.message.text.lower()
    #     if "service" in text:
    #         reply = "We offer plagiarism, AI detection, and document checking. What do you need?"
    #     elif "product" in text:
    #         reply = "Our products include Turnitin and AI detection reports."
    #     elif "contact" in text:
    #         reply = "Email us at info@example.com or call +1234567890."
    #     else:
    #         reply = (
    #             f"I received: '{text}'. Feel free to ask about pricing or services."
    #         )
    #     await update.message.reply_text(reply)


# --- handle button clicks ---
async def handle_callback_query(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    parts = data.split("|")
    choice = parts[0]
    business_connection_id = parts[1] if len(parts) > 1 else None

    if choice == "charges_yes":
        reply = "🤖 Send me your article."
        if business_connection_id:
            await context.bot.send_message(
                business_connection_id=business_connection_id,
                chat_id=chat_id,
                text=reply,
            )
            logger.info("Handled charges_yes")
        else:
            await context.bot.send_message(chat_id=chat_id, text=reply)
        return

    if choice == "charges_no":
        keyboard = [
            [
                InlineKeyboardButton(
                    "🇮🇳 India", callback_data=f"country_india|{business_connection_id}"
                ),
                InlineKeyboardButton(
                    "🌎 Non-Indian", callback_data=f"country_non_indian|{business_connection_id}"
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            business_connection_id=business_connection_id,
            chat_id=chat_id,
            text="🤖 From which country are you?",
            reply_markup=reply_markup,
        )
        logger.info("Handled charges_no")
        return

    if choice == "country_india":
        reply = indian_user_charges
    elif choice == "country_non_indian":
        reply = non_indian_user_charges
    else:
        reply = "🤖 I did not understand your choice."

    if business_connection_id:
        await context.bot.send_message(
            business_connection_id=business_connection_id,
            chat_id=chat_id,
            text=reply,
            parse_mode="Markdown",
        )
        await context.bot.send_message(
            business_connection_id=business_connection_id,
            chat_id=chat_id,
            text=f"🤖 Send me your article.",
            parse_mode="Markdown",
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown")


# --- errors ---

async def error_handler(update: object, context) -> None:
    logger.warning(f"Update {update} caused error {context.error}")
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(f"Error: {context.error}")
    except Exception as e:
        logger.error(f"Error sending error message: {e}")


# --- main ---

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.ALL, handle_all_updates))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_error_handler(error_handler)

    logger.info("Bot is starting to poll for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot stopped polling.")


if __name__ == "__main__":
    main()
