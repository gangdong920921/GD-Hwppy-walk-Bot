"""
걷기 챌린지 텔레그램 봇 (최종)
- 부녀회: 숫자(부) → 팀 → 구역 / [👑회장단][🌱새신자부][✨3040부] 버튼
- 장년회/자문회: 숫자(부) → 팀 → 구역 / [👑회장단][🌱새신자부] 버튼
- 청년회: 부 버튼(1~7부, 대학부, 새신자부, 기능과) → 구역 또는 부서
- 교역자: 부서 텍스트
- 1걸음 = 65cm = 0.026원
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
RATE_PER_STEP = 0.026
STEP_LENGTH_M = 0.65

GROUPS = ["부녀회", "장년회", "청년회", "자문회", "교역자"]

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ─────────────── 키보드 ───────────────
def group_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👩 부녀회", callback_data="grp:부녀회"),
         InlineKeyboardButton("👨 장년회", callback_data="grp:장년회")],
        [InlineKeyboardButton("🧑 청년회", callback_data="grp:청년회"),
         InlineKeyboardButton("💼 자문회", callback_data="grp:자문회")],
        [InlineKeyboardButton("⛪ 교역자", callback_data="grp:교역자")],
    ])


def youth_bu_keyboard():
    """청년회 부 선택"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1부", callback_data="ybu:1부"),
         InlineKeyboardButton("2부", callback_data="ybu:2부"),
         InlineKeyboardButton("3부", callback_data="ybu:3부"),
         InlineKeyboardButton("4부", callback_data="ybu:4부")],
        [InlineKeyboardButton("5부", callback_data="ybu:5부"),
         InlineKeyboardButton("6부", callback_data="ybu:6부"),
         InlineKeyboardButton("7부", callback_data="ybu:7부")],
        [InlineKeyboardButton("📚 대학부", callback_data="ybu:대학부"),
         InlineKeyboardButton("🌱 새신자부", callback_data="ybu:새신자부")],
        [InlineKeyboardButton("⚙️ 기능과", callback_data="ybu:기능과")],
    ])


def function_dept_keyboard():
    """기능과 10개 부서"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 회장단", callback_data="fdept:회장단"),
         InlineKeyboardButton("🏫 총교관", callback_data="fdept:총교관")],
        [InlineKeyboardButton("📋 기획문화과", callback_data="fdept:기획문화과"),
         InlineKeyboardButton("💬 상담심방과", callback_data="fdept:상담심방과")],
        [InlineKeyboardButton("📖 교육과", callback_data="fdept:교육과"),
         InlineKeyboardButton("⚽ 사업체육과", callback_data="fdept:사업체육과")],
        [InlineKeyboardButton("🤝 섭외과", callback_data="fdept:섭외과"),
         InlineKeyboardButton("🚗 봉사교통과", callback_data="fdept:봉사교통과")],
        [InlineKeyboardButton("✈️ 해외전도과", callback_data="fdept:해외전도과"),
         InlineKeyboardButton("📣 전도과", callback_data="fdept:전도과")],
    ])


def youth_7bu_gu_keyboard():
    """청년회 7부 구역 선택 (1~11구역, 국제부, 부장가편)"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1구역", callback_data="y7gu:1"),
         InlineKeyboardButton("2구역", callback_data="y7gu:2"),
         InlineKeyboardButton("3구역", callback_data="y7gu:3"),
         InlineKeyboardButton("4구역", callback_data="y7gu:4")],
        [InlineKeyboardButton("5구역", callback_data="y7gu:5"),
         InlineKeyboardButton("6구역", callback_data="y7gu:6"),
         InlineKeyboardButton("7구역", callback_data="y7gu:7"),
         InlineKeyboardButton("8구역", callback_data="y7gu:8")],
        [InlineKeyboardButton("9구역", callback_data="y7gu:9"),
         InlineKeyboardButton("10구역", callback_data="y7gu:10"),
         InlineKeyboardButton("11구역", callback_data="y7gu:11")],
        [InlineKeyboardButton("🌐 국제부 구역", callback_data="y7gu:국제부"),
         InlineKeyboardButton("📋 부장가편 구역", callback_data="y7gu:부장가편")],
    ])


