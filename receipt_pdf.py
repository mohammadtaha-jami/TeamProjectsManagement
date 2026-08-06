from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import arabic_reshaper
from bidi.algorithm import get_display
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from json_store import parse_price_amount


def _register_font() -> str:
    project_root = Path(__file__).resolve().parent
    candidates = [
        project_root / "assets" / "fonts" / "Dana-Black.ttf",
        project_root / "assetes" / "fonts" / "Dana-Black.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]
    for font_path in candidates:
        if font_path.exists():
            font_name = f"receipt-{font_path.stem}"
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                return font_name
            except Exception:
                continue
    return "Helvetica"


def _fa_shape(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def _fa_digits(value: str) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _safe_text(value: str | None, fallback: str = "-") -> str:
    text = (value or "").strip()
    return text if text else fallback


def _money(value: int) -> str:
    return _fa_digits(f"{value:,}") + " تومان"


def _wrap_long_html(
    raw: str | None,
    *,
    line_chars: int = 80,
    threshold: int = 100,
) -> str:
    """
    اگر طول متن از threshold بیشتر بود، هر line_chars کاراکتر یک بار شکسته می‌شود
    و با <br/> برای Paragraph به خط بعد می‌رود (ارتفاع ردیف جدول با تعداد خط هم‌خوان می‌شود).
    """
    text = (raw or "").strip()
    if not text:
        return _fa_shape(escape("-"))
    esc = escape(text)
    if len(text) <= threshold:
        return _fa_shape(esc)
    parts: list[str] = []
    for i in range(0, len(text), line_chars):
        chunk = text[i : i + line_chars]
        parts.append(_fa_shape(escape(chunk)))
    return "<br/>".join(parts)


def _cell_paragraph(text: str | None, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_wrap_long_html(text), style)


def _service_details_html(row: dict) -> str:
    terms = [x.strip() for x in (row.get("terms") or []) if isinstance(x, str) and x.strip()]
    extra_note = (row.get("extra_note") or "").strip()
    # fallback for legacy rows that only have plain description text
    if not terms and not extra_note:
        raw_desc = (row.get("description") or "").strip()
        if not raw_desc:
            return _fa_shape("-")
        lines = [x.strip() for x in raw_desc.splitlines() if x.strip()]
        return "<br/>".join(_fa_shape(escape(x)) for x in lines) if lines else _fa_shape(escape(raw_desc))

    detail_lines: list[str] = []
    if terms:
        detail_lines.append(_fa_shape("مفاد:"))
        detail_lines.extend(_fa_shape("• " + escape(term)) for term in terms)
    if extra_note:
        detail_lines.append(_fa_shape("توضیحات تکمیلی:"))
        detail_lines.append(_fa_shape(escape(extra_note)))
    return "<br/>".join(detail_lines) if detail_lines else _fa_shape("-")


def create_receipt_pdf(
    *,
    order_id: str,
    customer_snapshot: dict,
    services_detail: list[dict],
    total_amount: int,
    selected_plans: list[dict] | None = None,
    simple: bool = False,
) -> str:
    output_dir = Path(__file__).resolve().parent / "reciept"
    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / f"invoice-{order_id}.pdf"
    font_name = _register_font()

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=18,
        leading=22,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0f172a"),
    )
    normal_style = ParagraphStyle(
        "InvoiceNormal",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#1e293b"),
    )
    hint_style = ParagraphStyle(
        "InvoiceHint",
        parent=normal_style,
        fontSize=9,
        textColor=colors.HexColor("#475569"),
    )

    # سلول‌های جدول مشتری (مقدار در ستون ۰ — پهن)
    customer_value_style = ParagraphStyle(
        "CustVal",
        fontName=font_name,
        fontSize=10,
        leading=14,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#1e293b"),
    )
    # سلول جدول خدمات (قیمت + نام)
    service_body_style = ParagraphStyle(
        "SvcBody",
        fontName=font_name,
        fontSize=10,
        leading=14,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#1e293b"),
    )
    service_total_style = ParagraphStyle(
        "SvcTotal",
        parent=service_body_style,
        textColor=colors.HexColor("#166534"),
        fontName=font_name,
    )
    # جدول توضیحات: توضیح پهن‌تر، نام خدمت باریک‌تر
    desc_wide_style = ParagraphStyle(
        "DescWide",
        fontName=font_name,
        fontSize=9.5,
        leading=12.5,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#1e293b"),
    )
    desc_name_style = ParagraphStyle(
        "DescName",
        fontName=font_name,
        fontSize=9.5,
        leading=12.5,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#334155"),
    )

    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Invoice {order_id}",
    )

    # عرض مفید همان فریم سند (هم‌خوان با left/right margin بالا)
    inner_w = doc.width
    # مشتری: مقدار | برچسب
    cw_val = inner_w * 0.78
    cw_lbl = inner_w * 0.22
    # خدمات: قیمت (باریک) | نام خدمت (پهن‌تر از قبل؛ قبلاً قیمت ۱۲۰ و نام ۵۸ برعکس بود)
    svc_price_w = 38 * mm
    svc_name_w = inner_w - svc_price_w
    # توضیحات: توضیح (پهن) | نام خدمت (باریک)
    desc_text_w = inner_w * 0.72
    desc_name_w = inner_w - desc_text_w

    project_root = Path(__file__).resolve().parent
    logo_path = project_root / "assets" / "images" / "logo.png"
    logo_side = 24 * mm

    created_at = _fa_digits(datetime.now().strftime("%Y-%m-%d %H:%M"))
    title_text = "فاکتور ساده سفارش" if simple else "فاکتور سفارش"
    title_para = Paragraph(_fa_shape(title_text), title_style)
    meta_para = Paragraph(
        _fa_shape(f"شماره سفارش: {_safe_text(order_id)}")
        + "<br/>"
        + _fa_shape(f"تاریخ: {created_at}"),
        hint_style,
    )

    elements: list = []
    if logo_path.is_file():
        logo_img = Image(
            str(logo_path),
            width=logo_side,
            height=logo_side,
            mask="auto",
            hAlign="LEFT",
        )
        header_right = [title_para, Spacer(1, 6), meta_para]
        header_table = Table(
            [[logo_img, header_right]],
            colWidths=[logo_side, inner_w - logo_side],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 6 * mm),
                ]
            )
        )
        elements.append(header_table)
    else:
        elements.append(title_para)
        elements.append(Spacer(1, 6))
        elements.append(meta_para)
    elements.append(Spacer(1, 10))

    customer_table = Table(
        [
            [
                "",
                _fa_shape("اطلاعات مشتری"),
            ],
            [
                _cell_paragraph(customer_snapshot.get("name"), customer_value_style),
                _fa_shape("نام"),
            ],
            [
                _cell_paragraph(customer_snapshot.get("phone"), customer_value_style),
                _fa_shape("شماره تماس"),
            ],
            [
                _cell_paragraph(customer_snapshot.get("address"), customer_value_style),
                _fa_shape("آدرس"),
            ],
        ],
        colWidths=[cw_val, cw_lbl],
    )
    customer_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
                ("FONTNAME", (0, 0), (1, 3), font_name),
                ("FONTSIZE", (0, 0), (1, 0), 11),
                ("FONTSIZE", (0, 1), (1, 3), 10),
                ("ALIGN", (0, 0), (1, 3), "RIGHT"),
                ("VALIGN", (0, 0), (1, 3), "TOP"),
                ("BACKGROUND", (0, 1), (0, 3), colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (1, 1), (1, 3), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (1, 3), 0.6, colors.HexColor("#94a3b8")),
                ("RIGHTPADDING", (0, 0), (1, 3), 8),
                ("LEFTPADDING", (0, 0), (1, 3), 8),
            ]
        )
    )
    elements.append(customer_table)
    elements.append(Spacer(1, 10))

    if not simple:
        descriptions: list[tuple[str, dict]] = []
        for row in services_detail:
            name = _safe_text(row.get("name"))
            detail_html = _service_details_html(row)
            if detail_html and detail_html != _fa_shape("-"):
                descriptions.append((name, row))

        # ۲) جدول توضیحات در میانه (قبل از جدول قیمت/خدمات)
        if descriptions:
            elements.append(Paragraph(_fa_shape("توضیحات خدمات"), normal_style))
            elements.append(Spacer(1, 4))
            desc_rows: list[list] = [
                [
                    _fa_shape("توضیحات"),
                    _fa_shape("نام خدمت"),
                ]
            ]
            for name, row in descriptions:
                desc_rows.append(
                    [
                        Paragraph(_service_details_html(row), desc_wide_style),
                        _cell_paragraph(name, desc_name_style),
                    ]
                )
            desc_table = Table(
                desc_rows,
                colWidths=[desc_text_w, desc_name_w],
            )
            desc_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#1d4ed8")),
                        ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
                        ("FONTNAME", (0, 0), (1, 0), font_name),
                        ("FONTSIZE", (0, 0), (1, 0), 10),
                        ("ALIGN", (0, 0), (1, -1), "RIGHT"),
                        ("VALIGN", (0, 0), (1, -1), "TOP"),
                        ("GRID", (0, 0), (1, -1), 0.45, colors.HexColor("#93c5fd")),
                        ("BACKGROUND", (0, 1), (1, -1), colors.HexColor("#eff6ff")),
                        ("RIGHTPADDING", (0, 0), (1, -1), 8),
                        ("LEFTPADDING", (0, 0), (1, -1), 8),
                    ]
                )
            )
            elements.append(desc_table)
            elements.append(Spacer(1, 10))

        selected_plans = selected_plans or []
        if selected_plans:
            elements.append(Paragraph(_fa_shape("پلن‌های انتخابی"), normal_style))
            elements.append(Spacer(1, 4))
            plan_rows: list[list] = [[_fa_shape("مفاد و توضیحات تکمیلی"), _fa_shape("نام پلن")]]
            for pl in selected_plans:
                plan_name = _safe_text(pl.get("name"))
                terms = [x.strip() for x in (pl.get("terms") or []) if isinstance(x, str) and x.strip()]
                extra_note = (pl.get("extra_note") or "").strip()
                detail_lines: list[str] = []
                if terms:
                    detail_lines.append(_fa_shape("مفاد:"))
                    detail_lines.extend(_fa_shape(f"• {t}") for t in terms)
                if extra_note:
                    detail_lines.append(_fa_shape("توضیحات تکمیلی:"))
                    detail_lines.append(_fa_shape(extra_note))
                if not detail_lines:
                    detail_lines.append(_fa_shape("-"))
                plan_rows.append(
                    [
                        Paragraph("<br/>".join(detail_lines), desc_wide_style),
                        _cell_paragraph(plan_name, desc_name_style),
                    ]
                )
            plans_table = Table(plan_rows, colWidths=[desc_text_w, desc_name_w])
            plans_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#6d28d9")),
                        ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
                        ("FONTNAME", (0, 0), (1, 0), font_name),
                        ("FONTSIZE", (0, 0), (1, 0), 10),
                        ("ALIGN", (0, 0), (1, -1), "RIGHT"),
                        ("VALIGN", (0, 0), (1, -1), "TOP"),
                        ("GRID", (0, 0), (1, -1), 0.45, colors.HexColor("#c4b5fd")),
                        ("BACKGROUND", (0, 1), (1, -1), colors.HexColor("#f5f3ff")),
                        ("RIGHTPADDING", (0, 0), (1, -1), 8),
                        ("LEFTPADDING", (0, 0), (1, -1), 8),
                    ]
                )
            )
            elements.append(plans_table)
            elements.append(Spacer(1, 10))

    # ۳) جدول قیمت و خدمات + جمع کل — آخرین جدول اصلی
    service_rows: list[list] = [
        [
            _fa_shape("قیمت"),
            _fa_shape("خدمت"),
        ]
    ]
    for row in services_detail:
        name = _safe_text(row.get("name"))
        price_txt = _safe_text(row.get("price"), _money(0))
        service_rows.append(
            [
                _cell_paragraph(price_txt, service_body_style),
                _cell_paragraph(name, service_body_style),
            ]
        )
    service_rows.append(
        [
            _cell_paragraph(_money(total_amount), service_total_style),
            _cell_paragraph("جمع کل", service_total_style),
        ]
    )

    service_table = Table(service_rows, colWidths=[svc_price_w, svc_name_w])
    service_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
                ("FONTNAME", (0, 0), (1, 0), font_name),
                ("ALIGN", (0, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (1, 0), 10),
                ("GRID", (0, 0), (1, -1), 0.5, colors.HexColor("#94a3b8")),
                ("RIGHTPADDING", (0, 0), (1, -1), 8),
                ("LEFTPADDING", (0, 0), (1, -1), 8),
                ("BACKGROUND", (0, 1), (1, -2), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (0, -1), (1, -1), colors.HexColor("#dcfce7")),
            ]
        )
    )
    elements.append(service_table)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(_fa_shape("ساخته شده توسط Team baltazar"), hint_style))
    doc.build(elements)
    return str(file_path)


