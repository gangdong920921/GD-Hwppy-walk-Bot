import logging
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# 환경변수
TOKEN = "YOUR_TELEGRAM_TOKEN"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxEpLk7NIpFJDJQ6PDICcR3WUHMGT8eNkPHeqpFjT6B8tF-ugNqgDHMbBpXs-BR2hli/exec"

logging.basicConfig(level=logging.INFO)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """👟 걷기 챌린지에 오신 것을 환영합니다!

사용 방법:
/걸음수 8000 → 오늘 걸음수 입력
/순위 → 이번주 TOP 20
/전체순위 → 전체 랭킹
/내기록 → 내 통계 보기
"""
    await update.message.reply_text(msg)

# /걸음수
async def steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        steps = int(context.args[0])
    except:
        await update.message.reply_text("❗ 사용법: /걸음수 8000")
        return

    user = update.message.from_user

    payload = {
        "user_id": user.id,
        "name": user.first_name,
        "steps": steps
    }

    res = requests.post(APPS_SCRIPT_URL, json=payload)

    if res.status_code == 200:
        await update.message.reply_text(f"✅ {steps}걸음 저장 완료!")
    else:
        await update.message.reply_text("❌ 저장 실패")

# /순위
async def weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = requests.get(APPS_SCRIPT_URL + "?type=weekly")
    data = res.json()

    msg = "🏆 이번주 TOP 20\n\n"
    for i, user in enumerate(data, 1):
        msg += f"{i}. {user['name']} - {user['total']}걸음\n"

    await update.message.reply_text(msg)

# /전체순위
async def alltime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = requests.get(APPS_SCRIPT_URL + "?type=all")
    data = res.json()

    msg = "🏆 전체 순위 TOP 20\n\n"
    for i, user in enumerate(data, 1):
        msg += f"{i}. {user['name']} - {user['total']}걸음\n"

    await update.message.reply_text(msg)

# /내기록
async def my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = requests.get(APPS_SCRIPT_URL + "?type=all")
    data = res.json()

    user = update.message.from_user
    my_data = [u for u in data if u["name"] == user.first_name]

    if not my_data:
        await update.message.reply_text("기록이 없습니다 😢")
        return

    total = my_data[0]["total"]

    msg = f"""📊 내 기록

총 걸음수: {total}
"""
    await update.message.reply_text(msg)


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("걸음수", steps))
    app.add_handler(CommandHandler("순위", weekly))
    app.add_handler(CommandHandler("전체순위", alltime))
    app.add_handler(CommandHandler("내기록", my))

    print("봇 실행 중...")
    app.run_polling()


if __name__ == "__main__":
    main()