#!/usr/bin/env python3

import argparse
import json
import shutil
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


ORANGE = RGBColor(244, 126, 31)
DARK_ORANGE = RGBColor(235, 101, 32)
GRAY = RGBColor(156, 158, 160)
DARK_GRAY = RGBColor(75, 75, 77)
LIGHT_GRAY = RGBColor(242, 242, 242)
WHITE = RGBColor(255, 255, 255)
BLACK = RGBColor(35, 35, 35)
GREEN = RGBColor(73, 145, 92)
RED = RGBColor(194, 67, 67)

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = SKILL_ROOT / "assets" / "Yakov Elmaleh Presentation Template.pptx"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create or extend a sprint PowerPoint using the bundled thesis template."
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a clean sprint presentation.")
    create.add_argument("--sprint", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--subtitle", default="Yakov Elmaleh")
    create.add_argument("--output", type=Path, required=True)

    append = subparsers.add_parser("append", help="Append an experiment slide block.")
    append.add_argument("--presentation", type=Path, required=True)
    append.add_argument("--spec", type=Path, required=True)
    append.add_argument("--output", type=Path)
    append.add_argument("--in-place", action="store_true")

    return parser.parse_args()


def require_file(path, description):
    if not path.is_file():
        raise FileNotFoundError(f"{description} not found: {path}")


def remove_slide(prs, slide):
    slide_id = slide.slide_id
    for slide_id_element in list(prs.slides._sldIdLst):
        if int(slide_id_element.id) == slide_id:
            prs.part.drop_rel(slide_id_element.rId)
            prs.slides._sldIdLst.remove(slide_id_element)
            return
    raise RuntimeError(f"Could not remove slide {slide_id}")


def set_text(shape, text):
    shape.text_frame.clear()
    shape.text_frame.paragraphs[0].text = text


def create_presentation(args):
    require_file(args.template, "Template")
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite existing presentation: {args.output}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.template, args.output)
    prs = Presentation(args.output)

    for slide in list(prs.slides)[1:]:
        remove_slide(prs, slide)

    title_slide = prs.slides[0]
    if title_slide.shapes.title is None:
        raise RuntimeError("Template title slide has no title placeholder.")
    set_text(title_slide.shapes.title, args.title)

    subtitle = next(
        (shape for shape in title_slide.placeholders if shape.placeholder_format.idx == 1),
        None,
    )
    if subtitle is None:
        raise RuntimeError("Template title slide has no subtitle placeholder.")
    set_text(subtitle, f"{args.subtitle}\n{args.sprint}")

    prs.save(args.output)
    validate(args.output, expected_slides=1)
    print(args.output)


def remove_content_placeholder(slide):
    for shape in list(slide.placeholders):
        if shape.placeholder_format.idx == 1:
            shape._element.getparent().remove(shape._element)


def set_slide_title(slide, text):
    if slide.shapes.title is None:
        raise RuntimeError("Selected template layout has no title placeholder.")
    set_text(slide.shapes.title, text)
    frame = slide.shapes.title.text_frame
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    if len(text) <= 42:
        size = 30
    elif len(text) <= 62:
        size = 26
    else:
        size = 22
    for paragraph in frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(size)


def set_slide_number(slide, number):
    for shape in slide.placeholders:
        if shape.placeholder_format.idx == 12:
            set_text(shape, str(number))
            return


