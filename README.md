# ViraData Intelligence Dashboard Demo

## راه‌اندازی روی سیستم تازه

```powershell
git clone https://github.com/Arashkazemii/Intelligence-Dashboard---Demo.git
cd Intelligence-Dashboard---Demo
Copy-Item .env.example .env
# مقدار POSTGRES_PASSWORD را در .env برای همین سیستم تنظیم کنید.
docker compose up --build -d
docker compose exec api python -m app.demo_finance.seed --apply
```

داشبورد در `http://127.0.0.1:8080/` در دسترس است. فایل `.env` و داده‌های volume محلی منتقل نمی‌شوند؛ روی هر سیستم، `.env` را دوباره بسازید و دادهٔ نمایشی را با `schema.sql` و دستور seed بالا بازسازی کنید.

## رابط نمایشی

رابط `frontend` صفحهٔ شروع فارسی، گزارش مالی مبتنی بر API، جزئیات سطرها و نمای پرسش آزاد دارد. پرسش آزاد پس از تنظیم سرویس مدل فعال می‌شود.

با اجرای `docker compose up --build -d`، صفحه در `http://127.0.0.1:8080/` باز می‌شود. برای توسعه، API را روی `127.0.0.1:8000` و سپس `npm run dev` را در پوشهٔ `frontend` اجرا کنید؛ صفحه در `http://127.0.0.1:5173/` باز می‌شود. دادهٔ مالی باید پیش‌تر طبق راهنمای seed موجود نصب شده باشد. مسیرهای `/api/*` در Vite و Nginx با همان پیشوند به FastAPI فرستاده می‌شوند.

پایهٔ محلی دمو: React/TypeScript، FastAPI، PostgreSQL و Docker Compose. دادهٔ مالی ساختگی و API فقط‌خواندنی سناریوی Q2/Q3 ۲۰۲۶ آماده‌اند. تحلیل پرسش با مدل قابل پیکربندی است؛ ورود کاربر و استقرار سرور در این مرحله نیست.

## پیش‌نیازها در Windows

- Docker Desktop با Linux containers فعال
- برای اجرای جداگانه: Node.js 22، Python 3.11 یا بالاتر، PostgreSQL 16 یا بالاتر

## اجرای Docker (PowerShell)

```powershell
Copy-Item .env.example .env
# مقدار POSTGRES_PASSWORD را در .env برای سیستم خود عوض کنید.
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

صفحهٔ سادهٔ frontend در `http://127.0.0.1:8080` است. `/health` زنده بودن API را نشان می‌دهد. `/ready` اتصال واقعی به PostgreSQL را نیز بررسی می‌کند. `docker compose down` سرویس‌ها را می‌بندد و دادهٔ PostgreSQL را نگه می‌دارد.

## اجرای جداگانه در Windows

PostgreSQL را اجرا و پایگاه داده/کاربر مطابق `.env` ایجاد کنید. در اجرای جداگانه، پورت معمول PostgreSQL برابر 5432 است؛ پورت 5433 در `.env.example` برای جلوگیری از تداخل با PostgreSQL نصب‌شده روی میزبان انتخاب شده است. سپس:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:DATABASE_URL = 'postgresql://viradata_demo:<local-password>@127.0.0.1:5432/viradata_demo'
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

در PowerShell دوم:

```powershell
cd frontend
npm ci
npm run dev
```

صفحهٔ توسعه در `http://127.0.0.1:5173` است. Vite درخواست‌های `/api/*` را به API محلی می‌فرستد.

## بررسی ساخت

```powershell
cd frontend
npm ci
npm run build
```

اگر `npm ci` در یک PowerShell محدود با `ENOTCACHED` یا اتصال به `127.0.0.1:9` متوقف شد، ابتدا `npm config get offline` و متغیرهای `HTTP_PROXY`، `HTTPS_PROXY` و `ALL_PROXY` را بررسی کنید. فقط اگر این تنظیم‌ها برای اتصال شما لازم نیستند، در همان PowerShell اجرا کنید:

```powershell
$env:NPM_CONFIG_OFFLINE = 'false'
Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY -ErrorAction SilentlyContinue
npm ci
```

نتیجهٔ بررسی این سیستم و محدودیت دسترسی Docker در [docs/local-run-diagnostics.md](docs/local-run-diagnostics.md) ثبت شده است.

فایل `.env` در Git نادیده گرفته می‌شود. مقادیر `.env.example` صرفاً نمونه‌اند؛ برای VPS رمز جداگانه و تنظیمات شبکه/HTTPS لازم است.

## API دادهٔ مالی نمایشی

API فقط پس از نصب دستی [schema و seed](docs/design/synthetic-finance-implementation-notes.md) روی دیتابیس انتخاب‌شده، پاسخ دادهٔ مالی می‌دهد. راه‌اندازی FastAPI هیچ داده‌ای درج یا حذف نمی‌کند.

