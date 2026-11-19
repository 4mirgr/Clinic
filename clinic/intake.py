"""Patient-reported information, distinct from the physician's clinical record."""
INTAKE_FIELDS = [
 ('reported_current_problem','مشکل یا علامت فعلی',6000),
 ('reported_onset','زمان شروع و روند علائم',2000),
 ('reported_history','بیماری‌های قبلی و زمینه‌ای',10000),
 ('reported_surgeries','عمل جراحی و بستری قبلی',5000),
 ('reported_family_history','سابقه بیماری در خانواده',5000),
 ('reported_medications','داروهای مصرفی و مقدار مصرف',5000),
 ('reported_supplements','مکمل‌ها و داروهای بدون نسخه',3000),
 ('reported_allergies','حساسیت و نوع واکنش',5000),
 ('reported_social_history','سبک زندگی و مواجهه‌ها',5000),
]
