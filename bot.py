from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import os
from datetime import datetime, timedelta
import pytz

# Bot token from BotFather
TOKEN = "7850825321:AAHxoPdkBCfDxlz95_1q3TqEw-YAVb2w5gE"
AFFILIATE_MANAGER = "@xfAffiliateManger"  # Replace with actual handle

# In-memory storage (resets on bot restart)
users = {}  # Format: {user_id: {"joins": int, "balance": float, "username": str, "last_reset": datetime}}

# Dashboard keyboard
def get_dashboard_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Joins", callback_data="joins")],
        [InlineKeyboardButton("📊 Tier System", callback_data="tier_system")],
        [InlineKeyboardButton("🥇 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("📞 Support", callback_data="support")]
    ])

# Back button keyboard
def get_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

# Balance keyboard
def get_balance_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Request Payout", callback_data="request_payout")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

# Check and reset weekly joins
def check_weekly_reset(user_id):
    now = datetime.now(pytz.UTC)
    if user_id not in users:
        users[user_id] = {"joins": 0, "balance": 0.0, "username": "", "last_reset": now}
    else:
        last_reset = users[user_id]["last_reset"]
        if (now - last_reset).days >= 7:
            users[user_id]["joins"] = 0
            users[user_id]["last_reset"] = now

# Calculate tier and earnings
def get_user_tier_earnings(joins):
    if joins >= 100:
        return "Tier 3", 2.00 * joins
    elif joins >= 50:
        return "Tier 2", 1.50 * joins
    elif joins >= 25:
        return "Tier 1", 1.00 * joins
    return "Tier 0", 0.00

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    check_weekly_reset(user_id)
    users[user_id]["username"] = username
    
    # Generate unique affiliate link
    affiliate_link = affiliate_link = f"https://t.me/xForium?start={user_id}"
    
    welcome_message = (
        f"Welcome to the bot!\n"
        f"Your personal affiliate link: {affiliate_link}"
    )
    await update.message.reply_text(welcome_message, reply_markup=get_dashboard_keyboard())

# Handle referral link (/start with parameter)
async def handle_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    args = context.args
    
    if args and args[0].isdigit():
        referrer_id = int(args[0])
        if referrer_id != user_id:  # Prevent self-referral
            check_weekly_reset(referrer_id)
            users[referrer_id]["joins"] += 1
    
    check_weekly_reset(user_id)
    users[user_id]["username"] = username
    
    # Show dashboard
    affiliate_link = f"https://t.me/Affiliate_xforiumbot?start={user_id}"
    welcome_message = (
        f"Welcome to the bot!\n"
        f"Your personal affiliate link: {affiliate_link}"
    )
    await update.message.reply_text(welcome_message, reply_markup=get_dashboard_keyboard())

# Button handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    check_weekly_reset(user_id)

    if query.data == "joins":
        joins = users[user_id]["joins"]
        tier, earnings = get_user_tier_earnings(joins)
        message = (
            f"👤 Joins\n\n"
            f"You have {joins} joins.\n"
            f"Rank: {tier}\n"
            f"Earnings: £{earnings:.2f}\n\n"
            f"Joins reset every week.\n"
            f"Your earnings will be added to your balance once the week is over."
        )
        await query.message.reply_text(message, reply_markup=get_back_keyboard())

    elif query.data == "tier_system":
        message = (
            f"📊 Tier System\n\n"
            f"Tier 1: Reach 25 invites\n£1.00 per member\n\n"
            f"Tier 2: Reach 50 invites\n£1.50 per member\n\n"
            f"Tier 3: Reach 100 invites\n£2.00 per member"
        )
        await query.message.reply_text(message, reply_markup=get_back_keyboard())

    elif query.data == "leaderboard":
        # Get top 5 users by joins
        top_users = sorted(users.items(), key=lambda x: x[1]["joins"], reverse=True)[:5]
        leaderboard = [f"{i+1}) {user[1]['username']} - {user[1]['joins']}" 
                       for i, user in enumerate(top_users)]
        message = (
            f"🥇 Leaderboard\n\n"
            f"Top 5 joins:\n" + "\n".join(leaderboard or ["No data yet"]) +
            f"\n\nAppear on the top 5 leaderboard for a bonus at the end of the week!"
        )
        await query.message.reply_text(message, reply_markup=get_back_keyboard())

    elif query.data == "balance":
        balance = users[user_id]["balance"]
        message = f"💰 You have a balance of £{balance:.2f} ready to payout."
        await query.message.reply_text(message, reply_markup=get_balance_keyboard())

    elif query.data == "support":
        message = f"📞 Contact our affiliate manager: {AFFILIATE_MANAGER}"
        await query.message.reply_text(message, reply_markup=get_back_keyboard())

    elif query.data == "request_payout":
        # Placeholder for payout logic
        await query.message.reply_text("Payout request submitted! (Placeholder)", reply_markup=get_balance_keyboard())

    elif query.data == "back":
        await query.message.reply_text("Back to dashboard", reply_markup=get_dashboard_keyboard())

def main():
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start, filters=~filters.Regex(r"^\d+$")))
    application.add_handler(CommandHandler("start", handle_referral, filters=filters.Regex(r"^\d+$")))
    application.add_handler(CallbackQueryHandler(button))

    # Start webhook for Render
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path=TOKEN,
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    )

if __name__ == "__main__":
    main()