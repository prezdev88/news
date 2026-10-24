from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from urllib.parse import quote, urlparse

import cairo

from .config import AppError
from .sorting import alphabetical_key

SIZES = {"A4": (595.276, 841.89), "Carta": (612.0, 792.0)}
INK = (0.0, 0.0, 0.0)
GRAY = (0.32, 0.32, 0.32)
RULE = (0.65, 0.65, 0.65)
SERIF = "Liberation Serif"
SANS = "DejaVu Sans"
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


class LayoutOverflowError(AppError):
    """The edition needs shorter writing to fit without omitting articles."""


@dataclass(frozen=True)
class StoryStyle:
    headline_size: float
    body_size: float
    section_gap: float = 17
    paragraph_gap: float = 10
    source_gap: float = 12
    source_height: float = 24
    body_leading: float = 1.3
    source_single_line: bool = False


NORMAL = (StoryStyle(30, 11.2), StoryStyle(15.5, 10.1))
COMPACT = (
    StoryStyle(26, 10.8, 13, 7, 8, 11, 1.25, True),
    StoryStyle(14, 10.1, 12, 6, 8, 11, 1.25, True),
)
TIGHT = (
    StoryStyle(24, 10.5, 13, 7, 8, 11, 1.24, True),
    StoryStyle(13.2, 9.8, 12, 6, 8, 11, 1.24, True),
)
FLOW = (
    StoryStyle(20, 10.5, 12, 6, 6, 11, 1.24, True),
    StoryStyle(13.2, 9.8, 9, 4, 5, 11, 1.24, True),
)