def _roadmap_price_label(price_text: str, amount: int) -> tuple[str, bool]:
    pt = (price_text or "").strip()
    if amount > 0:
        return _money(amount), False
    if pt:
        return _fa_shape(escape(pt)), True
    return _fa_shape("طبق توافق"), True


def _roadmap_step_dict(
    idx: int,
    heading: str,
    subtitle: str,
    lead: str,
    items: list[str],
    price_label: str,
    price_variable: bool,
    *,
    is_future: bool = False,
) -> dict:
    return {
        "num_fa": _fa_digits(str(idx)),
        "heading": heading,
        "subtitle": subtitle or "",
        "lead": lead or "",
        "bullets": items or [],
        "price_label": price_label,
        "price_variable": price_variable,
        "is_future": is_future,
    }


def roadmap_steps_from_custom_order(row: dict) -> list[dict]:
    out: list[dict] = []
    idx = 1
    for st in row.get("steps") or []:
        if not isinstance(st, dict):
            continue
        title = (st.get("title") or "").strip()
        nm = (st.get("name") or "").strip()
        if title and nm:
            heading = f"{nm} — {title}"
        else:
            heading = nm or title or "مرحله"
        subtitle = ""
        items = [x for x in (st.get("description_lines") or []) if isinstance(x, str) and x.strip()]
        amt = int(st.get("price_amount") or 0)
        pt = (st.get("price") or "").strip()
        plabel, pvar = _roadmap_price_label(pt, amt)
        out.append(_roadmap_step_dict(idx, heading, subtitle, "", items, plabel, pvar))
        idx += 1
    return out


