# اجرای دائمی ARIAMIR TRAKER

## واقعیت مهم

برای اینکه ربات **واقعاً ۲۴ ساعته** روشن باشد و حافظه‌اش بدون مشکل کار کند، باید روی محیطی اجرا شود که:

1. ۲۴ ساعته روشن بماند.
2. حافظه دائمی یا دیسک دائمی داشته باشد.
3. اجازه اجرای دائمی Python بدهد.

### وضعیت فعلی روی GitHub Actions

فایل workflow فعلی ربات را **۲۴/۷ کامل** روشن نگه نمی‌دارد (Actions برای این کار ساخته نشده).

نسخه **lean** فعلی (برای نسوختن minutes):

| پنجره (تهران) | رفتار |
|---|---|
| حدود **۲۱:۳۰ تا ~۲۳:۰۰** | یک job حدود ۹۰ دقیقه |
| بقیه ساعات | خاموش |

`concurrency` جلوی دو instance همزمان را می‌گیرد.

⚠️ روی **ریپوی private**، GitHub Free فقط حدود **۲۰۰۰ دقیقه/ماه** می‌دهد.
نسخه قدیمی ۴ پنجره‌ای (~۹۰۰ دقیقه/روز) سهمیه را در ~۲ روز تمام می‌کرد.
جزئیات عیب‌یابی و جایگزین‌های رایگان: `docs/FREE_HOSTING.md`

### حافظه پایدار (دیگر از صفر شروع نمی‌شود)

بین هر اجرای Actions، دیتابیس روی branch جدا به نام **`bot-data`** ذخیره می‌شود:

1. **شروع job** → `data/` از `bot-data` restore می‌شود  
2. **پایان job** → SQLite checkpoint می‌شود و دوباره روی `bot-data` push می‌شود  
3. Artifact هم به‌عنوان بکاپ اضافه (۱۴ روز) آپلود می‌شود  

یعنی کاربران، گزارش‌ها، تعداد روز چالش، تسک‌های شخصی و تنظیمات یادآوری **بین اجراها حفظ می‌مانند**.

اگر branch `bot-data` را دستی پاک کنید، حافظه از صفر ساخته می‌شود.

اگر می‌خواهید ربات **واقعاً همیشه** فعال باشد، پیشنهاد اصلی: **Oracle Cloud Always Free VPS** (یا هر VPS دائمی دیگر).

---

# پیشنهاد اصلی: Oracle Cloud Always Free VPS

مزیت‌ها:

- رایگان
- ۲۴ ساعته روشن
- دیسک دائمی دارد
- برای SQLite مناسب است
- با systemd می‌شود ربات را طوری تنظیم کرد که اگر قطع شد خودکار روشن شود

عیب‌ها:

- ثبت‌نام ممکن است کارت بانکی بین‌المللی بخواهد.
- راه‌اندازی اولیه کمی فنی‌تر است.

---

# روش ۱: اجرای دائمی با Docker Compose

این روش ساده و تمیز است.

## 1. نصب Docker روی VPS Ubuntu

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 2. گرفتن پروژه

اگر پروژه را روی GitHub گذاشتی:

```bash
git clone https://github.com/YOUR_USERNAME/ariamir-tracker-bot.git
cd ariamir-tracker-bot
```

یا فایل ZIP را آپلود و unzip کن.

## 3. ساخت فایل .env

```bash
nano .env
```

داخلش بنویس:

```env
BOT_TOKEN=توکن_جدید_ربات
ADMIN_USERNAME=change_me
ADMIN_PASSWORD=رمز_قوی_تر_پیشنهادی
REMINDER_HOUR=22
REMINDER_MINUTE=0
CHALLENGE_DAYS=38
DATA_DIR=/app/data
DB_PATH=/app/data/ariamir_tracker.db
BACKUP_DIR=/app/data/backups
```

ذخیره: `Ctrl + O` بعد Enter  
خروج: `Ctrl + X`

## 4. اجرا

```bash
sudo docker compose up -d --build
```

## 5. دیدن لاگ

```bash
sudo docker compose logs -f
```

## 6. توقف

```bash
sudo docker compose down
```

## 7. آپدیت ربات

```bash
git pull
sudo docker compose up -d --build
```

---

# روش ۲: اجرای دائمی با systemd بدون Docker

## 1. ساخت کاربر مخصوص ربات

```bash
sudo adduser --system --group --home /opt/ariamir-tracker ariamir
```

## 2. کپی پروژه

```bash
sudo mkdir -p /opt/ariamir-tracker
sudo cp -r . /opt/ariamir-tracker/
sudo chown -R ariamir:ariamir /opt/ariamir-tracker
```

## 3. ساخت virtualenv

```bash
cd /opt/ariamir-tracker
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
sudo -u ariamir python3 -m venv .venv
sudo -u ariamir .venv/bin/pip install -r requirements.txt
```

## 4. ساخت .env

```bash
sudo nano /opt/ariamir-tracker/.env
```

محتوا:

```env
BOT_TOKEN=توکن_جدید_ربات
ADMIN_USERNAME=change_me
ADMIN_PASSWORD=رمز_قوی_تر_پیشنهادی
REMINDER_HOUR=22
REMINDER_MINUTE=0
CHALLENGE_DAYS=38
DATA_DIR=/opt/ariamir-tracker/data
DB_PATH=/opt/ariamir-tracker/data/ariamir_tracker.db
BACKUP_DIR=/opt/ariamir-tracker/data/backups
```

## 5. نصب سرویس systemd

```bash
sudo cp deploy/ariamir-tracker.service /etc/systemd/system/ariamir-tracker.service
sudo systemctl daemon-reload
sudo systemctl enable ariamir-tracker
sudo systemctl start ariamir-tracker
```

## 6. بررسی وضعیت

```bash
sudo systemctl status ariamir-tracker
```

## 7. دیدن لاگ زنده

```bash
journalctl -u ariamir-tracker -f
```

## 8. ری‌استارت بعد از تغییر کد

```bash
sudo systemctl restart ariamir-tracker
```

---

# حافظه و دیتابیس

ربات از SQLite استفاده می‌کند و فایل دیتابیس اینجاست:

```text
data/ariamir_tracker.db
```

بکاپ‌ها اینجا ذخیره می‌شوند:

```text
data/backups/
```

ربات هر روز ساعت 03:10 به وقت تهران بکاپ خودکار می‌گیرد.
از پنل مدیریت هم می‌توانی با دکمه «💾 بکاپ دیتابیس» فایل دیتابیس را بگیری.

### نکته مهم درباره GitHub Actions

دیتابیس بین jobها با **cache + artifact** حفظ می‌شود، ولی ۱۰۰٪ مثل دیسک VPS پایدار نیست.
برای حافظه جدی و بدون ریسک، VPS بهتر است.

---

# Secrets لازم در GitHub

Repository → Settings → Secrets and variables → Actions:

- `BOT_TOKEN`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

بعد از push شدن workflow جدید:

1. برو Actions
2. workflow به نام **Run ARIAMIR TRAKER always-on windows**
3. **Run workflow** را یک‌بار دستی بزن تا فوری تست شود

---

# پیشنهاد امنیتی جدی

اگر توکن را جایی عمومی فرستادی، حتماً از BotFather توکن جدید بگیر:

1. برو BotFather
2. ربات را انتخاب کن
3. API Token را Regenerate یا Revoke کن
4. توکن جدید را فقط داخل `.env` / GitHub Secrets بگذار

همچنین رمز ادمین را بهتر است عوض کنی.
