import logging
import os
import base64
import json
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import anthropic

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID    = int(os.getenv("ADMIN_CHAT_ID"))
SECOND_ADMIN_ID  = 8261222204
GROUP_INVITE     = os.getenv("GROUP_INVITE_LINK")
ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY")
COURSE_PRICE     = "50,000 ကျပ်"
KBZPAY_NUMBER    = os.getenv("KBZPAY_NUMBER", "09XXXXXXXXX")
KBZPAY_NAME      = os.getenv("KBZPAY_NAME", "TayZa")

SUPABASE_URL     = "https://fzqbrtxkanqubneltdqu.supabase.co"
SUPABASE_KEY     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ6cWJydHhrYW5xdWJuZWx0ZHF1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQyOTUzMTEsImV4cCI6MjA4OTg3MTMxMX0.-4NarhDoyyU7-nl_r_Ck2BJzXwwJsnKHzxfKwZ4XG8c"

ADMINS = (ADMIN_CHAT_ID, SECOND_ADMIN_ID)

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ── SUPABASE HELPERS ──────────────────────────────────────────────────────────
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def db_get(table, filters=""):
    r = httpx.get(f"{SUPABASE_URL}/rest/v1/{table}?{filters}", headers=HEADERS)
    return r.json() if r.status_code == 200 else []

def db_upsert(table, data):
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"},
        json=data
    )
    return r.status_code in (200, 201)

def db_update(table, data, filters):
    r = httpx.patch(f"{SUPABASE_URL}/rest/v1/{table}?{filters}", headers=HEADERS, json=data)
    return r.status_code in (200, 204)

def db_delete(table, filters):
    r = httpx.delete(f"{SUPABASE_URL}/rest/v1/{table}?{filters}", headers=HEADERS)
    return r.status_code in (200, 204)

# ── STUDENT STATE HELPERS ─────────────────────────────────────────────────────
def get_student(uid):
    rows = db_get("students", f"uid=eq.{uid}")
    return rows[0] if rows else None

def set_student_state(uid, state, name="", username=""):
    db_upsert("students", {"uid": uid, "state": state, "name": name, "username": username})

def get_state(uid):
    s = get_student(uid)
    return s["state"] if s else "new"

# ── TRANSACTION ID HELPERS ────────────────────────────────────────────────────
def is_duplicate_txn(txn_id):
    if not txn_id:
        return False
    rows = db_get("transactions", f"txn_id=eq.{txn_id}")
    return len(rows) > 0

def save_txn(txn_id):
    if txn_id:
        db_upsert("transactions", {"txn_id": txn_id})

# ── PENDING APPROVAL HELPERS ──────────────────────────────────────────────────
def save_pending(uid, name, username, ai_summary, msg_id):
    db_upsert("pending_approvals", {
        "uid": uid,
        "name": name,
        "username": username,
        "ai_summary": ai_summary,
        "msg_id": msg_id
    })

def remove_pending(uid):
    db_delete("pending_approvals", f"uid=eq.{uid}")

# ── VIDEO HELPERS ─────────────────────────────────────────────────────────────
def get_video(key):
    rows = db_get("videos", f"key=eq.{key}")
    return rows[0]["file_id"] if rows else None

def set_video(key, file_id):
    db_upsert("videos", {"key": key, "file_id": file_id})

def remove_video(key):
    db_update("videos", {"file_id": None}, f"key=eq.{key}")

# ── MESSAGES ──────────────────────────────────────────────────────────────────
WELCOME_MSG = """👋 မင်္ဂလာပါ!

TayZa Official Exclusive Program မှ ကြိုဆိုပါတယ် 🔥

ဒီ program မှာ မင်းရမည့်အရာတွေ —

🎬 Content Creation — hook၊ structure၊ real creator တွေသုံးတဲ့ strategy အကုန်
🤖 AI — နေ့တိုင်း AI ကို ကိုယ့်အကျိုးအတွက် ထိထိရောက်ရောက် သုံးတတ်အောင်
🧠 Mindset — ဦးနှောက်ထဲက အရင်ပြောင်းမှ ဘာမဆို အဆင်ပြေမည်

━━━━━━━━━━━━━━━

💰 ဈေးနှုန်း — """ + COURSE_PRICE + """

First batch သာ ဒီဈေးနဲ့ ရမည်။ နေရာ 100 သာ ရှိတည်။

━━━━━━━━━━━━━━━

📲 လျှောက်ထားဖို့ အဆင်သင့်ဖြစ်ရင် /enroll လို့ နှိပ်ပါ"""

ENROLL_MSG = """🙌 ကောင်းတယ်! လျှောက်ထားဖို့ ဆုံးဖြတ်လိုက်တာ မှန်ကန်တဲ့ ဆုံးဖြတ်ချက်ပါ။

ငွေပေးချေဖို့ အောက်ပါ နည်းလမ်းများ သုံးပါ —

🏦 KBZPay
   ဖုန်းနံပါတ် — `""" + KBZPAY_NUMBER + """`
   အကောင့်အမည် — """ + KBZPAY_NAME + """

💰 ပမာဏ — """ + COURSE_PRICE + """

━━━━━━━━━━━━━━━

⚠️ ငွေလွှဲခင် အကောင့်အမည် မှန်မမှန် သေချာစစ်ပါ။

✅ ငွေလွှဲပြီးရင် payment screenshot ကို ဒီ chat မှာ တိုက်ရိုက် ပို့ပေးပါ။"""