def roadmap_steps_from_standard_order(row: dict) -> list[dict]:
    service_ids = [x for x in (row.get("service_ids") or []) if isinstance(x, str) and x.strip()]
    plan_ids = [x for x in (row.get("plan_ids") or []) if isinstance(x, str) and x.strip()]
    details_by_id: dict[str, dict] = {}
    for d in row.get("services_detail") or []:
        if isinstance(d, dict) and isinstance(d.get("id"), str) and d.get("id"):
            details_by_id[d["id"]] = d
    plan_snap: dict[str, dict] = {}
    for p in row.get("selected_plans_snapshot") or []:
        if isinstance(p, dict) and isinstance(p.get("id"), str) and p.get("id"):
            plan_snap[p["id"]] = p

    out: list[dict] = []
    idx = 1
    for sid in service_ids:
        d = details_by_id.get(sid)
        if not d:
            continue
        name = (d.get("name") or "").strip() or "خدمت"
        terms = [x.strip() for x in (d.get("terms") or []) if isinstance(x, str) and x.strip()]
        if not terms:
            desc = (d.get("description") or "").strip()
            if desc:
                terms = [ln.strip() for ln in desc.splitlines() if ln.strip()]
        lead = (d.get("extra_note") or "").strip()
        amt = parse_price_amount(str(d.get("price") or ""))
        plabel, pvar = _roadmap_price_label(str(d.get("price") or ""), amt)
        out.append(_roadmap_step_dict(idx, name, "خدمت", lead, terms, plabel, pvar))
        idx += 1

    for pid in plan_ids:
        d = details_by_id.get(pid)
        if not d:
            continue
        snap = plan_snap.get(pid, {})
        name = (d.get("name") or "").strip() or "پلن"
        terms = [x.strip() for x in (snap.get("terms") or []) if isinstance(x, str) and x.strip()]
        lead = (snap.get("extra_note") or "").strip()
        amt = parse_price_amount(str(d.get("price") or ""))
        plabel, pvar = _roadmap_price_label(str(d.get("price") or ""), amt)
        out.append(_roadmap_step_dict(idx, name, "پلن", lead, terms, plabel, pvar))
        idx += 1

    return out


