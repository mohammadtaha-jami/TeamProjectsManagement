"""
seed.py — پر کردن Database با دادهٔ نمایشی (حدود ۵ آیتم در هر بخش)

Usage:
    python seed.py          # جایگزینی کامل داده‌ها
    python seed.py --merge  # فقط اگر فایل خالی باشد seed شود
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from json_store import write_list

# ── شناسه‌های ثابت برای ارجاع متقابل ─────────────────────────────────────

# دسته‌های اصلی (۵)
CAT_WEB = "a1000001-0000-4000-8000-000000000001"
CAT_SEO = "a1000002-0000-4000-8000-000000000002"
CAT_BRAND = "a1000003-0000-4000-8000-000000000003"
CAT_CONTENT = "a1000004-0000-4000-8000-000000000004"
CAT_SUPPORT = "a1000005-0000-4000-8000-000000000005"

# زیردسته‌ها (۵)
SUB_WP = "b2000001-0000-4000-8000-000000000001"
SUB_CUSTOM = "b2000002-0000-4000-8000-000000000002"
SUB_ONPAGE = "b2000003-0000-4000-8000-000000000003"
SUB_OFFPAGE = "b2000004-0000-4000-8000-000000000004"
SUB_LOGO = "b2000005-0000-4000-8000-000000000005"

# خدمات (۵)
SVC_WP = "c3000001-0000-4000-8000-000000000001"
SVC_REACT = "c3000002-0000-4000-8000-000000000002"
SVC_ONPAGE = "c3000003-0000-4000-8000-000000000003"
SVC_LOGO = "c3000004-0000-4000-8000-000000000004"
SVC_SUPPORT = "c3000005-0000-4000-8000-000000000005"

# پلن‌ها (۵)
PLN_STARTUP = "d4000001-0000-4000-8000-000000000001"
PLN_PRO = "d4000002-0000-4000-8000-000000000002"
PLN_CORP = "d4000003-0000-4000-8000-000000000003"
PLN_SEO = "d4000004-0000-4000-8000-000000000004"
PLN_BRAND = "d4000005-0000-4000-8000-000000000005"

# مشتریان (۵)
CUS_ALI = "e5000001-0000-4000-8000-000000000001"
CUS_SARA = "e5000002-0000-4000-8000-000000000002"
CUS_REZA = "e5000003-0000-4000-8000-000000000003"
CUS_MARYAM = "e5000004-0000-4000-8000-000000000004"
CUS_AMIR = "e5000005-0000-4000-8000-000000000005"

# سفارش‌های استاندارد (۵)
ORD_1 = "f6000001-0000-4000-8000-000000000001"
ORD_2 = "f6000002-0000-4000-8000-000000000002"
ORD_3 = "f6000003-0000-4000-8000-000000000003"
ORD_4 = "f6000004-0000-4000-8000-000000000004"
ORD_5 = "f6000005-0000-4000-8000-000000000005"

# سفارش‌های سفارشی (۵)
CORD_1 = "g7000001-0000-4000-8000-000000000001"
CORD_2 = "g7000002-0000-4000-8000-000000000002"
CORD_3 = "g7000003-0000-4000-8000-000000000003"
CORD_4 = "g7000004-0000-4000-8000-000000000004"
CORD_5 = "g7000005-0000-4000-8000-000000000005"


def _ts(days_ago: int = 0) -> str:
    return (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds")


def categories() -> list:
    return [
        {"id": CAT_WEB, "name": "طراحی و توسعه وب", "kind": "parent", "parent_id": None},
        {"id": CAT_SEO, "name": "سئو و دیجیتال مارکتینگ", "kind": "parent", "parent_id": None},
        {"id": CAT_BRAND, "name": "برندینگ و هویت بصری", "kind": "parent", "parent_id": None},
        {"id": CAT_CONTENT, "name": "تولید محتوا", "kind": "parent", "parent_id": None},
        {"id": CAT_SUPPORT, "name": "پشتیبانی و نگهداری", "kind": "parent", "parent_id": None},
        {"id": SUB_WP, "name": "وردپرس", "kind": "child", "parent_id": CAT_WEB},
        {"id": SUB_CUSTOM, "name": "اختصاصی (React / Laravel)", "kind": "child", "parent_id": CAT_WEB},
        {"id": SUB_ONPAGE, "name": "سئو On-Page", "kind": "child", "parent_id": CAT_SEO},
        {"id": SUB_OFFPAGE, "name": "سئو Off-Page", "kind": "child", "parent_id": CAT_SEO},
        {"id": SUB_LOGO, "name": "لوگو و ست هویت", "kind": "child", "parent_id": CAT_BRAND},
    ]


def services() -> list:
    return [
        {
            "id": SVC_WP,
            "name": "طراحی سایت وردپرسی شرکتی",
            "category_ids": [CAT_WEB, SUB_WP],
            "price": "15000000",
            "description": "",
            "terms": [
                "قالب پریمیوم با لایسنس",
                "تا ۸ صفحه محتوا",
                "ریسپانسیو موبایل و تبلت",
                "۱ ماه پشتیبانی رایگان",
            ],
            "extra_note": "مناسب کسب‌وکارهای کوچک و متوسط",
        },
        {
            "id": SVC_REACT,
            "name": "طراحی سایت اختصاصی React",
            "category_ids": [CAT_WEB, SUB_CUSTOM],
            "price": "45000000",
            "description": "",
            "terms": [
                "طراحی UI/UX اختصاصی",
                "فرانت React + API",
                "سرعت بالا و SEO-friendly",
                "۳ ماه پشتیبانی",
            ],
            "extra_note": "",
        },
        {
            "id": SVC_ONPAGE,
            "name": "بهینه‌سازی On-Page",
            "category_ids": [CAT_SEO, SUB_ONPAGE],
            "price": "8000000",
            "description": "",
            "terms": [
                "بررسی فنی سایت",
                "بهینه‌سازی متا و ساختار",
                "گزارش ماهانه",
            ],
            "extra_note": "برای سایت‌های موجود",
        },
        {
            "id": SVC_LOGO,
            "name": "طراحی لوگو و هویت بصری",
            "category_ids": [CAT_BRAND, SUB_LOGO],
            "price": "12000000",
            "description": "",
            "terms": [
                "۳ پیشنهاد اولیه",
                "۲ مرحله اصلاح",
                "تحویل فایل‌های Vector",
            ],
            "extra_note": "شامل راهنمای برند (Brand Guide)",
        },
        {
            "id": SVC_SUPPORT,
            "name": "پشتیبانی فنی ۳ ماهه",
            "category_ids": [CAT_SUPPORT],
            "price": "6000000",
            "description": "",
            "terms": [
                "رفع باگ و خطا",
                "بکاپ هفتگی",
                "پاسخگویی تلفنی",
            ],
            "extra_note": "",
        },
    ]


def plans() -> list:
    return [
        {
            "id": PLN_STARTUP,
            "name": "پلن استارتاپ",
            "category_ids": [],
            "service_ids": [SVC_WP],
            "price": "18000000",
            "terms": ["شامل دامنه و هاست ۱ ساله", "آموزش مدیریت سایت"],
            "extra_note": "بهترین گزینه برای شروع",
        },
        {
            "id": PLN_PRO,
            "name": "پلن حرفه‌ای (Business)",
            "category_ids": [],
            "service_ids": [SVC_WP, SVC_REACT, SVC_ONPAGE],
            "price": "55000000",
            "terms": ["طراحی + سئو پایه", "۶ ماه پشتیبانی"],
            "extra_note": "",
        },
        {
            "id": PLN_CORP,
            "name": "پلن سازمانی",
            "category_ids": [CAT_WEB],
            "service_ids": [SVC_REACT, SVC_SUPPORT],
            "price": "75000000",
            "terms": ["قرارداد SLA", "تیم اختصاصی"],
            "extra_note": "قابل مذاکره برای پروژه‌های بزرگ",
        },
        {
            "id": PLN_SEO,
            "name": "پلن سئو ۶ ماهه",
            "category_ids": [CAT_SEO],
            "service_ids": [SVC_ONPAGE],
            "price": "42000000",
            "terms": ["گزارش ماهانه", "لینک‌سازی هدفمند"],
            "extra_note": "",
        },
        {
            "id": PLN_BRAND,
            "name": "پلن برندینگ کامل",
            "category_ids": [],
            "service_ids": [SVC_LOGO],
            "price": "15000000",
            "terms": ["لوگو + کارت ویزیت + سربرگ"],
            "extra_note": "",
        },
    ]


def customers() -> list:
    return [
        {
            "id": CUS_ALI,
            "name": "علی محمدی",
            "phone": "09121234567",
            "address": "تهران، ونک، خیابان ملاصدرا",
        },
        {
            "id": CUS_SARA,
            "name": "سارا احمدی",
            "phone": "09351234567",
            "address": "مشهد، احمدآباد، پلاک ۱۲",
        },
        {
            "id": CUS_REZA,
            "name": "رضا کریمی",
            "phone": "09171234567",
            "address": "اصفهان، چهارباغ عباسی",
        },
        {
            "id": CUS_MARYAM,
            "name": "مریم حسینی",
            "phone": "09381234567",
            "address": "شیراز، معالی‌آباد",
        },
        {
            "id": CUS_AMIR,
            "name": "امیر رضایی",
            "phone": "09211234567",
            "address": "تبریز، ولیعصر",
        },
    ]


def orders() -> list:
    return [
        {
            "id": ORD_1,
            "created_at": _ts(10),
            "customer_id": CUS_ALI,
            "customer": {"name": "علی محمدی", "phone": "09121234567", "address": "تهران، ونک"},
            "plan_ids": [PLN_STARTUP],
            "service_ids": [],
            "services_detail": [
                {
                    "id": PLN_STARTUP,
                    "name": "پلن استارتاپ",
                    "price": "18000000",
                    "description": "",
                }
            ],
            "total_price": 18000000,
            "invoice_type": "current",
            "selected_plans_snapshot": [
                {
                    "id": PLN_STARTUP,
                    "name": "پلن استارتاپ",
                    "terms": ["شامل دامنه و هاست ۱ ساله", "آموزش مدیریت سایت"],
                    "extra_note": "بهترین گزینه برای شروع",
                }
            ],
        },
        {
            "id": ORD_2,
            "created_at": _ts(8),
            "customer_id": CUS_SARA,
            "customer": {"name": "سارا احمدی", "phone": "09351234567", "address": "مشهد"},
            "plan_ids": [],
            "service_ids": [SVC_REACT, SVC_ONPAGE],
            "services_detail": [
                {
                    "id": SVC_REACT,
                    "name": "طراحی سایت اختصاصی React",
                    "price": "45000000",
                    "description": "مفاد:\n- طراحی UI/UX اختصاصی\n- فرانت React + API",
                    "terms": ["طراحی UI/UX اختصاصی", "فرانت React + API"],
                    "extra_note": "",
                },
                {
                    "id": SVC_ONPAGE,
                    "name": "بهینه‌سازی On-Page",
                    "price": "8000000",
                    "description": "مفاد:\n- بررسی فنی سایت",
                    "terms": ["بررسی فنی سایت"],
                    "extra_note": "برای سایت‌های موجود",
                },
            ],
            "total_price": 53000000,
            "invoice_type": "current",
            "selected_plans_snapshot": [],
        },
        {
            "id": ORD_3,
            "created_at": _ts(5),
            "customer_id": CUS_REZA,
            "customer": {"name": "رضا کریمی", "phone": "09171234567", "address": "اصفهان"},
            "plan_ids": [PLN_PRO],
            "service_ids": [],
            "services_detail": [
                {"id": PLN_PRO, "name": "پلن حرفه‌ای (Business)", "price": "55000000", "description": ""}
            ],
            "total_price": 55000000,
            "invoice_type": "roadmap",
            "selected_plans_snapshot": [
                {
                    "id": PLN_PRO,
                    "name": "پلن حرفه‌ای (Business)",
                    "terms": ["طراحی + سئو پایه"],
                    "extra_note": "",
                }
            ],
        },
        {
            "id": ORD_4,
            "created_at": _ts(3),
            "customer_id": CUS_MARYAM,
            "customer": {"name": "مریم حسینی", "phone": "09381234567", "address": "شیراز"},
            "plan_ids": [],
            "service_ids": [SVC_LOGO],
            "services_detail": [
                {
                    "id": SVC_LOGO,
                    "name": "طراحی لوگو و هویت بصری",
                    "price": "12000000",
                    "description": "",
                    "terms": ["۳ پیشنهاد اولیه", "۲ مرحله اصلاح"],
                    "extra_note": "شامل راهنمای برند",
                }
            ],
            "total_price": 12000000,
            "invoice_type": "current",
            "selected_plans_snapshot": [],
        },
        {
            "id": ORD_5,
            "created_at": _ts(1),
            "customer_id": CUS_AMIR,
            "customer": {"name": "امیر رضایی", "phone": "09211234567", "address": "تبریز"},
            "plan_ids": [PLN_SEO],
            "service_ids": [SVC_SUPPORT],
            "services_detail": [
                {"id": PLN_SEO, "name": "پلن سئو ۶ ماهه", "price": "42000000", "description": ""},
                {
                    "id": SVC_SUPPORT,
                    "name": "پشتیبانی فنی ۳ ماهه",
                    "price": "6000000",
                    "description": "",
                    "terms": ["رفع باگ و خطا"],
                    "extra_note": "",
                },
            ],
            "total_price": 48000000,
            "invoice_type": "current",
            "selected_plans_snapshot": [
                {"id": PLN_SEO, "name": "پلن سئو ۶ ماهه", "terms": ["گزارش ماهانه"], "extra_note": ""}
            ],
        },
    ]


def custom_orders() -> list:
    return [
        {
            "id": CORD_1,
            "created_at": _ts(7),
            "customer_id": CUS_ALI,
            "customer": {"name": "علی محمدی", "phone": "09121234567", "address": "تهران"},
            "steps": [
                {
                    "title": "فاز اول",
                    "name": "طراحی UI",
                    "description_lines": ["وایرفریم", "طراحی صفحات اصلی"],
                    "price": "15000000",
                    "price_amount": 15000000,
                },
                {
                    "title": "فاز دوم",
                    "name": "توسعه فرانت",
                    "description_lines": ["React", "اتصال API"],
                    "price": "25000000",
                    "price_amount": 25000000,
                },
            ],
            "total_price": 40000000,
            "invoice_type": "roadmap",
        },
        {
            "id": CORD_2,
            "created_at": _ts(6),
            "customer_id": CUS_SARA,
            "customer": {"name": "سارا احمدی", "phone": "09351234567", "address": "مشهد"},
            "steps": [],
            "total_price": 8500000,
            "invoice_type": "simple",
            "simple_lines": [
                {
                    "name": "هاست سالانه",
                    "price": "2500000",
                    "unit_amount": 2500000,
                    "quantity": 1,
                    "description": "هاست پرسرعت",
                    "line_total": 2500000,
                },
                {
                    "name": "دامنه ir.",
                    "price": "600000",
                    "unit_amount": 600000,
                    "quantity": 1,
                    "description": "",
                    "line_total": 600000,
                },
                {
                    "name": "SSL",
                    "price": "5400000",
                    "unit_amount": 1800000,
                    "quantity": 3,
                    "description": "گواهی ۳ ساله",
                    "line_total": 5400000,
                },
            ],
        },
        {
            "id": CORD_3,
            "created_at": _ts(4),
            "customer_id": CUS_REZA,
            "customer": {"name": "رضا کریمی", "phone": "09171234567", "address": "اصفهان"},
            "steps": [],
            "total_price": 95000000,
            "invoice_type": "panel",
            "panel_plans": [
                {
                    "tier": "economic",
                    "price": "18000000",
                    "price_amount": 18000000,
                    "negotiable": False,
                    "services": [
                        {"name": "سایت وردپرسی ۵ صفحه", "service_id": SVC_WP},
                        {"name": "ریسپانسیو", "service_id": ""},
                        {"name": "فرم تماس", "service_id": ""},
                    ],
                },
                {
                    "tier": "gold",
                    "price": "55000000",
                    "price_amount": 55000000,
                    "negotiable": False,
                    "services": [
                        {"name": "طراحی UI/UX", "service_id": SVC_REACT},
                        {"name": "React SPA", "service_id": ""},
                        {"name": "سئو پایه", "service_id": SVC_ONPAGE},
                        {"name": "پشتیبانی ۶ ماه", "service_id": SVC_SUPPORT},
                    ],
                },
                {
                    "tier": "exclusive",
                    "price": "",
                    "price_amount": 0,
                    "negotiable": True,
                    "services": [
                        {"name": "تیم اختصاصی", "service_id": ""},
                        {"name": "معماری Enterprise", "service_id": ""},
                    ],
                },
            ],
        },
        {
            "id": CORD_4,
            "created_at": _ts(2),
            "customer_id": CUS_MARYAM,
            "customer": {"name": "مریم حسینی", "phone": "09381234567", "address": "شیراز"},
            "steps": [
                {
                    "title": "مرحله ۱",
                    "name": "تحقیق برند",
                    "description_lines": ["مصاحبه با ذینفعان", "تحلیل رقبا"],
                    "price": "5000000",
                    "price_amount": 5000000,
                },
                {
                    "title": "مرحله ۲",
                    "name": "طراحی هویت",
                    "description_lines": ["لوگو", "پالت رنگ", "تایپوگرافی"],
                    "price": "12000000",
                    "price_amount": 12000000,
                },
            ],
            "total_price": 17000000,
            "invoice_type": "current",
        },
        {
            "id": CORD_5,
            "created_at": _ts(0),
            "customer_id": CUS_AMIR,
            "customer": {"name": "امیر رضایی", "phone": "09211234567", "address": "تبریز"},
            "steps": [
                {
                    "title": "ماه اول",
                    "name": "تولید محتوا",
                    "description_lines": ["۱۰ مقاله وبلاگ", "۵ پست اینستاگرام"],
                    "price": "12000000",
                    "price_amount": 12000000,
                },
                {
                    "title": "ماه دوم",
                    "name": "سئو محتوا",
                    "description_lines": ["بهینه‌سازی مقالات", "لینک‌سازی داخلی"],
                    "price": "8000000",
                    "price_amount": 8000000,
                },
            ],
            "total_price": 20000000,
            "invoice_type": "roadmap",
        },
    ]


DATASETS: dict[str, callable] = {
    "categories": categories,
    "services": services,
    "plans": plans,
    "customers": customers,
    "orders": orders,
    "custom-order": custom_orders,
}


def run_seed(*, merge: bool = False) -> None:
    from json_store import read_list

    for key, builder in DATASETS.items():
        items = builder()
        if merge:
            existing = read_list(key)
            if existing:
                print(f"  skip {key}: {len(existing)} existing rows")
                continue
        write_list(key, items)
        print(f"  ok {key}: {len(items)} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data for TeamProjectsManagement")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Only seed empty JSON files; keep existing data",
    )
    args = parser.parse_args()

    mode = "merge" if args.merge else "replace"
    print(f"[seed] mode={mode}")
    run_seed(merge=args.merge)
    print("[seed] done.")
    print("  order page: http://127.0.0.1:5000/")
    print("  admin:      http://127.0.0.1:5000/modir")


if __name__ == "__main__":
    main()
