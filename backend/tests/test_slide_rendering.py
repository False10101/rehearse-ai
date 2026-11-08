from hashlib import sha256
from zipfile import ZipFile

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

from app.services import slide_rendering
from app.services.slide_rendering import (
    NS,
    fallback_font,
    normalize_preview_xml,
    prepare_render_copy,
)


def test_fallback_preserves_available_and_symbol_fonts():
    installed = {"arial", "times new roman", "courier new", "example sans"}
    for font in ("Arial", "Example Sans", "Example Sans Bold", "+mn-lt", "Wingdings", "Symbol"):
        assert fallback_font(font, installed) is None
    assert fallback_font("Missing Sans Bold Italics", installed) == ("Arial", True, True)
    assert fallback_font("Missing Serif", installed)[0] == "Times New Roman"
    assert fallback_font("Missing Mono", installed)[0] == "Courier New"
    assert fallback_font("Missing Sans", set()) is None
    assert fallback_font("Missing Sans", {"liberation sans"})[0] == "Liberation Sans"


def test_font_inventory_handles_aliases_and_failure(monkeypatch):
    class Result:
        stdout = "Arial,Arial Normal\nLiberation Sans\n"

    monkeypatch.setattr(slide_rendering.subprocess, "run", lambda *a, **kw: Result())
    assert slide_rendering.installed_font_families() == {
        "arial",
        "arial normal",
        "liberation sans",
    }

    def fail(*args, **kwargs):
        raise FileNotFoundError("fc-list missing")

    monkeypatch.setattr(slide_rendering.subprocess, "run", fail)
    assert slide_rendering.installed_font_families() == set()


def test_render_copy_preserves_upload_text_geometry_sizes_and_design_faults(tmp_path, monkeypatch):
    deck = Presentation()
    page = deck.slides.add_slide(deck.slide_layouts[6])
    box = page.shapes.add_textbox(Inches(8), Inches(1), Inches(4), Inches(0.2))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "A heading deliberately outside the slide"
    run.font.name = "Unavailable Sans Bold"
    run.font.size = Pt(42)
    run.font.color.rgb = RGBColor(255, 255, 0)
    source = tmp_path / "upload.pptx"
    deck.save(source)
    before = sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(slide_rendering, "installed_font_families", lambda: {"arial"})
    copied = prepare_render_copy(source, tmp_path / "scratch")
    assert source != copied and sha256(source.read_bytes()).hexdigest() == before
    with ZipFile(source) as original, ZipFile(copied) as preview:
        assert original.namelist() == preview.namelist()
        a = etree.fromstring(original.read("ppt/slides/slide1.xml"))
        b = etree.fromstring(preview.read("ppt/slides/slide1.xml"))
        assert a.xpath(".//a:t/text()", namespaces=NS) == b.xpath(".//a:t/text()", namespaces=NS)
        assert [etree.tostring(x) for x in a.findall(".//a:xfrm", NS)] == [
            etree.tostring(x) for x in b.findall(".//a:xfrm", NS)
        ]
        ar, br = a.find(".//a:rPr", NS), b.find(".//a:rPr", NS)
        assert ar.get("sz") == br.get("sz") == "4200"
        assert br.get("b") == "1"
        assert etree.tostring(ar.find("a:solidFill", NS)) == etree.tostring(
            br.find("a:solidFill", NS)
        )
        assert b.find(".//a:latin", NS).get("typeface") == "Arial"
        for entry in original.namelist():
            if not entry.startswith("ppt/") or not entry.endswith(".xml"):
                assert original.read(entry) == preview.read(entry)


def numbering_xml(entries):
    paragraphs = "".join(
        f'<a:p><a:pPr lvl="{level}"><a:buAutoNum type="arabicPeriod" startAt="{start}"/>'
        f"</a:pPr><a:r><a:t>{i}</a:t></a:r></a:p>"
        if start is not None
        else "<a:p><a:r><a:t>Separator</a:t></a:r></a:p>"
        for i, (level, start) in enumerate(entries)
    )
    return (
        f'<p:sp xmlns:p="{slide_rendering.PRESENTATION}" '
        f'xmlns:a="{slide_rendering.DRAWING}"><p:txBody>{paragraphs}</p:txBody></p:sp>'
    ).encode()


def test_numbering_continues_but_preserves_new_lists_and_changed_starts():
    source = numbering_xml([(1, 1), (1, 1), (1, 1), (1, 5), (1, None), (1, 1), (2, 1)])
    converted, _, count = normalize_preview_xml(source, set())
    markers = etree.fromstring(converted).findall(".//a:buAutoNum", NS)
    assert [n.get("startAt") for n in markers] == ["1", None, None, "5", "1", "1"]
    assert count == 2


def test_unchanged_xml_is_retained_byte_for_byte():
    source = (
        b'<a:rPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        b'<a:latin typeface="Arial"/></a:rPr>'
    )
    assert normalize_preview_xml(source, {"arial"}) == (source, {}, 0)
