from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils.text import slugify
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def build_report_card_pdf(report_card):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title=f"Report Card - {report_card.student.name}",
        author="Student Report Card Assistant",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#263b68"),
        spaceAfter=8 * mm,
    )
    body_style = styles["BodyText"]
    paragraph = lambda text: Paragraph(escape(str(text)), body_style)
    elements = [
        Paragraph("STUDENT REPORT CARD", title_style),
        Paragraph(f"<b>Student:</b> {escape(report_card.student.name)}", body_style),
        Paragraph(f"<b>Roll number:</b> {escape(report_card.student.roll_number)}", body_style),
        Paragraph(
            f"<b>Class / Section:</b> {escape(report_card.student.class_name)} / "
            f"{escape(report_card.student.section or '-')}",
            body_style,
        ),
        Paragraph(f"<b>Academic year:</b> {escape(report_card.student.academic_year)}", body_style),
        Paragraph(f"<b>Examination:</b> {escape(report_card.examination.name)}", body_style),
        Spacer(1, 5 * mm),
    ]

    subject_rows = [["Subject", "Marks", "Maximum", "Percentage", "Grade", "Result"]]
    for item in report_card.subject_results:
        subject_rows.append(
            [
                escape(item["subject"]),
                item["marks"],
                item["maximum_marks"],
                f'{item["percentage"]}%',
                escape(item["grade"]),
                "Pass" if item["passed"] else "Needs support",
            ]
        )
    subject_table = Table(
        subject_rows,
        repeatRows=1,
        colWidths=[48 * mm, 22 * mm, 22 * mm, 25 * mm, 16 * mm, 30 * mm],
    )
    subject_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4059b8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dce1ec")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fb")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    elements.extend(
        [
            subject_table,
            Spacer(1, 7 * mm),
            Paragraph(
                f"<b>Total:</b> {report_card.total_marks} / "
                f"{report_card.total_maximum_marks}",
                body_style,
            ),
            Paragraph(
                f"<b>Overall percentage:</b> {report_card.percentage}%",
                body_style,
            ),
            Paragraph(
                f"<b>Overall grade:</b> {report_card.overall_grade} &nbsp;&nbsp; "
                f"<b>Status:</b> {'PASS' if report_card.passed else 'FAIL'}",
                body_style,
            ),
        ]
    )
    if report_card.rank is not None:
        elements.append(Paragraph(f"<b>Class rank:</b> {report_card.rank}", body_style))
    if report_card.percentile is not None:
        elements.append(
            Paragraph(f"<b>Class percentile:</b> {report_card.percentile}%", body_style)
        )
    elif report_card.rank_unavailable_reason:
        elements.append(
            paragraph(
                report_card.rank_unavailable_reason
            )
        )
    elements.extend(
        [
            Spacer(1, 5 * mm),
            Paragraph(
                (
                    "<b>Academic feedback (AI-generated; teacher review):</b>"
                    if report_card.teacher_summary
                    else "<b>Academic feedback:</b>"
                ),
                body_style,
            ),
            paragraph(report_card.teacher_summary or "No feedback available."),
            Spacer(1, 10 * mm),
            Paragraph(
                f"<b>Teacher remarks:</b> {escape(report_card.teacher_remarks or ' ')}",
                body_style,
            ),
            Spacer(1, 15 * mm),
            Table(
                [["Teacher signature", "Date", "School seal"], ["", "", ""]],
                colWidths=[60 * mm, 55 * mm, 55 * mm],
                rowHeights=[8 * mm, 15 * mm],
                style=TableStyle(
                    [
                        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#7e8797")),
                        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ]
                ),
            ),
        ]
    )
    document.build(elements)
    filename = slugify(
        f"{report_card.student.roll_number}-{report_card.examination.name}"
    ) or "report-card"
    pdf_bytes = buffer.getvalue()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
    response["Content-Length"] = str(len(pdf_bytes))
    return response
