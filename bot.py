import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# 🔥 네 Apps Script URL (이미 적용 완료)
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlX_P6S7vVcCcKcFTK4lE2nbeoUpmwcwi0fw-HVaXs4a0gWZIP1fDJ8TgPSsaWMg/exec"

# 👉 여기에 BotFather 토큰 넣기
TOKEN = "YOUR_TELEGRAM_TOKEN"

logging.basicConfig(level=logging.INFO)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👟 걷기 챌린지 시작!\n\n"
        "/걸음수 8000\n"
        "/순위\n"
        "/전체순위\n"
        "/내기록"
    )

# /걸음수
async def steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ 사용법: /걸음수 8000")
        return

    try:
        step = int(context.args[0])
    except:
        await update.message.reply_text("❗ 숫자만 입력해주세요")
        return

    user = update.message.from_user

    payload = {
        "user_id": user.id,
        "name": user.first_name,
        "steps": step
    }

    try:
        res = requests.post(APPS_SCRIPT_URL, json=payload)
        if res.status_code == 200:
            await update.message.reply_text(f"✅ {step}걸음 저장 완료!")
        else:
            await update.message.reply_text("❌ 저장 실패")
    except:
        await update.message.reply_text("❌ 서버 오류")

# /순위
async def weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(APPS_SCRIPT_URL + "?type=weekly")
        data = res.json()

        msg = "🏆 이번주 TOP 20\n\n"
        for i, u in enumerate(data, 1):
            msg += f"{i}. {u['name']} - {u['total']}걸음\n"

        await update.message.reply_text(msg)
    except:
        await update.message.reply_text("❌ 불러오기 실패")

# /전체순위
async def alltime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(APPS_SCRIPT_URL + "?type=all")
        data = res.json()

        msg = "🏆 전체 순위 TOP 20\n\n"
        for i, u in enumerate(data, 1):
            msg += f"{i}. {u['name']} - {u['total']}걸음\n"

        await update.message.reply_text(msg)
    except:
        await update.message.reply_text("❌ 불러오기 실패")

# /내기록 (개선 버전)
async def my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(APPS_SCRIPT_URL + "?type=all")
        data = res.json()

        user = update.message.from_user

        # 이름 기준 (현재 구조)
        my = [u for u in data if u["name"] == user.first_name]

        if not my:
            await update.message.reply_text("기록 없음 😢")
            return

        total = my[0]["total"]

        await update.message.reply_text(
            f"📊 내 기록\n\n총 걸음수: {total}"
        )
    except:
        await update.message.reply_text("❌ 조회 실패")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("steps",   cmd_steps))
app.add_handler(CommandHandler("rank",    cmd_ranking))
app.add_handler(CommandHandler("total",   cmd_total_ranking))
app.add_handler(CommandHandler("me",      cmd_my_record))
app.add_handler(CommandHandler("help",    cmd_help))

    print("봇 실행 중...")
    app.run_polling()


if __name__ == "__main__":
    main()
