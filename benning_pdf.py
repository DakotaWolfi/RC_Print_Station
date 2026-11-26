"""Colour A4 layout for immutable BENNING report snapshots."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from benning_output import (RESULTS, examination_fields, measurement_summary,
                            report_checks, result_kind, selected_fields, visible_measurements)
from benning_store import SOURCES

DESIGN=Path(__file__).resolve().parent/"hmi"/"design"
NAVY=HexColor("#101923")
INK=HexColor("#243746")
MUTED=HexColor("#536878")
ORANGE=HexColor("#FF941F")
PALE=HexColor("#F0F4F7")
RED=HexColor("#9B252D")
GREEN=HexColor("#146343")
AMBER=HexColor("#845113")


def render(report):
    font="FMINoto"
    try:
        pdfmetrics.getFont(font)
    except KeyError:
        pdfmetrics.registerFont(TTFont(font,str(DESIGN/"typeface"/"NotoSans-Regular.ttf")))

    def cell(value,size=10,colour=INK,face=font):
        style=ParagraphStyle("report",fontName=face,fontSize=size,leading=size*1.3,
                             textColor=colour,splitLongWords=True)
        return Paragraph(escape(str(value)),style)

    simulated=report.get("source")=="SIMULATOR"
    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=42,rightMargin=42,
                          topMargin=158,bottomMargin=61,
                          title="Repair Café Riehen - "+("Simulationsprotokoll" if simulated else "BENNING Prüfprotokoll"),
                          author="FMI Printstation / Repair Café Riehen")
    width,height=A4
    area=width-84

    def frame(pdf,_doc):
        pdf.saveState()
        pdf.setFillColor(NAVY)
        pdf.rect(0,height-133,width,133,fill=1,stroke=0)
        pdf.setFillColor(ORANGE)
        pdf.rect(0,height-137,width,4,fill=1,stroke=0)
        pdf.drawImage(ImageReader(str(DESIGN/"brand.png")),42,height-87,
                      width=area,height=74,preserveAspectRatio=True,anchor="c")
        pdf.setFillColor(white)
        pdf.setFont("Helvetica-Bold",20)
        pdf.drawString(42,height-115,"Simulationsprotokoll" if simulated else "BENNING ST 725  /  Prüfprotokoll")
        pdf.setStrokeColor(PALE)
        pdf.line(42,49,width-42,49)
        pdf.setFillColor(MUTED)
        pdf.setFont(font,9)
        pdf.drawString(42,33,"FMI / Repair Café Riehen")
        pdf.drawRightString(width-42,33,str(pdf.getPageNumber()))
        pdf.restoreState()

    record=report.get("record") or {}
    status=result_kind(report)
    label,_,colour,paper=RESULTS[status]
    source=SOURCES.get(report.get("import_source"),"Keine elektrische Prüfung" if simulated else "Sicht- und Funktionsprüfung")
    original=record.get("verdict")
    summary_text="Original am BENNING: "+original if original else source
    heading="PRÜFPROTOKOLL" if report.get("source")=="EXAMINATION" else "BENNING-URTEIL"
    summary=Table([[cell(heading,10,MUTED)],
                   [cell(label,32,HexColor(colour),"Helvetica-Bold")],
                   [cell(summary_text,11,INK)]],colWidths=[area])
    summary.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),HexColor(paper)),
                                 ("LINEBEFORE",(0,0),(0,-1),4,HexColor(colour)),
                                 ("LEFTPADDING",(0,0),(-1,-1),14),
                                 ("TOPPADDING",(0,0),(-1,0),9),
                                 ("BOTTOMPADDING",(0,-1),(-1,-1),10)]))

    def details(fields):
        table=Table([[cell(key,9,MUTED),cell(value)] for key,value in fields],
                    colWidths=[135,area-135],hAlign="LEFT")
        table.setStyle(TableStyle([("BOTTOMPADDING",(0,0),(-1,-1),4),
                                   ("LINEBELOW",(0,0),(-1,-1),.4,PALE)]))
        return table

    fields=list(selected_fields(report))
    if report.get("import_source"):
        fields.append(("Datenquelle",source))
    story=[summary,Spacer(1,10),details(fields)]
    compact=[measurement_summary(row,csv_source=report.get("import_source") in ("usb","file-csv"))
             for row in visible_measurements(report)]
    if compact:
        has_limits=any(row[2] for row in compact)
        headers=["Messung","Originalwert"]+(["Grenzwert"] if has_limits else [])+["Einzelergebnis"]
        rows=[[cell(title,9,white,"Helvetica-Bold") for title in headers]]
        for name,value,limit,state,kind in compact:
            row=[cell(name),cell(value)]
            if has_limits:
                row.append(cell(limit))
            row.append(cell(state,9,HexColor(RESULTS[kind][2])))
            rows.append(row)
        widths=[108,108,94,area-310] if has_limits else [118,132,area-250]
        table=Table(rows,colWidths=widths,repeatRows=1,hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),
                                   ("ROWBACKGROUNDS",(0,1),(-1,-1),[PALE,white]),
                                   ("VALIGN",(0,0),(-1,-1),"TOP"),
                                   ("TOPPADDING",(0,0),(-1,-1),4),
                                   ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        story.extend((Spacer(1,10),cell("Messwerte",13,INK,"Helvetica-Bold"),Spacer(1,4),table))
    story.extend((Spacer(1,10),cell("Prüfstatus und Freigabe",13,INK,"Helvetica-Bold"),
                  details(report_checks(report))))
    exam=examination_fields(report)
    if exam:
        story.extend((Spacer(1,10),cell("Angaben der Prüfperson",13,INK,"Helvetica-Bold"),
                      details(exam)))
    if simulated:
        note="SIMULATION / KEINE ELEKTRISCHE PRÜFUNG. Keine Messwerte vorhanden."
    else:
        note=("Messwerte und Prüfergebnis vom BENNING ST 725 übernommen. " if original else "")
        note+="Die verantwortliche Prüfperson beurteilt die vollständige Prüfung und entscheidet, ob das Gerät freigegeben werden darf."
    story.extend((Spacer(1,10),cell(note,9,MUTED)))
    doc.build(story,onFirstPage=frame,onLaterPages=frame)
    return out.getvalue()
