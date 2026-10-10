"""Create an Excel feedback workbook without changing the source presentation."""

import io
import json
import zipfile
from xml.sax.saxutils import escape


def feedback_workbook(analysis: dict) -> bytes:
    rows = [
        [
            "Slide",
            "Score",
            "Overload",
            "Overload reason",
            "Visual hierarchy",
            "Suggestions",
            "Table tips",
            "References",
        ]
    ]
    for slide in analysis.get("per_slide", []):
        rows.append(
            [
                slide.get("num"),
                slide.get("slide_score"),
                slide.get("overload"),
                slide.get("overload_reason"),
                slide.get("visual_hierarchy_issues"),
                "\n".join(slide.get("improvement_suggestions", [])),
                "\n".join(slide.get("table_tips", [])),
                "\n".join(slide.get("refs_found", [])),
            ]
        )
    summary = [["Field", "Saved analysis"]]
    for key, value in analysis.items():
        if key != "per_slide":
            summary.append(
                [key, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)]
            )

    def sheet(data):
        body = []
        for index, row in enumerate(data, 1):
            cells = []
            for col, value in enumerate(row):
                # Inline strings prevent spreadsheet formulas in untrusted slide text.
                text = str(value) if value is not None else ""
                text = "".join(c for c in text if c in "\n\r\t" or ord(c) >= 32)
                cells.append(
                    f'<c r="{chr(65 + col)}{index}" t="inlineStr"><is>'
                    f'<t xml:space="preserve">{escape(text[:32767])}</t></is></c>'
                )
            body.append(f'<row r="{index}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
            'state="frozen"/></sheetView></sheetViews>'
            '<cols><col min="1" max="8" width="32" customWidth="1"/></cols>'
            f"<sheetData>{''.join(body)}</sheetData></worksheet>"
        )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-packag"
            "e.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\""
            "/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxml"
            "formats-officedocument.spreadsheetml.sheet.main+xml\"/><Override PartName=\"/x"
            "l/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officed"
            "ocument.spreadsheetml.worksheet+xml\"/><Override PartName=\"/xl/worksheets/she"
            "et2.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsh"
            "eetml.worksheet+xml\"/></Types>",
        )
        archive.writestr(
            "_rels/.rels",
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relatio"
            "nships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/offi"
            "ceDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Re"
            "lationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
            "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            "\"><sheets><sheet name=\"Slide feedback\" sheetId=\"1\" r:id=\"rId1\"/><sheet name="
            "\"Deck summary\" sheetId=\"2\" r:id=\"rId2\"/></sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relatio"
            "nships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/offi"
            "ceDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/><Re"
            "lationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/"
            "2006/relationships/worksheet\" Target=\"worksheets/sheet2.xml\"/></Relationship"
            "s>",
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet(rows))
        archive.writestr("xl/worksheets/sheet2.xml", sheet(summary))
    return output.getvalue()