def build_roadmap_template_context(source: str, row: dict) -> dict:
    project_root = Path(__file__).resolve().parent
    logo_path = project_root / "assets" / "images" / "logo.png"
    logo_src = logo_path.resolve().as_uri() if logo_path.is_file() else ""

    oid = str(row.get("id") or "")
    cust = row.get("customer") or {}
    cname = (cust.get("name") or "").strip() or "مشتری"

    dana_path = project_root / "assets" / "fonts" / "Dana-Black.ttf"
    dana_font_uri = dana_path.resolve().as_uri() if dana_path.is_file() else ""

    if source == "custom-order":
        steps = roadmap_steps_from_custom_order(row)
        intro = (
            f"این فاکتور رودمپ برای «{cname}» تهیه شده است. "
            f"شماره سفارش: {_fa_digits(oid)}."
        )
    else:
        steps = roadmap_steps_from_standard_order(row)
        intro = (
            f"تیم بالتازار مسیر همکاری را برای «{cname}» به‌صورت مرحله‌ای خلاصه کرده است. "
            f"شماره سفارش: {_fa_digits(oid)}."
        )
    section_title = "مراحل همکاری و خدمات"

    total_fa = _money(int(row.get("total_price") or 0))

    return {
        "doc_title": "فاکتور رودمپ | بالتازار",
        "logo_src": logo_src,
        "dana_font_uri": dana_font_uri,
        "header_title": "فاکتور رودمپ سفارش",
        "header_subtitle": "نمای مرحله‌ای مفاد و قیمت هر بخش",
        "tagline": f"جمع کل سفارش: {total_fa}",
        "intro_paragraph": intro,
        "section_title": section_title,
        "roadmap_steps": steps,
    }


