import json
import os
import csv
import re
import sqlite3
import tempfile
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from html import escape

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Amir_seyedi_1387").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Amir_seyedi_1387").strip()
REMINDER_HOUR = int(os.getenv("REMINDER_HOUR", "22"))
REMINDER_MINUTE = int(os.getenv("REMINDER_MINUTE", "0"))
DEFAULT_CHALLENGE_DAYS = int(os.getenv("CHALLENGE_DAYS", "38"))
TZ = ZoneInfo("Asia/Tehran")
DATA_DIR = os.getenv("DATA_DIR", ".").strip() or "."
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "ariamir_tracker.db")).strip()
BACKUP_DIR = os.getenv("BACKUP_DIR", os.path.join(DATA_DIR, "backups")).strip()
os.makedirs(BACKUP_DIR, exist_ok=True)

# Default challenge pillars (used for new users / reset)
DEFAULT_TASKS = [
    {"key": "nofap", "title": "کنترل عادت", "emoji": "🧠"},
    {"key": "study", "title": "درس", "emoji": "📚"},
    {"key": "med", "title": "مدیتیشن", "emoji": "🧘"},
    {"key": "sport", "title": "ورزش", "emoji": "🏋️"},
    {"key": "phone", "title": "مدیریت گوشی", "emoji": "📵"},
]

# Suggested presets for onboarding (user can mix/edit later)
SUGGESTED_TASK_PRESETS = [
    {"key": "nofap", "title": "کنترل عادت", "emoji": "🧠"},
    {"key": "study", "title": "درس / مطالعه", "emoji": "📚"},
    {"key": "med", "title": "مدیتیشن", "emoji": "🧘"},
    {"key": "sport", "title": "ورزش", "emoji": "🏋️"},
    {"key": "phone", "title": "مدیریت گوشی", "emoji": "📵"},
    {"key": "sleep", "title": "خواب منظم", "emoji": "💤"},
    {"key": "water", "title": "آب کافی", "emoji": "💧"},
    {"key": "english", "title": "زبان انگلیسی", "emoji": "🗣️"},
    {"key": "code", "title": "کدنویسی", "emoji": "💻"},
    {"key": "walk", "title": "پیاده‌روی", "emoji": "🚶"},
]

DAY_PRESETS = [21, 30, 38, 60, 90]
LEGACY_TASK_KEYS = ("nofap", "study", "med", "sport", "phone")
DEFAULT_EMOJIS = ["✅", "📌", "🎯", "💪", "🌟", "🔥", "📘", "🧘", "🏃", "💤", "🥗", "✍️", "🎧", "🧼", "📵"]

MOTIVATIONS = [
    "تو لازم نیست کامل باشی؛ فقط باید ادامه بدی.",
    "هر شب یک گزارش یعنی یک قدم واقعی به سمت نسخه بهتر خودت.",
    "بردهای کوچک، آدم بزرگ می‌سازن. امشب رو ثبت کن.",
    "اگر امروز سخت بود، همین که صادقانه گزارش بدی یعنی هنوز توی بازی هستی.",
    "انضباط یعنی حتی وقتی حوصله نداری، با خودت روراست بمونی.",
]


# Reply-keyboard labels (custom keyboard)
# Open/close is done by Telegram's native grid button next to the input box.
BTN_START = "🚀 استارت"
BTN_REPORT = "📝 ثبت گزارش امروز"
BTN_PANEL = "📊 داشبورد من"
BTN_HISTORY = "📅 تاریخچه"
BTN_ACHIEVE = "🏆 رکوردها"
BTN_SETTINGS = "⚙️ تنظیمات"
BTN_HELP = "ℹ️ راهنما"
BTN_HOME = "🏠 صفحه اول"

pending_reports: dict[int, dict] = {}
admin_login_state: dict[int, str] = {}
user_text_state: dict[int, dict] = {}
# user_id -> date string; only for that day the user may edit an already-saved report
edit_unlock: dict[int, str] = {}
# Temporary onboarding wizard state
onboarding_state: dict[int, dict] = {}


def now_tehran() -> datetime:
    return datetime.now(TZ)


def today_str() -> str:
    return now_tehran().date().isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def dumps_tasks(tasks: list[dict]) -> str:
    cleaned = []
    for t in tasks:
        key = str(t.get("key", "")).strip()
        title = str(t.get("title", "")).strip()[:40]
        emoji = str(t.get("emoji", "✅")).strip()[:4] or "✅"
        if key and title:
            cleaned.append({"key": key, "title": title, "emoji": emoji})
    return json.dumps(cleaned, ensure_ascii=False)


def loads_tasks(raw) -> list[dict]:
    if not raw:
        return [dict(t) for t in DEFAULT_TASKS]
    if isinstance(raw, list):
        data = raw
    else:
        try:
            data = json.loads(raw)
        except Exception:
            return [dict(t) for t in DEFAULT_TASKS]
    out = []
    for t in data:
        if not isinstance(t, dict):
            continue
        key = str(t.get("key", "")).strip()
        title = str(t.get("title", "")).strip()[:40]
        emoji = str(t.get("emoji", "✅")).strip()[:4] or "✅"
        if key and title:
            out.append({"key": key, "title": title, "emoji": emoji})
    return out or [dict(t) for t in DEFAULT_TASKS]


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                start_date TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                report_date TEXT NOT NULL,
                challenge_day INTEGER NOT NULL,
                nofap INTEGER NOT NULL DEFAULT 0,
                study INTEGER NOT NULL DEFAULT 0,
                med INTEGER NOT NULL DEFAULT 0,
                sport INTEGER NOT NULL DEFAULT 0,
                phone INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, report_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                logged_in_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        ensure_column(conn, "users", "reminder_hour", f"INTEGER DEFAULT {REMINDER_HOUR}")
        ensure_column(conn, "users", "reminder_minute", f"INTEGER DEFAULT {REMINDER_MINUTE}")
        ensure_column(conn, "users", "paused", "INTEGER DEFAULT 0")
        ensure_column(conn, "users", "challenge_days", f"INTEGER DEFAULT {DEFAULT_CHALLENGE_DAYS}")
        ensure_column(conn, "users", "tasks_json", "TEXT")
        ensure_column(conn, "users", "onboarding_done", "INTEGER DEFAULT 0")
        ensure_column(conn, "reports", "mood", "TEXT DEFAULT ''")
        ensure_column(conn, "reports", "note", "TEXT DEFAULT ''")
        ensure_column(conn, "reports", "tasks_done_json", "TEXT")

        # Seed defaults for existing users
        rows = conn.execute(
            "SELECT user_id, challenge_days, tasks_json, onboarding_done FROM users"
        ).fetchall()
        for r in rows:
            updates = []
            params = []
            if r["challenge_days"] is None or int(r["challenge_days"] or 0) <= 0:
                updates.append("challenge_days=?")
                params.append(DEFAULT_CHALLENGE_DAYS)
            if not r["tasks_json"]:
                updates.append("tasks_json=?")
                params.append(dumps_tasks(DEFAULT_TASKS))
            # Existing users who already used the bot skip onboarding
            if r["onboarding_done"] is None:
                has_report = conn.execute(
                    "SELECT 1 FROM reports WHERE user_id=? LIMIT 1", (r["user_id"],)
                ).fetchone()
                updates.append("onboarding_done=?")
                params.append(1 if has_report else 0)
            if updates:
                params.append(r["user_id"])
                conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id=?", params)
        # Rename legacy default title if still present
        for r in conn.execute("SELECT user_id, tasks_json FROM users").fetchall():
            tasks = loads_tasks(r["tasks_json"])
            changed = False
            for task in tasks:
                if task.get("key") == "nofap" and task.get("title") in {"ترک جق", "جق"}:
                    task["title"] = "کنترل عادت"
                    task["emoji"] = task.get("emoji") or "🧠"
                    changed = True
            if changed:
                conn.execute(
                    "UPDATE users SET tasks_json=? WHERE user_id=?",
                    (dumps_tasks(tasks), r["user_id"]),
                )
        conn.commit()


def log_event(event_type: str, user_id: int | None = None, payload: str = "") -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO events(user_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (user_id, event_type, payload[:1000], now_tehran().isoformat()),
        )
        conn.commit()


