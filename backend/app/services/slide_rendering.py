"""Prepare an isolated PPTX copy for the preview renderer.

Text extraction always uses the original upload. Rendering uses installed fonts
consistently instead of letting embedded and unavailable font faces produce
incompatible text metrics. Never change text-box dimensions or font sizes here.
"""

import logging
import re
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

logger = logging.getLogger(__name__)
DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
PRESENTATION = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": DRAWING, "p": PRESENTATION}
STYLE_SUFFIX = re.compile(
    r"[\s_-]+(semi[\s_-]*bold|demi[\s_-]*bold|extra[\s_-]*bold|bold|italics?|oblique|regular)$",
    re.IGNORECASE,
)


def installed_font_families() -> set[str]:
    try:
        result = subprocess.run(
            ["fc-list", "--format", "%{family}\\n"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception("Could not inventory installed fonts; retaining source font names")
        return set()
    return {
        family.strip().casefold()
        for line in result.stdout.splitlines()
        for family in line.split(",")
        if family.strip()
    }


def fallback_font(name: str, installed: set[str]) -> tuple[str, bool, bool] | None:
    if not name or name.startswith("+") or name.casefold() in installed:
        return None
    base = name
    while (match := STYLE_SUFFIX.search(base)) is not None:
        base = base[: match.start()]
    if base.casefold() in installed:
        return None
    # Symbol fonts encode glyphs rather than ordinary text; replacing those
    # with a sans-serif font would turn icons/bullets into different characters.
    if any(
        word in name.casefold() for word in ("symbol", "dingbat", "wingding", "webding", "emoji")
    ):
        return None
    lower = name.casefold()
    if any(word in lower for word in ("mono", "courier", "consolas", "menlo")):
        candidates = ("Courier New", "Liberation Mono", "DejaVu Sans Mono")
    elif "sans" not in lower and any(
        word in lower
        for word in ("serif", "times", "georgia", "cambria", "garamond", "baskerville")
    ):
        candidates = ("Times New Roman", "Liberation Serif", "DejaVu Serif")
    else:
        candidates = ("Arial", "Liberation Sans", "DejaVu Sans")
    replacement = next((font for font in candidates if font.casefold() in installed), None)
    if replacement is None:
        return None
    return replacement, "bold" in lower, "italic" in lower or "oblique" in lower


def normalize_preview_xml(data: bytes, fonts: set[str]) -> tuple[bytes, dict[str, str], int]:
    root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    substitutions: dict[str, str] = {}
    numbering_changes = 0
    for font in root.iter():
        if font.tag not in {f"{{{DRAWING}}}latin", f"{{{DRAWING}}}ea", f"{{{DRAWING}}}cs"}:
            continue
        name = font.get("typeface", "")
        replacement = fallback_font(name, fonts)
        if replacement is None:
            continue
        family, bold, italic = replacement
        font.set("typeface", family)
        parent = font.getparent()
        if parent.tag in {f"{{{DRAWING}}}{tag}" for tag in ("rPr", "defRPr", "endParaRPr")}:
            if bold:
                parent.set("b", "1")
            if italic:
                parent.set("i", "1")
        substitutions[name] = family

    for body in root.findall(".//p:txBody", NS):
        previous = None
        for paragraph in body.findall("a:p", NS):
            properties = paragraph.find("a:pPr", NS)
            number = paragraph.find("a:pPr/a:buAutoNum", NS)
            if number is None:
                previous = None
                continue
            signature = (properties.get("lvl", "0"), number.get("type"), number.get("startAt", "1"))
            # PowerPoint continues adjacent identical list settings. LibreOffice
            # restarts on every repeated startAt; retain the first start only.
            if signature == previous and "startAt" in number.attrib:
                number.attrib.pop("startAt")
                numbering_changes += 1
            previous = signature
    if not substitutions and not numbering_changes:
        return data, substitutions, numbering_changes
    return (
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True),
        substitutions,
        numbering_changes,
    )


def prepare_render_copy(source: Path, temporary_directory: Path) -> Path:
    fonts = installed_font_families()
    destination = temporary_directory / "render-input" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    substitutions: dict[str, str] = {}
    numbering_changes = 0
    with ZipFile(source) as original, ZipFile(destination, "w", ZIP_DEFLATED) as rendered:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename.startswith("ppt/") and entry.filename.endswith(".xml"):
                data, changed, numbered = normalize_preview_xml(data, fonts)
                substitutions.update(changed)
                numbering_changes += numbered
            rendered.writestr(entry, data)
    logger.info(
        "Preview compatibility fonts=%s numbering_changes=%s source=%s",
        substitutions,
        numbering_changes,
        source.name,
    )
    return destination