def render_roadmap_invoice_html(ctx: dict) -> str:
    templates_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return env.get_template("factor-roadmap.html").render(**ctx)


def _html_to_pdf_playwright(html: str, pdf_path: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "برای فاکتور رودمپ بستهٔ Playwright لازم است: pip install playwright و سپس playwright install chromium"
        ) from e
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_viewport_size({"width": 900, "height": 1123})
            page.set_content(html, wait_until="networkidle", timeout=120_000)
            page.emulate_media(media="print")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
            )
        finally:
            browser.close()


def create_roadmap_invoice_pdf(*, order_id: str, source: str, row: dict) -> str:
    ctx = build_roadmap_template_context(source, row)
    html = render_roadmap_invoice_html(ctx)
    output_dir = Path(__file__).resolve().parent / "reciept"
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"invoice-{order_id}.pdf"
    _html_to_pdf_playwright(html, file_path)
    return str(file_path)


def _amount_pretty_fa(amount: int) -> str:
    return _fa_digits(f"{amount:,}")


def _simple_item_html(name: str, description: str) -> Markup:
    nm = (name or "").strip() or "—"
    parts = [f'<span class="item-title">{escape(nm)}</span>']
    desc = (description or "").strip()
    if desc:
        parts.append(f'<span class="item-desc">{escape(desc)}</span>')
    return Markup("".join(parts))


def _simple_lines_for_template(row: dict) -> list[dict]:
    raw = row.get("simple_lines")
    rows: list[dict] = []
    if isinstance(raw, list) and raw:
        i = 0
        for ln in raw:
            if not isinstance(ln, dict):
                continue
            name = (ln.get("name") or "").strip()
            if not name:
                continue
            i += 1
            qty = int(ln.get("quantity") or 1)
            if qty < 1:
                qty = 1
            unit = int(ln.get("unit_amount") or 0)
            lt = int(ln.get("line_total") or unit * qty)
            desc = (ln.get("description") or "").strip()
            rows.append(
                {
                    "row_no_fa": _fa_digits(str(i)),
                    "item_html": _simple_item_html(name, desc),
                    "qty_fa": _fa_digits(str(qty)),
                    "unit_price_fa": _amount_pretty_fa(unit),
                    "line_total_fa": _amount_pretty_fa(lt),
                }
            )
        return rows
    idx = 0
    for d in row.get("services_detail") or []:
        if not isinstance(d, dict):
            continue
        name = (d.get("name") or "").strip() or "—"
        qty = int(d.get("quantity") or 1)
        if qty < 1:
            qty = 1
        unit = parse_price_amount(str(d.get("price") or ""))
        lt = int(d.get("line_total") or unit * qty)
        desc_chunks: list[str] = []
        terms = d.get("terms")
        if isinstance(terms, list) and terms:
            desc_chunks.extend(x.strip() for x in terms if isinstance(x, str) and x.strip())
        legacy = (d.get("description") or "").strip()
        if legacy and not desc_chunks:
            desc_chunks.append(legacy)
        desc = "\n".join(desc_chunks)
        idx += 1
        rows.append(
            {
                "row_no_fa": _fa_digits(str(idx)),
                "item_html": _simple_item_html(name, desc),
                "qty_fa": _fa_digits(str(qty)),
                "unit_price_fa": _amount_pretty_fa(unit),
                "line_total_fa": _amount_pretty_fa(lt),
            }
        )
    return rows


def build_simple_invoice_context(row: dict) -> dict:
    project_root = Path(__file__).resolve().parent
    logo_path = project_root / "assets" / "images" / "logo.png"
    logo_src = logo_path.resolve().as_uri() if logo_path.is_file() else ""
    dana_path = project_root / "assets" / "fonts" / "Dana-Black.ttf"
    dana_font_uri = dana_path.resolve().as_uri() if dana_path.is_file() else ""

    oid = str(row.get("id") or "")
    inv = "INV-" + (oid[:8].upper() if len(oid) >= 8 else oid.upper())
    inv_date = _fa_digits(datetime.now().strftime("%Y-%m-%d %H:%M"))
    table_lines = _simple_lines_for_template(row)
    total = int(row.get("total_price") or 0)

    return {
        "doc_title": "فاکتور فروش | بالتازار پلاس",
        "dana_font_uri": dana_font_uri,
        "logo_src": logo_src,
        "invoice_number": inv,
        "invoice_date": inv_date,
        "table_lines": table_lines,
        "grand_total_fa": _amount_pretty_fa(total),
    }