def register_user(update: Update) -> None:
    u = update.effective_user
    if not u:
        return
    new_user = False
    with db() as conn:
        row = conn.execute("SELECT user_id FROM users WHERE user_id=?", (u.id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET username=?, first_name=?, last_name=?, is_active=1 WHERE user_id=?",
                (u.username, u.first_name, u.last_name, u.id),
            )
        else:
            conn.execute(
                """
                INSERT INTO users(
                    user_id, username, first_name, last_name, start_date, created_at,
                    reminder_hour, reminder_minute, challenge_days, tasks_json, onboarding_done
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    u.id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    today_str(),
                    now_tehran().isoformat(),
                    REMINDER_HOUR,
                    REMINDER_MINUTE,
                    DEFAULT_CHALLENGE_DAYS,
                    dumps_tasks(DEFAULT_TASKS),
                ),
            )
            new_user = True
        conn.commit()
    if new_user:
        log_event("new_user", u.id, u.username or "")


def get_user(user_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def get_challenge_days(user_id: int) -> int:
    user = get_user(user_id)
    if not user:
        return DEFAULT_CHALLENGE_DAYS
    try:
        days = int(user["challenge_days"] or DEFAULT_CHALLENGE_DAYS)
    except Exception:
        days = DEFAULT_CHALLENGE_DAYS
    return max(1, min(days, 3650))


def get_user_tasks(user_id: int) -> list[dict]:
    user = get_user(user_id)
    if not user:
        return [dict(t) for t in DEFAULT_TASKS]
    return loads_tasks(user["tasks_json"])


def set_user_tasks(user_id: int, tasks: list[dict]) -> None:
    with db() as conn:
        conn.execute("UPDATE users SET tasks_json=? WHERE user_id=?", (dumps_tasks(tasks), user_id))
        conn.commit()


def set_challenge_days(user_id: int, days: int) -> None:
    days = max(1, min(int(days), 3650))
    with db() as conn:
        conn.execute("UPDATE users SET challenge_days=? WHERE user_id=?", (days, user_id))
        conn.commit()


def tasks_map(user_id: int) -> dict[str, dict]:
    return {t["key"]: t for t in get_user_tasks(user_id)}


def challenge_day(user_id: int) -> int:
    user = get_user(user_id)
    if not user:
        return 1
    start = date.fromisoformat(user["start_date"])
    days = get_challenge_days(user_id)
    day = (now_tehran().date() - start).days + 1
    return max(1, min(day, days))


def is_challenge_finished(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    start = date.fromisoformat(user["start_date"])
    return (now_tehran().date() - start).days + 1 > get_challenge_days(user_id)


def progress_bar(done: int, total: int, length: int = 12) -> str:
    if total <= 0:
        return "▱" * length
    filled = max(0, min(length, round((done / total) * length)))
    return "▰" * filled + "▱" * (length - filled)


async def safe_edit(query, text: str, **kwargs):
    try:
        return await query.edit_message_text(text, **kwargs)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return None
        raise


def empty_pending(user_id: int) -> dict:
    tasks = {t["key"]: False for t in get_user_tasks(user_id)}
    return {"tasks": tasks, "mood": "", "note": ""}


def get_today_report(user_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM reports WHERE user_id=? AND report_date=?",
            (user_id, today_str()),
        ).fetchone()


def is_edit_unlocked(user_id: int) -> bool:
    return edit_unlock.get(user_id) == today_str()


def unlock_edit_today(user_id: int) -> None:
    edit_unlock[user_id] = today_str()


def lock_edit_today(user_id: int) -> None:
    if edit_unlock.get(user_id) == today_str():
        edit_unlock.pop(user_id, None)


def pending_from_report(user_id: int, row) -> dict:
    """Prefill the report form from an already-saved row."""
    tasks = get_user_tasks(user_id)
    done_map = report_done_map(row, user_id)
    return {
        "tasks": {t["key"]: bool(done_map.get(t["key"])) for t in tasks},
        "mood": (row["mood"] or "") if row else "",
        "note": (row["note"] or "") if row else "",
    }


def saved_report_summary(user_id: int, row) -> str:
    tasks = get_user_tasks(user_id)
    done_map = report_done_map(row, user_id)
    score, total = score_of_report(row, user_id)
    lines = []
    for t in tasks:
        mark = "✅" if done_map.get(t["key"]) else "⬜"
        lines.append(f"{mark} {t['emoji']} {escape(t['title'])}")
    mood = escape(row["mood"]) if row["mood"] else "ثبت نشده"
    note = escape((row["note"] or "")[:200]) if row["note"] else "—"
    return (
        f"امتیاز: <b>{score}/{total}</b>\n"
        f"حال: <b>{mood}</b>\n"
        f"یادداشت: <b>{note}</b>\n\n"
        f"<b>تسک‌ها:</b>\n" + ("\n".join(lines) if lines else "—")
    )


def edit_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ بله، می‌خوام تغییر بدم", callback_data="edit_today_yes")],
            [InlineKeyboardButton("🔙 نه، برگشت", callback_data="edit_today_no")],
        ]
    )


def report_done_map(row, user_id: int | None = None) -> dict[str, int]:
    """Read task completion from flexible JSON, with legacy column fallback."""
    raw = row["tasks_done_json"] if "tasks_done_json" in row.keys() else None
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): 1 if int(v) else 0 for k, v in data.items()}
        except Exception:
            pass
    # Legacy fixed columns
    out = {}
    for k in LEGACY_TASK_KEYS:
        try:
            out[k] = 1 if int(row[k]) else 0
        except Exception:
            out[k] = 0
    return out


def score_of_report(row, user_id: int) -> tuple[int, int]:
    tasks = get_user_tasks(user_id)
    done_map = report_done_map(row, user_id)
    keys = [t["key"] for t in tasks]
    if not keys:
        keys = list(done_map.keys())
    score = sum(1 for k in keys if done_map.get(k))
    return score, len(keys) if keys else 1



def is_onboarding_done(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    try:
        return int(user["onboarding_done"] or 0) == 1
    except Exception:
        return False


def set_onboarding_done(user_id: int, done: bool = True) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE users SET onboarding_done=? WHERE user_id=?",
            (1 if done else 0, user_id),
        )
        conn.commit()


def start_onboarding(user_id: int) -> None:
    onboarding_state[user_id] = {
        "step": "days",
        "days": DEFAULT_CHALLENGE_DAYS,
        "selected": {t["key"] for t in DEFAULT_TASKS},
    }


def onboarding_tasks_for(user_id: int | None = None) -> list[dict]:
    # presets + user custom tasks during onboarding
    seen = set()
    out = []
    for t in SUGGESTED_TASK_PRESETS:
        if t["key"] in seen:
            continue
        seen.add(t["key"])
        out.append(dict(t))
    if user_id is not None:
        for t in (onboarding_state.get(user_id) or {}).get("custom_tasks") or []:
            if t.get("key") and t["key"] not in seen:
                seen.add(t["key"])
                out.append(dict(t))
    return out


def onboarding_tasks() -> list[dict]:
    return onboarding_tasks_for(None)


def onboarding_days_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for d in DAY_PRESETS:
        row.append(InlineKeyboardButton(f"{d} روز", callback_data=f"ob_days:{d}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✍️ عدد دلخواه", callback_data="ob_days_custom")])
    return InlineKeyboardMarkup(rows)


def onboarding_tasks_keyboard(user_id: int) -> InlineKeyboardMarkup:
    st = onboarding_state.get(user_id) or {"selected": set()}
    selected = set(st.get("selected") or [])
    rows = []
    for t in onboarding_tasks_for(user_id):
        mark = "✅" if t["key"] in selected else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {t['emoji']} {t['title']}",
                    callback_data=f"ob_toggle:{t['key']}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("✍️ تسک سفارشی", callback_data="ob_custom_task"),
            InlineKeyboardButton("♻️ پیش‌فرض", callback_data="ob_reset_tasks"),
        ]
    )
    rows.append([InlineKeyboardButton("✅ تأیید و شروع", callback_data="ob_finish")])
    rows.append([InlineKeyboardButton("⬅️ تغییر تعداد روز", callback_data="ob_back_days")])
    return InlineKeyboardMarkup(rows)


def onboarding_days_text(user_id: int) -> str:
    name = "دوست من"
    user = get_user(user_id)
    if user and user["first_name"]:
        name = escape(user["first_name"])
    return (
        f"<b>سلام {name} 🌱</b>\n"
        "به <b>ARIAMIR TRAKER</b> خوش اومدی.\n"
        "━━━━━━━━━━━━━━\n"
        "این ربات یک <b>ردیاب چالش رشد شخصی</b> است.\n"
        "اول چالش را طراحی می‌کنی، بعد هر روز گزارش می‌دهی.\n\n"
        "• مدت چالش قابل‌تنظیم\n"
        "• تسک‌های پیشنهادی و سفارشی\n"
        "• داشبورد، استریک و یادآوری\n\n"
        "<b>قدم ۱ از ۲:</b> چالشت چند روزه باشه؟"
    )


def onboarding_tasks_text(user_id: int) -> str:
    st = onboarding_state.get(user_id) or {}
    days = int(st.get("days") or DEFAULT_CHALLENGE_DAYS)
    selected = set(st.get("selected") or [])
    titles = []
    for t in onboarding_tasks_for(user_id):
        if t["key"] in selected:
            titles.append(f"{t['emoji']} {escape(t['title'])}")
    preview = "، ".join(titles) if titles else "هنوز چیزی انتخاب نشده"
    return (
        f"<b>قدم ۲ از ۲: تسک‌های روزانه</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"طول چالش: <b>{days}</b> روز\n"
        f"انتخاب‌شده: <b>{len(selected)}</b>\n"
        f"{preview}\n\n"
        "از لیست پیشنهادی تیک بزن.\n"
        "می‌تونی بعداً از تنظیمات هم عوض کنی.\n"
        "حداقل ۱ تسک لازم است."
    )


async def show_onboarding(chat_id: int, context: ContextTypes.DEFAULT_TYPE, edit_query=None):
    if chat_id not in onboarding_state:
        start_onboarding(chat_id)
    step = onboarding_state[chat_id].get("step", "days")
    if step == "tasks":
        text = onboarding_tasks_text(chat_id)
        kb = onboarding_tasks_keyboard(chat_id)
    else:
        text = onboarding_days_text(chat_id)
        kb = onboarding_days_keyboard()
    if edit_query:
        await safe_edit(edit_query, text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def finish_onboarding(user_id: int, query=None, context: ContextTypes.DEFAULT_TYPE | None = None):
    st = onboarding_state.get(user_id) or {}
    days = max(1, min(int(st.get("days") or DEFAULT_CHALLENGE_DAYS), 3650))
    selected = set(st.get("selected") or [])
    tasks = [dict(t) for t in onboarding_tasks_for(user_id) if t["key"] in selected]
    if not tasks:
        tasks = [dict(t) for t in DEFAULT_TASKS]
    set_challenge_days(user_id, days)
    set_user_tasks(user_id, tasks)
    set_onboarding_done(user_id, True)
    onboarding_state.pop(user_id, None)
    pending_reports.pop(user_id, None)
    log_event("onboarding_done", user_id, f"days={days};tasks={len(tasks)}")
    pillars = "\n".join(f"{t['emoji']} {escape(t['title'])}" for t in tasks)
    text = (
        "<b>✅ چالش آماده شد!</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"📅 مدت: <b>{days}</b> روز\n"
        f"✅ تسک‌ها:\n{pillars}\n\n"
        "از همین الان می‌تونی گزارش امروزت رو ثبت کنی.\n"
        "اگر خواستی بعداً از ⚙️ تنظیمات عوضش کن."
    )
    if query is not None:
        await safe_edit(query, text, parse_mode=ParseMode.HTML)
        if context is not None:
            await context.bot.send_message(
                user_id,
                "منوی امکانات در کیبورد پایین فعال شد 👇",
                reply_markup=features_keyboard(),
            )
    elif context is not None:
        await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML, reply_markup=features_keyboard())




def landing_keyboard() -> ReplyKeyboardMarkup:
    """Custom keyboard after /start: only Start.
    Telegram client shows a native grid icon to show/hide this keyboard.
    """
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_START)]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="استارت را بزن…",
    )


def features_keyboard() -> ReplyKeyboardMarkup:
    """Expanded custom keyboard with app features.
    User opens/closes it with Telegram's built-in keyboard toggle (grid icon).
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_REPORT)],
            [KeyboardButton(BTN_PANEL), KeyboardButton(BTN_HISTORY)],
            [KeyboardButton(BTN_ACHIEVE), KeyboardButton(BTN_SETTINGS)],
            [KeyboardButton(BTN_HELP), KeyboardButton(BTN_HOME)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="یک گزینه انتخاب کن…",
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return landing_keyboard()


def app_menu_keyboard() -> ReplyKeyboardMarkup:
    return features_keyboard()


def landing_text() -> str:
    return (
        "━━━━━━━━━━━━━━\n"
        "<b>🤖 ARIAMIR TRAKER</b>\n"
        "━━━━━━━━━━━━━━\n\n"
        "به ربات خوش اومدی 🌱\n\n"
        "اینجا می‌تونی مسیر رشد شخصیت رو بسازی و پیگیری کنی:\n"
        "• انتخاب مدت چالش\n"
        "• تعریف تسک‌های روزانه\n"
        "• ثبت گزارش و دیدن پیشرفت\n"
        "• استریک، تاریخچه و یادآوری\n\n"
        "از کیبورد پایین روی <b>استارت</b> بزن 👇\n"
        "برای باز/بسته کردن کیبورد، همان دکمه <b>چهارخانه</b> کنار کادر پیام را بزن."
    )


def started_text(uid: int) -> str:
    days = get_challenge_days(uid)
    tasks = get_user_tasks(uid)
    pillars = "\n".join(f"{x['emoji']} {escape(x['title'])}" for x in tasks) or "—"
    return (
        "<b>✅ آماده استفاده</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"📅 چالش فعلی: <b>{days}</b> روز\n"
        f"✅ تعداد تسک‌ها: <b>{len(tasks)}</b>\n\n"
        "<b>تسک‌های فعال:</b>\n"
        f"{pillars}\n\n"
        "از <b>کیبورد پایین</b> یکی را انتخاب کن.\n"
        "برای مخفی/ظاهر کردن کیبورد → دکمه چهارخانه کنار کادر نوشتن."
    )


async def open_features_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit_query=None):
    """Show expanded feature custom keyboard."""
    uid = update.effective_user.id if update and update.effective_user else None
    if edit_query is not None:
        uid = edit_query.from_user.id
    if uid is None:
        return
    if not is_onboarding_done(uid):
        start_onboarding(uid)
        await show_onboarding(uid, context, edit_query=edit_query)
        return
    text = started_text(uid)
    kb = features_keyboard()
    if edit_query is not None:
        try:
            await edit_query.edit_message_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        await context.bot.send_message(uid, "منوی امکانات آماده است 👇", reply_markup=kb)
    else:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def go_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to landing with only Start on custom keyboard."""
    await update.effective_message.reply_text(
        landing_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=landing_keyboard(),
    )


def report_keyboard(user_id: int) -> InlineKeyboardMarkup:
    state = pending_reports.setdefault(user_id, empty_pending(user_id))
    # keep pending keys in sync with current tasks
    current = get_user_tasks(user_id)
    state["tasks"] = {t["key"]: bool(state.get("tasks", {}).get(t["key"], False)) for t in current}
    rows = []
    for t in current:
        checked = state["tasks"].get(t["key"], False)
        mark = "✅" if checked else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {t['emoji']} {t['title']}",
                    callback_data=f"toggle:{t['key']}",
                )
            ]
        )
    mood = state.get("mood") or "ثبت نشده"
    rows.append([InlineKeyboardButton(f"🙂 حال امروز: {mood}", callback_data="choose_mood")])
    rows.append(
        [
            InlineKeyboardButton("📝 افزودن یادداشت", callback_data="add_note"),
            InlineKeyboardButton("🔄 ریست", callback_data="reset_report"),
        ]
    )
    rows.append([InlineKeyboardButton("✅ تایید و ثبت نهایی", callback_data="confirm_report")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def mood_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("😄 عالی", callback_data="mood:عالی"),
                InlineKeyboardButton("🙂 خوب", callback_data="mood:خوب"),
            ],
            [
                InlineKeyboardButton("😐 معمولی", callback_data="mood:معمولی"),
                InlineKeyboardButton("😔 سخت", callback_data="mood:سخت"),
            ],
            [InlineKeyboardButton("⬅️ برگشت به گزارش", callback_data="open_report")],
        ]
    )


def settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    user = get_user(user_id)
    paused = bool(user["paused"]) if user else False
    days = get_challenge_days(user_id)
    task_count = len(get_user_tasks(user_id))
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"📅 تعداد روز چالش: {days}", callback_data="set_days")],
            [InlineKeyboardButton(f"✅ مدیریت تسک‌ها ({task_count})", callback_data="manage_tasks")],
            [InlineKeyboardButton("⏰ تغییر ساعت یادآوری", callback_data="set_time")],
            [
                InlineKeyboardButton(
                    "▶️ فعال‌سازی یادآوری" if paused else "⏸ توقف یادآوری",
                    callback_data="toggle_pause",
                )
            ],
            [InlineKeyboardButton("🔁 شروع دوباره چالش از امروز", callback_data="reset_challenge_confirm")],
            [InlineKeyboardButton("🧩 راه‌اندازی دوباره (روز + تسک)", callback_data="reonboard")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
        ]
    )


def tasks_keyboard(user_id: int) -> InlineKeyboardMarkup:
    tasks = get_user_tasks(user_id)
    rows = []
    for t in tasks:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{t['emoji']} {t['title']}",
                    callback_data=f"task_info:{t['key']}",
                ),
                InlineKeyboardButton("🗑", callback_data=f"task_del:{t['key']}"),
            ]
        )
    rows.append([InlineKeyboardButton("➕ افزودن تسک جدید", callback_data="task_add")])
    rows.append([InlineKeyboardButton("♻️ بازگردانی تسک‌های پیش‌فرض", callback_data="task_reset_confirm")])
    rows.append([InlineKeyboardButton("⬅️ برگشت به تنظیمات", callback_data="settings")])
    return InlineKeyboardMarkup(rows)


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 کاربران", callback_data="admin:users"),
                InlineKeyboardButton("📈 گزارش کلی", callback_data="admin:summary"),
            ],
            [
                InlineKeyboardButton("🏅 رتبه‌بندی", callback_data="admin:ranking"),
                InlineKeyboardButton("🧾 لاگ‌ها", callback_data="admin:events"),
            ],
            [
                InlineKeyboardButton("📣 پیام همگانی", callback_data="admin:broadcast"),
                InlineKeyboardButton("📤 CSV", callback_data="admin:csv"),
            ],
            [InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="admin:backup")],
            [InlineKeyboardButton("🚪 خروج", callback_data="admin:logout")],
        ]
    )


def is_admin(user_id: int) -> bool:
    with db() as conn:
        return conn.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,)).fetchone() is not None


def save_report(user_id: int, state: dict) -> None:
    d = today_str()
    day = challenge_day(user_id)
    tasks = get_user_tasks(user_id)
    vals = {t["key"]: 1 if state.get("tasks", {}).get(t["key"]) else 0 for t in tasks}
    mood = state.get("mood", "")[:30]
    note = state.get("note", "")[:600]
    ts = now_tehran().isoformat()
    # Keep legacy columns populated when keys match (backward compatible)
    legacy = {k: int(vals.get(k, 0)) for k in LEGACY_TASK_KEYS}
    with db() as conn:
        conn.execute(
            """
            INSERT INTO reports(
                user_id, report_date, challenge_day,
                nofap, study, med, sport, phone,
                mood, note, tasks_done_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, report_date) DO UPDATE SET
                challenge_day=excluded.challenge_day,
                nofap=excluded.nofap,
                study=excluded.study,
                med=excluded.med,
                sport=excluded.sport,
                phone=excluded.phone,
                mood=excluded.mood,
                note=excluded.note,
                tasks_done_json=excluded.tasks_done_json,
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                d,
                day,
                legacy["nofap"],
                legacy["study"],
                legacy["med"],
                legacy["sport"],
                legacy["phone"],
                mood,
                note,
                json.dumps(vals, ensure_ascii=False),
                ts,
                ts,
            ),
        )
        conn.commit()
    total = len(tasks) or 1
    log_event("report_saved", user_id, f"{sum(vals.values())}/{total} mood={mood}")