SCREENSHOT_RECEIVED_MSG = """⏳ Screenshot ရပြီ! စစ်ဆေးနေပါတယ်...

မကြာမီ အတည်ပြုပေးပါမည် 🙏"""

APPROVED_MSG = """🎉 ဝင်ရောက်ခွင့် အတည်ပြုပြီးပါပြီ!

TayZa Official Exclusive Program မှ ကြိုဆိုပါတယ် 🔥

👇 ဒီ link ကို နှိပ်ပြီး group ထဲ ဝင်ပါ —

"""

REJECTED_MSG = """❌ ငွေပေးချေမှု အတည်မပြုနိုင်ပါ။

Screenshot ကို ပြန်စစ်ကြည့်ပြီး မှန်ကန်တဲ့ screenshot ကို ပြန်ပို့ပေးပါ။

မေးစရာရှိရင် ဒီ chat မှာ မေးနိုင်ပါတယ် 🙏"""

DUPLICATE_MSG = """⚠️ ဒီ receipt ကို အသုံးပြီးသားပါ။

မှန်ကန်တဲ့ မင်းရဲ့ transaction screenshot အသစ် ပို့ပေးပါ။"""

# ── ADMIN VIDEO COMMANDS ──────────────────────────────────────────────────────

async def set_welcome_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("⚠️ Video message ကို reply လုပ်ပြီး /setwelcomevideo နှိပ်ပါ။")
        return
    set_video("welcome", update.message.reply_to_message.video.file_id)
    await update.message.reply_text("✅ Welcome video (/start) set လုပ်ပြီး!")

async def set_enroll_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("⚠️ Video message ကို reply လုပ်ပြီး /setenrollvideo နှိပ်ပါ။")
        return
    set_video("enroll", update.message.reply_to_message.video.file_id)
    await update.message.reply_text("✅ Enroll video (/enroll) set လုပ်ပြီး!")

async def set_approve_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("⚠️ Video message ကို reply လုပ်ပြီး /setapprovevideo နှိပ်ပါ။")
        return
    set_video("approve", update.message.reply_to_message.video.file_id)
    await update.message.reply_text("✅ Approve video set လုပ်ပြီး!")

async def remove_welcome_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    remove_video("welcome")
    await update.message.reply_text("✅ Welcome video ဖျက်ပြီး။")

async def remove_enroll_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    remove_video("enroll")
    await update.message.reply_text("✅ Enroll video ဖျက်ပြီး။")

async def remove_approve_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    remove_video("approve")
    await update.message.reply_text("✅ Approve video ဖျက်ပြီး။")

async def video_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    w = get_video("welcome")
    e = get_video("enroll")
    a = get_video("approve")
    await update.message.reply_text(f"""📹 Video Status

/start video: {'✅ Set' if w else '❌ Not set'}
/enroll video: {'✅ Set' if e else '❌ Not set'}
Approve video: {'✅ Set' if a else '❌ Not set'}""")

# ── MAIN HANDLERS ─────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    username = update.effective_user.username or ""
    set_student_state(uid, "new", name, username)
    vid = get_video("welcome")
    if vid:
        await ctx.bot.send_video(chat_id=uid, video=vid)
    await update.message.reply_text(WELCOME_MSG)


