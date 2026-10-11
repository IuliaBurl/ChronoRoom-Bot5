import html
import logging
import os
import re
from enum import Enum, auto

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
)

load_dotenv()  # reads a local .env (git-ignored) before the settings below are evaluated

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# httpx logs every request at INFO level, and the Telegram API URL contains the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def derive_channel_url(username: str, explicit_url: str = "") -> str:
    """CHANNEL_URL wins; otherwise it is built from a public @username.

    A private channel (numeric id) has no such URL, so CHANNEL_URL must be set for it.
    """
    if explicit_url.strip():
        return explicit_url.strip()
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,}", username):
        return f"https://t.me/{username.lstrip('@')}"
    return ""


TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()
CHANNEL_URL = derive_channel_url(CHANNEL_USERNAME, os.getenv("CHANNEL_URL", ""))

# All texts are sent with parse_mode=HTML (the application default, see main()).
# Anything that comes from outside (a user's name, environment values) goes through esc().
BOT_DESCRIPTIONS = {
    "bot1": {
        "name": "🎯 ChronoBot 1",
        "link": "https://t.me/ChronoRoom_bot",
        "title": "Compatibility Tests",
        "description": (
            "✨ <b>How does it work?</b>\n"
            "• Take an interesting test\n"
            "• Bot will find people with similar answers\n"
            "• Create a group and send the link\n"
            "• Bot will send it to all participants\n"
            "• Chat with like-minded people!"
        )
    },
    "bot2": {
        "name": "🎲 ChronoBot 2",
        "link": "https://t.me/ChronoRoom1_bot",
        "title": "Lucky Dice",
        "description": (
            "✨ <b>What awaits you?</b>\n"
            "• Answer unusual questions\n"
            "• Create a unique profile\n"
            "• Roll the 'Lucky Dice'\n"
            "• Find out your 'lucky person'\n"
            "• Message them first!"
        )
    },
    "bot3": {
        "name": "🎤 ChronoBot 3",
        "link": "https://t.me/ChronoRoom2_bot",
        "title": "Anonymous Voice Chat",
        "description": (
            "✨ <b>Chat features:</b>\n"
            "• Voice-only communication\n"
            "• Automatic voice masking\n"
            "• Interesting sound effects\n"
            "• Built-in mini-games\n"
            "• Complete anonymity!"
        )
    },
    "bot4": {
        "name": "🌍 ChronoBot 4",
        "link": "https://t.me/ChronoRoom3_bot",
        "title": "Global Profile Board",
        "description": (
            "✨ <b>Features:</b>\n"
            "• Browse random profiles\n"
            "• Message people anonymously through the bot\n"
            "• Select several people and create a group chat\n"
            "• Send group invitations they can accept or decline\n"
            "• New people every day!"
        )
    }
}

SUBSCRIPTION_UNKNOWN_ALERT = (
    "⚠️ Couldn't verify your subscription right now. Please try again in a minute."
)


def esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


class SubscriptionStatus(Enum):
    SUBSCRIBED = auto()
    NOT_SUBSCRIBED = auto()
    UNKNOWN = auto()  # Telegram could not tell us (outage, wrong channel, bot is not an admin)


class ConfigurationError(RuntimeError):
    pass


async def get_subscription_status(bot, user_id: int) -> SubscriptionStatus:
    """Fails closed, but does not blame the user: if Telegram cannot confirm the membership
    the status is UNKNOWN (access is not granted, the user is asked to try again later)."""
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
    except TelegramError as e:
        # BadRequest / Forbidden point to a configuration problem (wrong channel, the bot is
        # not an admin there); other errors are usually temporary.
        level = logging.ERROR if isinstance(e, (BadRequest, Forbidden)) else logging.WARNING
        logger.log(level, "Subscription check failed for %s, access NOT granted: %s", user_id, e)
        return SubscriptionStatus.UNKNOWN

    subscribed = member.status in (
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    ) or (member.status == ChatMemberStatus.RESTRICTED and member.is_member)

    return SubscriptionStatus.SUBSCRIBED if subscribed else SubscriptionStatus.NOT_SUBSCRIBED