def get_reports(user_id: int, limit: int | None = None):
    q = "SELECT * FROM reports WHERE user_id=? ORDER BY report_date DESC"
    params: list = [user_id]
    if limit:
        q += " LIMIT ?"
        params.append(limit)
    with db() as conn:
        return conn.execute(q, params).fetchall()


def user_stats(user_id: int) -> dict:
    rows = list(reversed(get_reports(user_id)))
    tasks = get_user_tasks(user_id)
    keys = [t["key"] for t in tasks]
    total_reports = len(rows)
    done_tasks = 0
    full_days = 0
    best_day_score = 0
    task_totals = {k: 0 for k in keys}

    for r in rows:
        done_map = report_done_map(r, user_id)
        score = sum(1 for k in keys if done_map.get(k))
        done_tasks += score
        best_day_score = max(best_day_score, score)
        if keys and score == len(keys):
            full_days += 1
        for k in keys:
            task_totals[k] += 1 if done_map.get(k) else 0

    streak = 0
    if rows:
        by_date = {date.fromisoformat(r["report_date"]): r for r in rows}
        cur = now_tehran().date()
        cur_map = report_done_map(by_date[cur], user_id) if cur in by_date else {}
        if cur not in by_date or (keys and sum(1 for k in keys if cur_map.get(k)) != len(keys)):
            cur -= timedelta(days=1)
        while cur in by_date:
            dm = report_done_map(by_date[cur], user_id)
            if not keys or sum(1 for k in keys if dm.get(k)) != len(keys):
                break
            streak += 1
            cur -= timedelta(days=1)

    return {
        "total_reports": total_reports,
        "done_tasks": done_tasks,
        "full_days": full_days,
        "streak": streak,
        "best_day_score": best_day_score,
        "task_totals": task_totals,
        "task_count": len(keys),
    }