class Typesetter:
    def __init__(self, context, links=False):
        self.context = context
        self.links = links
        # Recording and PDF surfaces must measure the same unrounded glyphs.
        options = context.get_font_options()
        options.set_hint_metrics(cairo.HINT_METRICS_OFF)
        context.set_font_options(options)

    def font(self, size, family=SERIF, bold=False, italic=False):
        self.context.select_font_face(family, cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        self.context.set_font_size(size)

    def width(self, value):
        return self.context.text_extents(value).x_advance

    def text(self, value, x, top, size=10, family=SERIF, bold=False, italic=False, color=INK, align="left", box_width=0):
        self.font(size, family, bold, italic)
        if align == "center":
            x += (box_width - self.width(value)) / 2
        elif align == "right":
            x += box_width - self.width(value)
        self.context.set_source_rgb(*color)
        self.context.move_to(x, top + self.context.font_extents()[0])
        self.context.show_text(value)

    def lines(self, text, width, size, family=SERIF, bold=False, italic=False):
        self.font(size, family, bold, italic)
        lines = []
        current = ""
        for word in text.split():
            if self.width(word) > width:
                if current:
                    lines.append(current)
                    current = ""
                piece = ""
                for letter in word:
                    if piece and self.width(piece + letter) > width:
                        lines.append(piece)
                        piece = letter
                    else:
                        piece += letter
                current = piece
            elif current and self.width(current + " " + word) > width:
                lines.append(current)
                current = word
            else:
                current = (current + " " + word).strip()
        if current:
            lines.append(current)
        return lines

    def paragraph(self, value, x, top, width, size=10, leading=None, family=SERIF, bold=False, italic=False, color=INK):
        leading = leading or size * 1.28
        lines = self.lines(value, width, size, family, bold, italic)
        for index, line in enumerate(lines):
            self.text(line, x, top + index * leading, size, family, bold, italic, color)
        return len(lines) * leading

    def rule(self, x, y, width, weight=0.5, color=RULE):
        self.context.set_source_rgb(*color)
        self.context.set_line_width(weight)
        self.context.move_to(x, y)
        self.context.line_to(x + width, y)
        self.context.stroke()

    def source(self, story, x, top, width, single_line=False):
        article = story["article"]
        timestamp = article.published.strftime("%d/%m · %H:%M")
        label = f"{article.source} · {timestamp}" + (" ↗" if single_line else "")
        self.font(7.2, SANS)
        size = min(7.2, 7.2 * width / max(self.width(label), 1))
        add_link = self.links and urlparse(article.url).scheme in {"http", "https"}
        if add_link:
            url = quote(article.url, safe=":/?=&%-._~#")
            link_height = 11 if single_line else 23
            self.context.tag_begin(cairo.TAG_LINK, f"uri='{url}' rect=[{x} {top} {width} {link_height}]")
        self.text(label, x, top, size, SANS, color=GRAY)
        if not single_line:
            self.text("Leer fuente original ↗", x, top + 12, 7.2, SANS, color=GRAY)
        if add_link:
            self.context.tag_end(cairo.TAG_LINK)

    def story_size(self, story, width, style):
        section_lines = self.lines(story["section"].upper(), width, 7.5, SANS, bold=True)
        headline_lines = self.lines(story["headline"], width, style.headline_size, bold=True)
        body_lines = self.lines(story["summary"], width, style.body_size)
        return (
            style.section_gap + max(0, len(section_lines) - 1) * 10 + len(headline_lines) * style.headline_size * 1.02
            + style.paragraph_gap + len(body_lines) * style.body_size * style.body_leading
            + style.source_gap + style.source_height
        )

    def draw_story(self, story, x, top, width, style):
        section_lines = self.lines(story["section"].upper(), width, 7.5, SANS, bold=True)
        for index, line in enumerate(section_lines):
            self.text(line, x, top + index * 10, 7.5, SANS, bold=True)
        y = top + style.section_gap + max(0, len(section_lines) - 1) * 10
        y += self.paragraph(story["headline"], x, y, width, style.headline_size, style.headline_size * 1.02, bold=True)
        y += style.paragraph_gap
        y += self.paragraph(story["summary"], x, y, width, style.body_size, style.body_size * style.body_leading)
        self.source(story, x, y + style.source_gap, width, style.source_single_line)


def _flow_plan(typesetter, stories, content_width, available, gap):
    """Balance contiguous stories across columns using measured text heights."""
    best = None
    row_gap = 10
    for columns in (2, 3):
        column_width = (content_width - (columns - 1) * gap) / columns
        heights = [typesetter.story_size(story, column_width, FLOW[0 if index == 0 else 1]) for index, story in enumerate(stories)]
        for cuts in combinations(range(1, len(stories)), columns - 1):
            bounds = (0, *cuts, len(stories))
            groups = [list(range(bounds[index], bounds[index + 1])) for index in range(columns)]
            totals = [sum(heights[index] for index in group) + row_gap * (len(group) - 1) for group in groups]
            needed = max(totals)
            if needed <= available and (best is None or needed < best["needed"]):
                best = {"groups": groups, "heights": heights, "width": column_width, "row_gap": row_gap, "needed": needed}
    return best


def _draw_flow(typesetter, stories, plan, margin, story_top, available, gap):
    for column, group in enumerate(plan["groups"]):
        x = margin + column * (plan["width"] + gap)
        y = story_top
        for position, index in enumerate(group):
            typesetter.draw_story(stories[index], x, y, plan["width"], FLOW[0 if index == 0 else 1])
            y += plan["heights"][index]
            if position < len(group) - 1:
                typesetter.rule(x, y + plan["row_gap"] / 2, plan["width"], 0.5)
                y += plan["row_gap"]
        if column:
            context = typesetter.context
            context.set_source_rgb(*RULE)
            context.set_line_width(0.4)
            context.move_to(x - gap / 2, story_top)
            context.line_to(x - gap / 2, story_top + available)
            context.stroke()


def _draw_masthead(typesetter, edition, margin, content_width, compact=False):
    created = edition["created"]
    date = f"{DAYS[created.weekday()].capitalize()} {created.day} de {MONTHS[created.month - 1]} de {created.year}"
    typesetter.rule(margin, 25, content_width, 1.5, INK)
    typesetter.text("CHILE · EDICIÓN NACIONAL", margin, 33, 7.5, SANS, bold=True)
    typesetter.text("UNA PÁGINA PARA EMPEZAR EL DÍA", margin, 33, 7.0, SANS, align="right", box_width=content_width)
    typesetter.text("La Mañana", margin, 43 if compact else 46, 32 if compact else 46, SERIF, bold=True, align="center", box_width=content_width)
    topic_header = "  /  ".join(sorted({story["section"].upper() for story in edition["stories"]}, key=alphabetical_key))
    topic_lines = typesetter.lines(topic_header, content_width, 7.3, SANS)
    if len(topic_lines) > 2:
        last_line = topic_lines[1]
        while last_line and typesetter.width(last_line + "…") > content_width:
            last_line = last_line[:-1]
        topic_lines = [topic_lines[0], last_line + "…"]
    for index, line in enumerate(topic_lines):
        top = 82 if compact else 98 if len(topic_lines) == 1 else 94
        typesetter.text(line, margin, top + index * 8, 7.3, SANS, align="center", box_width=content_width)
    typesetter.rule(margin, 103 if compact else 116, content_width, 1.6, INK)
    typesetter.rule(margin, 106 if compact else 120, content_width, 0.4, INK)
    typesetter.text(date, margin, 113 if compact else 128, 8.1, SANS)
    if edition.get("demo"):
        right = "MAQUETA · CONTENIDO DE EJEMPLO"
    else:
        right = f"CIERRE {created:%H:%M} · ÚLTIMAS {edition['lookback_hours']} H"
    typesetter.text(right, margin, 113 if compact else 128, 6.9, SANS, align="right", box_width=content_width)
    typesetter.rule(margin, 127 if compact else 149, content_width, 0.5, INK)


def _draw_page(context, edition, paper, links=False):
    width, height = SIZES[paper]
    context.set_source_rgb(1, 1, 1)
    context.paint()
    typesetter = Typesetter(context, links)
    margin = 32
    content_width = width - 2 * margin
    stories = edition["stories"]
    if not 3 <= len(stories) <= 7:
        raise AppError("La maqueta requiere entre 3 y 7 noticias.")
    footer_y = height - 52
    story_top = 162
    gap = 18
    columns = 3 if len(stories) in {4, 6, 7} else 2
    column_width = (content_width - (columns - 1) * gap) / columns
    remaining = stories[1:]
    rows = math.ceil(len(remaining) / columns)
    lead_gap = 24
    row_gap = 22
    available = footer_y - story_top - 15
    styles = (COMPACT, TIGHT) if len(stories) >= 6 else (NORMAL, COMPACT, TIGHT)
    flow = None
    compact_header = False
    for lead_style, article_style in styles:
        row_heights = [
            max(typesetter.story_size(story, column_width, article_style) for story in remaining[row * columns:(row + 1) * columns])
            for row in range(rows)
        ]
        lead_height = typesetter.story_size(stories[0], content_width, lead_style)
        needed = lead_height + lead_gap + sum(row_heights) + (rows - 1) * row_gap
        if needed <= available:
            break
    else:
        flow = _flow_plan(typesetter, stories, content_width, available, gap)
        if flow is None:
            compact_header = True
            story_top = 132
            available = footer_y - story_top - 15
            flow = _flow_plan(typesetter, stories, content_width, available, gap)
        if flow is None:
            raise LayoutOverflowError(
                f"Las {len(stories)} noticias no caben en una página con letra legible. "
                "Se necesitan resúmenes más breves; no se eliminarán noticias automáticamente."
            )
    _draw_masthead(typesetter, edition, margin, content_width, compact_header)
    if flow is not None:
        _draw_flow(typesetter, stories, flow, margin, story_top, available, gap)
    else:
        extra = available - needed
        typesetter.draw_story(stories[0], margin, story_top, content_width, lead_style)
        y = story_top + lead_height + 13 + extra * 0.25
        typesetter.rule(margin, y, content_width, 1, INK)
        y += 11
        for row in range(rows):
            row_height = row_heights[row] + extra * 0.75 / rows
            group = remaining[row * columns:(row + 1) * columns]
            for index, story in enumerate(group):
                x = margin + index * (column_width + gap)
                typesetter.draw_story(story, x, y, column_width, article_style)
                if index:
                    context.set_source_rgb(*RULE)
                    context.set_line_width(0.4)
                    context.move_to(x - gap / 2, y)
                    context.line_to(x - gap / 2, y + row_height - 5)
                    context.stroke()
            y += row_height
            if row < rows - 1:
                typesetter.rule(margin, y + row_gap / 2, content_width, 0.5)
                y += row_gap

    typesetter.rule(margin, footer_y, content_width, 1.2, INK)
    if edition.get("demo"):
        note = "Maqueta de diseño. Estos textos explican la app y no son noticias reales."
    else:
        note = "Resúmenes generados con IA local. Consulta cada medio para leer la información completa."
    typesetter.text(note, margin, footer_y + 10, 7.2, SANS, color=GRAY)
    source_count = len({story["article"].source for story in stories})
    typesetter.text(f"{len(stories)} NOTICIAS · {source_count} {'MEDIO' if source_count == 1 else 'MEDIOS'}", margin, footer_y + 27, 7, SANS, bold=True)
    typesetter.text("LA MAÑANA  /  01", margin, footer_y + 27, 7, SANS, align="right", box_width=content_width)


def render_edition(edition: dict, pdf_path: Path, paper: str = "Carta", *, preview: bool = True) -> Path:
    if paper not in SIZES:
        raise AppError("El papel debe ser A4 o Carta.")
    width, height = SIZES[paper]
    recording = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, (0, 0, width, height))
    _draw_page(cairo.Context(recording), edition, paper)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = pdf_path.with_suffix(".pdf.tmp")
    try:
        surface = cairo.PDFSurface(str(temporary), width, height)
        surface.set_metadata(cairo.PDF_METADATA_TITLE, "La Mañana · Chile")
        surface.set_metadata(cairo.PDF_METADATA_AUTHOR, "La Mañana · IA local")
        context = cairo.Context(surface)
        _draw_page(context, edition, paper, links=True)
        context.show_page()
        surface.finish()
        temporary.replace(pdf_path)
        if preview:
            image = cairo.ImageSurface(cairo.FORMAT_RGB24, round(width * 1.6), round(height * 1.6))
            image_context = cairo.Context(image)
            image_context.scale(1.6, 1.6)
            image_context.set_source_surface(recording, 0, 0)
            image_context.paint()
            image.write_to_png(str(pdf_path.with_suffix(".png")))
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return pdf_path
