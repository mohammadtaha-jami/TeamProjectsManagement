from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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
    title_para = Paragraph(_fa_shape("فاکتور سفارش"), title_style)
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
