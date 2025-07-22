from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import os
from datetime import datetime
import pytz
import psycopg2
from psycopg2 import pool

# Bot token and settings
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7850825321:AAHxoPdkBCfDxlz95_1q3TqEw-YAVb2w5gE")
AFFILIATE_MANAGER = "@xfAffliateManger"  # Client's Telegram handle
MANAGER_ID = "7677838863"  # Client's Telegram ID
CHANNEL_ID = "@xForium"
ADMINS = [7553301979, 7677838863]  # Your ID and client's ID

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
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            user_id BIGINT PRIMARY KEY,
                            username TEXT,
                            joins INTEGER DEFAULT 0,
                            balance FLOAT DEFAULT 0.0,
                            last_reset TIMESTAMP WITH TIME ZONE
                        )
                    """)
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

def check_weekly_reset(user_id):
    now = datetime.now(pytz.UTC)
    try:
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT last_reset, joins, balance FROM users WHERE user_id = %s", (user_id,))
                user = cur.fetchone()
                if user:
                    last_reset = user[0]
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

def get_user_tier_earnings(joins):
    if joins >= 100:
        return "Tier 3", 2.00 * joins
    elif joins >= 50:
        return "Tier 2", 1.50 * joins
    elif joins >= 25:
        return "Tier 1", 1.00 * joins
    return "Tier 0", 0.00

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

def get_dashboard_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Joins", callback_data="joins")],
        [InlineKeyboardButton("📊 Tier System", callback_data="tier_system")],
        [InlineKeyboardButton("🥇 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("📞 Support", callback_data="support")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

def get_balance_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Request Payout", callback_data="request_payout")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")]
    ])

async def view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    try:
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, username, joins, balance FROM users")
                users = cur.fetchall()
            db_pool.putconn(conn)
        if not users:
            await update.message.reply_text("No users found.")
            return
        message = "Users:\n" + "\n".join(
            f"ID: {user[0]}, Username: {user[1]}, Joins: {user[2]}, Balance: £{user[3]:.2f}"
            for user in users
        )
        await update.message.reply_text(message)
    except Exception as e:
        print(f"Error in view_users: {e}")
        await update.message.reply_text("Error fetching users.")

async def view_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    try:
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, referrer_id, referred_id, join_time FROM referrals")
                referrals = cur.fetchall()
            db_pool.putconn(conn)
        if not referrals:
            await update.message.reply_text("No referrals found.")
            return
        message = "Referrals:\n" + "\n".join(
            f"ID: {r[0]}, Referrer ID: {r[1]}, Referred ID: {r[2]}, Time: {r[3]}"
            for r in referrals
        )
        await update.message.reply_text(message)
    except Exception as e:
        print(f"Error in view_referrals: {e}")
        await update.message.reply_text("Error fetching referrals.")

async def view_payouts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    try:
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, user_id, amount, request_time, status FROM payouts")
                payouts = cur.fetchall()
            db_pool.putconn(conn)
        if not payouts:
            await update.message.reply_text("No payouts found.")
            return
        message = "Payouts:\n" + "\n".join(
            f"ID: {p[0]}, User ID: {p[1]}, Amount: £{p[2]:.2f}, Time: {p[3]}, Status: {p[4]}"
            for p in payouts
        )
        await update.message.reply_text(message)
    except Exception as e:
        print(f"Error in view_payouts: {e}")
        await update.message.reply_text("Error fetching payouts.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    try:
        get_or_create_user(user_id, username)
        check_weekly_reset(user_id)
        affiliate_link = f"https://t.me/xForium?start={user_id}"
        welcome_message = (
            f"Welcome to the bot!\n"
            f"Your personal affiliate link to join {CHANNEL_ID}: {affiliate_link}\n\n"
            f"Please join {CHANNEL_ID} to start earning referrals!"
        )
        await update.message.reply_text(welcome_message, reply_markup=get_dashboard_keyboard())
    except Exception as e:
        print(f"Error in start: {e}")
        await update.message.reply_text("Oops, something went wrong! Please try again later.")

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
                            SELECT id FROM referrals WHERE referrer_id = %s AND referred_id = %s
                        """, (referrer_id, user_id))
                        if not cur.fetchone():
                            cur.execute("""
                                INSERT INTO referrals (referrer_id, referred_id, join_time)
                                VALUES (%s, %s, %s)
                            """, (referrer_id, user_id, datetime.now(pytz.UTC)))
                            conn.commit()
                    db_pool.putconn(conn)
        
        affiliate_link = f"https://t.me/xForium?start={user_id}"
        welcome_message = (
            f"Welcome to the bot!\n"
            f"Your personal affiliate link to join {CHANNEL_ID}: {affiliate_link}\n\n"
            f"Please join {CHANNEL_ID} to start earning referrals!"
        )
        await update.message.reply_text(welcome_message, reply_markup=get_dashboard_keyboard())
    except Exception as e:
        print(f"Error in handle_referral: {e}")
        await update.message.reply_text("Oops, something went wrong! Please try again later.")

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
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start, filters=~filters.Regex(r"^\d+$")))
    application.add_handler(CommandHandler("start", handle_referral, filters=filters.Regex(r"^\d+$")))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("viewusers", view_users))
    application.add_handler(CommandHandler("viewreferrals", view_referrals))
    application.add_handler(CommandHandler("viewpayouts", view_payouts))
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path=TOKEN,
        webhook_url=f"https://my-telegram-bot-qqbx.onrender.com/{TOKEN}"
    )

if __name__ == "__main__":
    main()