def rank_title(percent: int) -> str:
    if percent >= 90:
        return "👑 افسانه‌ای"
    if percent >= 70:
        return "🔥 جنگجو"
    if percent >= 45:
        return "💪 رو به رشد"
    if percent >= 20:
        return "🌱 شروع خوب"
    return "🧩 تازه‌کار"


def user_panel_text(user_id: int) -> str:
    user = get_user(user_id)
    stats = user_stats(user_id)
    days = get_challenge_days(user_id)
    tasks = get_user_tasks(user_id)
    total_tasks = days * max(1, len(tasks))
    percent = round((stats["done_tasks"] / total_tasks) * 100) if total_tasks else 0
    bar = progress_bar(stats["done_tasks"], total_tasks)
    day = challenge_day(user_id)
    name = escape((user["first_name"] if user else "دوست من") or "دوست من")
    status = (
        "🏁 چالش تموم شده؛ ولی ثبت گزارش هنوز فعاله."
        if is_challenge_finished(user_id)
        else f"🔥 روز <b>{day}</b> از <b>{days}</b>"
    )
    reminder = f"{int(user['reminder_hour']):02d}:{int(user['reminder_minute']):02d}" if user else "22:00"
    paused = "متوقف" if user and user["paused"] else "فعال"
    task_lines = []
    tmap = {t["key"]: t for t in tasks}
    for k, v in stats["task_totals"].items():
        t = tmap.get(k, {"emoji": "✅", "title": k})
        task_lines.append(f"{t['emoji']} {escape(t['title'])}: <b>{v}</b> بار")
    full_label = f"{stats['task_count']}/{stats['task_count']}" if stats["task_count"] else "کامل"
    return (
        f"<b>📊 داشبورد ARIAMIR TRAKER</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"سلام {name} 👋\n"
        f"{status}\n"
        f"رتبه فعلی: <b>{rank_title(percent)}</b>\n\n"
        f"{bar} <b>{percent}%</b>\n\n"
        f"✅ مجموع کارها: <b>{stats['done_tasks']}</b> / <b>{total_tasks}</b>\n"
        f"🗓 گزارش‌های ثبت‌شده: <b>{stats['total_reports']}</b> روز\n"
        f"🌟 روزهای کامل ({full_label}): <b>{stats['full_days']}</b> روز\n"
        f"🔥 استریک فعلی: <b>{stats['streak']}</b> روز\n"
        f"📅 طول چالش: <b>{days}</b> روز | تسک‌ها: <b>{len(tasks)}</b>\n"
        f"⏰ یادآوری: <b>{reminder}</b> | وضعیت: <b>{paused}</b>\n\n"
        f"<b>ریزعملکرد:</b>\n"
        + ("\n".join(task_lines) if task_lines else "هنوز تسکی تعریف نشده.")
    )


def history_text(user_id: int) -> str:
    rows = get_reports(user_id, 7)
    if not rows:
        return "<b>📅 تاریخچه</b>\n\nهنوز گزارشی ثبت نکردی. اولین گزارش رو امروز بزن 🌱"
    tasks = get_user_tasks(user_id)
    tmap = {t["key"]: t for t in tasks}
    parts = ["<b>📅 تاریخچه ۷ گزارش آخر</b>", "━━━━━━━━━━━━━━"]
    for r in rows:
        score, total = score_of_report(r, user_id)
        done_map = report_done_map(r, user_id)
        done = " ".join(tmap[k]["emoji"] for k in tmap if done_map.get(k)) or "—"
        mood = f" | حال: {escape(r['mood'])}" if r["mood"] else ""
        note = f"\n📝 {escape(r['note'][:120])}" if r["note"] else ""
        parts.append(
            f"<b>{r['report_date']}</b> | روز {r['challenge_day']} | <b>{score}/{total}</b>{mood}\n{done}{note}"
        )
    return "\n\n".join(parts)


def achievements_text(user_id: int) -> str:
    s = user_stats(user_id)
    badges = []
    if s["total_reports"] >= 1:
        badges.append("🌱 اولین گزارش")
    if s["full_days"] >= 1:
        badges.append("🌟 اولین روز کامل")
    if s["streak"] >= 3:
        badges.append("🔥 استریک ۳ روزه")
    if s["streak"] >= 7:
        badges.append("⚡ استریک ۷ روزه")
    if s["done_tasks"] >= 50:
        badges.append("💪 ۵۰ کار انجام‌شده")
    if s["done_tasks"] >= 100:
        badges.append("👑 ۱۰۰ کار انجام‌شده")
    if not badges:
        badges.append("🧩 هنوز نشانی نگرفتی؛ امروز شروع کن")
    return "<b>🏆 رکوردها و نشان‌ها</b>\n━━━━━━━━━━━━━━\n" + "\n".join(badges)


def settings_text(uid: int) -> str:
    user = get_user(uid)
    reminder = f"{int(user['reminder_hour']):02d}:{int(user['reminder_minute']):02d}" if user else "22:00"
    paused = "⏸ متوقف" if user and user["paused"] else "▶️ فعال"
    days = get_challenge_days(uid)
    tasks = get_user_tasks(uid)
    task_preview = "\n".join(f"• {t['emoji']} {escape(t['title'])}" for t in tasks) or "—"
    return (
        "<b>⚙️ تنظیمات ARIAMIR TRAKER</b>\n"
        "ردیاب چالش رشد شخصی\n"
        "━━━━━━━━━━━━━━\n"
        f"📅 تعداد روز چالش: <b>{days}</b>\n"
        f"✅ تعداد تسک‌ها: <b>{len(tasks)}</b>\n"
        f"⏰ ساعت یادآوری: <b>{reminder}</b>\n"
        f"وضعیت یادآوری: <b>{paused}</b>\n\n"
        f"<b>تسک‌های فعلی:</b>\n{task_preview}\n\n"
        "از دکمه‌های زیر می‌تونی روز چالش و تسک‌ها رو شخصی‌سازی کنی."
    )


def tasks_manage_text(uid: int) -> str:
    tasks = get_user_tasks(uid)
    lines = [f"{i}. {t['emoji']} <b>{escape(t['title'])}</b>" for i, t in enumerate(tasks, 1)]
    body = "\n".join(lines) if lines else "هنوز تسکی نداری."
    return (
        "<b>✅ مدیریت تسک‌های چالش</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"{body}\n\n"
        "➕ تسک جدید اضافه کن یا 🗑 برای حذف.\n"
        "حداکثر <b>12</b> تسک می‌تونی داشته باشی."
    )


def make_task_key(title: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]+", "_", title.strip().lower())
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        base = "task"
    base = base[:24]
    # Prefer ASCII-ish keys for callback_data safety
    if re.search(r"[\u0600-\u06FF]", base) or not base:
        base = f"task_{abs(hash(title)) % 10_000_000}"
    key = base
    n = 2
    while key in existing or key in {"home", "settings", "open_report"}:
        key = f"{base}_{n}"
        n += 1
    return key


def pick_emoji(title: str, index: int) -> str:
    title_l = title.lower()
    mapping = [
        (("عادت", "کنترل", "نفس", "discipline"), "🧠"),
        (("درس", "مطالعه", "کتاب", "study", "read"), "📚"),
        (("ورزش", "باشگاه", "دویدن", "sport", "gym"), "🏋️"),
        (("مدیتیشن", "آرامش", "meditation"), "🧘"),
        (("گوشی", "موبایل", "phone"), "📵"),
        (("خواب", "sleep"), "💤"),
        (("آب", "water"), "💧"),
        (("غذا", "رژیم", "diet"), "🥗"),
        (("نماز", "دعا", "قرآن"), "🕌"),
        (("انگلیسی", "زبان", "english"), "🗣️"),
        (("کد", "برنامه", "code"), "💻"),
    ]
    for keys, emoji in mapping:
        if any(k in title_l for k in keys):
            return emoji
    return DEFAULT_EMOJIS[index % len(DEFAULT_EMOJIS)]


