# ARIAMIR TRAKER

ربات تلگرامی مدیریت چالش رشد شخصی.

> این مخزن **عمومی** است تا دقایق GitHub Actions رایگان و نامحدود بماند. هیچ توکن/رمزی در کد وجود ندارد — متغیرهای حساس فقط در GitHub Secrets نگهداری می‌شوند.

## اجرای سریع (محلی)

```bash
cp .env.example .env
# BOT_TOKEN و مشخصات ادمین را فقط در .env بگذار
python -m pip install -r requirements.txt
python bot.py
```

## نکات امنیتی

- توکن و رمزها را فقط در `.env` یا GitHub Secrets نگه دارید
- `.env` و دیتابیس commit نمی‌شوند
- فایل zip آماده اجرا را از بسته‌ی محلی بگیرید، نه از سورس عمومی

## مستندات بیشتر

- `راهنما` داخل بسته‌ی zip
- `docs/` برای جزئیات deploy و هاستینگ
