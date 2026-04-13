from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _register_font() -> str:
    candidates = [
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


def _safe_text(value: str | None, fallback: str = "-") -> str:
    text = (value or "").strip()
    return text if text else fallback


def _money(value: int) -> str:
    return f"{value:,} تومان"


def create_receipt_pdf(
    *,
    order_id: str,
    customer_snapshot: dict,
    services_detail: list[dict],
    total_amount: int,
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
        alignment=2,
        textColor=colors.HexColor("#0f172a"),
    )
    normal_style = ParagraphStyle(
        "InvoiceNormal",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        alignment=2,
        textColor=colors.HexColor("#1e293b"),
    )
    hint_style = ParagraphStyle(
        "InvoiceHint",
        parent=normal_style,
        fontSize=9,
        textColor=colors.HexColor("#475569"),
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

    elements = []
    elements.append(Paragraph("فاکتور سفارش", title_style))
    elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(
            f"شماره سفارش: {_safe_text(order_id)}<br/>تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            hint_style,
        )
    )
    elements.append(Spacer(1, 10))

    customer_table = Table(
        [
            ["اطلاعات مشتری", ""],
            ["نام", _safe_text(customer_snapshot.get("name"))],
            ["شماره تماس", _safe_text(customer_snapshot.get("phone"))],
            ["آدرس", _safe_text(customer_snapshot.get("address"))],
        ],
        colWidths=[40 * mm, 138 * mm],
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
                ("VALIGN", (0, 0), (1, 3), "MIDDLE"),
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

    service_rows = [["خدمت", "قیمت"]]
    descriptions: list[tuple[str, str]] = []
    for row in services_detail:
        name = _safe_text(row.get("name"))
        service_rows.append([name, _safe_text(row.get("price"), _money(0))])
        if (row.get("description") or "").strip():
            descriptions.append((name, row["description"].strip()))

    service_rows.append(["جمع کل", _money(total_amount)])

    service_table = Table(service_rows, colWidths=[120 * mm, 58 * mm])
    service_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
                ("FONTNAME", (0, 0), (1, -1), font_name),
                ("ALIGN", (0, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (1, -1), 10),
                ("GRID", (0, 0), (1, -1), 0.5, colors.HexColor("#94a3b8")),
                ("RIGHTPADDING", (0, 0), (1, -1), 8),
                ("LEFTPADDING", (0, 0), (1, -1), 8),
                ("BACKGROUND", (0, 1), (1, -2), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (0, -1), (1, -1), colors.HexColor("#dcfce7")),
                ("TEXTCOLOR", (0, -1), (1, -1), colors.HexColor("#166534")),
            ]
        )
    )
    elements.append(service_table)
    elements.append(Spacer(1, 10))

    if descriptions:
        elements.append(Paragraph("توضیحات خدمات", normal_style))
        desc_rows = [["نام خدمت", "توضیحات"]]
        for name, desc in descriptions:
            desc_rows.append([name, desc])
        desc_table = Table(desc_rows, colWidths=[55 * mm, 123 * mm])
        desc_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#1d4ed8")),
                    ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
                    ("FONTNAME", (0, 0), (1, -1), font_name),
                    ("FONTSIZE", (0, 0), (1, -1), 9.5),
                    ("ALIGN", (0, 0), (1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (1, -1), "TOP"),
                    ("GRID", (0, 0), (1, -1), 0.45, colors.HexColor("#93c5fd")),
                    ("BACKGROUND", (0, 1), (1, -1), colors.HexColor("#eff6ff")),
                    ("RIGHTPADDING", (0, 0), (1, -1), 8),
                    ("LEFTPADDING", (0, 0), (1, -1), 8),
                ]
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(desc_table)

    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Generated by Team Project", hint_style))
    doc.build(elements)
    return str(file_path)