def add_textbox(slide, x, y, width, height, text, size=18, color=BLACK,
                bold=False, align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
    shape = slide.shapes.add_textbox(
        Inches(x), Inches(y), Inches(width), Inches(height)
    )
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.vertical_anchor = valign
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = str(text)
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return shape


def add_rect(slide, x, y, width, height, color, rounded=False, line_color=None):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type, Inches(x), Inches(y), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
    return shape


def add_bullets(slide, x, y, width, height, items, size=17, color=BLACK):
    shape = slide.shapes.add_textbox(
        Inches(x), Inches(y), Inches(width), Inches(height)
    )
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = str(item)
        paragraph.level = 0
        paragraph.font.name = "Arial"
        paragraph.font.size = Pt(size)
        paragraph.font.color.rgb = color
        paragraph.space_after = Pt(8)
        paragraph.text = f"• {paragraph.text}"
    return shape


def add_section_card(slide, x, y, width, height, heading, accent):
    add_rect(slide, x, y, width, height, LIGHT_GRAY, rounded=True, line_color=GRAY)
    add_rect(slide, x, y, 0.12, height, accent)
    add_textbox(slide, x + 0.28, y + 0.18, width - 0.48, 0.4, heading,
                size=18, color=accent, bold=True)


def add_intro_slide(prs, spec):
    slide = prs.slides.add_slide(prs.slide_layouts[7])
    remove_content_placeholder(slide)
    set_slide_title(slide, spec["experiment"])
    set_slide_number(slide, len(prs.slides))

    add_section_card(slide, 0.9, 1.55, 5.55, 4.75, "WHAT IS THE NEW TASK?", ORANGE)
    add_textbox(slide, 1.22, 2.25, 4.9, 3.5, spec["task"], size=22,
                color=DARK_GRAY, valign=MSO_ANCHOR.MIDDLE)

    add_section_card(slide, 6.85, 1.55, 5.55, 4.75, "WHY DO WE NEED IT?", DARK_ORANGE)
    add_bullets(slide, 7.18, 2.18, 4.9, 3.7, spec["why"], size=17)


def metric_rows(data):
    old_metrics = data["old"]["metrics"]
    new_metrics = data["new"]["metrics"]
    keys = list(old_metrics)
    keys.extend(key for key in new_metrics if key not in old_metrics)
    return [
        [key, old_metrics.get(key, "—"), new_metrics.get(key, "—")]
        for key in keys
    ]


def add_table(slide, x, y, width, height, columns, rows, font_size=12,
              column_widths=None):
    table = slide.shapes.add_table(
        len(rows) + 1, len(columns), Inches(x), Inches(y), Inches(width), Inches(height)
    ).table
    if column_widths:
        for index, value in enumerate(column_widths):
            table.columns[index].width = Inches(value)

    values = [columns] + rows
    for row_index, row in enumerate(values):
        for column_index, value in enumerate(row):
            cell = table.cell(row_index, column_index)
            cell.text = str(value)
            cell.fill.solid()
            cell.fill.fore_color.rgb = ORANGE if row_index == 0 else (
                WHITE if row_index % 2 else LIGHT_GRAY
            )
            cell.margin_left = Inches(0.06)
            cell.margin_right = Inches(0.04)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = (
                    PP_ALIGN.LEFT if column_index == 0 else PP_ALIGN.CENTER
                )
                for run in paragraph.runs:
                    run.font.name = "Arial"
                    run.font.size = Pt(font_size)
                    run.font.color.rgb = WHITE if row_index == 0 else BLACK
                    run.font.bold = row_index == 0
    return table


def add_data_slide(prs, spec):
    slide = prs.slides.add_slide(prs.slide_layouts[7])
    remove_content_placeholder(slide)
    set_slide_title(slide, f"{spec['experiment']} — Data Analysis")
    set_slide_number(slide, len(prs.slides))

    data = spec["data"]
    add_textbox(slide, 0.95, 1.42, 3.85, 0.42, data["old"]["name"],
                size=19, color=GRAY, bold=True, align=PP_ALIGN.CENTER)
    add_textbox(slide, 8.55, 1.42, 3.85, 0.42, data["new"]["name"],
                size=19, color=ORANGE, bold=True, align=PP_ALIGN.CENTER)

    rows = metric_rows(data)
    add_table(
        slide,
        1.0,
        1.95,
        11.35,
        min(3.8, 0.52 * (len(rows) + 1)),
        ["Data item", data["old"]["name"], data["new"]["name"]],
        rows,
        font_size=12,
        column_widths=[3.4, 3.95, 4.0],
    )

    notes = data.get("notes", [])
    if notes:
        note_y = 2.08 + min(3.8, 0.52 * (len(rows) + 1))
        add_rect(slide, 1.0, note_y, 11.35, 0.95, LIGHT_GRAY, rounded=True, line_color=GRAY)
        add_textbox(slide, 1.2, note_y + 0.12, 1.15, 0.28, "Analysis", 13, ORANGE, True)
        add_bullets(slide, 2.25, note_y + 0.09, 9.75, 0.72, notes, size=11)


def numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Bar-chart value is not numeric: {value!r}")


def add_bar_results(slide, results):
    columns = results["columns"]
    category_index = columns.index(results["category_column"])
    value_index = columns.index(results["value_column"])
    pairs = [
        (str(row[category_index]), numeric(row[value_index]))
        for row in results["rows"]
    ]
    if not pairs:
        raise ValueError("Bar chart requires at least one result row.")

    maximum = max(value for _, value in pairs)
    if maximum <= 0:
        raise ValueError("Bar chart values must include a positive number.")

    y = 1.72
    available_height = 4.85
    row_height = min(0.62, available_height / len(pairs))
    for label, value in pairs:
        add_textbox(slide, 1.0, y, 2.55, row_height, label, 12, DARK_GRAY, True,
                    valign=MSO_ANCHOR.MIDDLE)
        add_rect(slide, 3.7, y + 0.11, 7.25, max(0.18, row_height - 0.2), LIGHT_GRAY,
                 rounded=True)
        add_rect(slide, 3.7, y + 0.11, 7.25 * value / maximum,
                 max(0.18, row_height - 0.2), ORANGE, rounded=True)
        add_textbox(slide, 11.15, y, 1.05, row_height, f"{value:.3f}", 12,
                    DARK_GRAY, True, PP_ALIGN.RIGHT, MSO_ANCHOR.MIDDLE)
        y += row_height


def add_results_slide(prs, spec):
    slide = prs.slides.add_slide(prs.slide_layouts[7])
    remove_content_placeholder(slide)
    set_slide_title(slide, f"{spec['experiment']} — Results")
    set_slide_number(slide, len(prs.slides))

    results = spec["results"]
    visual = results.get("visual", "table")
    if visual == "table":
        rows = results["rows"]
        columns = results["columns"]
        font_size = 12 if len(rows) <= 10 else 9
        height = min(5.25, 0.42 * (len(rows) + 1))
        add_table(slide, 0.85, 1.45, 11.65, height, columns, rows, font_size=font_size)
    elif visual == "bar":
        add_bar_results(slide, results)
    else:
        raise ValueError(f"Unsupported results.visual: {visual!r}")


def add_conclusions_slide(prs, spec):
    slide = prs.slides.add_slide(prs.slide_layouts[7])
    remove_content_placeholder(slide)
    set_slide_title(slide, "Conclusions")
    set_slide_number(slide, len(prs.slides))

    conclusions = spec["conclusions"]
    add_section_card(slide, 0.9, 1.55, 5.55, 4.75, "FINDINGS", GREEN)
    add_bullets(slide, 1.22, 2.18, 4.9, 3.7, conclusions["findings"], size=16)
    add_section_card(slide, 6.85, 1.55, 5.55, 4.75, "NEXT STEPS", ORANGE)
    add_bullets(slide, 7.18, 2.18, 4.9, 3.7, conclusions["next_steps"], size=16)


def load_spec(path):
    require_file(path, "Experiment specification")
    with path.open(encoding="utf-8") as stream:
        spec = json.load(stream)
    required = ["experiment", "task", "why", "data", "results", "conclusions"]
    missing = [field for field in required if field not in spec]
    if missing:
        raise ValueError(f"Experiment specification is missing: {', '.join(missing)}")
    return spec


def append_presentation(args):
    require_file(args.presentation, "Presentation")
    spec = load_spec(args.spec)

    if args.in_place and args.output:
        raise ValueError("Use either --in-place or --output, not both.")
    if args.in_place:
        output = args.presentation
    elif args.output:
        output = args.output
    else:
        output = args.presentation.with_name(
            f"{args.presentation.stem}-updated{args.presentation.suffix}"
        )

    if output.exists() and output != args.presentation:
        raise FileExistsError(f"Refusing to overwrite existing presentation: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation(args.presentation)
    initial_count = len(prs.slides)

    if spec.get("include_intro", True):
        add_intro_slide(prs, spec)
    add_data_slide(prs, spec)
    add_results_slide(prs, spec)
    if spec.get("include_conclusions", True):
        add_conclusions_slide(prs, spec)

    prs.save(output)
    validate(output, expected_slides=len(prs.slides))
    print(f"{output} ({initial_count} -> {len(prs.slides)} slides)")


def validate(path, expected_slides):
    reopened = Presentation(path)
    if len(reopened.slides) != expected_slides:
        raise RuntimeError(
            f"Saved presentation has {len(reopened.slides)} slides; expected {expected_slides}."
        )


def main():
    args = parse_args()
    try:
        if args.command == "create":
            create_presentation(args)
        else:
            append_presentation(args)
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