def render_simple_invoice_html(ctx: dict) -> str:
    templates_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return env.get_template("factor-simple.html").render(**ctx)


def create_simple_invoice_pdf(*, order_id: str, row: dict) -> str:
    ctx = build_simple_invoice_context(row)
    html = render_simple_invoice_html(ctx)
    output_dir = Path(__file__).resolve().parent / "reciept"
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"invoice-{order_id}.pdf"
    _html_to_pdf_playwright(html, file_path)
    return str(file_path)


def custom_order_to_services_detail(row: dict) -> list[dict]:
    out: list[dict] = []
    for i, st in enumerate(row.get("steps") or []):
        if not isinstance(st, dict):
            continue
        title = (st.get("title") or "").strip()
        nm = (st.get("name") or "").strip()
        name = " — ".join(x for x in [nm, title] if x) or nm or title or f"مرحله {i + 1}"
        terms = [x for x in (st.get("description_lines") or []) if isinstance(x, str) and x.strip()]
        out.append(
            {
                "id": f"step-{i}",
                "name": name,
                "price": st.get("price", ""),
                "description": "",
                "terms": terms,
                "extra_note": "",
            }
        )
    return out


PANEL_TIER_META: dict[str, dict[str, str]] = {
    "economic": {
        "title": "اقتصادی",
        "card_class": "economic-card",
        "badge_text": "شروع هوشمند برند",
        "badge_icon": "fas fa-seedling",
        "sparkle_icon": "fas fa-leaf",
    },
    "bronze": {
        "title": "برنز ای",
        "card_class": "bronze-card",
        "badge_text": "گارانتی کیفیت کدنویسی",
        "badge_icon": "fas fa-award",
        "sparkle_icon": "fas fa-leaf",
    },
    "silver": {
        "title": "نقره ای",
        "card_class": "silver-card",
        "badge_text": "عملکرد فوق سریع",
        "badge_icon": "fas fa-tachometer-alt",
        "sparkle_icon": "fas fa-star-of-life",
    },
    "gold": {
        "title": "طلایی",
        "card_class": "gold-card",
        "badge_text": "پرفروش‌ترین پنل حرفه‌ای",
        "badge_icon": "fas fa-fire",
        "sparkle_icon": "fas fa-crown",
    },
    "diamond": {
        "title": "الماسی",
        "card_class": "diamond-card",
        "badge_text": "ادیشن لوکس و بی‌نظیر",
        "badge_icon": "fas fa-gem",
        "sparkle_icon": "fas fa-glasses",
    },
    "exclusive": {
        "title": "اختصاصی",
        "card_class": "exclusive-card",
        "badge_text": "ویژه برندهای بین‌المللی",
        "badge_icon": "fas fa-champagne-glasses",
        "sparkle_icon": "fas fa-infinity",
    },
}

_SERVICE_ICON_RULES: list[tuple[tuple[str, ...], str]] = [
    (("ssl", "گواهی", "امنیت", "قفل"), "fas fa-lock"),
    (("موبایل", "ریسپانسیو", "تبلت"), "fas fa-mobile-alt"),
    (("سئو", "xml", "نقشه سایت"), "fas fa-chart-simple"),
    (("react", "vue", "نکست", "spa", "pwa", "لاراول", "node", "full-stack", "داینامیک"), "fas fa-code"),
    (("صفحه", "بلاگ", "محتوا"), "fas fa-file-alt"),
    (("گالری", "تصویر", "ویدیو", "اینفوگرافیک"), "fas fa-images"),
    (("پشتیبانی", "رفع باگ", "vip"), "fas fa-headset"),
    (("الماس", "لوکس"), "fas fa-diamond"),
    (("سرعت", "عملکرد", "بهینه", "ابری", "بارگذاری"), "fas fa-tachometer-alt"),
    (("بکاپ", "دیتابیس", "database"), "fas fa-database"),
    (("api", "درگاه", "اتصال", "plug"), "fas fa-plug"),
    (("بانک", "shield", "امنیت پیشرفته"), "fas fa-shield-alt"),
    (("پنل مدیریت", "داشبورد"), "fas fa-chalkboard-user"),
    (("هاست", "دامنه", "server"), "fas fa-server"),
    (("مشاوره", "ممتاز", "دائم", "۲۴"), "fas fa-hand-holding-heart"),
    (("برند", "دی‌ان‌ای", "منحصربه‌فرد", "palette"), "fas fa-palette"),
    (("مارکت", "شبکه اجتماعی", "cogs", "قابلیت"), "fas fa-cogs"),
    (("تیم", "ui/ux", "کاربر"), "fas fa-users"),
    (("رقبا", "استراتژی", "آنالیز"), "fas fa-search-dollar"),
    (("انیمیشن", "افکت", "magic"), "fas fa-magic"),
    (("طلایی", "gem", "پریمیوم"), "fas fa-gem"),
    (("وردپرس", "شرکتی"), "fas fa-check-circle"),
    (("فرم تماس",), "fas fa-check-circle"),
    (("رشد", "chart"), "fas fa-chart-line"),
    (("آپلود", "cloud"), "fas fa-cloud-upload-alt"),
    (("مشاوره آنلاین", "concierge"), "fas fa-concierge-bell"),
]