def chairman_keyboard(group: str = ""):
    """회장단/새신자부 버튼 (부녀회/장년회/자문회용)
    부녀회만 3040부 버튼 추가"""
    rows = [
        [InlineKeyboardButton("👑 회장단", callback_data="chair:회장단"),
         InlineKeyboardButton("🌱 새신자부", callback_data="chair:새신자부")],
    ]
    if group == "부녀회":
        rows.append(
            [InlineKeyboardButton("✨ 3040부", callback_data="chair:3040")]
        )
    return InlineKeyboardMarkup(rows)


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 이번주 순위", callback_data="rank"),
            InlineKeyboardButton("💎 전체 순위", callback_data="total"),
        ],
        [
            InlineKeyboardButton("📊 내 기록", callback_data="me"),
            InlineKeyboardButton("➕ 다음 기록 넣기", callback_data="restart"),
        ],
    ])


def restart_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👟 다시 시도", callback_data="restart")]
    ])


# ─────────────── 헬퍼 ───────────────
def fetch_profile(user_id: int):
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
    """프로필 → 표시용 라벨"""
    group = profile.get("group", "")

    # 교역자: 부서 텍스트
    if group == "교역자":
        dept = profile.get("dept", "")
        return dept if dept else ""

    # 청년회
    if group == "청년회":
        bu = profile.get("bu")
        gu = profile.get("gu")
        dept = profile.get("dept", "")

        bu_str = ""
        if bu not in (None, "", 0):
            bu_str = str(bu)
            if bu_str.isdigit():
                bu_str = f"{bu_str}부"

        # 기능과 → "기능과 / 부서"
        if bu_str == "기능과" and dept:
            return f"{bu_str} {dept}"

        parts = [bu_str] if bu_str else []
        if gu not in (None, "", 0):
            gu_str = str(gu)
            if gu_str.isdigit():
                gu_str = f"{gu_str}구역"
            elif gu_str in ("국제부", "부장가편"):
                # 7부의 특수 구역
                gu_str = f"{gu_str} 구역"
            parts.append(gu_str)
        return " ".join(parts)

    # 부녀회/장년회/자문회
    bu = profile.get("bu")
    team = profile.get("team")
    gu = profile.get("gu")

    # 회장단
    if str(bu) == "회장단":
        return "회장단"

    parts = []
    if bu not in (None, "", 0):
        bu_str = str(bu)
        if bu_str.isdigit():
            bu_str = f"{bu_str}부"
        elif bu_str == "3040":
            bu_str = "3040부"
        # "새신자부"는 그대로
        parts.append(bu_str)
    if team not in (None, "", 0):
        team_str = str(team)
        if team_str.isdigit():
            team_str = f"{team_str}팀"
        parts.append(team_str)
    if gu not in (None, "", 0):
        gu_str = str(gu)
        if gu_str.isdigit():
            gu_str = f"{gu_str}구역"
        parts.append(gu_str)
    return " ".join(parts)


def parse_number(text: str):
    cleaned = text.replace(" ", "").replace("부", "").replace("팀", "").replace("구역", "")
    try:
        n = int(cleaned)
        if n < 0 or n > 999:
            return None
        return n
    except ValueError:
        return None


def steps_to_km(steps: int) -> float:
    return round(steps * STEP_LENGTH_M / 1000, 2)


# ─────────────── /start ───────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    context.user_data.clear()

    profile = fetch_profile(user.id)

    if profile:
        context.user_data["profile"] = profile
        context.user_data["stage"] = "waiting_photo"
        team_label = format_team_label(profile)
        sub = f"({profile['group']}"
        if team_label:
            sub += f" / {team_label}"
        sub += ")"
        await update.message.reply_text(
            f"👋 {profile['name']}님 안녕하세요!\n"
            f"{sub}\n\n"
            f"오늘도 걸으셨나요? 💪\n"
            f"걷기 인증사진을 올려주세요 📸\n\n"
            f"💡 정보 변경: /register\n"
            f"💡 취소: /cancel"
        )
    else:
        await start_registration(update, context)


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


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("✅ 취소되었어요.\n다시 시작하려면 /start")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 사용 방법\n\n"
        "1️⃣ /start → 인증사진\n"
        "2️⃣ 걸음수 입력 → 거리 자동 계산\n"
        "3️⃣ 적립금 확인! 💰\n\n"
        f"💡 1걸음 = 65cm\n"
        f"💡 1걸음당 {RATE_PER_STEP}원 적립\n"
        "💡 하루 여러 번 등록 가능 (누적)\n\n"
        "기타 명령어:\n"
        "/register - 정보 다시 등록\n"
        "/cancel - 진행 취소\n"
        "/me - 내 기록\n"
        "/rank - 이번주 순위\n"
        "/total - 전체 순위"
    )