async def enroll(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    username = update.effective_user.username or ""
    if get_state(uid) == "enrolled":
        await update.message.reply_text("✅ မင်းက ဒီ program မှာ ဝင်ပြီးသားပါ! Group link ကို ယခင်က ပို့ပြီးပါပြီ။")
        return
    set_student_state(uid, "awaiting_screenshot", name, username)
    vid = get_video("enroll")
    if vid:
        await ctx.bot.send_video(chat_id=uid, video=vid)
    await update.message.reply_text(ENROLL_MSG, parse_mode="Markdown")


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user
    state = get_state(uid)

    if state not in ("awaiting_screenshot", "new"):
        await update.message.reply_text("ဝင်ရောက်ဖို့ အရင် /enroll နှိပ်ပါ။")
        return

    await update.message.reply_text(SCREENSHOT_RECEIVED_MSG)
    set_student_state(uid, "pending_approval", user.full_name, user.username or "")

    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    img_bytes = await file.download_as_bytearray()
    img_b64 = base64.standard_b64encode(img_bytes).decode()

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}
                    },
                    {
                        "type": "text",
                        "text": f"""This is a payment screenshot for a course enrollment. The course costs {COURSE_PRICE} (50000 Myanmar Kyats).
Please check:
1. Is this a legitimate KBZPay payment screenshot?
2. Does the amount match 50,000 MMK?
3. What is the transaction ID or reference number?
4. What is the transaction date and time?
5. What is the recipient name?
Reply in this exact JSON format only:
{{"looks_valid": true/false, "amount_detected": "amount or null", "payment_method": "KBZPay/unknown", "transaction_id": "the exact transaction ID or null", "transaction_date": "date and time or null", "recipient_name": "name or null", "confidence": "high/medium/low", "notes": "brief note"}}"""
                    }
                ]
            }]
        )

        result_text = response.content[0].text.strip()
        if "{" in result_text:
            result_text = result_text[result_text.index("{"):result_text.rindex("}")+1]
        result = json.loads(result_text)

        valid       = result.get("looks_valid", False)
        amount      = result.get("amount_detected", "မသိ")
        method      = result.get("payment_method", "မသိ")
        txn_id      = result.get("transaction_id")
        txn_date    = result.get("transaction_date", "မသိ")
        recipient   = result.get("recipient_name", "မသိ")
        confidence  = result.get("confidence", "low")
        notes       = result.get("notes", "")

        # Duplicate check
        if txn_id and is_duplicate_txn(txn_id):
            await update.message.reply_text(DUPLICATE_MSG)
            set_student_state(uid, "awaiting_screenshot", user.full_name, user.username or "")
            await ctx.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"🚨 Duplicate receipt!\n\n👤 {user.full_name} (@{user.username or 'no username'})\n🆔 {uid}\n📋 Transaction ID: {txn_id}"
            )
            return

        save_txn(txn_id)

        ai_summary = f"""{'✅' if valid else '⚠️'} AI စစ်ဆေးချက် — {'Valid' if valid else 'Suspicious'}
💰 Amount: {amount}
📱 Method: {method}
🧾 Transaction ID: {txn_id or 'မတွေ့'}
📅 Date: {txn_date}
👤 Recipient: {recipient}
🎯 Confidence: {confidence}
📝 {notes}
{'⚠️ Transaction ID မတွေ့ — ဂရုစိုက်ပါ' if not txn_id else ''}"""

    except Exception as e:
        log.error(f"Claude API error: {e}")
        ai_summary = "⚠️ AI စစ်ဆေးမရ — ကိုယ်တိုင် စစ်ဆေးပါ"

    name     = user.full_name
    username = f"@{user.username}" if user.username else "username မရှိ"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{uid}")
    ]])

    caption = f"""💳 ငွေပေးချေမှု စစ်ဆေးပေးပါ

👤 Student: {name} ({username})
🆔 User ID: {uid}

{ai_summary}"""

    # Forward screenshot and save to Supabase
    fwd = await ctx.bot.forward_message(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=update.effective_chat.id,
        message_id=update.message.message_id
    )
    msg = await ctx.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=caption,
        reply_markup=keyboard
    )
    # Save pending approval to Supabase — survives crashes
    save_pending(uid, name, username, ai_summary, msg.message_id)


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, uid_str = query.data.split("_", 1)
    uid = int(uid_str)

    if action == "approve":
        set_student_state(uid, "enrolled")
        remove_pending(uid)
        vid = get_video("approve")
        if vid:
            await ctx.bot.send_video(chat_id=uid, video=vid)
        await ctx.bot.send_message(chat_id=uid, text=APPROVED_MSG + GROUP_INVITE)
        await query.edit_message_text(text=query.message.text + "\n\n✅ APPROVED — Group link ပို့ပြီး")

    elif action == "reject":
        set_student_state(uid, "awaiting_screenshot")
        remove_pending(uid)
        await ctx.bot.send_message(chat_id=uid, text=REJECTED_MSG)
        await query.edit_message_text(text=query.message.text + "\n\n❌ REJECTED — Student ကို အသိပေးပြီး")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    state = get_state(uid)

    if state == "new":
        await update.message.reply_text(WELCOME_MSG)
    elif state == "awaiting_screenshot":
        await update.message.reply_text("📸 Payment screenshot ကို ဒီ chat မှာ တိုက်ရိုက် ပို့ပေးပါ။")
    elif state == "pending_approval":
        await update.message.reply_text("⏳ မင်းရဲ့ payment ကို စစ်ဆေးနေဆဲပါ။ မကြာမီ အတည်ပြုပေးပါမည် 🙏")
    elif state == "enrolled":
        await update.message.reply_text("✅ မင်းက ဒီ program မှာ ဝင်ပြီးသားပါ! Group ထဲမှာ ကြည့်ပါ 🔥")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",               start))
    app.add_handler(CommandHandler("enroll",              enroll))
    app.add_handler(CommandHandler("setwelcomevideo",     set_welcome_video))
    app.add_handler(CommandHandler("setenrollvideo",      set_enroll_video))
    app.add_handler(CommandHandler("setapprovevideo",     set_approve_video))
    app.add_handler(CommandHandler("removewelcomevideo",  remove_welcome_video))
    app.add_handler(CommandHandler("removeenrollvideo",   remove_enroll_video))
    app.add_handler(CommandHandler("removeapprovevideo",  remove_approve_video))
    app.add_handler(CommandHandler("videostatus",         video_status))
    app.add_handler(MessageHandler(filters.PHOTO,         handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