async def send_home(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id,
        landing_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=landing_keyboard(),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    await update.effective_message.reply_text(
        landing_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=landing_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    text = (
        "<b>ℹ️ راهنمای ARIAMIR TRAKER</b>\n"
        "ردیاب چالش رشد شخصی\n\n"
        "/start — شروع / راه‌اندازی چالش\n"
        "/report — ثبت گزارش امروز\n"
        "/panel — داشبورد پیشرفت\n"
        "/history — تاریخچه گزارش‌ها\n"
        "/settings — تنظیمات روز، تسک و یادآوری\n"
        "/admin — پنل مدیریت\n\n"
        "<b>چطور کار می‌کند؟</b>\n"
        "1) مدت چالش را مشخص می‌کنی\n"
        "2) تسک‌های روزانه را انتخاب یا می‌سازی\n"
        "3) هر روز گزارش می‌دهی و پیشرفت می‌بینی\n\n"
        "گزارش فقط با <b>تایید و ثبت نهایی</b> ذخیره می‌شود.\n"
        "اگر امروز قبلاً گزارش داده باشی، برای ویرایش دوباره تأیید گرفته می‌شود."
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=features_keyboard())


async def show_edit_confirm(chat_id: int, context: ContextTypes.DEFAULT_TYPE, row, edit_query=None):
    days = get_challenge_days(chat_id)
    text = (
        f"<b>⚠️ گزارش امروز قبلاً ثبت شده</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"روز <b>{challenge_day(chat_id)}</b> از <b>{days}</b>\n\n"
        f"{saved_report_summary(chat_id, row)}\n\n"
        "نمی‌تونی مستقیم عوضش کنی.\n"
        "اگر واقعاً می‌خوای ویرایش کنی، تأیید کن 👇"
    )
    if edit_query:
        await safe_edit(edit_query, text, parse_mode=ParseMode.HTML, reply_markup=edit_confirm_keyboard())
    else:
        await context.bot.send_message(
            chat_id, text, parse_mode=ParseMode.HTML, reply_markup=edit_confirm_keyboard()
        )


async def open_report_message(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    edit_query=None,
    *,
    force_edit: bool = False,
    skip_existing_check: bool = False,
):
    """Open daily report form.

    If today's report already exists and edit is not unlocked, ask for confirmation first.
    """
    existing = None if skip_existing_check else get_today_report(chat_id)
    if existing is not None and not force_edit and not is_edit_unlocked(chat_id):
        await show_edit_confirm(chat_id, context, existing, edit_query=edit_query)
        return

    if force_edit and existing is not None:
        pending_reports[chat_id] = pending_from_report(chat_id, existing)
    elif chat_id not in pending_reports:
        # If unlocked and a saved report exists, prefill once
        if existing is not None and is_edit_unlocked(chat_id):
            pending_reports[chat_id] = pending_from_report(chat_id, existing)
        else:
            pending_reports[chat_id] = empty_pending(chat_id)

    tasks = get_user_tasks(chat_id)
    days = get_challenge_days(chat_id)
    motivation = MOTIVATIONS[challenge_day(chat_id) % len(MOTIVATIONS)]
    state = pending_reports[chat_id]
    state["tasks"] = {t["key"]: bool(state.get("tasks", {}).get(t["key"], False)) for t in tasks}
    selected = sum(1 for v in state["tasks"].values() if v)
    total = len(tasks) or 1
    note = "✅ یادداشت اضافه شده" if state.get("note") else "یادداشت نداری"
    editing_note = ""
    if existing is not None or is_edit_unlocked(chat_id):
        editing_note = "✏️ <b>حالت ویرایش گزارش امروز</b>\n"
    text = (
        f"<b>📝 گزارش روز {challenge_day(chat_id)} از {days}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{editing_note}"
        f"{motivation}\n\n"
        f"انتخاب‌شده: <b>{selected}/{total}</b>\n"
        f"حال امروز: <b>{escape(state.get('mood') or 'ثبت نشده')}</b>\n"
        f"یادداشت: <b>{note}</b>\n\n"
        "گزینه‌های انجام‌شده رو تیک بزن و آخرش تایید کن 👇"
    )
    if edit_query:
        await safe_edit(edit_query, text, parse_mode=ParseMode.HTML, reply_markup=report_keyboard(chat_id))
    else:
        await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=report_keyboard(chat_id))


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    uid = update.effective_user.id
    if not is_onboarding_done(uid):
        start_onboarding(uid)
        await show_onboarding(uid, context)
        return
    await open_report_message(uid, context)


async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    uid = update.effective_user.id
    await update.effective_message.reply_text(
        user_panel_text(uid), parse_mode=ParseMode.HTML, reply_markup=features_keyboard()
    )


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    uid = update.effective_user.id
    await update.effective_message.reply_text(
        history_text(uid), parse_mode=ParseMode.HTML, reply_markup=features_keyboard()
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    uid = update.effective_user.id
    await update.effective_message.reply_text(
        settings_text(uid), parse_mode=ParseMode.HTML, reply_markup=settings_keyboard(uid)
    )


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    uid = update.effective_user.id
    if is_admin(uid):
        await update.effective_message.reply_text(
            "<b>🔐 پنل مدیریت ARIAMIR TRAKER</b>\nیک گزینه را انتخاب کن:",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return
    admin_login_state[uid] = "username"
    await update.effective_message.reply_text("🔐 ورود ادمین — نام کاربری را بفرست:")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    uid = update.effective_user.id
    text = (update.effective_message.text or "").strip()

    # ===== Custom reply keyboard actions =====
    # Note: open/close of the keyboard UI is Telegram's native grid button.
    # We only switch keyboard *content* (Start-only vs features).
    if text in {BTN_START, "استارت", "Start", "start"}:
        await open_features_menu(update, context)
        return
    if text in {BTN_HOME, "منوی اصلی", "صفحه اول", "خانه"}:
        await go_home_screen(update, context)
        return
    if text == BTN_REPORT:
        if not is_onboarding_done(uid):
            start_onboarding(uid)
            await show_onboarding(uid, context)
            return
        await open_report_message(uid, context)
        return
    if text == BTN_PANEL:
        if not is_onboarding_done(uid):
            start_onboarding(uid)
            await show_onboarding(uid, context)
            return
        await update.effective_message.reply_text(
            user_panel_text(uid), parse_mode=ParseMode.HTML, reply_markup=features_keyboard()
        )
        return
    if text == BTN_HISTORY:
        if not is_onboarding_done(uid):
            start_onboarding(uid)
            await show_onboarding(uid, context)
            return
        await update.effective_message.reply_text(
            history_text(uid), parse_mode=ParseMode.HTML, reply_markup=features_keyboard()
        )
        return
    if text == BTN_ACHIEVE:
        if not is_onboarding_done(uid):
            start_onboarding(uid)
            await show_onboarding(uid, context)
            return
        await update.effective_message.reply_text(
            achievements_text(uid), parse_mode=ParseMode.HTML, reply_markup=features_keyboard()
        )
        return
    if text == BTN_SETTINGS:
        if not is_onboarding_done(uid):
            start_onboarding(uid)
            await show_onboarding(uid, context)
            return
        await update.effective_message.reply_text(
            settings_text(uid), parse_mode=ParseMode.HTML, reply_markup=settings_keyboard(uid)
        )
        return
    if text == BTN_HELP:
        await update.effective_message.reply_text(
            (
                "<b>ℹ️ راهنمای ARIAMIR TRAKER</b>\n"
                "ردیاب چالش رشد شخصی\n\n"
                "کیبورد پایین (دکمه چهارخانه کنار کادر پیام):\n"
                f"• {BTN_START} — شروع / باز شدن امکانات\n"
                f"• {BTN_REPORT} — گزارش روزانه\n"
                f"• {BTN_PANEL} — داشبورد\n"
                f"• {BTN_HISTORY} — تاریخچه\n"
                f"• {BTN_SETTINGS} — تنظیمات\n"
                f"• {BTN_HOME} — برگشت به صفحه اول (فقط استارت)\n\n"
                "باز و بسته کردن خودِ کیبورد با دکمه <b>چهارخانه</b> تلگرام است.\n"
                "در منوی دستورات ربات فقط /start وجود دارد."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=features_keyboard(),
        )
        return

    # Onboarding custom inputs
    if uid in onboarding_state and not is_onboarding_done(uid):
        st = onboarding_state[uid]
        mode = (user_text_state.get(uid) or {}).get("mode")
        if mode == "ob_days_custom":
            try:
                days = int(text.strip())
                if not (1 <= days <= 3650):
                    raise ValueError
                st["days"] = days
                st["step"] = "tasks"
                user_text_state.pop(uid, None)
                await update.effective_message.reply_text(
                    f"✅ مدت چالش: <b>{days}</b> روز",
                    parse_mode=ParseMode.HTML
                )
                await show_onboarding(uid, context)
            except Exception:
                await update.effective_message.reply_text(
                    "یک عدد معتبر بین 1 تا 3650 بفرست. مثال: <code>45</code>",
                    parse_mode=ParseMode.HTML
                )
            return
        if mode == "ob_custom_task":
            title = text.strip()[:40]
            if len(title) < 2:
                await update.effective_message.reply_text("عنوان خیلی کوتاهه. حداقل ۲ حرف.")
                return
            customs = st.setdefault("custom_tasks", [])
            existing_keys = {t["key"] for t in onboarding_tasks()} | {t["key"] for t in customs}
            # temporary add into custom list and selected
            key = make_task_key(title, existing_keys)
            emoji = pick_emoji(title, len(customs))
            item = {"key": key, "title": title, "emoji": emoji}
            customs.append(item)
            # also inject into SUGGESTED dynamically via custom_tasks only; keyboard reads both
            st.setdefault("selected", set()).add(key)
            # store for keyboard rendering
            user_text_state.pop(uid, None)
            await update.effective_message.reply_text(
                f"✅ تسک <b>{escape(emoji)} {escape(title)}</b> اضافه و انتخاب شد.",
                parse_mode=ParseMode.HTML
            )
            await show_onboarding(uid, context)
            return

    if uid in admin_login_state:
        step = admin_login_state[uid]
        if step == "username":
            if text == ADMIN_USERNAME:
                admin_login_state[uid] = "password"
                await update.effective_message.reply_text("✅ نام کاربری درست بود. رمز عبور را بفرست:")
            else:
                admin_login_state.pop(uid, None)
                await update.effective_message.reply_text("❌ نام کاربری اشتباه بود. دوباره /admin را بزن.")
            return
        if step == "password":
            if text == ADMIN_PASSWORD:
                with db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO admins(user_id, username, logged_in_at) VALUES (?, ?, ?)",
                        (uid, update.effective_user.username, now_tehran().isoformat()),
                    )
                    conn.commit()
                admin_login_state.pop(uid, None)
                await update.effective_message.reply_text(
                    "✅ ورود موفق بود. پنل مدیریت فعال شد.", reply_markup=admin_keyboard()
                )
            else:
                admin_login_state.pop(uid, None)
                await update.effective_message.reply_text("❌ رمز اشتباه بود. دوباره /admin را بزن.")
            return

    state = user_text_state.get(uid)
    if state:
        mode = state.get("mode")
        if mode == "note":
            if get_today_report(uid) is not None and not is_edit_unlocked(uid):
                user_text_state.pop(uid, None)
                await update.effective_message.reply_text(
                    "⚠️ گزارش امروز قبلاً ثبت شده. اول باید ویرایش را تأیید کنی."
                )
                await open_report_message(uid, context)
                return
            pending_reports.setdefault(uid, empty_pending(uid))["note"] = text[:600]
            user_text_state.pop(uid, None)
            await update.effective_message.reply_text("✅ یادداشتت به گزارش امروز اضافه شد.")
            await open_report_message(uid, context, skip_existing_check=True)
            return
        if mode == "set_time":
            try:
                hh, mm = map(int, text.replace("٫", ":").split(":"))
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    raise ValueError
                with db() as conn:
                    conn.execute(
                        "UPDATE users SET reminder_hour=?, reminder_minute=? WHERE user_id=?",
                        (hh, mm, uid),
                    )
                    conn.commit()
                user_text_state.pop(uid, None)
                await update.effective_message.reply_text(
                    f"✅ ساعت یادآوری روی {hh:02d}:{mm:02d} تنظیم شد.",
                    reply_markup=settings_keyboard(uid),
                )
            except Exception:
                await update.effective_message.reply_text("فرمت درست نیست. مثلا اینطوری بفرست: 22:00")
            return
        if mode == "set_days":
            try:
                days = int(text.strip())
                if not (1 <= days <= 3650):
                    raise ValueError
                set_challenge_days(uid, days)
                user_text_state.pop(uid, None)
                log_event("challenge_days_set", uid, str(days))
                await update.effective_message.reply_text(
                    f"✅ تعداد روز چالش روی <b>{days}</b> تنظیم شد.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=settings_keyboard(uid),
                )
            except Exception:
                await update.effective_message.reply_text(
                    "یک عدد معتبر بین 1 تا 3650 بفرست. مثال: <code>38</code> یا <code>21</code>",
                    parse_mode=ParseMode.HTML
                )
            return
        if mode == "task_add":
            title = text.strip()[:40]
            if len(title) < 2:
                await update.effective_message.reply_text("عنوان تسک خیلی کوتاهه. حداقل ۲ حرف بنویس.")
                return
            tasks = get_user_tasks(uid)
            if len(tasks) >= 12:
                user_text_state.pop(uid, None)
                await update.effective_message.reply_text(
                    "❌ حداکثر ۱۲ تسک می‌تونی داشته باشی. اول یکی رو حذف کن.",
                    reply_markup=tasks_keyboard(uid),
                )
                return
            if any(t["title"] == title for t in tasks):
                await update.effective_message.reply_text("این عنوان از قبل هست. یه عنوان دیگه بفرست.")
                return
            existing = {t["key"] for t in tasks}
            key = make_task_key(title, existing)
            emoji = pick_emoji(title, len(tasks))
            tasks.append({"key": key, "title": title, "emoji": emoji})
            set_user_tasks(uid, tasks)
            pending_reports.pop(uid, None)
            user_text_state.pop(uid, None)
            log_event("task_added", uid, title)
            await update.effective_message.reply_text(
                f"✅ تسک <b>{escape(emoji)} {escape(title)}</b> اضافه شد.",
                parse_mode=ParseMode.HTML,
                reply_markup=tasks_keyboard(uid),
            )
            return
        if mode == "broadcast" and is_admin(uid):
            user_text_state.pop(uid, None)
            sent, failed = await broadcast_message(context, text)
            await update.effective_message.reply_text(
                f"📣 پیام همگانی ارسال شد.\n✅ موفق: {sent}\n❌ ناموفق: {failed}",
                reply_markup=admin_keyboard(),
            )
            return

    await update.effective_message.reply_text(
        "پیامت رو گرفتم ✅\nبرای کار با ربات از منوی زیر استفاده کن.",
        reply_markup=features_keyboard(),
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    register_user(update)
    data = query.data or ""

    # Onboarding callbacks
    if data.startswith("ob_") or (not is_onboarding_done(uid) and data in {"open_report", "my_panel", "history", "settings", "achievements"}):
        if not is_onboarding_done(uid) and data in {"open_report", "my_panel", "history", "settings", "achievements"}:
            if uid not in onboarding_state:
                start_onboarding(uid)
            await show_onboarding(uid, context, edit_query=query)
            return
        if data.startswith("ob_days:"):
            days = int(data.split(":", 1)[1])
            st = onboarding_state.setdefault(uid, {"step": "days", "selected": {t["key"] for t in DEFAULT_TASKS}})
            st["days"] = days
            st["step"] = "tasks"
            await show_onboarding(uid, context, edit_query=query)
            return
        if data == "ob_days_custom":
            onboarding_state.setdefault(uid, {"step": "days", "selected": {t["key"] for t in DEFAULT_TASKS}})
            user_text_state[uid] = {"mode": "ob_days_custom"}
            await safe_edit(
                query,
                "📅 تعداد روز دلخواه را بفرست.\nمثال: <code>45</code>\nبازه: 1 تا 3650",
                parse_mode=ParseMode.HTML
            )
            return
        if data.startswith("ob_toggle:"):
            key = data.split(":", 1)[1]
            st = onboarding_state.setdefault(uid, {"step": "tasks", "selected": set(), "days": DEFAULT_CHALLENGE_DAYS})
            selected = set(st.get("selected") or [])
            if key in selected:
                selected.remove(key)
            else:
                selected.add(key)
            st["selected"] = selected
            st["step"] = "tasks"
            await show_onboarding(uid, context, edit_query=query)
            return
        if data == "ob_custom_task":
            onboarding_state.setdefault(uid, {"step": "tasks", "selected": set(), "days": DEFAULT_CHALLENGE_DAYS})
            user_text_state[uid] = {"mode": "ob_custom_task"}
            await safe_edit(
                query,
                "✍️ عنوان تسک سفارشی را بفرست.\nمثال: <code>مطالعه کتاب</code> یا <code>تمرین گیتار</code>",
                parse_mode=ParseMode.HTML
            )
            return
        if data == "ob_reset_tasks":
            st = onboarding_state.setdefault(uid, {"step": "tasks", "days": DEFAULT_CHALLENGE_DAYS})
            st["selected"] = {t["key"] for t in DEFAULT_TASKS}
            st["custom_tasks"] = []
            st["step"] = "tasks"
            await show_onboarding(uid, context, edit_query=query)
            return
        if data == "ob_back_days":
            st = onboarding_state.setdefault(uid, {"selected": {t["key"] for t in DEFAULT_TASKS}})
            st["step"] = "days"
            await show_onboarding(uid, context, edit_query=query)
            return
        if data == "ob_finish":
            st = onboarding_state.get(uid) or {}
            if not st.get("selected"):
                await query.answer("حداقل یک تسک انتخاب کن.", show_alert=True)
                return
            await finish_onboarding(uid, query=query, context=context)
            return

    if data == "home":
        # Back to landing: only Start on reply keyboard
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=uid,
            text=landing_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=landing_keyboard(),
        )
    elif data == "menu_start":
        # Inline fallback if old messages still have it
        if not is_onboarding_done(uid):
            start_onboarding(uid)
            await show_onboarding(uid, context, edit_query=query)
            return
        days = get_challenge_days(uid)
        tasks = get_user_tasks(uid)
        pillars = "\n".join(f"{t['emoji']} {escape(t['title'])}" for t in tasks)
        text = (
            "<b>✅ شروع شد</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"📅 چالش فعلی: <b>{days}</b> روز\n"
            f"✅ تعداد تسک‌ها: <b>{len(tasks)}</b>\n\n"
            "<b>تسک‌های فعال:</b>\n"
            f"{pillars}\n\n"
            "یکی از گزینه‌ها رو انتخاب کن 👇"
        )
        await safe_edit(query, text, parse_mode=ParseMode.HTML)
    elif data == "open_report":
        if not is_onboarding_done(uid):
            if uid not in onboarding_state:
                start_onboarding(uid)
            await show_onboarding(uid, context, edit_query=query)
            return
        await open_report_message(uid, context, edit_query=query)
    elif data == "edit_today_yes":
        existing = get_today_report(uid)
        if not existing:
            await open_report_message(uid, context, edit_query=query, skip_existing_check=True)
            return
        unlock_edit_today(uid)
        log_event("report_edit_unlocked", uid, today_str())
        await open_report_message(uid, context, edit_query=query, force_edit=True)
    elif data == "edit_today_no":
        pending_reports.pop(uid, None)
        await safe_edit(
            query,
            "<b>👌 باشه، گزارش امروزت همون‌طور که ثبت شده باقی موند.</b>\n"
            "اگر خواستی بعداً عوضش کنی، دوباره «ثبت گزارش امروز» رو بزن.",
            parse_mode=ParseMode.HTML
        )
    elif data.startswith("toggle:"):
        # While a saved report exists and edit is locked, block silent edits
        if get_today_report(uid) is not None and not is_edit_unlocked(uid):
            await open_report_message(uid, context, edit_query=query)
            return
        key = data.split(":", 1)[1]
        valid = {t["key"] for t in get_user_tasks(uid)}
        if key in valid:
            st = pending_reports.setdefault(uid, empty_pending(uid))
            st["tasks"][key] = not st["tasks"].get(key, False)
        await open_report_message(uid, context, edit_query=query, skip_existing_check=True)
    elif data == "choose_mood":
        if get_today_report(uid) is not None and not is_edit_unlocked(uid):
            await open_report_message(uid, context, edit_query=query)
            return
        await safe_edit(
            query,
            "<b>🙂 حال امروزت چطور بود؟</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=mood_keyboard(),
        )
    elif data.startswith("mood:"):
        if get_today_report(uid) is not None and not is_edit_unlocked(uid):
            await open_report_message(uid, context, edit_query=query)
            return
        pending_reports.setdefault(uid, empty_pending(uid))["mood"] = data.split(":", 1)[1]
        await open_report_message(uid, context, edit_query=query, skip_existing_check=True)
    elif data == "add_note":
        if get_today_report(uid) is not None and not is_edit_unlocked(uid):
            await open_report_message(uid, context, edit_query=query)
            return
        user_text_state[uid] = {"mode": "note"}
        await safe_edit(query, "📝 یادداشت کوتاه امروزت رو بفرست. مثلا: امروز سخت بود ولی تسلیم نشدم.")
    elif data == "reset_report":
        if get_today_report(uid) is not None and not is_edit_unlocked(uid):
            await open_report_message(uid, context, edit_query=query)
            return
        pending_reports[uid] = empty_pending(uid)
        await open_report_message(uid, context, edit_query=query, skip_existing_check=True)
    elif data == "confirm_report":
        if get_today_report(uid) is not None and not is_edit_unlocked(uid):
            await open_report_message(uid, context, edit_query=query)
            return
        state = pending_reports.get(uid, empty_pending(uid))
        was_edit = get_today_report(uid) is not None
        save_report(uid, state)
        tasks = get_user_tasks(uid)
        score = sum(1 for v in state.get("tasks", {}).values() if v)
        total = len(tasks) or 1
        pending_reports.pop(uid, None)
        lock_edit_today(uid)
        if was_edit:
            msg = "✏️ گزارش امروزت با موفقیت به‌روز شد."
        elif score == total and total > 0:
            msg = f"🌟 عالی! روز کامل {total}/{total} ثبت شد."
        else:
            msg = "✅ گزارش ثبت شد. فردا می‌تونی بهترش کنی."
        await safe_edit(
            query,
            f"<b>{msg}</b>\n\nامتیاز امروز: <b>{score}/{total}</b>\n\n{user_panel_text(uid)}",
            parse_mode=ParseMode.HTML,
            reply_markup=features_keyboard(),
        )
    elif data == "my_panel":
        await safe_edit(query, user_panel_text(uid), parse_mode=ParseMode.HTML)
    elif data == "history":
        await safe_edit(query, history_text(uid), parse_mode=ParseMode.HTML)
    elif data == "achievements":
        await safe_edit(query, achievements_text(uid), parse_mode=ParseMode.HTML)
    elif data == "settings":
        await safe_edit(query, settings_text(uid), parse_mode=ParseMode.HTML, reply_markup=settings_keyboard(uid))
    elif data == "reonboard":
        set_onboarding_done(uid, False)
        start_onboarding(uid)
        await show_onboarding(uid, context, edit_query=query)
    elif data == "set_days":
        user_text_state[uid] = {"mode": "set_days"}
        await safe_edit(
            query,
            "📅 <b>تعداد روز چالش</b> رو بفرست.\n"
            f"فعلی: <b>{get_challenge_days(uid)}</b>\n"
            "مثال: <code>21</code> یا <code>38</code> یا <code>100</code>\n"
            "بازه مجاز: 1 تا 3650",
            parse_mode=ParseMode.HTML
        )
    elif data == "manage_tasks":
        await safe_edit(
            query,
            tasks_manage_text(uid),
            parse_mode=ParseMode.HTML,
            reply_markup=tasks_keyboard(uid),
        )
    elif data == "task_add":
        if len(get_user_tasks(uid)) >= 12:
            await safe_edit(
                query,
                "❌ حداکثر ۱۲ تسک. اول یکی را حذف کن.",
                reply_markup=tasks_keyboard(uid),
            )
            return
        user_text_state[uid] = {"mode": "task_add"}
        await safe_edit(
            query,
            "➕ عنوان تسک جدید را بفرست.\n"
            "مثال: <code>مطالعه انگلیسی</code> یا <code>پیاده‌روی</code> یا <code>کدنویسی</code>\n"
            "حداکثر ۴۰ حرف.",
            parse_mode=ParseMode.HTML
        )
    elif data.startswith("task_del:"):
        key = data.split(":", 1)[1]
        tasks = [t for t in get_user_tasks(uid) if t["key"] != key]
        if not tasks:
            await query.answer("حداقل یک تسک باید بمونه.", show_alert=True)
            return
        set_user_tasks(uid, tasks)
        pending_reports.pop(uid, None)
        log_event("task_deleted", uid, key)
        await safe_edit(query, tasks_manage_text(uid), parse_mode=ParseMode.HTML, reply_markup=tasks_keyboard(uid))
    elif data.startswith("task_info:"):
        key = data.split(":", 1)[1]
        t = tasks_map(uid).get(key)
        if not t:
            await query.answer("پیدا نشد", show_alert=True)
            return
        await query.answer(f"{t['emoji']} {t['title']}", show_alert=False)
    elif data == "task_reset_confirm":
        await safe_edit(
            query,
            "⚠️ تسک‌ها به ۵ مورد پیش‌فرض برگردند؟",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("✅ بله، پیش‌فرض", callback_data="task_reset_yes")],
                    [InlineKeyboardButton("❌ نه", callback_data="manage_tasks")],
                ]
            ),
        )
    elif data == "task_reset_yes":
        set_user_tasks(uid, DEFAULT_TASKS)
        pending_reports.pop(uid, None)
        log_event("tasks_reset", uid)
        await safe_edit(query, tasks_manage_text(uid), parse_mode=ParseMode.HTML, reply_markup=tasks_keyboard(uid))
    elif data == "set_time":
        user_text_state[uid] = {"mode": "set_time"}
        await safe_edit(
            query,
            "⏰ ساعت یادآوری رو با فرمت 24 ساعته بفرست. مثال: <code>22:00</code>",
            parse_mode=ParseMode.HTML
        )
    elif data == "toggle_pause":
        user = get_user(uid)
        new_val = 0 if user and user["paused"] else 1
        with db() as conn:
            conn.execute("UPDATE users SET paused=? WHERE user_id=?", (new_val, uid))
            conn.commit()
        await safe_edit(query, settings_text(uid), parse_mode=ParseMode.HTML, reply_markup=settings_keyboard(uid))
    elif data == "reset_challenge_confirm":
        await safe_edit(
            query,
            "⚠️ مطمئنی چالش از امروز دوباره شروع بشه؟ گزارش‌های قبلی پاک نمی‌شن، فقط روز شروع عوض می‌شه.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("✅ بله، شروع دوباره", callback_data="reset_challenge_yes")],
                    [InlineKeyboardButton("❌ نه", callback_data="settings")],
                ]
            ),
        )
    elif data == "reset_challenge_yes":
        with db() as conn:
            conn.execute("UPDATE users SET start_date=? WHERE user_id=?", (today_str(), uid))
            conn.commit()
        log_event("challenge_reset", uid)
        await safe_edit(query, "✅ چالش از امروز دوباره شروع شد. بزن بریم!")
    elif data == "help":
        await safe_edit(
            query,
            "<b>ℹ️ راهنما</b>\n"
            "ARIAMIR TRAKER ردیاب چالش رشد شخصی است.\n"
            "اول روز و تسک‌ها را می‌چینی، بعد هر روز گزارش می‌دهی.\n"
            "از تنظیمات می‌تونی همه چیز را دوباره شخصی‌سازی کنی.",
            parse_mode=ParseMode.HTML
        )
    elif data.startswith("admin:"):
        await handle_admin_callback(query, context)