async def render(update: Update, text: str, reply_markup: InlineKeyboardMarkup):
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
            # e.g. the message can no longer be edited: show the screen in a new message
            logger.warning("Could not edit the message, sending a new one: %s", e)
            await query.get_bot().send_message(
                chat_id=query.from_user.id, text=text, reply_markup=reply_markup
            )
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def show_subscription_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    keyboard = [
        [InlineKeyboardButton("📢 Subscribe to channel", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ I subscribed", callback_data="check_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"👋 Welcome to ChronoRoom, {esc(user.first_name)}!\n\n"
        "✨ <b>This is a gateway to bots for communication and meeting people</b>\n\n"
        "📢 <b>To use it, you need to subscribe to the channel:</b>\n"
        f"{esc(CHANNEL_USERNAME)}\n\n"
        "After subscribing, click '✅ I subscribed'"
    )

    await render(update, text, reply_markup)


async def show_unknown_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shown when the subscription could not be verified: it is NOT 'you are not subscribed'."""
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Try again", callback_data="check_subscription")]]
    )
    text = (
        "⚠️ <b>Couldn't verify your subscription right now</b>\n\n"
        "Telegram did not answer. This is temporary - please try again in a minute."
    )
    await render(update, text, reply_markup)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    keyboard = [
        [InlineKeyboardButton("🎯 ChronoBot 1", callback_data="bot1")],
        [InlineKeyboardButton("🎲 ChronoBot 2", callback_data="bot2")],
        [InlineKeyboardButton("🎤 ChronoBot 3", callback_data="bot3")],
        [InlineKeyboardButton("🌍 ChronoBot 4", callback_data="bot4")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"🌟 <b>Welcome, {esc(user.first_name)}!</b>\n\n"
        "🎭 <b>Choose a bot for communication and meeting people:</b>\n\n"
        "👇 <b>Click the button to learn more</b>"
    )

    await render(update, text, reply_markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    status = await get_subscription_status(context.bot, user.id)

    if status is SubscriptionStatus.SUBSCRIBED:
        await show_main_menu(update, context)
    elif status is SubscriptionStatus.UNKNOWN:
        await show_unknown_menu(update, context)
    else:
        await show_subscription_menu(update, context)


async def show_bot_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    bot = BOT_DESCRIPTIONS.get(query.data)
    if bot is None:
        await query.answer()
        return

    status = await get_subscription_status(context.bot, user.id)

    if status is SubscriptionStatus.UNKNOWN:
        # temporary problem: keep what the user is looking at
        await query.answer(SUBSCRIPTION_UNKNOWN_ALERT, show_alert=True)
        return

    if status is SubscriptionStatus.NOT_SUBSCRIBED:
        await query.answer("❌ Please subscribe to the channel first", show_alert=True)
        await show_subscription_menu(update, context)
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🚀 Go to bot", url=bot["link"])],
        [InlineKeyboardButton("🔙 Back to list", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"<b>{esc(bot['name'])}</b>\n"
        f"<i>{esc(bot['title'])}</i>\n\n"
        f"{bot['description']}\n\n"
        "👇 <b>Click the button below to get started:</b>"
    )

    await render(update, text, reply_markup)


async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    status = await get_subscription_status(context.bot, user.id)

    if status is SubscriptionStatus.SUBSCRIBED:
        await query.answer("✅ Subscription confirmed!", show_alert=True)
        await show_main_menu(update, context)
    elif status is SubscriptionStatus.UNKNOWN:
        await query.answer(SUBSCRIPTION_UNKNOWN_ALERT, show_alert=True)
    else:
        await query.answer("❌ You are not subscribed to the channel", show_alert=True)
        await show_subscription_menu(update, context)


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await show_main_menu(update, context)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == "check_subscription":
        await check_subscription(update, context)
    elif query.data == "back_to_menu":
        await back_to_menu(update, context)
    elif query.data in BOT_DESCRIPTIONS:
        await show_bot_info(update, context)
    else:
        await query.answer()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🆘 <b>Help</b>\n\n"
        "✨ <b>How to use:</b>\n"
        "1. Subscribe to our channel\n"
        "2. Choose a bot you like\n"
        "3. Read the description of features\n"
        "4. Click 'Go to bot'\n"
        "5. Enjoy communicating!\n\n"
        "📢 <b>Mandatory requirement:</b>\n"
        "To access the bots, you need to subscribe to the channel.\n\n"
        "🤖 <b>Our bots:</b>\n"
        "• ChronoBot 1 — Compatibility Tests\n"
        "• ChronoBot 2 — Lucky Dice\n"
        "• ChronoBot 3 — Voice Chat\n"
        "• ChronoBot 4 — Profile Board"
    )

    await update.message.reply_text(help_text)


async def verify_channel_access(application: Application) -> None:
    """Fail fast on a wrong channel or missing admin rights.

    Otherwise such a misconfiguration would show every user "not subscribed" with no hint why.
    """
    try:
        me = await application.bot.get_chat_member(CHANNEL_USERNAME, application.bot.id)
    except (BadRequest, Forbidden) as e:
        raise ConfigurationError(
            f"The bot cannot read the members of {CHANNEL_USERNAME}: {e}. "
            "Add the bot to the channel as an administrator and check CHANNEL_USERNAME."
        ) from e
    except TelegramError as e:
        logger.warning("Could not verify access to %s at startup (checked again on demand): %s",
                       CHANNEL_USERNAME, e)
        return

    if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        logger.warning("The bot is not an administrator of %s: membership checks may fail",
                       CHANNEL_USERNAME)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled error", exc_info=context.error)


def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN is not set")
    if not CHANNEL_USERNAME:
        raise SystemExit("CHANNEL_USERNAME is not set")
    if not CHANNEL_URL:
        raise SystemExit("CHANNEL_URL must be set: it cannot be derived from CHANNEL_USERNAME "
                         "(private channel?)")

    application = (
        Application.builder()
        .token(TOKEN)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .post_init(verify_channel_access)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)

    logger.info("=" * 50)
    logger.info("ChronoRoom Bot started!")
    logger.info(f"Channel: {CHANNEL_USERNAME}")
    logger.info("Bots in system: %d", len(BOT_DESCRIPTIONS))
    logger.info("=" * 50)

    try:
        application.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])
    except ConfigurationError as e:
        logger.error("%s", e)
        raise SystemExit(1) from e


if __name__ == '__main__':
    main()