def pick_service_icon(service_name: str) -> str:
    """همهٔ خدمات پلن با آیکون تیک یکسان نمایش داده می‌شوند."""
    return "fas fa-check-circle"


def _panel_price_display(plan: dict) -> tuple[str, str]:
    if plan.get("negotiable") or plan.get("tier") == "exclusive":
        return "توافقی", "متناسب با پروژه"
    raw = (plan.get("price") or "").strip()
    amt = int(plan.get("price_amount") or 0)
    if raw and not raw.replace(",", "").replace("٬", "").isdigit():
        parts = raw.split()
        main = parts[0] if parts else raw
        small = " ".join(parts[1:]) if len(parts) > 1 else "تومان"
        return _fa_digits(main), _fa_digits(small) if small != "تومان" else "تومان"
    if amt > 0:
        return _fa_digits(f"{amt:,}"), "تومان"
    return _fa_digits(raw) if raw else "—", "تومان"


def _estimate_panel_card_height_mm(card: dict, scale: float = 1.0) -> float:
    """تخمین ارتفاع کارت برای چیدمان دو ستونه (میلی‌متر)."""
    n = len(card.get("services") or [])
    return (64.0 + n * 6.5) * scale


def _row_height_mm(card_a: dict, card_b: dict | None, scale: float) -> float:
    h_a = _estimate_panel_card_height_mm(card_a, scale)
    if card_b is None:
        return h_a
    h_b = _estimate_panel_card_height_mm(card_b, scale)
    return max(h_a, h_b)


def _remaining_rows_height_mm(
    cards: list[dict], start: int, row_gap_mm: float, scale: float
) -> float:
    if start >= len(cards):
        return 0.0
    total = 0.0
    i = start
    first = True
    while i < len(cards):
        if not first:
            total += row_gap_mm
        c2 = cards[i + 1] if i + 1 < len(cards) else None
        total += _row_height_mm(cards[i], c2, scale)
        i += 2 if c2 else 1
        first = False
    return total


def _paginate_panel_at_scale(
    cards: list[dict], scale: float, row_gap_mm: float
) -> list[dict]:
    """صفحه‌بندی دو ستونه: هر ردیف حداکثر ۲ پلن؛ ردیفی که جا نشود به صفحه بعد."""
    first_page_mm = 118.0
    next_page_mm = 252.0

    pages: list[dict] = []
    idx = 0
    page_index = 0

    while idx < len(cards):
        is_first = page_index == 0
        base_avail = first_page_mm if is_first else next_page_mm
        page_cards: list[dict] = []
        used_mm = 0.0

        while idx < len(cards):
            remaining = base_avail - used_mm
            avail = remaining

            c2 = cards[idx + 1] if idx + 1 < len(cards) else None
            row_h = _row_height_mm(cards[idx], c2, scale)
            gap = row_gap_mm if page_cards else 0.0

            if page_cards and used_mm + gap + row_h > avail:
                break

            if not page_cards and row_h > avail:
                if c2:
                    page_cards.extend([cards[idx], cards[idx + 1]])
                    idx += 2
                else:
                    page_cards.append(cards[idx])
                    idx += 1
                used_mm += row_h
                break

            if used_mm + gap + row_h <= avail or not page_cards:
                used_mm += (gap if page_cards else 0.0) + row_h
                if c2:
                    page_cards.extend([cards[idx], cards[idx + 1]])
                    idx += 2
                else:
                    page_cards.append(cards[idx])
                    idx += 1
            else:
                break

        pages.append(
            {
                "cards": page_cards,
                "is_first": is_first,
                "is_last": idx >= len(cards),
                "page_break": page_index > 0,
            }
        )
        page_index += 1

    if pages:
        pages[-1]["is_last"] = True
    return pages


