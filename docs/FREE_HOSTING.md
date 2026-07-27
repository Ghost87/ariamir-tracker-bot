# چرا ربات روی GitHub Actions بالا نمی‌آید؟ و چطور رایگان اجرا کنیم؟

## تشخیص سریع

اگر در صفحه Actions پیام‌هایی مثل این‌ها می‌بینی، مشکل **سهمیه/صورتحساب** است نه باگ کد:

- `The job was not started because recent account payments have failed`
- `spending limit needs to be increased`
- `minutes quota exceeded` / Actions disabled

### واقعیت مصرف workflow قبلی

| مورد | مقدار |
|---|---|
| اجرا در روز | ۴ بار |
| هر اجرا | حدود ۳ ساعت و ۴۵ دقیقه |
| مصرف روزانه | حدود **۹۰۰ دقیقه** |
| مصرف ماهانه | حدود **۲۷٬۰۰۰ دقیقه** |
| سهمیه Free برای **ریپوی خصوصی** | حدود **۲٬۰۰۰ دقیقه / ماه** |
| نتیجه | سهمیه در حدود **۲ روز** تمام می‌شود |

پس حدس «محدودیت استفاده تموم شده» **کاملاً محتمل و منطقی** است.

---

## الان workflow را چطور کم‌مصرف کردم؟

نسخه جدید فقط **۱ بار در روز** حدود **۹۰ دقیقه** (حدود ۲۱:۳۰ تهران) اجرا می‌شود.

- مصرف تقریبی: حدود ۲۷۰۰ دقیقه/ماه  
- هنوز برای private Free کمی سنگین است  
- برای پایدار شدن روی Actions، یکی از دو کار زیر را بکن:

### راه A (سریع‌ترین روی GitHub): Public کردن ریپو
1. Repo → **Settings → General → Danger Zone → Change repository visibility → Public**
2. برای **public repo**، دقایق Actions روی runnerهای استاندارد GitHub معمولاً **رایگان/بدون سقف دقیقه ماهانه private** حساب می‌شود
3. **Secrets** را دوباره چک کن: `BOT_TOKEN`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`
4. Actions → workflow را **Run workflow** بزن

> اگر کد/توکن حساس داخل repo نباشد (توکن فقط Secret باشد) public کردن برای این پروژه معمولاً اوکی است.

### راه B: ریپو private بماند
1. برو: [GitHub Billing](https://github.com/settings/billing)
2. **Actions spending limit** را از `$0` حداقل به مقدار کوچک بالا ببر (گاهی حتی برای استفاده از free allowance لازم است)
3. صبر کن تا دوره billing ریست شود یا usage را کم کن
4. workflow lean جدید را دستی Run کن

---

## راه‌های رایگان بهتر از GitHub Actions برای ربات

GitHub Actions برای CI عالی است، ولی برای ربات polling «همیشه‌روشن» ساخته نشده.  
برای رایگانِ واقعی‌تر:

### ۱) بهترین گزینه رایگان واقعی: Oracle Cloud Always Free VPS
- VM همیشه روشن
- SQLite کامل و پایدار
- با Docker یا systemd ربات ۲۴/۷ می‌ماند
- راهنمای همین پروژه: `docs/DEPLOY_FREE_ALWAYS_ON.md`

**خلاصه مسیر:**
1. ساخت حساب Always Free
2. Ubuntu VM
3. `git clone` + `.env`
4. `docker compose up -d` یا systemd

### ۲) Railway / Render / Koyeb / Fly.io (آسان‌تر از VPS)
- اتصال به GitHub
- Env: `BOT_TOKEN`, ...
- Start command: `python bot.py`
- دیسک پایدار برای SQLite مهم است (Free tier بعضی‌ها ephemeral است)
- cold start / sleep در بعضی پلن‌های رایگان polling را خراب می‌کند

| پلتفرم | مناسب polling؟ | نکته |
|---|---|---|
| Oracle VPS | عالی | بهترین رایگان پایدار |
| Railway | خوب | اعتبار/تریال محدود |
| Render Worker | متوسط | free ممکن است sleep کند |
| Fly.io | خوب | نیاز به تنظیم machine |
| GitHub Actions | ضعیف برای ۲۴/۷ | فقط پنجره زمانی |

### ۳) کامپیوتر/لپ‌تاپ خودت (موقت)
```bash
cd ariamir-tracker-bot
cp .env.example .env   # اگر نداری
./scripts/run_local.sh
```
تا وقتی سیستم روشن و اینترنت داشته باشد کار می‌کند.

---

## چک‌لیست عیب‌یابی (۵ دقیقه)

1. **Actions tab** را باز کن؛ آخرین run را ببین (queued / failed / cancelled؟)
2. اگر run اصلاً start نمی‌شود → Billing / minutes / spending limit
3. اگر start می‌شود و سریع می‌میرد → لاگ را باز کن:
   - `BOT_TOKEN` خالی؟
   - Conflict: `terminated by other getUpdates request` یعنی instance دیگری همزمان روشن است
4. Secrets:
   - `BOT_TOKEN`
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
5. بعد از public کردن یا ریست billing، یک **Run workflow** دستی بزن

---

## پیشنهاد من برای تو (اولویت)

1. **اگر می‌خواهی همین روش GitHub را نگه داری:** ریپو را **Public** کن + workflow lean جدید
2. **اگر می‌خواهی ربات واقعاً همیشه جواب بدهد:** **Oracle Always Free VPS**
3. تا آن موقع: همین‌جا/`run_local` برای تست کوتاه

---

## مصرف تخمینی بعد از lean workflow

| سناریو | مصرف ماهانه تقریبی |
|---|---|
| ۱ × ۹۰ دقیقه/روز | ~۲۷۰۰ min |
| ۱ × ۶۰ دقیقه/روز | ~۱۸۰۰ min (داخل Free private) |
| Public repo | معمولاً محدودیت دقیقه private اعمال نمی‌شود |

اگر بخواهی، می‌توانم workflow را حتی به **۶۰ دقیقه فقط شب‌ها** هم ببرم تا داخل ۲۰۰۰ دقیقه private جا شود.

---

## فهرست کامل‌تر راه‌های جایگزین

ببین: `docs/HOSTING_ALTERNATIVES.md`
