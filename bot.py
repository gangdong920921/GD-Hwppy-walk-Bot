"""
걷기 챌린지 텔레그램 봇
- 대화형: 사진 → 걸음수 → 거리(km) 순서로 질문
- 1km당 27원 적립
- 사진은 Google Drive에 저장 (Apps Script가 처리)
- 누적 적립금 표시
"""

import os
import logging
import base64
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ─────────────── 설정 ───────────────
TOKEN = os.environ["TELEGRAM_TOKEN"]
APPS_SCRIPT_URL = os.environ["APPS_SCRIPT_URL"]
RATE_PER_KM = 27  # 1km당 적립금 (원)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ─────────────── 대화 상태 ───────────────
# context.user_data에 저장될 키
# stage: "waiting_photo" | "waiting_steps" | "waiting_km"
# photo_b64: base64로 인코딩된 사진
# steps: 걸음수


# ─────────────── 공통 키보드 ───────────────
def main_menu_keyboard():
    """결과 화면에 보여줄 버튼"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 이번주 순위", callback_data="rank"),
            InlineKeyboardButton("💎 전체 순위", callback_data="total"),
        ],
        [
            InlineKeyboardButton("📊 내 기록", callback_data="me"),
            InlineKeyboardButton("➕ 추가 등록", callback_data="restart"),
        ],
    ])


def restart_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👟 다시 등록하기", callback_data="restart")]
    ])


# ─────────────── /start ───────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    context.user_data.clear()
    context.user_data["stage"] = "waiting_photo"

    await update.message.reply_text(
        f"👋 안녕하세요 {user.first_name}님!\n\n"
        f"오늘도 걸으셨나요? 💪\n"
        f"걷기 인증사진을 올려주세요 📸\n\n"
        f"(언제든 /cancel 로 처음부터 다시 시작할 수 있어요)"
    )


# ─────────────── /cancel ───────────────
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "✅ 취소되었어요.\n다시 시작하려면 /start 를 눌러주세요!"
    )


# ─────────────── /help ───────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 사용 방법\n\n"
        "1️⃣ /start → 인증사진 올리기\n"
        "2️⃣ 걸음수 입력\n"
        "3️⃣ 거리(km) 입력\n"
        "4️⃣ 적립금 확인! 💰\n\n"
        f"💡 1km당 {RATE_PER_KM}원 적립됩니다.\n"
        "💡 하루에 여러 번 등록하면 누적돼요!\n\n"
        "기타 명령어:\n"
        "/cancel - 진행 중인 등록 취소\n"
        "/me - 내 누적 기록 보기\n"
        "/rank - 이번주 순위\n"
        "/total - 전체 순위"
    )


# ─────────────── 사진 받기 ───────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stage = context.user_data.get("stage")

    # 아직 시작 안 했으면 자동으로 시작
    if stage != "waiting_photo":
        context.user_data.clear()
        context.user_data["stage"] = "waiting_photo"

    try:
        # 가장 큰 해상도의 사진 가져오기
        photo = update.message.photo[-1]
        file = await photo.get_file()

        # 사진 다운로드 (메모리에)
        photo_bytes = await file.download_as_bytearray()
        photo_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")

        # 사이즈 체크 (Apps Script 한계 고려)
        size_kb = len(photo_bytes) / 1024
        logging.info(f"사진 크기: {size_kb:.1f}KB")

        context.user_data["photo_b64"] = photo_b64
        context.user_data["stage"] = "waiting_steps"

        await update.message.reply_text(
            "✨ 사진 잘 받았어요!\n\n"
            "오늘 몇 걸음 걸으셨나요? 👟\n"
            "(숫자만 입력해주세요. 예: 8000)"
        )
    except Exception:
        logging.exception("사진 처리 실패")
        await update.message.reply_text(
            "❌ 사진 처리 중 오류가 발생했어요.\n다시 보내주세요!"
        )


# ─────────────── 텍스트 받기 (걸음수 / km) ───────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    stage = context.user_data.get("stage")

    # 시작 안 한 상태에서 텍스트 입력
    if not stage:
        await update.message.reply_text(
            "👋 먼저 /start 를 눌러서 시작해주세요!\n"
            "또는 인증사진을 바로 올려주셔도 돼요 📸"
        )
        return

    # 사진을 기다리는 중인데 텍스트가 옴
    if stage == "waiting_photo":
        await update.message.reply_text(
            "📸 먼저 인증사진을 올려주세요!\n"
            "(취소하려면 /cancel)"
        )
        return

    # 걸음수 입력 단계
    if stage == "waiting_steps":
        try:
            steps = int(text.replace(",", "").replace(" ", ""))
            if steps < 0 or steps > 200000:
                raise ValueError("범위 벗어남")
        except ValueError:
            await update.message.reply_text(
                "❗ 걸음수는 숫자로 입력해주세요!\n예: 8000"
            )
            return

        context.user_data["steps"] = steps
        context.user_data["stage"] = "waiting_km"

        await update.message.reply_text(
            f"좋아요! 👟 {steps:,}걸음\n\n"
            f"그럼 거리(km)는 얼마인가요? 📏\n"
            f"(예: 5.5)"
        )
        return

    # km 입력 단계
    if stage == "waiting_km":
        try:
            km = float(text.replace(",", ".").replace(" ", ""))
            if km < 0 or km > 200:
                raise ValueError("범위 벗어남")
        except ValueError:
            await update.message.reply_text(
                "❗ 거리는 숫자로 입력해주세요!\n예: 5.5"
            )
            return

        # 모든 데이터 모임 → 서버 전송
        await submit_record(update, context, km)


# ─────────────── 서버 전송 ───────────────
async def submit_record(update: Update, context: ContextTypes.DEFAULT_TYPE, km: float):
    user = update.message.from_user
    steps = context.user_data.get("steps", 0)
    photo_b64 = context.user_data.get("photo_b64", "")

    today_money = round(km * RATE_PER_KM)

    # 처리 중 메시지
    processing_msg = await update.message.reply_text(
        "⏳ 저장 중이에요... 잠시만 기다려주세요!"
    )

    payload = {
        "action": "submit",
        "user_id": user.id,
        "name": user.first_name,
        "username": user.username or "",
        "steps": steps,
        "km": km,
        "money": today_money,
        "photo_b64": photo_b64,
    }

    try:
        res = requests.post(APPS_SCRIPT_URL, json=payload, timeout=60)
        res.raise_for_status()
        data = res.json()

        total_money = data.get("total_money", today_money)
        total_km = data.get("total_km", km)
        total_steps = data.get("total_steps", steps)

        # 처리 중 메시지 삭제
        await processing_msg.delete()

        # 결과 메시지
        result_msg = (
            "🎉 *수고하셨어요!*\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"📸 인증 완료\n"
            f"👟 {steps:,}걸음\n"
            f"📏 {km}km\n"
            f"💰 오늘 적립: *{today_money:,}원*\n"
            "━━━━━━━━━━━━━━━\n"
            f"💎 누적 적립금: *{total_money:,}원*\n"
            f"🚶 누적 거리: {total_km}km\n"
            f"📊 누적 걸음: {total_steps:,}걸음"
        )

        await update.message.reply_text(
            result_msg,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    except Exception:
        logging.exception("저장 실패")
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ 저장 중 오류가 발생했어요. 다시 시도해주세요!",
            reply_markup=restart_keyboard(),
        )

    # 상태 초기화
    context.user_data.clear()


# ─────────────── 버튼 콜백 ───────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    user = query.from_user

    if action == "restart":
        context.user_data.clear()
        context.user_data["stage"] = "waiting_photo"
        await query.message.reply_text(
            "👟 새 등록을 시작할게요!\n인증사진을 올려주세요 📸"
        )
        return

    if action == "rank":
        await send_ranking(query, "weekly", "🏆 이번주 TOP 20")
        return

    if action == "total":
        await send_ranking(query, "all", "💎 전체 누적 TOP 20")
        return

    if action == "me":
        await send_my_record(query, user)
        return


async def send_ranking(query, type_param: str, title: str):
    try:
        res = requests.get(f"{APPS_SCRIPT_URL}?type={type_param}", timeout=15)
        data = res.json()

        if not data:
            await query.message.reply_text(f"{title}\n\n아직 기록이 없어요 😢")
            return

        msg = f"{title}\n\n"
        for i, u in enumerate(data, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = u.get("name", "?")
            money = u.get("total_money", 0)
            km = u.get("total_km", 0)
            msg += f"{medal} {name} - {money:,}원 ({km}km)\n"

        await query.message.reply_text(msg)
    except Exception:
        logging.exception("순위 조회 실패")
        await query.message.reply_text("❌ 순위를 불러올 수 없어요.")


async def send_my_record(query, user):
    try:
        res = requests.get(
            f"{APPS_SCRIPT_URL}?type=me&user_id={user.id}", timeout=15
        )
        data = res.json()

        if not data or not data.get("found"):
            await query.message.reply_text(
                "📊 아직 기록이 없어요.\n첫 등록을 해보세요! 👟"
            )
            return

        msg = (
            f"📊 *{user.first_name}님의 기록*\n\n"
            f"💎 누적 적립금: *{data.get('total_money', 0):,}원*\n"
            f"🚶 누적 거리: {data.get('total_km', 0)}km\n"
            f"👟 누적 걸음: {data.get('total_steps', 0):,}걸음\n"
            f"📅 참여일수: {data.get('days', 0)}일"
        )
        await query.message.reply_text(msg, parse_mode="Markdown")
    except Exception:
        logging.exception("내 기록 조회 실패")
        await query.message.reply_text("❌ 기록을 불러올 수 없어요.")


# ─────────────── 명령어 버전 (구버전 호환) ───────────────
async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class FakeQuery:
        message = update.message
    await send_ranking(FakeQuery(), "weekly", "🏆 이번주 TOP 20")


async def cmd_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class FakeQuery:
        message = update.message
    await send_ranking(FakeQuery(), "all", "💎 전체 누적 TOP 20")


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class FakeQuery:
        message = update.message
        from_user = update.message.from_user
    await send_my_record(FakeQuery(), update.message.from_user)


# ─────────────── 메인 ───────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # 명령어
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler("total", cmd_total))

    # 사진 받기
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # 텍스트 받기 (명령어 제외)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # 버튼 콜백
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("봇 실행 중...")
    app.run_polling()


if __name__ == "__main__":
    main()
