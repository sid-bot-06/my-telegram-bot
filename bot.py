from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import os
from datetime import datetime, timedelta
import pytz
import psycopg2
from psycopg2 import pool

# Bot token and affiliate manager
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7850825321:AAHxoPdkBCfDxlz95_1q3TqEw-YAVb2w5gE")
AFFILIATE_MANAGER = "@kamizkae"  # Replace with your Telegram handle
MANAGER_ID = "7182401388"  # Replace with your 10-digit Telegram ID
CHANNEL_ID = "@xForium"

# Database connection pool
db_pool = None

def init_db():
    global db_pool
    db_url = os.getenv("DATABASE_URL")
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, db_url)
        if db_pool:
            with db_pool.getconn() as conn:
                with conn.cursor() as cur:
                    # Create users table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            user_id BIGINT PRIMARY KEY,
                            username TEXT,
                            joins INTEGER DEFAULT 0,
                            balance FLOAT DEFAULT 0.0,
                            last_reset TIMESTAMP WITH TIME ZONE
                        )
                    """)
                    # Create referrals table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS referrals (
                            id SERIAL PRIMARY KEY,
                            referrer_id BIGINT,
                            referred_id BIGINT,
                            join_time TIMESTAMP WITH TIME ZONE,
                            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                            FOREIGN KEY (referred_id) REFERENCES users(user_id)
                        )
                    """)
                    # Create payouts table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS payouts (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            amount FLOAT,
                            request_time TIMESTAMP WITH TIME ZONE,
                            status TEXT DEFAULT 'Pending',
                            FOREIGN KEY (user_id) REFERENCES users(user_id)
                        )
                    """)
                    conn.commit()
                db_pool.putconn(conn)
    except Exception as e:
        print(f"Database initialization failed: {e}")

# Get or create user
def get_or_create_user(user_id, username):
    try:
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                user = cur.fetchone()
                if not user:
                    now = datetime.now(pytz.UTC)
                    cur.execute("""
                        INSERT INTO users (user_id, username, joins, balance, last_reset)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (user_id, username, 0, 0.0, now))
                    conn.commit()
                else:
                    cur.execute("UPDATE users SET username = %s WHERE user_id = %s", (username, user_id))
                    conn.commit()
            db_pool.putconn(conn)
    except Exception as e:
        print(f"Error in get_or_create_user: {e}")

# Check and reset weekly joins
def check_weekly_reset(user_id):
    now = datetime.now(pytz.UTC)
    try:
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT last_reset, joins, balance FROM users WHERE user_id = %s", (user_id,))
                user = cur.fetchone()
                if user:
                    last_reset = user[0]
                    # Ensure last_reset is timezone-aware
                    if last_reset.tzinfo is None:
                        last_reset = last_reset.replace(tzinfo=pytz.UTC)
                    if (now - last_reset).days >= 7:
                        tier, earnings = get_user_tier_earnings(user[1])
                        new_balance = user[2] + earnings
                        cur.execute("""
                            UPDATE users SET joins = 0, balance = %s, last_reset = %s WHERE user_id = %s
                        """, (new_balance, now, user_id))
                        conn.commit()
            db_pool.putconn(conn)
    except Exception as e:
        print(f"Error in check_weekly_reset: {e}")

# Calculate tier and earnings
def get_user_tier_earnings(joins):
    if joins >= 100:
        return "Tier 3", 2.00 * joins
    elif joins >= 50:
        return "Tier 2", 1.50 * joins
    elif joins >= 25:
        return "Tier 1", 1.00 * joins
    return "Tier 0", 0.00

# Get user data
def get_user_data(user_id):
    try:
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT joins, balance, username FROM users WHERE user_id = %s", (user_id,))
                user = cur.fetchone()
            db_pool.putconn(conn)
        return user or (0, 0.0, "Unknown")
    except Exception as e:
        print(f"Error in get_user_data: {e}")
        return (0, 0.0, "Unknown")

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

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    try:
        get_or_create_user(user_id, username)
        check_weekly_reset(user_id)
        affiliate_link = f"https://t.me/xForium?start={user_id}"
        welcome_message = (
            f"Welcome to the bot!\n"
            f"Your personal affiliate link to join {CHANNEL_ID}: {affiliate_link}"
        )
        await update.message.reply_text(welcome_message, reply_markup=get_dashboard_keyboard())
    except Exception as e:
        print(f"Error in start: {e}")
        await update.message.reply_text("Oops, something went wrong! Please try again later.")

