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

from benning_csv import outcome
from benning_output import measurement_state, selected_fields, show_value
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
        return Paragraph(escape(str(value) or "fehlt"),style)

    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=42,rightMargin=42,
                          topMargin=158,bottomMargin=61,
                          title="Repair Café Riehen - BENNING Prüfprotokoll",
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
        pdf.drawString(42,height-115,"BENNING ST 725  /  Prüfprotokoll")
        pdf.setStrokeColor(PALE)
        pdf.line(42,49,width-42,49)
        pdf.setFillColor(MUTED)
        pdf.setFont(font,9)
        pdf.drawString(42,33,"FMI / Repair Café Riehen · Importiertes Testergebnis")
        pdf.drawRightString(width-42,33,str(pdf.getPageNumber()))
        pdf.restoreState()

    source=SOURCES[report["import_source"]]
    result=report["record"]["verdict"]
    result_colour=GREEN if outcome(result)=="PASS" else RED
    summary=Table([[cell("ORIGINALERGEBNIS DES TESTERS",10,MUTED),
                    cell(source,10,MUTED)],
                   [cell(result,16,result_colour),cell("Messbericht aus dem Gerätespeicher",9,MUTED)]],
                  colWidths=[area*.55,area*.45])
    summary.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PALE),
                                 ("LEFTPADDING",(0,0),(-1,-1),12),
                                 ("BOTTOMPADDING",(0,1),(-1,1),9)]))
    details=Table([[cell(key,9,MUTED),cell(value)] for key,value in selected_fields(report)],
                  colWidths=[130,area-130])
    details.setStyle(TableStyle([("BOTTOMPADDING",(0,0),(-1,-1),5),
                                 ("LINEBELOW",(0,0),(-1,-1),.4,PALE)]))
    rows=[[cell(title,9,white) for title in ("Messung","Originalwert","Grenzwert","Einzelergebnis")]]
    for item in report["measurements"]:
        state,kind=measurement_state(item)
        name=item["name"]+(" / "+item["test"] if item.get("test") else "")
        rows.append([cell(name),cell(show_value(item.get("value"),item.get("unit"))),
                     cell(show_value(item.get("limit"),item.get("limit_unit"))),
                     cell(state,9,{"PASS":GREEN,"FAIL":RED,"partial":AMBER,"missing":MUTED}[kind])])
    measurements=Table(rows,colWidths=[100,105,105,area-310],repeatRows=1,hAlign="LEFT")
    measurements.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),
                                      ("ROWBACKGROUNDS",(0,1),(-1,-1),[PALE,white]),
                                      ("VALIGN",(0,0),(-1,-1),"TOP"),
                                      ("TOPPADDING",(0,0),(-1,-1),6),
                                      ("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story=[summary,Spacer(1,12),details,Spacer(1,13),
           cell("Messwerte und verfügbare Grenzwerte",13,INK,"Helvetica-Bold"),
           Spacer(1,5),measurements,Spacer(1,12),
           cell("Die Printstation übernimmt das originale Testergebnis. Sie erteilt keine Sicherheitsfreigabe.",9,MUTED)]
    doc.build(story,onFirstPage=frame,onLaterPages=frame)
    return out.getvalue()
