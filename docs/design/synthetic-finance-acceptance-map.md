# نگاشت پذیرش دادهٔ مالی v1 به آزمون‌ها

مبنا: بندهای ۱ تا ۱۰ بخش ۵ سند [طرح داده و شاخص‌ها](synthetic-finance-data-and-metrics-v1.md). نام‌ها به توابع `backend/tests/test_demo_finance_reconciliation.py` اشاره دارند.

| بند | آزمون موجود | پوشش و تکمیل این نوبت |
| --- | --- | --- |
| ۱. پایداری seed | `test_seed_is_stable_across_two_postgresql_databases` | دو دیتابیس، snapshot برابر، ۳۶ سطر، نسخه و اجرای دوباره بدون درج. |
| ۲. سطر به ماه | `test_line_to_month_and_month_to_quarter`، `test_return_reverses_july_item_in_august_and_cannot_overreturn`، `test_correction_is_recognized_in_september_not_june` | شش جمع خام ماهانه و مقادیر منفی برگشت/مثبت اصلاح به‌صورت جداگانه. |
| ۳. ماه به فصل | `test_line_to_month_and_month_to_quarter` | دو فصل، جمع ماه‌ها و جمع خام شش ماه. |
| ۴. پل سود | `test_profit_bridge_reconciles_with_expense_drivers` | دو معادلهٔ پل و تغییر دسته‌های هزینه. |
| ۵. برگشت بین‌ماه | `test_return_reverses_july_item_in_august_and_cannot_overreturn` | منبع، مقدار/مبلغ، منع برگشت بیش از فروش و ثابت‌ماندن رقم ژوئیه. |
| ۶. اصلاح بین‌فصل | `test_correction_is_recognized_in_september_not_june` | ارجاع سطرها، ثابت‌ماندن ژوئن/Q2 و محاسبهٔ سپتامبر بدون اصلاح با حذف آن از query آزمایشی. سند posted حذف نمی‌شود. |
| ۷. وضعیت و یکتایی | `test_status_pairing_uniqueness_sources_and_posted_immutability` | draft، یکتایی، bucket/category، نامتغیربودن posted و منبع ناهم‌bucket. **تکمیل:** منبع ناموجود نیز صریحاً رد می‌شود. |
| ۸. drill-down | `test_drilldown_reconciles_categories_centers_and_source_rows` | **تکمیل:** تطبیق سطر، دسته و مرکز برای هر شش ماه و هر دو فصل؛ OPEX Q3 و شناسه‌های منبع. API فیلترشده فقط جمع bucket را نام‌گذاری می‌کند، نه سود مرکز. |
| ۹. صفر و دادهٔ غایب | `test_incomplete_coverage_zero_missing_and_tehran_boundary` | پوشش ناقص/غایب، صفر تأییدشده و مرز زمانی تهران. |
| ۱۰. سناریوی فرضی | `test_shipping_what_if_is_separate_from_observed_data` | سود مدل‌شده و واقعی جدا. **تکمیل:** پل سود پیش و پس از سناریو برابر است. |

انتظارهای پولی آزمون‌ها ثابت و مستقل از تابع seed هستند. اجرای این نگاشت به دو دیتابیس محلی اختصاصی PostgreSQL نیاز دارد.