async def handle_admin_callback(query, context: ContextTypes.DEFAULT_TYPE):
    uid = query.from_user.id
    data = query.data
    if not is_admin(uid):
        await safe_edit(query, "❌ دسترسی نداری. اول /admin را بزن و وارد شو.")
        return
    if data == "admin:logout":
        with db() as conn:
            conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
            conn.commit()
        await safe_edit(query, "🚪 از پنل مدیریت خارج شدی.")
    elif data == "admin:back":
        await safe_edit(
            query,
            "<b>🔐 پنل مدیریت</b>\nیک گزینه را انتخاب کن:",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
    elif data == "admin:summary":
        await safe_edit(query, admin_summary_text(), parse_mode=ParseMode.HTML, reply_markup=admin_keyboard())
    elif data == "admin:ranking":
        await safe_edit(query, ranking_text(), parse_mode=ParseMode.HTML, reply_markup=admin_keyboard())
    elif data == "admin:events":
        await safe_edit(query, events_text(), parse_mode=ParseMode.HTML, reply_markup=admin_keyboard())
    elif data == "admin:broadcast":
        user_text_state[uid] = {"mode": "broadcast"}
        await safe_edit(query, "📣 متن پیام همگانی را بفرست. برای لغو، /start را بزن.")
    elif data == "admin:users":
        await admin_users(query)
    elif data.startswith("admin:user:"):
        target_id = int(data.split(":")[-1])
        await safe_edit(
            query,
            admin_user_text(target_id),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📅 تاریخچه کاربر", callback_data=f"admin:history:{target_id}")],
                    [
                        InlineKeyboardButton("⬅️ کاربران", callback_data="admin:users"),
                        InlineKeyboardButton("🏠 پنل", callback_data="admin:back"),
                    ],
                ]
            ),
        )
    elif data.startswith("admin:history:"):
        target_id = int(data.split(":")[-1])
        await safe_edit(
            query,
            history_text(target_id),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ برگشت", callback_data=f"admin:user:{target_id}")]]
            ),
        )
    elif data == "admin:csv":
        path = export_csv()
        with open(path, "rb") as f:
            await context.bot.send_document(chat_id=uid, document=f, filename="ariamir_reports.csv")
        await safe_edit(query, "📤 خروجی CSV ارسال شد.", reply_markup=admin_keyboard())
    elif data == "admin:backup":
        path = backup_database()
        with open(path, "rb") as f:
            await context.bot.send_document(chat_id=uid, document=f, filename=os.path.basename(path))
        await safe_edit(query, "💾 بکاپ دیتابیس ارسال شد.", reply_markup=admin_keyboard())


