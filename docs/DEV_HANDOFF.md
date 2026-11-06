# انتقال کار — G0-r1

تاریخ ۱۵ آبان ۱۴۰۵؛ **status: waiting_for_owner**. G0 نمونهٔ اجرایی و ZIP دارد؛ تأیید مالک هنوز دریافت نشده. هیچ M1 یا مرحلهٔ بعدی شروع نشده است.

## قرارداد جاری
PRD فایل تاریخی PKL_PRD_v3_11_Production.md با محتوای ۳٫۱۲. همهٔ صوت و بکاپ/بازیابی فقط G5-پایانی؛ از کد G0 حذف شده‌اند. ذخیرهٔ SQLite، بازگشایی، کنترل دو تب و پیش‌نویس داخل تب در G0 فعال‌اند. مرور واقعی و Undo زمان‌بندی هنوز پیاده نشده‌اند؛ دکمه‌های نتیجه صرفاً پیش‌نمایش‌اند.

## خروجی و منبع
بسته: dist/MyStudySystem-G0-r1-win.zip؛ هش: فایل هم‌نام .sha256؛ مشخصهٔ منبع و اعضای بسته: BUILD_MANIFEST.json داخل ZIP. خلاصهٔ نهایی: dist/RELEASE.json. به درخواست صریح مالک، Git این پوشه به تاریخچهٔ مخزن mehghasemi/MyStudySystem متصل شد و انتشار اولیهٔ G0-r1 آماده شد. مرجع انتشار: https://github.com/mehghasemi/MyStudySystem/releases/tag/G0-r1 . فایل ZIP همان خروجی آزموده‌شده است؛ تغییرات این انتشار فقط راهنما و اطلاعات GitHub هستند.

## نقشهٔ کد
- app/store.py: schema 2، notes/sources/highlights/settings/operations، ذخیرهٔ idempotent و seed صریح. هیچ backup/migration ندارد. دیتابیس داخل ZIP نیست.
- app/main.py: قفل تک‌نویسنده، loopback، Host/Origin/CSRF، static allowlist، هماهنگی تب‌ها و خروج.
- app/static: سه نما، UI مشترک، جست‌وجو و تقویم. منبع طراحی و معماری در ARCHITECTURE و ADR 002.
- scripts/Launcher.cs و build.py: راه‌انداز C# با .NET ویندوز و Python ایزوله همراه بسته؛ قفل ابزارها در toolchain.lock.json. PyInstaller نصب نشد و استفاده نمی‌شود؛ Node فقط ابزار آزمون است.
- tests/test_store.py، browser.cjs، quality.cjs و package_lifecycle.py: شواهد واقعی پایین. آزمون‌های F1 فقط در F1_TRACEABILITY نگاشت شده‌اند؛ ماژول آینده ساخته نشده.

## فرمان‌ها و نتیجهٔ واقعی
از ریشه در PowerShell:
`python -X utf8 -m unittest discover -s tests -v` → ۱۵ پاس.
`node tests/browser.cjs` → ۱۷ پاس.
`node tests/browser.cjs <EXE استخراج‌شده>` → ۱۷ پاس.
`node tests/quality.cjs` → ۹ پاس؛ PDF مصنوعی از Chrome و استخراج pypdf محیط، نه دادهٔ مالک.
`python -X utf8 scripts/build.py` → ZIP، manifest و SHA-256.
`python -X utf8 tests/package_lifecycle.py` → ۷ پاس؛ PATH بدون Python، cwd متفاوت، app/data و خطاهای واقعی فایل.
جزئیات ردیف‌ها و موارد دستی باز در TEST_MATRIX؛ گزارش‌های JSON و تصاویر در docs/evidence. پس از تغییر سازندهٔ ZIP، بررسی عضویت دقیق allowlist و چرخهٔ بسته باید روی ZIP نهایی اجرا شود؛ نتیجهٔ نهایی package-lifecycle.json و RELEASE.json مرجع‌اند.

## ایرادهای رفع‌شده و موارد باز
فوکوس Tab از تقویم خارج می‌شد؛ focus trap صریح اضافه شد. تازه‌سازی نشانگر انتخاب گزیده را پاک می‌کرد؛ DOM متن ثابت بی‌جهت بازنویسی نمی‌شود. container queries چیدمان زوم را اصلاح کردند. هر دو مسیر در منبع و بسته بازآزمایی شدند.
موارد باز: Narrator واقعی، حساب Windows تازه/دستگاه دوم، زوم واقعی تنظیمات مرورگر، SmartScreen فایل دانلودی و Copy دستی از PDF viewer. fallback قلم و بزرگ‌نمایی شبیه‌سازی شده‌اند؛ ادعای قبولی موارد باز نشود. پیش‌نویس ذخیره‌نشده در crash تضمین ندارد و بسته ابزار بازیابی ندارد. شرح دقیق در evidence/known-findings.md.

## ادامه
منتظر بازخورد مالک بمانید. گزارش ایراد فقط اصلاح همین G0 و ساخت r2 را مجاز می‌کند. مرحلهٔ M1-الف یا هر نوبت بعدی فقط پس از درخواست صریح مالک. برای اصلاح ابتدا ردیف TEST_MATRIX، مالک کد در ARCHITECTURE و کوچک‌ترین نمونهٔ بازتولید را بخوانید؛ از بازخوانی کل PRD خودداری کنید. دادهٔ واقعی یا DB شخصی به زمینهٔ مدل وارد نشود. هیچ زمان‌بندی ادامه فعال نشده است.
