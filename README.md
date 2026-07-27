# ARIAMIR TRAKER

ربات تلگرامی مدیریت **چالش رشد شخصی** با راه‌اندازی تعاملی، مدت و تسک‌های قابل‌تنظیم، گزارش روزانه، داشبورد، استریک، یادآوری، بکاپ و پنل مدیریت.

ربات: [@ARIAMIRTRAKER_BOT](https://t.me/ARIAMIRTRAKER_BOT)

## ساختار پروژه

```text
ariamir-tracker-bot/
├── bot.py                 # کد اصلی ربات
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
├── .github/workflows/     # اجرای زمان‌بندی‌شده + حافظه پایدار
├── deploy/                # systemd برای VPS
├── docs/                  # مستندات، BotFather، رزومه
├── tests/                 # تست‌های آفلاین
├── scripts/               # اسکریپت‌های کمکی
│   ├── run_local.sh
│   └── run_tests.sh
└── data/                  # دیتابیس و بکاپ (gitignore)
```

## امکانات

### کاربر

- **راه‌اندازی اولیه تعاملی** در `/start`:
  - انتخاب تعداد روز چالش (۲۱ / ۳۰ / ۳۸ / ۶۰ / ۹۰ یا عدد دلخواه)
  - انتخاب تسک‌ها از پیشنهادها + افزودن تسک سفارشی
- ثبت گزارش روزانه با دکمه‌های Inline
- اگر گزارش امروز ثبت شده باشد، برای ویرایش دوباره تأیید می‌گیرد
- تسک‌های پیشنهادی پیش‌فرض:
  - 🧠 کنترل عادت
  - 📚 درس
  - 🧘 مدیتیشن
  - 🏋️ ورزش
  - 📵 مدیریت گوشی
- پیشنهادهای بیشتر هنگام onboarding: خواب، آب، زبان، کدنویسی، پیاده‌روی و ...
- ثبت حال امروز و یادداشت روزانه
- داشبورد پیشرفت، تاریخچه، نشان‌ها و استریک
- تنظیم ساعت یادآوری شخصی / توقف یادآوری
- شروع دوباره چالش یا راه‌اندازی دوباره (روز + تسک)

### مدیریت

- ورود امن با نام کاربری و رمز از `.env`
- کاربران، پرونده، تاریخچه، گزارش کلی، رتبه‌بندی
- لاگ رویدادها، پیام همگانی، CSV، بکاپ دیتابیس

### پایداری و حافظه

- SQLite با WAL
- بکاپ خودکار روزانه ساعت 03:10 تهران
- Docker و systemd برای اجرای دائمی
- روی GitHub Actions: ذخیره/بازیابی حافظه از branch `bot-data`

## نصب محلی

```bash
pip install -r requirements.txt
cp .env.example .env
# .env را پر کن
python bot.py
# یا:
./scripts/run_local.sh
```

## تنظیمات .env

```env
BOT_TOKEN=توکن_ربات
ADMIN_USERNAME=Amir_seyedi_1387
ADMIN_PASSWORD=رمز_قوی
REMINDER_HOUR=22
REMINDER_MINUTE=0
CHALLENGE_DAYS=38
DATA_DIR=./data
DB_PATH=./data/ariamir_tracker.db
BACKUP_DIR=./data/backups
```

`CHALLENGE_DAYS` فقط مقدار پیش‌فرض برای کاربران جدید است؛ هر کاربر در onboarding می‌تواند آن را عوض کند.

## اجرای دائمی / نیمه‌دائمی

- **نیمه‌دائمی رایگان (GitHub Actions - lean):**
  - حدود **۲۱:۳۰ تهران، ~۹۰ دقیقه** (برای تمام‌نشدن سریع minutes)
  - جزئیات: `.github/workflows/run-bot-nightly.yml`
  - اگر run نمی‌شود: احتمالاً سهمیه private تموم شده → `docs/FREE_HOSTING.md`
- **حافظه پایدار:** branch `bot-data`
- **دائمی ۲۴/۷:** `docs/DEPLOY_FREE_ALWAYS_ON.md` (پیشنهاد: Oracle Always Free VPS)
- **راهنمای رایگان کامل:** `docs/FREE_HOSTING.md`

## اجرای Docker

```bash
cp .env.example .env
# .env را پر کن
sudo docker compose up -d --build
sudo docker compose logs -f
```

## دستورات ربات

- `/start` شروع / راه‌اندازی چالش
- `/report` ثبت گزارش امروز
- `/panel` داشبورد پیشرفت
- `/history` تاریخچه گزارش‌ها
- `/settings` تنظیمات (روز + تسک + یادآوری)
- `/admin` پنل مدیریت
- `/help` راهنما

### شخصی‌سازی

از `/settings` یا ⚙️:

1. 📅 تعداد روز چالش
2. ✅ مدیریت تسک‌ها
3. 🧩 راه‌اندازی دوباره (روز + تسک)

## متن‌های معرفی و BotFather

- `docs/BOTFATHER_PROFILE.md` — About / Description / Commands / پست‌ها
- `docs/RESUME_BLURB.md` — متن رزومه و نمونه‌کار

## نکته امنیتی

توکن را داخل کد ننویس. فقط `.env` یا GitHub Secrets.  
اگر توکن جایی لو رفت، از BotFather توکن جدید بگیر.
