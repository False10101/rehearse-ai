"""One slide scene shared by the PowerPoint writer and browser previews.

Coordinates and font sizes are pixels on a 1280 x 720 canvas. The writer scales
the entire scene uniformly, including type, to the uploaded presentation.
"""

import math

AGENDA_LAYOUTS = {
    "paired-sections": "Numbered sections",
    "editorial-list": "Minimal sidebar",
    "ruled-list": "Ruled rows",
    "statement-grid": "Statement grid",
    "capsule-columns": "Diamond capsules",
}

# Each theme supplies coordinated section accents, not one repeated color.
AGENDA_THEMES = {
    "violet": ["7051BA", "8B5EA7", "5268AC", "A54C83", "557F95", "76649C"],
    "ocean": ["147CA1", "2470A8", "26968E", "385C9B", "328BB4", "286C7C"],
    "forest": ["367654", "648139", "368784", "69854F", "2B675E", "7A742D"],
    "sunset": ["C55446", "B27420", "B44274", "A85B39", "91722D", "976083"],
    "midnight": ["283F70", "3E6290", "4F5886", "3B747E", "615A86", "4B708E"],
    "slate": ["475569", "64748B", "526B72", "716A83", "586577", "687C83"],
}

PREVIEW_ITEMS = [
    {"title": "The challenge", "description": "The problem our project sets out to address."},
    {
        "title": "Research approach",
        "description": "How we gathered evidence and explored the context.",
    },
    {"title": "Key findings", "description": "The patterns and insights that shaped our work."},
    {
        "title": "Proposed solution",
        "description": "Our response to the needs identified in the research.",
    },
    {"title": "Evaluation", "description": "What we tested and what the results revealed."},
    {"title": "Future direction", "description": "The opportunities we will explore next."},
]


def theme_colors(name: str) -> dict[str, str]:
    return {
        "paper": "FFFFFF",
        "ink": "253047",
        "muted": "667085",
        "rule": "DCE3EB",
        **{f"accent{i}": color for i, color in enumerate(AGENDA_THEMES[name])},
        **{f"tint{i}": _tint(color) for i, color in enumerate(AGENDA_THEMES[name])},
    }


def _tint(color: str) -> str:
    return "".join(f"{round(int(color[i : i + 2], 16) * 0.18 + 255 * 0.82):02X}" for i in (0, 2, 4))


