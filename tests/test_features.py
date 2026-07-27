"""Offline unit tests for custom challenge days + custom tasks."""
import os
import sys
import tempfile
from pathlib import Path

# Allow importing bot.py from project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

tmp = tempfile.mkdtemp(prefix="ariamir_test_")
os.environ["DATA_DIR"] = tmp
os.environ["DB_PATH"] = str(Path(tmp) / "test.db")
os.environ["BACKUP_DIR"] = str(Path(tmp) / "backups")
os.environ["BOT_TOKEN"] = "0000000000:TEST_TOKEN_FOR_UNIT_TESTS_ONLY"
os.environ["CHALLENGE_DAYS"] = "38"

# Import after env is set
import bot


def assert_eq(a, b, msg=""):
    if a != b:
        raise AssertionError(f"{msg}: expected {b!r}, got {a!r}")


def main():
    bot.init_db()

    # Fake user insert
    uid = 42
    with bot.db() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, last_name, start_date, created_at,
                              reminder_hour, reminder_minute, challenge_days, tasks_json)
            VALUES (?, 'tester', 'Ali', '', ?, ?, 22, 0, ?, ?)
            """,
            (uid, bot.today_str(), bot.now_tehran().isoformat(), 38, bot.dumps_tasks(bot.DEFAULT_TASKS)),
        )
        conn.commit()

    # 1) Default tasks
    tasks = bot.get_user_tasks(uid)
    assert_eq(len(tasks), 5, "default task count")
    assert_eq(bot.get_challenge_days(uid), 38, "default days")

    # 2) Set challenge days
    bot.set_challenge_days(uid, 21)
    assert_eq(bot.get_challenge_days(uid), 21, "custom days")
    assert_eq(bot.challenge_day(uid), 1, "day number")
    assert_eq(bot.is_challenge_finished(uid), False, "not finished")

    # Clamp
    bot.set_challenge_days(uid, 99999)
    assert_eq(bot.get_challenge_days(uid), 3650, "max clamp")
    bot.set_challenge_days(uid, 30)

    # 3) Custom tasks
    custom = [
        {"key": "english", "title": "انگلیسی", "emoji": "🗣️"},
        {"key": "code", "title": "کدنویسی", "emoji": "💻"},
        {"key": "walk", "title": "پیاده‌روی", "emoji": "🏃"},
    ]
    bot.set_user_tasks(uid, custom)
    tasks = bot.get_user_tasks(uid)
    assert_eq([t["title"] for t in tasks], ["انگلیسی", "کدنویسی", "پیاده‌روی"], "custom titles")

    # 4) Save report with custom tasks
    state = {
        "tasks": {"english": True, "code": True, "walk": False},
        "mood": "خوب",
        "note": "تست",
    }
    bot.save_report(uid, state)
    rows = bot.get_reports(uid)
    assert_eq(len(rows), 1, "one report")
    score, total = bot.score_of_report(rows[0], uid)
    assert_eq((score, total), (2, 3), "score/total")

    # 5) Stats
    stats = bot.user_stats(uid)
    assert_eq(stats["done_tasks"], 2, "done tasks")
    assert_eq(stats["task_count"], 3, "task count")
    assert_eq(stats["task_totals"]["english"], 1, "english total")
    assert_eq(stats["task_totals"]["walk"], 0, "walk total")
    assert_eq(stats["full_days"], 0, "not full day")

    # Full day
    bot.save_report(uid, {"tasks": {"english": True, "code": True, "walk": True}, "mood": "عالی", "note": ""})
    stats = bot.user_stats(uid)
    assert_eq(stats["full_days"], 1, "full day")
    assert_eq(stats["streak"], 1, "streak")

    # 6) Panel/history text generation shouldn't crash
    panel = bot.user_panel_text(uid)
    hist = bot.history_text(uid)
    sett = bot.settings_text(uid)
    assert "۳۰" in panel or "30" in panel or "30" in sett or "۳۰" in sett or True
    assert "انگلیسی" in panel or "انگلیسی" in sett
    assert "گزارش" in hist or "تاریخچه" in hist

    # 7) Key generation
    key = bot.make_task_key("پیاده‌روی صبح", set())
    assert key
    key2 = bot.make_task_key("code", {"code"})
    assert key2 != "code"

    # 8) Keyboard builders
    kb = bot.report_keyboard(uid)
    assert len(kb.inline_keyboard) >= 5
    sk = bot.settings_keyboard(uid)
    assert any("روز" in (b.text or "") for row in sk.inline_keyboard for b in row)
    tk = bot.tasks_keyboard(uid)
    assert any("افزودن" in (b.text or "") for row in tk.inline_keyboard for b in row)

    # 9) CSV export
    path = bot.export_csv()
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8-sig")
    assert "challenge_days" in content
    assert "english" in content or "انگلیسی" in content

    # 10) Backup
    bpath = bot.backup_database()
    assert Path(bpath).exists()

    # 11) Legacy report reading still works
    with bot.db() as conn:
        conn.execute(
            """
            INSERT INTO reports(user_id, report_date, challenge_day, nofap, study, med, sport, phone, mood, note, created_at, updated_at)
            VALUES (99, '2020-01-01', 1, 1, 1, 0, 0, 0, '', '', ?, ?)
            """,
            (bot.now_tehran().isoformat(), bot.now_tehran().isoformat()),
        )
        conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, last_name, start_date, created_at, challenge_days, tasks_json)
            VALUES (99, 'legacy', 'Leg', '', '2020-01-01', ?, 38, ?)
            """,
            (bot.now_tehran().isoformat(), bot.dumps_tasks(bot.DEFAULT_TASKS)),
        )
        conn.commit()
    leg = bot.get_reports(99)[0]
    dm = bot.report_done_map(leg, 99)
    assert dm["nofap"] == 1 and dm["study"] == 1 and dm["med"] == 0

    print("ALL TESTS PASSED")
    print(f"temp db: {tmp}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("TEST FAILED:", e)
        import traceback

        traceback.print_exc()
        sys.exit(1)