def paginate_panel_cards(cards: list[dict]) -> list[dict]:
    """چیدمان دو ستونه؛ پلن‌های اضافه در ردیف‌های بعدی یا صفحه بعد."""
    if not cards:
        return [
            {
                "cards": [],
                "is_first": True,
                "is_last": True,
                "page_break": False,
            }
        ]

    row_gap_mm = 10.0
    return _paginate_panel_at_scale(cards, 1.0, row_gap_mm)


def build_panel_invoice_context(row: dict) -> dict:
    project_root = Path(__file__).resolve().parent
    logo_path = project_root / "assets" / "images" / "logo.png"
    if not logo_path.is_file():
        logo_path = project_root / "assetes" / "images" / "logo.png"
    logo_src = logo_path.resolve().as_uri() if logo_path.is_file() else ""
    dana_path = project_root / "assets" / "fonts" / "Dana-Black.ttf"
    if not dana_path.is_file():
        dana_path = project_root / "assetes" / "fonts" / "Dana-Black.ttf"
    dana_font_uri = dana_path.resolve().as_uri() if dana_path.is_file() else ""

    cards: list[dict] = []
    for raw in row.get("panel_plans") or []:
        if not isinstance(raw, dict):
            continue
        tier = str(raw.get("tier") or "bronze").strip()
        meta = PANEL_TIER_META.get(tier, PANEL_TIER_META["bronze"])
        services_html: list[dict] = []
        for svc in raw.get("services") or []:
            if isinstance(svc, dict):
                nm = (svc.get("name") or "").strip()
            elif isinstance(svc, str):
                nm = svc.strip()
            else:
                continue
            if not nm:
                continue
            icon = pick_service_icon(nm) or "fas fa-check-circle"
            services_html.append({"text": nm, "icon": icon})
        price_main, price_small = _panel_price_display(raw)
        cards.append(
            {
                "title": meta["title"],
                "card_class": meta["card_class"],
                "services": services_html,
                "price_main": price_main,
                "price_small": price_small,
                "sparkle_icon": meta["sparkle_icon"],
            }
        )

    panel_pages = paginate_panel_cards(cards)

    return {
        "doc_title": "پنل‌های تیم برندینگ بالتازار پلاس",
        "dana_font_uri": dana_font_uri,
        "logo_src": logo_src,
        "panel_cards": cards,
        "panel_pages": panel_pages,
        "contact_phone": "۰۹۳۳۰۲۵۷۰۸۹",
    }


def render_panel_invoice_html(ctx: dict) -> str:
    templates_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return env.get_template("factor-panel.html").render(**ctx)


def create_panel_invoice_pdf(*, order_id: str, row: dict) -> str:
    ctx = build_panel_invoice_context(row)
    html = render_panel_invoice_html(ctx)
    output_dir = Path(__file__).resolve().parent / "reciept"
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"invoice-{order_id}.pdf"
    _html_to_pdf_playwright(html, file_path)
    return str(file_path)


def issue_invoice_for_stored_order(source: str, row: dict) -> str:
    if not isinstance(row, dict):
        raise ValueError("bad_order")
    oid = row.get("id")
    if not isinstance(oid, str) or not oid.strip():
        raise ValueError("bad_order_id")
    oid = oid.strip()
    it = (row.get("invoice_type") or "current").strip()
    if it not in ("current", "panel", "simple", "roadmap"):
        it = "current"
    customer = row.get("customer") or {}
    total = int(row.get("total_price") or 0)

    if it == "roadmap":
        return create_roadmap_invoice_pdf(order_id=oid, source=source, row=row)

    if it == "simple":
        return create_simple_invoice_pdf(order_id=oid, row=row)

    if it == "panel":
        return create_panel_invoice_pdf(order_id=oid, row=row)

    if source == "custom-order":
        details = custom_order_to_services_detail(row)
        selected_plans: list[dict] = []
    else:
        details = row.get("services_detail") or []
        if not isinstance(details, list):
            details = []
        selected_plans = row.get("selected_plans_snapshot") or []
        if not isinstance(selected_plans, list):
            selected_plans = []

    return create_receipt_pdf(
        order_id=oid,
        customer_snapshot=customer if isinstance(customer, dict) else {},
        services_detail=[x for x in details if isinstance(x, dict)],
        total_amount=total,
        selected_plans=[x for x in selected_plans if isinstance(x, dict)],
    )