def _wrap(text: str, width: float, size: float, bold: bool) -> list[str]:
    # Conservative advances avoid depending on Mac-only fonts for Ubuntu output.
    # Explicit line breaks are shared with SVG, so the preview and PPTX agree.
    def measure(word):
        return (
            sum(
                0.9 if c in "MW@%" else 0.3 if c in "il.,'!:;|" else 0.66 if c.isupper() else 0.56
                for c in word
            )
            * size
            * (1.04 if bold else 1)
        )

    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if line and measure(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
        if measure(word) > width:
            raise ValueError("An agenda word is too long to fit the selected layout.")
    if line:
        lines.append(line)
    return lines


def agenda_scene(items: list[dict[str, str]], layout: str) -> list[dict]:
    if layout not in AGENDA_LAYOUTS or not 4 <= len(items) <= 6:
        raise ValueError("Choose one of the five layouts with four to six sections.")
    nodes: list[dict] = []

    def rect(x, y, w, h, color, radius=0, stroke=None, rotation=0):
        nodes.append(
            dict(
                kind="rect",
                x=x,
                y=y,
                w=w,
                h=h,
                color=color,
                radius=radius,
                stroke=stroke,
                rotation=rotation,
            )
        )

    def line(x, y, x2, y2, color="rule", weight=1):
        nodes.append(dict(kind="line", x=x, y=y, x2=x2, y2=y2, color=color, weight=weight))

    def text(value, x, y, w, h, size, color="ink", bold=False, align="left", serif=False):
        lines = _wrap(value, w, size, bold)
        while len(lines) * size * 1.2 > h and size > 15:
            size -= 1
            lines = _wrap(value, w, size, bold)
        if len(lines) * size * 1.2 > h:
            raise ValueError("Agenda text exceeds its layout space. Shorter wording is required.")
        nodes.append(
            dict(
                kind="text",
                x=x,
                y=y,
                w=w,
                h=h,
                size=size,
                color=color,
                bold=bold,
                align=align,
                serif=serif,
                lines=lines,
            )
        )

    def icon(index, x, y, color):
        # Six simple editable symbols: flag, search, bars, target, checklist, arrow.
        if index == 0:
            line(x, y, x, y + 30, color, 2.5)
            line(x, y, x + 25, y + 4, color, 2.5)
            line(x + 25, y + 4, x + 20, y + 15, color, 2.5)
            line(x + 20, y + 15, x, y + 11, color, 2.5)
        elif index in (1, 3):
            nodes.append(dict(kind="circle", x=x, y=y, w=23, h=23, color=color))
            if index == 1:
                line(x + 20, y + 20, x + 30, y + 30, color, 2.5)
            else:
                nodes.append(dict(kind="circle", x=x + 7, y=y + 7, w=9, h=9, color=color))
        elif index == 2:
            for j, height in enumerate((12, 22, 30)):
                rect(x + j * 11, y + 30 - height, 6, height, color, 1)
        elif index == 4:
            for j in range(3):
                line(x, y + j * 11, x + 3, y + j * 11 + 3, color, 2)
                line(x + 3, y + j * 11 + 3, x + 8, y + j * 11 - 3, color, 2)
                line(x + 14, y + j * 11, x + 30, y + j * 11, color, 2)
        else:
            line(x, y + 28, x + 28, y, color, 2.5)
            line(x + 12, y, x + 28, y, color, 2.5)
            line(x + 28, y, x + 28, y + 16, color, 2.5)

    count = len(items)
    rows = math.ceil(count / 2)
    if layout in ("paired-sections", "ruled-list", "capsule-columns"):
        text(
            "Agenda",
            100,
            42,
            1080,
            64,
            42,
            bold=True,
            align="center",
            serif=layout == "paired-sections",
        )

    if layout == "paired-sections":
        rect(0, 0, 32, 32, "accent0")
        rect(24, 22, 22, 22, "tint0")
        for i, item in enumerate(items):
            column, row = divmod(i, rows)
            x, y = 96 + column * 580, 176 + row * (470 / rows)
            text(f"{i + 1:02}", x, y, 100, 80, 58, f"accent{i}", True, serif=True)
            line(x + 111, y, x + 111, y + 110, f"accent{i}", 3)
            text(item["title"], x + 135, y, 355, 60, 25, f"accent{i}", True, serif=True)
            text(item["description"], x + 135, y + 66, 355, 64, 18, "ink", serif=True)

    elif layout == "editorial-list":
        text("agenda", 66, 298, 275, 80, 52, bold=True)
        rect(68, 398, 88, 6, "accent0")
        line(354, 65, 354, 655)
        for i, item in enumerate(items):
            y = 111 + i * (504 / count)
            text(f"{i + 1:02}", 410, y, 70, 40, 28, f"accent{i}", True)
            text(item["title"], 510, y, 680, 34, 23, bold=True)
            text(item["description"], 510, y + 39, 680, 35, 17, "muted")

    elif layout == "ruled-list":
        step = 520 / count
        for i, item in enumerate(items):
            y = 142 + i * step
            text(f"{i + 1:02}", 92, y + 5, 90, 56, 40, f"accent{i}", True)
            text(item["title"], 214, y + 7, 305, 64, 23, bold=True)
            text(item["description"], 560, y + 8, 620, 65, 19, "muted")
            if i < count - 1:
                line(92, y + step - 12, 1188, y + step - 12, f"accent{i}", 1)

    elif layout == "statement-grid":
        text("Agenda", 70, 278, 310, 80, 57, bold=True)
        text("What we’ll cover", 74, 388, 280, 50, 22, "muted")
        rect(74, 464, 116, 5, "accent0")
        step = 590 / rows
        for i, item in enumerate(items):
            column, row = i % 2, i // 2
            x, y = 480 + column * 375, 58 + row * step
            text(f"{i + 1:02}", x, y, 120, 63, 52, f"accent{i}", True)
            line(x, y + 71, x + 320, y + 71, f"tint{i}", 3)
            text(item["title"], x, y + 88, 320, 55, 23, bold=True)
            text(item["description"], x, y + 146, 320, step - 151, 17, "muted")

    else:  # Diamond-number capsules, down each column like the supplied reference.
        for i, item in enumerate(items):
            column, row = divmod(i, rows)
            x, y = 90 + column * 600, 186 + row * (474 / rows)
            rect(x + 52, y, 452, 124, "paper", 50, f"tint{i}")
            rect(x + 387, y, 73, 112, f"accent{i}", 10)
            rect(x + 397, y + 24, 53, 55, "paper", 8)
            icon(i, x + 409, y + 37, f"accent{i}")
            rect(x + 7, y + 15, 86, 86, f"tint{i}", 6, rotation=45)
            rect(x, y + 9, 86, 86, f"accent{i}", 6, rotation=45)
            text(f"{i + 1:02}", x - 2, y + 28, 90, 56, 37, "paper", True, "center")
            text(item["title"], x + 112, y + 9, 254, 53, 21, f"accent{i}", True)
            text(item["description"], x + 112, y + 62, 254, 59, 16, "ink")
    return nodes


def agenda_catalog() -> dict:
    return {
        "width": 1280,
        "height": 720,
        "themes": {name: theme_colors(name) for name in AGENDA_THEMES},
        "templates": [
            {"id": layout, "name": name, "nodes": agenda_scene(PREVIEW_ITEMS, layout)}
            for layout, name in AGENDA_LAYOUTS.items()
        ],
    }
