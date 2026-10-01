import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes                                                                          from telegram.constants import ParseMode

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


TOKEN = ""                         
CHANNEL_URL = ""

BOT_DESCRIPTIONS = {
    "bot1": {
        "name": "🎯 ChronoBot 1",
        "link": "https://t.me/ChronoRoom_bot",  # Fixed!
        "title": "Compatibility Tests",
        "description": (
            "✨ *How does it work?*\n"
            "• Take an interesting test\n"
            "• Bot will find people with similar answers\n"
            "• Create a group and send the link\n"
            "• Bot will send it to all participants\n"                                       "• Chat with like-minded people!"
        )
    },
    "bot2": {
        "name": "🎲 ChronoBot 2",
        "link": "https://t.me/ChronoRoom1_bot",  # Fixed!
        "title": "Lucky Dice",
        "description": (
            "✨ *What awaits you?*\n"
            "• Answer unusual questions\n"
            "• Create a unique profile\n"
            "• Roll the 'Lucky Dice'\n"
            "• Find out your 'lucky person'\n"
            "• Message them first!"
        )
    },
    "bot3": {
        "name": "🎤 ChronoBot 3",
        "link": "https://t.me/ChronoRoom2_bot",  # Fixed!                                "title": "Anonymous Voice Chat",
        "description": (
            "✨ *Chat features:*\n"                                                          "• Voice-only communication\n"
            "• Automatic voice masking\n"
            "• Interesting sound effects\n"                                                  "• Built-in mini-games\n"
            "• Complete anonymity!"
        )
    },
    "bot4": {
        "name": "🌍 ChronoBot 4",
        "link": "https://t.me/ChronoRoom3_bot",  # Fixed!
        "title": "Global Profile Board",
        "description": (
            "✨ *Features:*\n"
            "• Browse random profiles\n"
            "• Message anonymously or openly\n"
            "• Create group chats\n"                                                         "• Send friend requests\n"
            "• New people every day!"
        )                                                                            }
}

async def is_user_subscribed(bot, user_id: int) -> bool:                             try:
        chat_member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']          except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False

async def show_subscription_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user                                                 
    keyboard = [
        [InlineKeyboardButton("📢 Subscribe to channel", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ I subscribed", callback_data="check_subscription")]
    ]                                                                            
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"👋 Welcome to ChronoRoom, {user.first_name}!\n\n"
        "✨ *This is a gateway to bots for communication and meeting people*\n\n"
        "📢 *To use it, you need to subscribe to the channel:*\n"                        f"{CHANNEL_USERNAME}\n\n"
        "After subscribing, click '✅ I subscribed'"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:                                                                                await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

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
        f"🌟 *Welcome, {user.first_name}!*\n\n"
        "🎭 *Choose a bot for communication and meeting people:*\n\n"                    "👇 *Click the button to learn more*"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )                                                                            else:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
                                                                                     # Check subscription
    is_subscribed = await is_user_subscribed(context.bot, user.id)

    if not is_subscribed:
        await show_subscription_menu(update, context)
    else:
        await show_main_menu(update, context)

async def show_bot_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query                                                    await query.answer()

    user = query.from_user

    is_subscribed = await is_user_subscribed(context.bot, user.id)
    if not is_subscribed:
        await query.answer("❌ Please subscribe to the channel first", show_alert=True)                                                                                   await show_subscription_menu(update, context)
        return
                                                                                     bot_key = query.data
    bot = BOT_DESCRIPTIONS[bot_key]

    keyboard = [
        [InlineKeyboardButton("🚀 Go to bot", url=bot["link"])],
        [InlineKeyboardButton("🔙 Back to list", callback_data="back_to_menu")]
    ]                                                                            
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (                                                                             f"*{bot['name']}*\n"
        f"_{bot['title']}_\n\n"
        f"{bot['description']}\n\n"
        "👇 *Click the button below to get started:*"                                )
                                                                                     await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
                                                                                 # Check subscription
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔍 Checking subscription...")                                                                                                                 user = query.from_user

    is_subscribed = await is_user_subscribed(context.bot, user.id)

    if is_subscribed:
        await query.answer("✅ Subscription confirmed!", show_alert=True)
        await show_main_menu(update, context)                                        else:
        await query.answer("❌ You are not subscribed to the channel", show_alert=True)
        await show_subscription_menu(update, context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == "check_subscription":
        await check_subscription(update, context)                                    elif query.data == "back_to_menu":
        await show_main_menu(update, context)
    elif query.data in ["bot1", "bot2", "bot3", "bot4"]:
        await show_bot_info(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (                                                                        "🆘 *Help*\n\n"
        "✨ *How to use:*\n"
        "1. Subscribe to our channel\n"
        "2. Choose a bot you like\n"
        "3. Read the description of features\n"
        "4. Click 'Go to bot'\n"                                                         "5. Enjoy communicating!\n\n"
        "📢 *Mandatory requirement:*\n"
        "To access the bots, you need to subscribe to the channel.\n\n"
        "🤖 *Our bots:*\n"
        "• ChronoBot 1 — Compatibility Tests\n"
        "• ChronoBot 2 — Lucky Dice\n"
        "• ChronoBot 3 — Voice Chat\n"                                                   "• ChronoBot 4 — Profile Board"
    )

    await update.message.reply_text(
        help_text,                                                                       parse_mode=ParseMode.MARKDOWN
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()                     
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(CallbackQueryHandler(button_handler))


    print("=" * 50)
    print("🤖 ChronoRoom Bot started!")
    print(f"📢 Channel: {CHANNEL_USERNAME}")
    print("✨ Bots in system: 4")
    print("=" * 50)
    print("⚠️  IMPORTANT: Make sure that:")
    print("1. Bot is added to the channel @ChronoRoom")
    print("2. Bot has administrator rights in the channel")                          print("=" * 50)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
