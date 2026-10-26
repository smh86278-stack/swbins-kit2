# -*- coding: utf-8 -*-
"""작은 xlsx 쓰기 — 의존성 없이(이 PC 는 pip 가 막혀 있다) zipfile 로 엑셀 파일을 만든다.

시트 = (이름, 행 목록, 열 너비 목록). 칸은 문자열·숫자·None, 또는 dict:
  {"v": 값, "s": "head"|"num"|"bnum"|"bold"|"note", "f": "SUM(E2:E9)"}   (f 가 있으면 v 는 미리 계산해 둔 값)
첫 행은 머리글로 고정(틀 고정). 수식은 엑셀이 열 때 다시 계산한다(fullCalcOnLoad).
"""
import io
import zipfile
from xml.sax.saxutils import escape

STYLES = {None: 0, "head": 1, "num": 2, "bnum": 3, "bold": 4, "note": 5}

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="11"/><name val="맑은 고딕"/></font><font><b/><sz val="11"/><name val="맑은 고딕"/></font><font><sz val="10"/><color rgb="FF6B7280"/><name val="맑은 고딕"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEEF2FF"/></patternFill></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="6">
<xf/>
<xf fontId="1" fillId="2" applyFont="1" applyFill="1"/>
<xf numFmtId="3" applyNumberFormat="1"/>
<xf numFmtId="3" fontId="1" applyNumberFormat="1" applyFont="1"/>
<xf fontId="1" applyFont="1"/>
<xf fontId="2" applyFont="1"/>
</cellXfs>
</styleSheet>"""


def col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, c):
    if not isinstance(c, dict):
        c = {"v": c}
    v, s, f = c.get("v"), STYLES[c.get("s")], c.get("f")
    if s == 0 and isinstance(v, (int, float)) and not isinstance(v, bool):
        s = STYLES["num"]
    attr = ' r="%s"%s' % (ref, ' s="%d"' % s if s else "")
    if f:
        return '<c%s><f>%s</f><v>%s</v></c>' % (attr, escape(f), v if v is not None else 0)
    if v is None or v == "":
        return '<c%s/>' % attr if s else ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return '<c%s><v>%s</v></c>' % (attr, v)
    return '<c%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (attr, escape(str(v)))


def _sheet(rows, widths):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>']
    if widths:
        out.append("<cols>%s</cols>" % "".join('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (i + 1, i + 1, w) for i, w in enumerate(widths)))
    out.append("<sheetData>")
    for r, row in enumerate(rows, 1):
        out.append('<row r="%d">%s</row>' % (r, "".join(_cell("%s%d" % (col(i), r), c) for i, c in enumerate(row))))
    out.append("</sheetData></worksheet>")
    return "".join(out)


def build(sheets):
    """[(이름, 행들, 열 너비들)] → xlsx 바이트."""
    n = len(sheets)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(n))
                   + "</Types>")
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(name[:31]), i + 1, i + 1) for i, (name, _, _) in enumerate(sheets))
                   + '</sheets><calcPr fullCalcOnLoad="1"/></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(n))
                   + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' % (n + 1))
        z.writestr("xl/styles.xml", STYLES_XML)
        for i, (_, rows, widths) in enumerate(sheets):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), _sheet(rows, widths))
    return buf.getvalue()
