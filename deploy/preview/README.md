# پیش‌نمایش عمومی طراحی کلینیک

مالک صریحاً نمایش آزمایشی صفحات در `https://drgerami-md.ir/clinic` را انتخاب کرده است. این نسخه از قالب‌های واقعی Django ساخته می‌شود؛ داده‌ها کاملاً مصنوعی‌اند و حساب عمومی، رمز عبور، پرونده واقعی یا بانک زنده ندارد. تمام صفحات برچسب پیش‌نمایش دارند و ثبت فرم/آپلود در HTML غیرفعال و در Worker نیز رد می‌شود. چاپ هم برچسب نمایشی را حفظ می‌کند.

## ساخت و بررسی

```bash
# output باید هنوز وجود نداشته باشد؛ اسکریپت پوشه موجود را بازنویسی نمی‌کند.
.venv/bin/python scripts/build_preview.py --output /tmp/clinic-preview-review
.venv/bin/python manage.py test --noinput
node --test deploy/preview/worker.test.mjs
# برای بررسی نسخه public ثبت‌شده در مخزن:
.venv/bin/python scripts/check_preview.py
```

اسکریپت ساخت، متغیرهای دیتابیس و Google را در فرایند خودش جایگزین می‌کند و یک SQLite موقت جدا می‌سازد. هیچ اطلاعاتی از دیتابیس checkout نمی‌خواند. تمام scriptهای قالب، توکن‌های مخفی و فرم‌های دارای نوشتن حذف/غیرفعال می‌شوند. فقط JavaScript مستقل پیش‌نمایش برای منو، حالت روز/شب، جست‌وجوی نمایشی و چاپ باقی می‌ماند. فرم‌های ورود رمز نمی‌پذیرند. نتیجه نهایی در `public/` و manifest محدود مسیرها ثبت شده است.

برای به‌روزرسانی، ابتدا خروجی تازه را در یک پوشه جدید بسازید و بررسی کنید؛ سپس فقط HTML/QR/manifest تأییدشده را در `public/` جایگزین کنید. فایل‌های `.data`، `.env`، پایگاه‌داده یا نشست‌ها هرگز در این پوشه قرار نمی‌گیرند. استفاده از اطلاعات واقعی در این صادرکننده ممنوع است.

## اتصال دامنه

Worker با نام مستقل `gerami-clinic-preview` فقط روی دو الگوی زیر قرار می‌گیرد:

```text
drgerami-md.ir/clinic
drgerami-md.ir/clinic/*
```

کد انتشار، factory موجود در `worker.mjs` را با manifest و **SHA کامل commit عمومیِ تأییدشده** فراخوانی می‌کند. فایل‌ها فقط از مسیرهای مجاز همان commit مخزن `4mirgr/Clinic` در GitHub دریافت و در کش عمومی لبه نگهداری می‌شوند. درخواست مرورگر، cookie، headerهای ورود یا body به GitHub ارسال نمی‌شوند؛ API یا مقصد دلخواهی وجود ندارد. پاسخ هیچ cookie نشست ایجاد نمی‌کند. نمایش HTML بدون کش مرورگر است؛ assetها حداکثر پنج دقیقه در مرورگر کش می‌شوند.

این Worker به دیتابیس، KV، R2، secret، حساب Google، پلن پولی یا میزبان Python متصل نیست. فایل‌های سایت اصلی و تنظیمات پروژه‌های دیگر تغییر نمی‌کنند. `POST/PUT` و مسیرهای ناشناخته رد می‌شوند. نبود فایل یا اختلال دریافت منبع، خطای موقت می‌دهد و با صفحه جعلی موفقیت پوشانده نمی‌شود. غیرفعال‌کردن همین دو route، ترافیک را به Pages موجود برمی‌گرداند؛ routeهای سایر بخش‌ها را تغییر ندهید.

## نسخه کامل آینده

این انتشار معادل استقرار Django نیست. Cloudflare اکنون از Django در Python Workers پشتیبانی می‌کند، ولی backendهای D1/DO مستندشده برای Django تراکنش ندارند؛ نباید `transaction.atomic` برنامه را بی‌اثر کنیم. اتصال PostgreSQL و فایل‌های خصوصی باید جداگانه طراحی و آزموده شود. Containers نیز پلن پولی می‌خواهد و در این مرحله انتخاب نشده است. منابع بررسی‌شده:

- https://developers.cloudflare.com/workers/languages/python/packages/django/
- https://developers.cloudflare.com/hyperdrive/examples/python-workers/
- https://developers.cloudflare.com/containers/platform/pricing/
