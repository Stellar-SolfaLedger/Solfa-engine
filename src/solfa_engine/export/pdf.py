"""Professional PDF score report generation using ReportLab."""

import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted

from solfa_engine.schemas import TranscriptionResult


def generate_pdf_score(result: TranscriptionResult, title: str = "SolfaLedger Transcription") -> bytes:
    """
    Render transcription metadata, traditional tonic solfa notation, and measure tables into a PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#0f172a"),
    )

    meta_chip_style = ParagraphStyle(
        "MetaChip",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#0284c7"),
    )

    h2_style = ParagraphStyle(
        "Heading2Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=14,
        spaceAfter=6,
    )

    solfa_pre_style = ParagraphStyle(
        "SolfaPreformatted",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#09090b"),
    )

    footer_style = ParagraphStyle(
        "FooterNote",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=colors.HexColor("#94a3b8"),
        alignment=1,  # Center
    )

    story = []

    # Title & Subtitle
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            "<font color='#64748b'>Certified On-Chain Tonic Solfa Score — Stellar Soroban Protected</font>",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 12))

    # Musical Metadata Chips Table
    meta_data = [
        [
            Paragraph(f"<b>KEY:</b> {result.tonic}", meta_chip_style),
            Paragraph(f"<b>TEMPO:</b> {int(round(result.bpm))} BPM", meta_chip_style),
            Paragraph(f"<b>TIME SIGNATURE:</b> {result.time_signature}", meta_chip_style),
            Paragraph(f"<b>CONFIDENCE:</b> {int(result.confidences.key * 100)}%", meta_chip_style),
        ]
    ]
    t_meta = Table(meta_data, colWidths=[130, 130, 140, 130])
    t_meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f9ff")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#bae6fd")),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(t_meta)
    story.append(Spacer(1, 14))

    # Traditional Tonic Solfa Section
    story.append(Paragraph("Traditional Tonic Solfa Score", h2_style))
    story.append(Spacer(1, 4))

    # Boxed Solfa Text
    solfa_box = Preformatted(result.solfa_text, solfa_pre_style)
    t_solfa = Table([[solfa_box]], colWidths=[530])
    t_solfa.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                ("PADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(t_solfa)
    story.append(Spacer(1, 14))

    # Measure Details Breakdown Table
    story.append(Paragraph("Measure Breakdown", h2_style))
    story.append(Spacer(1, 4))

    table_rows = [["Bar #", "Start (s)", "Solfa Notes", "MIDI Pitches"]]
    for m in result.measures[:16]:  # Show first 16 bars in PDF table
        solfa_list = " ".join(f"{n.solfa}{n.octave}" for n in m.notes) or "-"
        midi_list = " ".join(str(n.midi) for n in m.notes) or "-"
        table_rows.append([str(m.index), f"{m.start_sec:.2f}s", solfa_list, midi_list])

    t_measures = Table(table_rows, colWidths=[50, 70, 260, 150])
    t_measures.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_measures)
    story.append(Spacer(1, 20))

    # Web3 Verification Footer
    story.append(
        Paragraph(
            "Transcribed by SolfaLedger • Verified on Stellar Soroban • Powered by basic-pitch & signal processing",
            footer_style,
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
