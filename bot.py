import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# 🔥 환경변수에서 가져오기 (Render 대시보드 → Environment)
TOKEN = os.environ["TELEGRAM_TOKEN"]
APPS_SCRIPT_URL = os.environ["APPS_SCRIPT_URL"]

logging.basicConfig(level=logging.INFO)


# /start
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👟 걷기 챌린지 시작!\n\n"
        "/steps 8000  - 오늘 걸음수 저장\n"
        "/rank         - 이번주 TOP 20\n"
        "/total        - 전체 누적 TOP 20\n"
        "/me           - 내 기록 보기\n"
        "/help         - 도움말"
    )


# /help
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 명령어 안내\n\n"
        "/steps 8000 → 8000걸음 저장\n"
        "/rank → 이번주 순위\n"
        "/total → 전체 순위\n"
        "/me → 내 누적 기록"
    )


# /steps
async def cmd_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ 사용법: /steps 8000")
        return

    try:
        step = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ 숫자만 입력해주세요")
        return

    user = update.message.from_user

    payload = {
        "user_id": user.id,
        "name": user.first_name,
        "steps": step,
    }

    try:
        res = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        if res.status_code == 200:
            await update.message.reply_text(f"✅ {step}걸음 저장 완료!")
        else:
            await update.message.reply_text("❌ 저장 실패")
    except Exception:
        logging.exception("steps error")
        await update.message.reply_text("❌ 서버 오류")


# /rank (이번주 순위)
async def cmd_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(APPS_SCRIPT_URL + "?type=weekly", timeout=10)
        data = res.json()

        if not data:
            await update.message.reply_text("아직 이번주 기록이 없어요 😢")
            return

        msg = "🏆 이번주 TOP 20\n\n"
        for i, u in enumerate(data, 1):
            msg += f"{i}. {u['name']} - {u['total']}걸음\n"

        await update.message.reply_text(msg)
    except Exception:
        logging.exception("ranking error")
        await update.message.reply_text("❌ 불러오기 실패")


# /total (전체 순위)
async def cmd_total_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(APPS_SCRIPT_URL + "?type=all", timeout=10)
        data = res.json()

        if not data:
            await update.message.reply_text("아직 기록이 없어요 😢")
            return

        msg = "🏆 전체 순위 TOP 20\n\n"
        for i, u in enumerate(data, 1):
            msg += f"{i}. {u['name']} - {u['total']}걸음\n"

        await update.message.reply_text(msg)
    except Exception:
        logging.exception("total error")
        await update.message.reply_text("❌ 불러오기 실패")


# /me (내 기록)
async def cmd_my_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(APPS_SCRIPT_URL + "?type=all", timeout=10)
        data = res.json()

        user = update.message.from_user
        mine = [u for u in data if u["name"] == user.first_name]

        if not mine:
            await update.message.reply_text("기록 없음 😢")
            return

        total = mine[0]["total"]
        await update.message.reply_text(
            f"📊 내 기록\n\n총 걸음수: {total}"
        )
    except Exception:
        logging.exception("me error")
        await update.message.reply_text("❌ 조회 실패")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("steps", cmd_steps))
    app.add_handler(CommandHandler("rank",  cmd_ranking))
    app.add_handler(CommandHandler("total", cmd_total_ranking))
    app.add_handler(CommandHandler("me",    cmd_my_record))

    print("봇 실행 중...")
    app.run_polling()


if __name__ == "__main__":
    main()
