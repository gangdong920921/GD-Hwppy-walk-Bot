"""
걷기 챌린지 텔레그램 봇 (최종 안정화 버전)
- 신규 사용자: 소속 → 이름 → 부 → 팀 → 구역 등록
- 등록된 사용자: 사진 → 걸음수 → km
- 1km당 27원 적립
- 사진은 Google Drive에 저장 (Apps Script 처리)
- Render Web Service 호환 (더미 웹서버 포함)
"""

import os
import logging
import base64
import threading
import http.server
import socketserver
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

GROUPS = ["부녀회", "장년회", "청년회", "자문회", "교역자"]

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ─────────────── 키보드 ───────────────
def group_keyboard():
    """소속 선택 버튼"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👩 부녀회", callback_data="grp:부녀회"),
         InlineKeyboardButton("👨 장년회", callback_data="grp:장년회")],
        [InlineKeyboardButton("🧑 청년회", callback_data="grp:청년회"),
         InlineKeyboardButton("💼 자문회", callback_data="grp:자문회")],
        [InlineKeyboardButton("⛪ 교역자", callback_data="grp:교역자")],
    ])


def main_menu_keyboard():
    """결과 화면 메뉴"""
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
        [InlineKeyboardButton("👟 다시 시도", callback_data="restart")]
    ])


# ─────────────── 헬퍼 ───────────────
def fetch_profile(user_id: int):
    """Apps Script에서 프로필 조회. 없으면 None"""
    try:
        res = requests.get(
            f"{APPS_SCRIPT_URL}?type=profile&user_id={user_id}", timeout=15
        )
        data = res.json()
        if data.get("found"):
            return data
    except Exception:
        logging.exception("프로필 조회 실패")
    return None


def format_team_label(profile: dict) -> str:
    """프로필 → '2부 3팀 5구역' 형태"""
    parts = []
    bu = profile.get("bu")
    team = profile.get("team")
    gu = profile.get("gu")
    if bu not in (None, "", 0):
        parts.append(f"{bu}부")
    if team not in (None, "", 0):
        parts.append(f"{team}팀")
    if gu not in (None, "", 0):
        parts.append(f"{gu}구역")
    return " ".join(parts)


def parse_number(text: str):
    """텍스트에서 숫자만 추출. 실패시 None"""
    cleaned = text.replace(" ", "").replace("부", "").replace("팀", "").replace("구역", "")
    try:
        n = int(cleaned)
        if n < 0 or n > 999:
            return None
        return n
    except ValueError:
        return None


# ─────────────── /start ───────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    context.user_data.clear()

    profile = fetch_profile(user.id)

    if profile:
        # 기존 사용자
        context.user_data["profile"] = profile
        context.user_data["stage"] = "waiting_photo"
        team_label = format_team_label(profile)
        await update.message.reply_text(
            f"👋 {profile['name']}님 안녕하세요!\n"
            f"({profile['group']} / {team_label})\n\n"
            f"오늘도 걸으셨나요? 💪\n"
            f"걷기 인증사진을 올려주세요 📸\n\n"
            f"💡 정보 변경: /등록\n"
            f"💡 취소: /cancel"
        )
    else:
        # 신규 사용자
        await start_registration(update, context)


# ─────────────── /등록 ───────────────
async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await start_registration(update, context)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stage"] = "reg_group"
    await update.message.reply_text(
        "👋 안녕하세요! 걷기 챌린지에 오신 걸 환영해요 🎉\n\n"
        "먼저 등록부터 할게요.\n"
        "어디 소속이신가요?",
        reply_markup=group_keyboard(),
    )


# ─────────────── /cancel ───────────────
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "✅ 취소되었어요.\n다시 시작하려면 /start"
    )


# ─────────────── /help ───────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 사용 방법\n\n"
        "1️⃣ /start → 인증사진\n"
        "2️⃣ 걸음수 입력\n"
        "3️⃣ 거리(km) 입력\n"
        "4️⃣ 적립금 확인! 💰\n\n"
        f"💡 1km당 {RATE_PER_KM}원 적립\n"
        "💡 하루 여러 번 등록 가능 (누적)\n\n"
        "기타 명령어:\n"
        "/등록 - 정보 다시 등록\n"
        "/cancel - 진행 취소\n"
        "/me - 내 기록\n"
        "/rank - 이번주 순위\n"
        "/total - 전체 순위"
    )


# ─────────────── 사진 받기 ───────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    # 등록 안 된 사용자면 등록부터
    if "profile" not in context.user_data:
        profile = fetch_profile(user.id)
        if not profile:
            await update.message.reply_text(
                "📝 먼저 등록이 필요해요!\n/start 를 눌러주세요."
            )
            return
        context.user_data["profile"] = profile

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()
        photo_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")

        size_kb = len(photo_bytes) / 1024
        logging.info(f"사진 크기: {size_kb:.1f}KB")

        context.user_data["photo_b64"] = photo_b64
        context.user_data["stage"] = "waiting_steps"

        await update.message.reply_text(
            "✨ 사진 잘 받았어요!\n\n"
            "오늘 몇 걸음 걸으셨나요? 👟\n"
            "(숫자만 입력. 예: 8000)"
        )
    except Exception:
        logging.exception("사진 처리 실패")
        await update.message.reply_text(
            "❌ 사진 처리 중 오류가 발생했어요. 다시 보내주세요!"
        )


# ─────────────── 텍스트 받기 ───────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    stage = context.user_data.get("stage")
    user = update.message.from_user

    # ── 등록: 이름 ──
    if stage == "reg_name":
        if len(text) > 20 or len(text) < 1:
            await update.message.reply_text("❗ 이름은 1~20자로 입력해주세요.")
            return
        context.user_data["reg_name"] = text
        context.user_data["stage"] = "reg_bu"
        await update.message.reply_text(
            f"{text}님, 반가워요! 😊\n\n"
            f"몇 부이신가요?\n"
            f"(숫자만 입력. 예: 2)"
        )
        return

    # ── 등록: 부 ──
    if stage == "reg_bu":
        bu = parse_number(text)
        if bu is None:
            await update.message.reply_text("❗ 숫자만 입력해주세요. (예: 2)")
            return
        context.user_data["reg_bu"] = bu
        context.user_data["stage"] = "reg_team"
        await update.message.reply_text(
            f"{bu}부 ✅\n\n"
            f"몇 팀이신가요?\n"
            f"(숫자만 입력. 예: 3)"
        )
        return

    # ── 등록: 팀 ──
    if stage == "reg_team":
        team = parse_number(text)
        if team is None:
            await update.message.reply_text("❗ 숫자만 입력해주세요. (예: 3)")
            return
        context.user_data["reg_team"] = team
        context.user_data["stage"] = "reg_gu"
        await update.message.reply_text(
            f"{team}팀 ✅\n\n"
            f"몇 구역이신가요?\n"
            f"(숫자만 입력. 예: 5)"
        )
        return

    # ── 등록: 구역 → 저장 ──
    if stage == "reg_gu":
        gu = parse_number(text)
        if gu is None:
            await update.message.reply_text("❗ 숫자만 입력해주세요. (예: 5)")
            return
        context.user_data["reg_gu"] = gu
        await save_profile(update, context)
        return

    # ── 일반 단계: 등록 안 됐으면 안내 ──
    if "profile" not in context.user_data and stage not in ("reg_group", "reg_name", "reg_bu", "reg_team", "reg_gu"):
        profile = fetch_profile(user.id)
        if not profile:
            await update.message.reply_text(
                "📝 먼저 등록이 필요해요!\n/start 를 눌러주세요."
            )
            return
        context.user_data["profile"] = profile

    # ── 시작 안 함 ──
    if not stage:
        await update.message.reply_text(
            "👋 /start 를 눌러서 시작해주세요!\n또는 인증사진을 바로 올려주셔도 돼요 📸"
        )
        return

    # ── 사진 대기 중인데 텍스트 ──
    if stage == "waiting_photo":
        await update.message.reply_text(
            "📸 먼저 인증사진을 올려주세요!\n(취소: /cancel)"
        )
        return

    # ── 걸음수 ──
    if stage == "waiting_steps":
        try:
            steps = int(text.replace(",", "").replace(" ", ""))
            if steps < 0 or steps > 200000:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❗ 걸음수는 숫자로! (예: 8000)")
            return

        context.user_data["steps"] = steps
        context.user_data["stage"] = "waiting_km"
        await update.message.reply_text(
            f"좋아요! 👟 {steps:,}걸음\n\n"
            f"그럼 거리(km)는 얼마인가요? 📏\n"
            f"(예: 5.5)"
        )
        return

    # ── km ──
    if stage == "waiting_km":
        try:
            km = float(text.replace(",", ".").replace(" ", ""))
            if km < 0 or km > 200:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❗ 거리는 숫자로! (예: 5.5)")
            return

        await submit_record(update, context, km)
        return


# ─────────────── 프로필 저장 ───────────────
async def save_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    group = context.user_data.get("reg_group", "")
    name = context.user_data.get("reg_name", "")
    bu = context.user_data.get("reg_bu", "")
    team = context.user_data.get("reg_team", "")
    gu = context.user_data.get("reg_gu", "")

    payload = {
        "action": "register",
        "user_id": user.id,
        "username": user.username or "",
        "group": group,
        "name": name,
        "bu": bu,
        "team": team,
        "gu": gu,
    }

    processing = await update.message.reply_text("⏳ 등록 중이에요...")

    try:
        res = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
        res.raise_for_status()
        data = res.json()

        if not data.get("ok"):
            raise Exception(data.get("error", "unknown"))

        profile = {
            "group": group,
            "name": name,
            "bu": bu,
            "team": team,
            "gu": gu,
        }
        context.user_data.clear()
        context.user_data["profile"] = profile
        context.user_data["stage"] = "waiting_photo"

        team_label = format_team_label(profile)

        try:
            await processing.delete()
        except:
            pass

        await update.message.reply_text(
            f"✅ 등록 완료!\n\n"
            f"👤 {name}\n"
            f"🏷 {group} / {team_label}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"이제 걷기 인증을 시작할게요! 💪\n"
            f"인증사진을 올려주세요 📸"
        )
    except Exception:
        logging.exception("프로필 저장 실패")
        try:
            await processing.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ 등록 실패. 다시 시도해주세요.\n/start"
        )
        context.user_data.clear()


# ─────────────── 기록 제출 ───────────────
async def submit_record(update: Update, context: ContextTypes.DEFAULT_TYPE, km: float):
    user = update.message.from_user
    profile = context.user_data.get("profile", {})
    steps = context.user_data.get("steps", 0)
    photo_b64 = context.user_data.get("photo_b64", "")

    today_money = round(km * RATE_PER_KM)

    processing_msg = await update.message.reply_text(
        "⏳ 저장 중이에요... 잠시만 기다려주세요!"
    )

    payload = {
        "action": "submit",
        "user_id": user.id,
        "username": user.username or "",
        "name": profile.get("name", user.first_name),
        "group": profile.get("group", ""),
        "bu": profile.get("bu", ""),
        "team": profile.get("team", ""),
        "gu": profile.get("gu", ""),
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

        try:
            await processing_msg.delete()
        except:
            pass

        team_label = format_team_label(profile)

        result_msg = (
            "🎉 *수고하셨어요!*\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"👤 {profile.get('name', '')} ({profile.get('group', '')}/{team_label})\n"
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

    # 기록 데이터만 초기화 (프로필은 유지)
    keep_profile = context.user_data.get("profile")
    context.user_data.clear()
    if keep_profile:
        context.user_data["profile"] = keep_profile


# ─────────────── 버튼 콜백 ───────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    user = query.from_user

    # 소속 선택
    if action.startswith("grp:"):
        group = action.split(":", 1)[1]
        context.user_data["reg_group"] = group
        context.user_data["stage"] = "reg_name"
        await query.message.reply_text(
            f"✅ {group} 선택!\n\n"
            f"이름을 알려주세요. 😊\n"
            f"(예: 박윤정)"
        )
        return

    if action == "restart":
        if "profile" not in context.user_data:
            profile = fetch_profile(user.id)
            if profile:
                context.user_data["profile"] = profile
        context.user_data["stage"] = "waiting_photo"
        for k in ["photo_b64", "steps"]:
            context.user_data.pop(k, None)
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
            group = u.get("group", "")
            team_label = format_team_label(u)
            money = u.get("total_money", 0)
            km = u.get("total_km", 0)

            sub_parts = []
            if group: sub_parts.append(group)
            if team_label: sub_parts.append(team_label)
            sub_str = f" ({'/'.join(sub_parts)})" if sub_parts else ""

            msg += f"{medal} {name}{sub_str}\n     💰 {money:,}원 ({km}km)\n"

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

        name = data.get("name", "")
        group = data.get("group", "")
        team_label = format_team_label(data)
        msg = (
            f"📊 *{name}님의 기록*\n"
            f"({group} / {team_label})\n\n"
            f"💎 누적 적립금: *{data.get('total_money', 0):,}원*\n"
            f"🚶 누적 거리: {data.get('total_km', 0)}km\n"
            f"👟 누적 걸음: {data.get('total_steps', 0):,}걸음\n"
            f"📅 참여일수: {data.get('days', 0)}일"
        )
        await query.message.reply_text(msg, parse_mode="Markdown")
    except Exception:
        logging.exception("내 기록 조회 실패")
        await query.message.reply_text("❌ 기록을 불러올 수 없어요.")


# ─────────────── 명령어 단축 ───────────────
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


# ─────────────── Render Web Service용 더미 서버 ───────────────
class HealthHandler(http.server.BaseHTTPRequestHandler):
    """Render 포트 체크용. 실제 기능 없음."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        return  # 로그 시끄러운 거 끄기


def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        with socketserver.TCPServer(("0.0.0.0", port), HealthHandler) as httpd:
            print(f"더미 웹서버 실행 중 (포트 {port})")
            httpd.serve_forever()
    except Exception as e:
        logging.exception(f"더미 서버 에러: {e}")


# ─────────────── 메인 ───────────────
def main():
    # 1) 더미 웹서버 (Render 포트 검사 통과용)
    threading.Thread(target=start_dummy_server, daemon=True).start()

    # 2) 텔레그램 봇
    app = ApplicationBuilder().token(TOKEN).build()

    # 명령어
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("등록", cmd_register))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler("total", cmd_total))

    # 사진
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # 텍스트 (명령어 제외)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # 버튼
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("봇 실행 중...")
    # drop_pending_updates=True : 이전 인스턴스의 큐를 지워서 충돌 방지
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