# ─────────────── 사진 ───────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if "profile" not in context.user_data:
        profile = fetch_profile(user.id)
        if not profile:
            await update.message.reply_text("📝 먼저 등록이 필요해요!\n/start 를 눌러주세요.")
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
        await update.message.reply_text("❌ 사진 처리 중 오류. 다시 보내주세요!")


# ─────────────── 텍스트 ───────────────
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

        group = context.user_data.get("reg_group")
        if group == "교역자":
            context.user_data["stage"] = "reg_dept"
            await update.message.reply_text(
                f"{text}님, 반가워요! 😊\n\n"
                f"어느 부서이신가요?\n"
                f"(예: 교육부, 청년부, 행정부)"
            )
        elif group == "청년회":
            context.user_data["stage"] = "reg_youth_bu"
            await update.message.reply_text(
                f"{text}님, 반가워요! 😊\n\n"
                f"어느 부이신가요?",
                reply_markup=youth_bu_keyboard(),
            )
        else:
            # 부녀회/장년회/자문회
            context.user_data["stage"] = "reg_bu"
            if group == "부녀회":
                extra_btn_text = "👑 회장단 / 🌱 새신자부 / ✨ 3040부는 아래 버튼!"
            else:
                extra_btn_text = "👑 회장단 / 🌱 새신자부는 아래 버튼!"

            await update.message.reply_text(
                f"{text}님, 반가워요! 😊\n\n"
                f"몇 부이신가요?\n"
                f"숫자만 입력 (예: 2)\n\n"
                f"{extra_btn_text}",
                reply_markup=chairman_keyboard(group),
            )
        return

    # ── 등록: 교역자 부서 ──
    if stage == "reg_dept":
        if len(text) > 20 or len(text) < 1:
            await update.message.reply_text("❗ 부서는 1~20자로 입력해주세요.")
            return
        context.user_data["reg_dept"] = text
        await save_profile(update, context)
        return

    # ── 등록: 부 (부녀회/장년회/자문회) ──
    if stage == "reg_bu":
        bu = parse_number(text)
        if bu is None:
            group = context.user_data.get("reg_group", "")
            extra = "💡 3040부는 아래 ✨3040부 버튼\n" if group == "부녀회" else ""
            await update.message.reply_text(
                "❗ 숫자만 입력해주세요. (예: 2)\n"
                f"{extra}"
                "💡 회장단/새신자부는 아래 버튼"
            )
            return
        context.user_data["reg_bu"] = bu
        context.user_data["stage"] = "reg_team"
        await update.message.reply_text(
            f"{bu}부 ✅\n\n몇 팀이신가요?\n(숫자만 입력. 예: 3)"
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
            f"{team}팀 ✅\n\n몇 구역이신가요?\n(숫자만 입력. 예: 5)"
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

    # ── 일반 ──
    reg_stages = ("reg_group", "reg_name", "reg_bu", "reg_team", "reg_gu",
                  "reg_dept", "reg_youth_bu", "reg_youth_fdept", "reg_youth_7gu")
    if "profile" not in context.user_data and stage not in reg_stages:
        profile = fetch_profile(user.id)
        if not profile:
            await update.message.reply_text("📝 먼저 등록이 필요해요!\n/start 를 눌러주세요.")
            return
        context.user_data["profile"] = profile

    if not stage:
        await update.message.reply_text(
            "👋 /start 를 눌러서 시작해주세요!\n또는 인증사진을 바로 올려주셔도 돼요 📸"
        )
        return

    if stage == "waiting_photo":
        await update.message.reply_text("📸 먼저 인증사진을 올려주세요!\n(취소: /cancel)")
        return

    if stage == "waiting_steps":
        try:
            steps = int(text.replace(",", "").replace(" ", ""))
            if steps < 0 or steps > 200000:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❗ 걸음수는 숫자로! (예: 8000)")
            return

        context.user_data["steps"] = steps
        km = steps_to_km(steps)
        await submit_record(update, context, km)
        return


# ─────────────── 프로필 저장 ───────────────
async def save_profile(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """update 또는 callback_query 둘 다 받을 수 있게"""
    # callback_query 에는 .from_user 가 직접 있고,
    # update.message 의 경우는 message.from_user 에 있음
    if hasattr(update_or_query, 'from_user') and not hasattr(update_or_query, 'effective_message'):
        # callback_query
        user = update_or_query.from_user
        message = update_or_query.message
    else:
        # update
        user = update_or_query.message.from_user
        message = update_or_query.message

    group = context.user_data.get("reg_group", "")
    name = context.user_data.get("reg_name", "")
    bu = context.user_data.get("reg_bu", "")
    team = context.user_data.get("reg_team", "")
    gu = context.user_data.get("reg_gu", "")
    dept = context.user_data.get("reg_dept", "")

    payload = {
        "action": "register",
        "user_id": user.id,
        "username": user.username or "",
        "group": group,
        "name": name,
        "bu": bu,
        "team": team,
        "gu": gu,
        "dept": dept,
    }

    processing = await message.reply_text("⏳ 등록 중이에요...")

    try:
        res = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
        res.raise_for_status()
        data = res.json()

        if not data.get("ok"):
            raise Exception(data.get("error", "unknown"))

        profile = {
            "group": group, "name": name,
            "bu": bu, "team": team, "gu": gu, "dept": dept,
        }
        context.user_data.clear()
        context.user_data["profile"] = profile
        context.user_data["stage"] = "waiting_photo"

        team_label = format_team_label(profile)

        try: await processing.delete()
        except: pass

        sub = group
        if team_label:
            sub += f" / {team_label}"

        await message.reply_text(
            f"✅ 등록 완료!\n\n"
            f"👤 {name}\n"
            f"🏷 {sub}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"이제 걷기 인증을 시작할게요! 💪\n"
            f"인증사진을 올려주세요 📸"
        )
    except Exception:
        logging.exception("프로필 저장 실패")
        try: await processing.delete()
        except: pass
        await message.reply_text("❌ 등록 실패. 다시 시도해주세요.\n/start")
        context.user_data.clear()


# ─────────────── 기록 제출 ───────────────
async def submit_record(update: Update, context: ContextTypes.DEFAULT_TYPE, km: float):
    user = update.message.from_user
    profile = context.user_data.get("profile", {})
    steps = context.user_data.get("steps", 0)
    photo_b64 = context.user_data.get("photo_b64", "")

    today_money = round(steps * RATE_PER_STEP)

    processing_msg = await update.message.reply_text("⏳ 저장 중이에요...")

    payload = {
        "action": "submit",
        "user_id": user.id,
        "username": user.username or "",
        "name": profile.get("name", user.first_name),
        "group": profile.get("group", ""),
        "bu": profile.get("bu", ""),
        "team": profile.get("team", ""),
        "gu": profile.get("gu", ""),
        "dept": profile.get("dept", ""),
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

        try: await processing_msg.delete()
        except: pass

        team_label = format_team_label(profile)
        group = profile.get("group", "")
        sub = group
        if team_label:
            sub += f"/{team_label}"

        result_msg = (
            "🎉 *수고하셨어요!*\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"👤 {profile.get('name', '')} ({sub})\n"
            f"📸 인증 완료\n"
            f"👟 {steps:,}걸음\n"
            f"📏 {km}km (1걸음=65cm 환산)\n"
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
        try: await processing_msg.delete()
        except: pass
        await update.message.reply_text(
            "❌ 저장 실패. 다시 시도해주세요!",
            reply_markup=restart_keyboard(),
        )

    keep_profile = context.user_data.get("profile")
    context.user_data.clear()
    if keep_profile:
        context.user_data["profile"] = keep_profile


# ─────────────── 버튼 ───────────────
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
            f"(예: 김강동)"
        )
        return

    # 청년회 부 선택
    if action.startswith("ybu:"):
        bu = action.split(":", 1)[1]
        context.user_data["reg_bu"] = bu

        if bu == "기능과":
            context.user_data["stage"] = "reg_youth_fdept"
            await query.message.reply_text(
                f"⚙️ 기능과 ✅\n\n"
                f"어느 과이신가요?",
                reply_markup=function_dept_keyboard(),
            )
        elif bu == "7부":
            # 🆕 7부는 구역 버튼 (1~11, 국제부, 부장가편)
            context.user_data["stage"] = "reg_youth_7gu"
            await query.message.reply_text(
                f"7부 ✅\n\n"
                f"어느 구역이신가요?",
                reply_markup=youth_7bu_gu_keyboard(),
            )
        else:
            context.user_data["stage"] = "reg_gu"
            await query.message.reply_text(
                f"{bu} ✅\n\n"
                f"몇 구역이신가요?\n"
                f"(숫자만 입력. 예: 5)"
            )
        return

    # 🆕 청년회 7부 구역 선택 → 바로 저장
    if action.startswith("y7gu:"):
        gu = action.split(":", 1)[1]
        # 숫자면 int로, 아니면 텍스트 그대로 (국제부/부장가편)
        if gu.isdigit():
            context.user_data["reg_gu"] = int(gu)
        else:
            context.user_data["reg_gu"] = gu
        await save_profile(query, context)
        return

    # 청년회 기능과 부서 선택 → 바로 저장
    if action.startswith("fdept:"):
        dept = action.split(":", 1)[1]
        context.user_data["reg_dept"] = dept
        context.user_data["reg_gu"] = ""
        await save_profile(query, context)
        return

    # 회장단/새신자부/3040부 버튼 (부녀회/장년회/자문회)
    if action.startswith("chair:"):
        choice = action.split(":", 1)[1]

        if choice == "회장단":
            # 팀/구역 없이 바로 저장
            context.user_data["reg_bu"] = "회장단"
            context.user_data["reg_team"] = ""
            context.user_data["reg_gu"] = ""
            await save_profile(query, context)
            return

        elif choice == "새신자부":
            # 새신자부 → 구역 입력 받기
            context.user_data["reg_bu"] = "새신자부"
            context.user_data["reg_team"] = ""
            context.user_data["stage"] = "reg_gu"
            await query.message.reply_text(
                f"🌱 새신자부 ✅\n\n"
                f"몇 구역이신가요?\n"
                f"(숫자만 입력. 예: 5)"
            )
            return

        elif choice == "3040":
            # 3040부 → 구역 입력 (팀 없음)
            context.user_data["reg_bu"] = "3040"
            context.user_data["reg_team"] = ""
            context.user_data["stage"] = "reg_gu"
            await query.message.reply_text(
                f"✨ 3040부 ✅\n\n"
                f"몇 구역이신가요?\n"
                f"(숫자만 입력. 예: 5)"
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
            "👟 다음 기록을 넣어볼게요!\n인증사진을 올려주세요 📸"
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
        sub = group
        if team_label:
            sub += f" / {team_label}"

        msg = (
            f"📊 *{name}님의 기록*\n"
            f"({sub})\n\n"
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
    class FakeQuery: message = update.message
    await send_ranking(FakeQuery(), "weekly", "🏆 이번주 TOP 20")


async def cmd_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class FakeQuery: message = update.message
    await send_ranking(FakeQuery(), "all", "💎 전체 누적 TOP 20")


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class FakeQuery:
        message = update.message
        from_user = update.message.from_user
    await send_my_record(FakeQuery(), update.message.from_user)


# ─────────────── 더미 서버 ───────────────
class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>해피 워크 챌린지 봇</title></head>
<body style='font-family:sans-serif;text-align:center;padding:50px;'>
<h1>🚶 해피 워크 챌린지</h1>
<p>봇이 정상 작동 중입니다 ✅</p>
</body></html>"""
        self.wfile.write(html.encode("utf-8"))
    def log_message(self, format, *args):
        return


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        with ReusableTCPServer(("0.0.0.0", port), HealthHandler) as httpd:
            print(f"더미 웹서버 실행 중 (포트 {port})")
            httpd.serve_forever()
    except Exception as e:
        logging.exception(f"더미 서버 에러: {e}")


# ─────────────── 좀비 봇 정리 ───────────────
def cleanup_telegram():
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true"
        res = requests.get(url, timeout=10)
        logging.info(f"좀비 폴링 정리: {res.json()}")
    except Exception as e:
        logging.warning(f"좀비 정리 실패 (무시하고 계속): {e}")


# ─────────────── 메인 ───────────────
def main():
    cleanup_telegram()
    threading.Thread(target=start_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler("total", cmd_total))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("봇 실행 중...")

    while True:
        try:
            app.run_polling(drop_pending_updates=True, close_loop=False)
            break
        except Exception as e:
            logging.exception(f"봇 폴링 에러: {e}")
            err_str = str(e).lower()
            if "conflict" in err_str:
                logging.warning("⚠️ Conflict 감지, 좀비 정리 후 재시작...")
                import time
                time.sleep(5)
                cleanup_telegram()
                time.sleep(3)
                continue
            else:
                raise


if __name__ == "__main__":
    main()