async def admin_users(query):
    with db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 30").fetchall()
    if not rows:
        await safe_edit(query, "هنوز کاربری ثبت نشده.", reply_markup=admin_keyboard())
        return
    buttons = []
    for r in rows:
        display = r["first_name"] or r["username"] or str(r["user_id"])
        uname = f"@{r['username']}" if r["username"] else "بدون یوزرنیم"
        buttons.append(
            [InlineKeyboardButton(f"👤 {display} | {uname}", callback_data=f"admin:user:{r['user_id']}")]
        )
    buttons.append([InlineKeyboardButton("⬅️ برگشت", callback_data="admin:back")])
    await safe_edit(
        query,
        "<b>👥 کاربران ربات</b>\nیک نفر را انتخاب کن:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def admin_summary_text() -> str:
    with db() as conn:
        users_count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        active = conn.execute("SELECT COUNT(*) c FROM users WHERE is_active=1 AND paused=0").fetchone()["c"]
        reports_count = conn.execute("SELECT COUNT(*) c FROM reports").fetchone()["c"]
        today_reports = conn.execute(
            "SELECT COUNT(*) c FROM reports WHERE report_date=?", (today_str(),)
        ).fetchone()["c"]
        rows = conn.execute("SELECT * FROM reports").fetchall()
    total_done = 0
    total_possible = 0
    for r in rows:
        dm = report_done_map(r)
        if r["tasks_done_json"]:
            total_done += sum(1 for v in dm.values() if v)
            total_possible += max(1, len(dm))
        else:
            total_done += sum(int(r[k]) for k in LEGACY_TASK_KEYS)
            total_possible += len(LEGACY_TASK_KEYS)
    percent = round((total_done / total_possible) * 100) if total_possible else 0
    return (
        "<b>📈 گزارش کلی ربات</b>\n━━━━━━━━━━━━━━\n"
        f"👥 کل کاربران: <b>{users_count}</b>\n"
        f"✅ کاربران فعال یادآوری: <b>{active}</b>\n"
        f"📝 کل گزارش‌ها: <b>{reports_count}</b>\n"
        f"🌙 گزارش‌های امروز: <b>{today_reports}</b>\n"
        f"📊 درصد انجام بین گزارش‌ها: <b>{percent}%</b>"
    )


def ranking_text() -> str:
    with db() as conn:
        users = conn.execute("SELECT user_id, first_name, username FROM users").fetchall()
    scored = []
    for u in users:
        s = user_stats(u["user_id"])
        scored.append((s["done_tasks"], s["streak"], u))
    scored.sort(reverse=True, key=lambda x: (x[0], x[1]))
    if not scored:
        return "<b>🏅 رتبه‌بندی</b>\nهنوز داده‌ای نیست."
    lines = ["<b>🏅 رتبه‌بندی کاربران</b>", "━━━━━━━━━━━━━━"]
    for i, (done, streak, u) in enumerate(scored[:10], 1):
        name = escape(u["first_name"] or u["username"] or str(u["user_id"]))
        lines.append(f"{i}. <b>{name}</b> — ✅ {done} | 🔥 {streak}")
    return "\n".join(lines)


def events_text() -> str:
    with db() as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 10").fetchall()
    if not rows:
        return "<b>🧾 لاگ‌ها</b>\nفعلا لاگی نیست."
    lines = ["<b>🧾 آخرین رویدادها</b>", "━━━━━━━━━━━━━━"]
    for r in rows:
        lines.append(
            f"• {escape(r['event_type'])} | <code>{r['user_id'] or '-'}</code> | {escape((r['created_at'] or '')[5:16])}"
        )
    return "\n".join(lines)


def admin_user_text(target_id: int) -> str:
    u = get_user(target_id)
    if not u:
        return "کاربر پیدا نشد."
    s = user_stats(target_id)
    uname = f"@{u['username']}" if u["username"] else "بدون یوزرنیم"
    days = get_challenge_days(target_id)
    tasks = get_user_tasks(target_id)
    return (
        "<b>👤 پرونده کاربر</b>\n━━━━━━━━━━━━━━\n"
        f"نام: <b>{escape(u['first_name'] or '')}</b>\n"
        f"یوزرنیم: <b>{escape(uname)}</b>\n"
        f"آیدی: <code>{target_id}</code>\n"
        f"شروع: <b>{u['start_date']}</b> | روز <b>{challenge_day(target_id)}</b> از <b>{days}</b>\n"
        f"تسک‌ها: <b>{len(tasks)}</b>\n"
        f"وضعیت یادآوری: <b>{'متوقف' if u['paused'] else 'فعال'}</b>\n\n"
        f"📝 گزارش‌ها: <b>{s['total_reports']}</b>\n"
        f"✅ مجموع کارها: <b>{s['done_tasks']}</b>\n"
        f"🌟 روزهای کامل: <b>{s['full_days']}</b>\n"
        f"🔥 استریک: <b>{s['streak']}</b>"
    )


async def broadcast_message(context: ContextTypes.DEFAULT_TYPE, text: str) -> tuple[int, int]:
    with db() as conn:
        users = conn.execute("SELECT user_id FROM users WHERE is_active=1").fetchall()
    sent = failed = 0
    for r in users:
        try:
            await context.bot.send_message(
                r["user_id"],
                f"<b>📣 پیام مدیر ARIAMIR TRAKER</b>\n\n{escape(text)}",
                parse_mode=ParseMode.HTML
            )
            sent += 1
        except (Forbidden, BadRequest):
            failed += 1
    log_event("broadcast", None, text)
    return sent, failed


def backup_database() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = now_tehran().strftime("%Y-%m-%d_%H-%M-%S")
    dst = os.path.join(BACKUP_DIR, f"ariamir_tracker_backup_{stamp}.db")
    with sqlite3.connect(DB_PATH) as source:
        with sqlite3.connect(dst) as target:
            source.backup(target)
    return dst


def cleanup_old_backups(keep: int = 14) -> None:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    files = sorted(
        [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith(".db")],
        key=os.path.getmtime,
        reverse=True,
    )
    for old in files[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass


async def automatic_backup(context: ContextTypes.DEFAULT_TYPE):
    try:
        path = backup_database()
        cleanup_old_backups()
        log_event("auto_backup", None, os.path.basename(path))
        print(f"Automatic backup created: {path}")
    except Exception as e:
        print(f"Automatic backup failed: {e}")


def export_csv() -> str:
    fd, path = tempfile.mkstemp(prefix="ariamir_reports_", suffix=".csv")
    os.close(fd)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT u.user_id, u.username, u.first_name, u.start_date, u.reminder_hour, u.reminder_minute,
                   u.paused, u.challenge_days, u.tasks_json,
                   r.report_date, r.challenge_day, r.tasks_done_json, r.nofap, r.study, r.med, r.sport, r.phone,
                   r.mood, r.note, r.updated_at
            FROM users u
            LEFT JOIN reports r ON u.user_id = r.user_id
            ORDER BY u.user_id, r.report_date
            """
        ).fetchall()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "user_id",
                "username",
                "first_name",
                "start_date",
                "challenge_days",
                "tasks",
                "reminder",
                "paused",
                "report_date",
                "challenge_day",
                "tasks_done",
                "mood",
                "note",
                "updated_at",
            ]
        )
        for r in rows:
            tasks = loads_tasks(r["tasks_json"])
            task_titles = " | ".join(f"{t['emoji']}{t['title']}" for t in tasks)
            done = r["tasks_done_json"] or ""
            if not done and r["report_date"]:
                done = json.dumps({k: int(r[k] or 0) for k in LEGACY_TASK_KEYS}, ensure_ascii=False)
            writer.writerow(
                [
                    r["user_id"],
                    r["username"],
                    r["first_name"],
                    r["start_date"],
                    r["challenge_days"] or DEFAULT_CHALLENGE_DAYS,
                    task_titles,
                    f"{r['reminder_hour']:02d}:{r['reminder_minute']:02d}",
                    r["paused"],
                    r["report_date"],
                    r["challenge_day"],
                    done,
                    r["mood"],
                    r["note"],
                    r["updated_at"],
                ]
            )
    return path


async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    now = now_tehran()
    with db() as conn:
        users = conn.execute("SELECT * FROM users WHERE is_active=1 AND paused=0").fetchall()
    for u in users:
        uid = u["user_id"]
        if is_challenge_finished(uid):
            continue
        if int(u["reminder_hour"]) != now.hour or int(u["reminder_minute"]) != now.minute:
            continue
        with db() as conn:
            exists = conn.execute(
                "SELECT id FROM events WHERE user_id=? AND event_type='reminder_sent' AND payload=?",
                (uid, today_str()),
            ).fetchone()
        if exists:
            continue
        # If already reported today, don't push a fresh editable form silently
        if get_today_report(uid) is not None:
            continue
        pending_reports[uid] = empty_pending(uid)
        days = get_challenge_days(uid)
        try:
            await context.bot.send_message(
                uid,
                f"<b>⏰ وقت گزارش شبانه ARIAMIR TRAKER</b>\n━━━━━━━━━━━━━━\nامروز روز <b>{challenge_day(uid)}</b> از <b>{days}</b> بود.\nصادقانه انتخاب کن چی انجام شد 👇",
                parse_mode=ParseMode.HTML,
                reply_markup=report_keyboard(uid),
            )
            log_event("reminder_sent", uid, today_str())
        except Exception as e:
            print(f"Could not send reminder to {uid}: {e}")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN خالی است. فایل .env بساز و توکن را داخلش قرار بده.")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.job_queue.run_repeating(daily_reminder, interval=60, first=5, name="personal_reminders")
    app.job_queue.run_daily(
        automatic_backup, time=time(hour=3, minute=10, tzinfo=TZ), name="daily_database_backup"
    )

    # Bot Menu (Telegram side menu): only /start
    async def _post_init(application: Application):
        from telegram import BotCommand
        await application.bot.set_my_commands(
            [BotCommand("start", "شروع ربات")]
        )
    app.post_init = _post_init

    print("ARIAMIR TRAKER ULTRA is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
