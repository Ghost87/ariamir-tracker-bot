#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧹 ابزار پاک‌سازی داده‌های کاربران/تاریخچه — ARIAMIR Tracker Bot
ساخته‌شده توسط ARIAMIR (@ARIAMIR_IR)

دو حالت:
  wipe_all     → حذف همه‌ی کاربران + گزارش‌ها + رویدادها + لیست ادمین‌ها (شروع تازه)
  history_only → حذف فقط تاریخچه (reports + events) — کاربران و ادمین‌ها می‌مانند

استفاده:
  python scripts/admin_tools.py --action wipe_all
  python scripts/admin_tools.py --action history_only
  (مسیر دیتابیس با --db قابل تغییر است؛ پیش‌فرض: data/ariamir_tracker.db)
"""
import argparse
import os
import sqlite3
import sys

ACTION_TABLES = {
    "wipe_all": ["reports", "events", "users", "admins"],
    "history_only": ["reports", "events"],
}
ALL_TRACKED = ["users", "reports", "events", "admins"]


def count(cur: sqlite3.Cursor, table: str) -> int:
    try:
        return cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error:
        return -1


def snapshot(cur: sqlite3.Cursor, label: str) -> None:
    print(f"\n📊 {label}")
    for t in ALL_TRACKED:
        c = count(cur, t)
        print(f"   {t:<10} : {'—' if c < 0 else str(c) + ' ردیف'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="پاک‌سازی داده‌های ربات ترکر")
    parser.add_argument("--action", required=True, choices=list(ACTION_TABLES.keys()))
    parser.add_argument("--db", default=os.environ.get("DB_PATH", "data/ariamir_tracker.db"))
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"❌ دیتابیس پیدا نشد: {args.db} — چیزی برای پاک‌سازی نیست.")
        return 1

    con = sqlite3.connect(args.db)
    cur = con.cursor()
    print(f"🧹 ابزار مدیریتی ARIAMIR Tracker | حالت: {args.action}")
    snapshot(cur, "قبل از پاک‌سازی:")

    for t in ACTION_TABLES[args.action]:
        try:
            cur.execute(f"DELETE FROM {t}")
        except sqlite3.Error:
            pass  # جدول هنوز ساخته نشده — مهم نیست

    con.commit()
    if args.action == "wipe_all":
        print("\n🗑️ همه‌ی کاربران، گزارش‌ها، رویدادها و ادمین‌ها حذف شدند.")
    else:
        print("\n🗑️ تاریخچه (گزارش‌ها + رویدادها) حذف شد — کاربران ماندند.")
    snapshot(cur, "بعد از پاک‌سازی:")
    cur.execute("VACUUM")
    con.close()
    print("\n✅ پاک‌سازی با موفقیت انجام شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
