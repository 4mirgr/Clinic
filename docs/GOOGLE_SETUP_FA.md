# راه‌اندازی گوگل با حفظ حساب مشترک — ۲۲ نوامبر ۲۰۲۶

کاربر فقط یک حساب دارد: مرجع مشترک موجود `upwbktvnybsjugdegjji` در Supabase Auth. ثبت‌نام از آدرس سایت یا ورودی کلینیک باید به همین مرجع برسد؛ حساب یا رمز دوم ساخته نمی‌شود. در حالت مشترک، ورود محلی مستقل Django فعال نمی‌شود. اتصال تقویم، اجازه مدیریت رویدادهای **پزشک** است و از بیمار چنین اجازه‌ای گرفته نمی‌شود.

## نتیجه بررسی واقعی

- پس از درخواست دوبارهٔ دسترسی، ابزار Google Calendar این گفتگو حساب `dr.gerami.md@gmail.com` و تقویم اصلی با نقش owner را دید؛ FreeBusy هم موفق بود.
- با درخواست صریح مالک، رویداد خصوصی یک‌دقیقه‌ای «آزمایش اتصال کلینیک» برای ۲۳ نوامبر ۱۲:۰۰ تهران ساخته، عنوانش ویرایش، دوباره خوانده و سپس حذف شد. مهمان بیرونی یا یادآور نداشت. رویداد آزمایشی باقی نماند.
- endpoint عمومی تنظیمات Auth مشترک در همین تاریخ: `google=false`، `email=true`، ثبت‌نام مجاز. بنابراین ورود گوگل سایت هنوز در آن مرجع فعال نیست. این نتیجه وجود یا نبود OAuth Client در Google Cloud مالک را ثابت نمی‌کند.
- backend خصوصی کلینیک، OAuth مخصوص آن و scheduler روی دامنه فعال نیستند. اتصال موفق ابزار گفتگو، اعتبارنامه قابل انتقال به کد پنل ایجاد نمی‌کند؛ پنل Client و توکن اختصاصی خودش را لازم دارد.

## اقدام دقیق مالک در حساب خودش

۱. [Clients در Google Auth Platform](https://console.cloud.google.com/auth/clients) را با حساب پزشکی باز کنید و ابتدا پروژه‌های موجود را بررسی کنید. اگر Client از نوع **Web application** دارید، همان پروژه قابل استفاده است؛ قبل از بررسی، پروژه تکراری نسازید. اگر ندارید، پروژه/Client مناسب بسازید. برای این مرحله Billing یا سرویس پولی فعال نکنید.

۲. Branding/Audience را برای `drgerami-md.ir` تکمیل کنید؛ برای تست، حساب پزشکی را Test user قرار دهید. [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) در همان پروژه باید فعال شود. ورود عمومی سایت فقط OpenID/email/profile می‌خواهد؛ scopeهای تقویم در درخواست جداگانهٔ مدیر پنل خواسته می‌شوند. الزامات انتشار/verification گوگل باید در خود کنسول بررسی شوند؛ حالت Testing ممکن است refresh token کوتاه‌عمر داشته باشد.

۳. callbackها دو کاربرد دارند:

| کاربرد | URI دقیق |
| --- | --- |
| ورود مشترک سایت و کلینیک از Supabase | `https://upwbktvnybsjugdegjji.supabase.co/auth/v1/callback` |
| اتصال تقویم در backend خصوصی فعلی Django | `https://drgerami-md.ir/dash/calendar/oauth/callback/` |

Origin سایت: `https://drgerami-md.ir`. یک Web Client می‌تواند URIهای مجاز لازم را داشته باشد؛ Client جدا در همان پروژه هم ممکن است. تعداد Clientها، تعداد حساب کاربران نیست. URI تقویم تنها پس از استقرار backend و ingress واقعی جواب می‌دهد؛ پیش‌نمایش `/clinic/` callback پزشکی اجرا نمی‌کند.

۴. Client ID و Secret مربوط به ورود را **مستقیم** در [Google provider همان پروژه موجود](https://supabase.com/dashboard/project/upwbktvnybsjugdegjji/auth/providers) وارد و Google را فعال کنید. ثبت‌نام و نقش‌های موجود را حفظ کنید. در [URL configuration](https://supabase.com/dashboard/project/upwbktvnybsjugdegjji/auth/url-configuration)، callback سایت `https://drgerami-md.ir/api/account/callback?flow=*` را کنار URLهای قبلی IntMed نگه دارید؛ آن‌ها را جایگزین نکنید. Secret در چت، Git یا کد مرورگر قرار نگیرد.

۵. پس از آماده‌شدن backend خصوصی، در secret manager میزبان مقادیر Calendar تنظیم شوند: `GOOGLE_CLIENT_ID`، `GOOGLE_CLIENT_SECRET`، `GOOGLE_TOKEN_ENCRYPTION_KEY` مستقل Fernet، `GOOGLE_REDIRECT_URI` مطابق جدول و `GOOGLE_CALENDAR_ACCOUNT=dr.gerami.md@gmail.com`. کلید رمزنگاری تولید و همراه برنامه پشتیبان‌گیری اسرار شود؛ توکن موجود با کلید تصادفی تازه باز نمی‌شود. این مقادیر از اتصال ابزار گفتگو قابل استخراج نیستند.

۶. اجرای خصوصی باید همان origin و `/dash/`، دیتابیس/مدارک خصوصی و cookie/CSRF درست داشته باشد. حالت مشترک و اتصال حساب‌های قدیمی فقط طبق [قرارداد هویت](SHARED_SUPABASE_IDENTITY.md) و [ابزار اتصال صریح](IDENTITY_BINDING.md) فعال شوند. بیماران ثبت‌نام دوم ندارند و پرونده قدیمی با ایمیل یا کد ملی حدس زده نمی‌شود.

۷. مدیر وارد صفحه تقویم شود، «اتصال حساب گوگل» را بزند، حساب پزشکی و مجوزها را در صفحه رسمی Google تأیید کند. ابتدا `python manage.py check_calendar` و سپس `python manage.py check_calendar --probe` اجرا شود. probe فقط یک بازه آینده را می‌خواند؛ ثبت/ویرایش واقعی پنل هنوز به آزمایش کنترل‌شده روی همان backend نیاز دارد.

۸. روزها، ساعات مطب و مدت ویزیت را خود پزشک تعیین کند. retry و تطبیق طبق [OPERATIONS.md](OPERATIONS.md) زمان‌بندی شوند. انتخاب قطعی مالک: تغییر زمان/حذف رویدادهای متعلق به پنل در Google خودکار وارد پنل شود؛ رویدادهای شخصی وارد پرونده نمی‌شوند و تداخل با نوبت دیگر برای بررسی پزشک نگه داشته می‌شود.
