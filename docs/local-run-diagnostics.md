# Local run diagnostics — 2026-10-18

این گزارش مربوط به محیط اجرای محدود همین نشست است. تنظیمات سراسری Windows، شبکه یا Docker تغییر نکرد.

## Docker

- `docker context show`: `desktop-linux`
- `whoami /groups`: عضویت `DESKTOP-0O54QL3\docker-users` فعال است.
- پردازش‌های `Docker Desktop` و `com.docker.backend` فعال‌اند. سرویس `com.docker.service` در وضعیت `Stopped / Disabled` است.
- `docker info`: `open //./pipe/dockerDesktopLinuxEngine: Access is denied.`
- `docker -H npipe:////./pipe/docker_engine info`: `open //./pipe/docker_engine: Access is denied.`
- `docker desktop status`: ایجاد فایل log در `%LOCALAPPDATA%\Docker\log\host` با `Access is denied` متوقف شد. با انتقال موقت `LOCALAPPDATA` به داخل پروژه نیز وضعیت Docker قابل دریافت نبود.
- `docker compose --env-file .env.example config --quiet`: موفق.
- `docker compose up --build -d` با متغیرهای نمونهٔ موقت: پیش از build تصویر با `open //./pipe/dockerDesktopLinuxEngine: Access is denied` متوقف شد.

نتیجه: دسترسی این محیط به pipe موتور Docker و مسیر log فراهم نیست. چون حساب عضو `docker-users` است، کمبود عضویت گروه علت اثبات‌شده نیست. وضعیت دسترسی Docker در PowerShell عادی کاربر باید جدا بررسی شود.

## npm و Vite

- `npm config get offline`: `true` از `NPM_CONFIG_OFFLINE=true`.
- `HTTP_PROXY`، `HTTPS_PROXY` و `ALL_PROXY`: همگی `http://127.0.0.1:9`.
- `npm ping` با تغییر فقط `NPM_CONFIG_OFFLINE=false` در همان فرایند: `ECONNREFUSED 127.0.0.1:9`.
- `npm ping` پس از حذف موقت سه proxy در همان فرایند: `PONG 3853ms`.
- `npm ci` با شبکهٔ باز: در lifecycle script با `Error: spawn EPERM` متوقف شد.
- `node -e` با `child_process.spawnSync` برای `node.exe` و `cmd.exe`: هر دو `EPERM`؛ پس خطا محدود به Vite یا esbuild نیست.
- `npm ci --ignore-scripts`: `added 71 packages in 9s`.
- `npm run build`: موفق؛ TypeScript و Vite، 27 module، خروجی `dist/assets/index-8i-KQlT3.js` با اندازهٔ 224.39 kB.
- `npm run dev`: بارگذاری تنظیم Vite در `esbuild` با `Error: spawn EPERM` متوقف شد.

نتیجه: تنظیم‌های محیطی مانع دریافت بسته‌ها بودند و در همان فرایند اصلاح شدند. محدودیت ایجاد پردازش فرزند در برخی فرمان‌های این محیط باقی است؛ تغییر امنیت Windows انجام نشد.

## اجرای میزبان، بدون Docker

PostgreSQL 18 موقت روی `127.0.0.1:55432`، FastAPI روی `127.0.0.1:8000` و خروجی build frontend از وب‌سرور ساده روی `127.0.0.1:5173` اجرا شدند:

- frontend `/`: HTTP 200، عنوان درست
- فایل JavaScript: HTTP 200، 224394 bytes
- API `/health`: `{"status":"ok"}`
- API `/ready`: `{"status":"ready"}` با اتصال واقعی PostgreSQL

این بررسی، مسیر Docker و proxy داخل Nginx را تأیید نمی‌کند. سرویس‌های موقت پس از بررسی متوقف شدند.