# Handle referral link (/start with parameter)
async def handle_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    args = context.args
    
    try:
        get_or_create_user(user_id, username)
        check_weekly_reset(user_id)
        
        if args and args[0].isdigit():
            referrer_id = int(args[0])
            if referrer_id != user_id:  # Prevent self-referral
                get_or_create_user(referrer_id, "Unknown")
                check_weekly_reset(referrer_id)
                with db_pool.getconn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO referrals (referrer_id, referred_id, join_time)
                            VALUES (%s, %s, %s)
                        """, (referrer_id, user_id, datetime.now(pytz.UTC)))
                        cur.execute("UPDATE users SET joins = joins + 1 WHERE user_id = %s", (referrer_id,))
                        conn.commit()
                    db_pool.putconn(conn)
        
        affiliate_link = f"https://t.me/xForium?start={user_id}"
        welcome_message = (
            f"Welcome to the bot!\n"
            f"Your personal affiliate link to join {CHANNEL_ID}: {affiliate_link}"
        )
        await update.message.reply_text(welcome_message, reply_markup=get_dashboard_keyboard())
    except Exception as e:
        print(f"Error in handle_referral: {e}")
        await update.message.reply_text("Oops, something went wrong! Please try again later.")

# Button handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    try:
        get_or_create_user(user_id, query.from_user.username or "Unknown")
        check_weekly_reset(user_id)

        if query.data == "joins":
            joins, balance, username = get_user_data(user_id)
            tier, earnings = get_user_tier_earnings(joins)
            message = (
                f"👤 Joins\n\n"
                f"You have {joins} joins to {CHANNEL_ID}.\n"
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
            with db_pool.getconn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username, joins FROM users ORDER BY joins DESC LIMIT 5")
                    top_users = cur.fetchall()
                db_pool.putconn(conn)
            leaderboard = [f"{i+1}) {user[0]} - {user[1]}" for i, user in enumerate(top_users)]
            message = (
                f"🥇 Leaderboard\n\n"
                f"Top 5 joins to {CHANNEL_ID}:\n" + "\n".join(leaderboard or ["No data yet"]) +
                f"\n\nAppear on the top 5 leaderboard for a bonus at the end of the week!"
            )
            await query.message.reply_text(message, reply_markup=get_back_keyboard())

        elif query.data == "balance":
            joins, balance, username = get_user_data(user_id)
            message = f"💰 You have a balance of £{balance:.2f} ready to payout."
            await query.message.reply_text(message, reply_markup=get_balance_keyboard())

        elif query.data == "request_payout":
            joins, balance, username = get_user_data(user_id)
            if balance <= 0:
                await query.message.reply_text("You do not have balance to payout.", reply_markup=get_balance_keyboard())
            else:
                with db_pool.getconn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO payouts (user_id, amount, request_time)
                            VALUES (%s, %s, %s)
                        """, (user_id, balance, datetime.now(pytz.UTC)))
                        cur.execute("UPDATE users SET balance = 0 WHERE user_id = %s", (user_id,))
                        conn.commit()
                    db_pool.putconn(conn)
                await context.bot.send_message(
                    chat_id=MANAGER_ID,
                    text=(
                        f"Payout Request:\n"
                        f"User: @{username} (ID: {user_id})\n"
                        f"Amount: £{balance:.2f}"
                    )
                )
                await query.message.reply_text("Payout request submitted! You will be contacted soon.", reply_markup=get_balance_keyboard())

        elif query.data == "support":
            message = f"📞 Contact our affiliate manager: {AFFILIATE_MANAGER}"
            await query.message.reply_text(message, reply_markup=get_back_keyboard())

        elif query.data == "back":
            await query.message.reply_text("Back to dashboard", reply_markup=get_dashboard_keyboard())
    except Exception as e:
        print(f"Error in button: {e}")
        await query.message.reply_text("Oops, something went wrong! Please try again later.")

def main():
    # Initialize database
    init_db()
    
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start, filters=~filters.Regex(r"^\d+$")))
    application.add_handler(CommandHandler("start", handle_referral, filters=filters.Regex(r"^\d+$")))
    application.add_handler(CallbackQueryHandler(button))

    # Start webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path=TOKEN,
        webhook_url=f"https://my-telegram-bot-qqbx.onrender.com/{TOKEN}"
    )

if __name__ == "__main__":
    main()