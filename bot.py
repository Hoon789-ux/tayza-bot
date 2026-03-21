import logging
import os
import base64
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import anthropic

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN       = os.getenv("BOT_TOKEN")          # your bot token from @BotFather
ADMIN_CHAT_ID   = int(os.getenv("ADMIN_CHAT_ID")) # your personal Telegram user ID
GROUP_INVITE    = os.getenv("GROUP_INVITE_LINK")  # the private group invite link
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")  # your Anthropic API key
COURSE_PRICE    = "50,000 ကျပ်"
KBZPAY_NUMBER   = os.getenv("KBZPAY_NUMBER", "09XXXXXXXXX")   # your KBZPay number
WAVEPAY_NUMBER  = os.getenv("WAVEPAY_NUMBER", "09XXXXXXXXX")  # your Wave Pay number

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ── STUDENT STATE TRACKING ────────────────────────────────────────────────────
# States: "new" | "awaiting_screenshot" | "pending_approval" | "enrolled"
student_state: dict[int, str] = {}

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

🏦 KBZPay — `""" + KBZPAY_NUMBER + """`
📱 Wave Pay — `""" + WAVEPAY_NUMBER + """`

💰 ပမာဏ — """ + COURSE_PRICE + """

━━━━━━━━━━━━━━━

✅ ငွေလွှဲပြီးရင် payment screenshot ကို ဒီ chat မှာ တိုက်ရိုက် ပို့ပေးပါ။

မေးချင်တာရှိရင် screenshot နဲ့အတူ မေးနိုင်ပါတယ်။"""

SCREENSHOT_RECEIVED_MSG = """⏳ Screenshot ရပြီ! စစ်ဆေးနေပါတယ်...

မကြာမီ အတည်ပြုပေးပါမည် 🙏"""

APPROVED_MSG = """🎉 ဝင်ရောက်ခွင့် အတည်ပြုပြီးပါပြီ!

TayZa Official Exclusive Program မှ ကြိုဆိုပါတယ် 🔥

👇 ဒီ link ကို နှိပ်ပြီး group ထဲ ဝင်ပါ —

"""

REJECTED_MSG = """❌ ငွေပေးချေမှု အတည်မပြုနိုင်ပါ။

Screenshot ကို ပြန်စစ်ကြည့်ပြီး မှန်ကန်တဲ့ screenshot ကို ပြန်ပို့ပေးပါ။

မေးစရာရှိရင် ဒီ chat မှာ မေးနိုင်ပါတယ် 🙏"""

# ── HANDLERS ──────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    student_state[uid] = "new"
    await update.message.reply_text(WELCOME_MSG)


async def enroll(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if student_state.get(uid) == "enrolled":
        await update.message.reply_text("✅ မင်းက ဒီ program မှာ ဝင်ပြီးသားပါ! Group link ကို ယခင်က ပို့ပြီးပါပြီ။")
        return
    student_state[uid] = "awaiting_screenshot"
    await update.message.reply_text(ENROLL_MSG, parse_mode="Markdown")


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user

    if student_state.get(uid) not in ("awaiting_screenshot", "new"):
        await update.message.reply_text("ဝင်ရောက်ဖို့ အရင် /enroll နှိပ်ပါ။")
        return

    await update.message.reply_text(SCREENSHOT_RECEIVED_MSG)
    student_state[uid] = "pending_approval"

    # Download the photo
    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    img_bytes = await file.download_as_bytearray()
    img_b64 = base64.standard_b64encode(img_bytes).decode()

    # Ask Claude to verify the screenshot
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
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
                        
Please check if this looks like a legitimate KBZPay or Wave Pay payment screenshot and if the amount matches 50,000 MMK.

Reply in this exact JSON format only:
{{"looks_valid": true/false, "amount_detected": "amount you see or null", "payment_method": "KBZPay/WavePay/unknown", "confidence": "high/medium/low", "notes": "brief note"}}"""
                    }
                ]
            }]
        )
        
        result_text = response.content[0].text.strip()
        # Extract JSON from response
        if "{" in result_text:
            result_text = result_text[result_text.index("{"):result_text.rindex("}")+1]
        result = json.loads(result_text)
        
        valid = result.get("looks_valid", False)
        amount = result.get("amount_detected", "မသိ")
        method = result.get("payment_method", "မသိ")
        confidence = result.get("confidence", "low")
        notes = result.get("notes", "")

        ai_summary = f"""{'✅' if valid else '⚠️'} AI စစ်ဆေးချက် — {'Valid ဖြစ်ဟန်ရှိ' if valid else 'Suspicious ဖြစ်နိုင်'}
💰 Amount: {amount}
📱 Method: {method}
🎯 Confidence: {confidence}
📝 {notes}"""

    except Exception as e:
        log.error(f"Claude API error: {e}")
        ai_summary = "⚠️ AI စစ်ဆေးမရ — ကိုယ်တိုင် စစ်ဆေးပါ"

    # Forward to admin with approve/reject buttons
    name = user.full_name
    username = f"@{user.username}" if user.username else "username မရှိ"
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{uid}")
    ]])

    caption = f"""💳 ငွေပေးချေမှု စစ်ဆေးပေးပါ

👤 Student: {name} ({username})
🆔 User ID: {uid}

{ai_summary}"""

    await ctx.bot.forward_message(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=update.effective_chat.id,
        message_id=update.message.message_id
    )
    await ctx.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=caption,
        reply_markup=keyboard
    )


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, uid_str = query.data.split("_", 1)
    uid = int(uid_str)

    if action == "approve":
        student_state[uid] = "enrolled"
        await ctx.bot.send_message(
            chat_id=uid,
            text=APPROVED_MSG + GROUP_INVITE
        )
        await query.edit_message_text(
            text=query.message.text + "\n\n✅ APPROVED — Group link ပို့ပြီး"
        )
    elif action == "reject":
        student_state[uid] = "awaiting_screenshot"
        await ctx.bot.send_message(chat_id=uid, text=REJECTED_MSG)
        await query.edit_message_text(
            text=query.message.text + "\n\n❌ REJECTED — Student ကို အသိပေးပြီး"
        )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = student_state.get(uid, "new")

    if state == "new":
        await update.message.reply_text(WELCOME_MSG)
    elif state == "awaiting_screenshot":
        await update.message.reply_text(
            "📸 Payment screenshot ကို ဒီ chat မှာ တိုက်ရိုက် ပို့ပေးပါ။\n\nမေးချင်တာရှိရင် screenshot နဲ့အတူ ပို့နိုင်ပါတယ်။"
        )
    elif state == "pending_approval":
        await update.message.reply_text("⏳ မင်းရဲ့ payment ကို စစ်ဆေးနေဆဲပါ။ မကြာမီ အတည်ပြုပေးပါမည် 🙏")
    elif state == "enrolled":
        await update.message.reply_text("✅ မင်းက ဒီ program မှာ ဝင်ပြီးသားပါ! Group ထဲမှာ ကြည့်ပါ 🔥")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("enroll", enroll))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