```powershell
cd backend
$env:DATABASE_URL = 'postgresql://USER:PASSWORD@127.0.0.1:PORT/DB_NAME'
python -m app.demo_finance.seed --apply
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`GET /api/demo-finance/q2-q3-2026` شاخص‌های Q2/Q3، تغییرات، روند ماهانه، پل سود، هزینه‌های Q3 و سطرهای منبع را برمی‌گرداند. `GET /api/demo-finance/lines?period=q3&bucket=OPEX&category_id=shipping` سطرهای فیلترشده و **جمع همان bucket** را می‌دهد؛ این جمع سود مرکز یا دسته نام‌گذاری نمی‌شود. مبلغ‌ها رشتهٔ ده‌دهیِ دقیق بر حسب تومان ساختگی‌اند. `coverage=missing` یعنی مبلغ `null` است، نه صفر. [نگاشت بندهای پذیرش](docs/design/synthetic-finance-acceptance-map.md) و آزمون‌های PostgreSQL در اسناد پروژه‌اند.

برای اجرای آزمون‌ها، سه دیتابیس محلی اختصاصی با نام‌های `viradata_finance_test_a`، `viradata_finance_test_b` و `viradata_finance_test_api` بسازید. از پوشهٔ `backend`، `requirements-dev.txt` را نصب کنید، `TEST_DATABASE_URL`، `TEST_DATABASE_URL_SECONDARY` و `TEST_API_DATABASE_URL` را به ترتیب روی آن‌ها تنظیم کنید، سپس `python -m pytest -q tests/test_demo_finance_reconciliation.py tests/test_demo_finance_api.py` را اجرا کنید. آزمون‌ها دیتابیس‌ها را حذف نمی‌کنند.

## تصمیم‌های باز مرحلهٔ بعد

- روش هویت و نشست کاربر و نحوهٔ ایجاد حساب
- قالب و منبع دادهٔ کاملاً ساختگی و حد مجاز سؤال‌ها
- معماری اجرای تحلیل و گزارش تعاملی، پس از دریافت اسناد AI Copilot
# پرسش فارسی از دادهٔ مالی نمایشی

گزارش ثابت Q2/Q3 بدون مدل کار می‌کند. برای پرسش آزاد، در محیط backend سه متغیر زیر را تنظیم کنید:

```env
FINANCE_LLM_BASE_URL=https://your-compatible-service.example/v1
FINANCE_LLM_MODEL=your-model-name
FINANCE_LLM_API_KEY=your-key
```

نشانی باید HTTPS یا localhost باشد. سرویس باید `POST /chat/completions` و `response_format: json_object` را پشتیبانی کند. مدل فقط طرح ساختاریافتهٔ پرسش را برمی‌گرداند؛ API عددها را از محاسبات مالی موجود و سطرهای ثبت‌شده می‌خواند. کلید فقط در backend استفاده می‌شود. `GET /api/demo-finance/question-capability` وضعیت فعال‌سازی و catalog را برمی‌گرداند.

```http
POST /api/demo-finance/question
Content-Type: application/json

{"question":"چرا سود فصل سوم کمتر شد؟"}
```

پاسخ موفق شامل `status=answered`، `layout` (`overview` یا `focus`)، `widgets` محدود به `kpis`, `card`, `trend`, `comparison`, `bridge`, `expense_mix`، `values` با دوره، واحد، پوشش و `line_ids`، مسیرهای `drilldowns`، شناسه و نسخهٔ dataset و در صورت نیاز `report` و `insights` است. مدل فقط `intent`, `metrics`, `periods`, `category`, `view` را انتخاب می‌کند. backend چیدمان، مبلغ‌ها و insight تطبیق سود را از دادهٔ تأییدشده می‌سازد؛ SQL، متن تحلیلی و عدد تولیدشده توسط مدل استفاده نمی‌شود. نمای کلی پنج بخش دارد و پرسش ساده فقط کارت مرتبط را نشان می‌دهد.

فقط دوره‌های `q2`, `q3` و ماه‌های `2026-04` تا `2026-09` و شاخص‌های درآمد، بهای کالا، هزینهٔ عملیاتی و سود عملیاتی پشتیبانی می‌شوند. فیلتر دستهٔ هزینهٔ عملیاتی به حمل، حقوق و اداری محدود است. برای دوره یا فیلد ناموجود، پاسخ `data_unavailable` بدون عدد ساختگی برمی‌گردد. `coverage=missing` صفر تلقی نمی‌شود. مبلغ دقیق در API رشتهٔ تومان ساختگی است و UI آن را به میلیارد تومان ساختگی تبدیل می‌کند. insight پل سود تجزیهٔ حسابداری است و علت تجاری واقعی را اثبات نمی‌کند. پاسخ نامعتبر مدل خطای ۵۰۲ و گزینهٔ تلاش دوباره دارد؛ فقط نوع خطا، بدون متن پاسخ یا کلید، در لاگ ثبت می‌شود.
