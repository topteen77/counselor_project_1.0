"""Convert counsellor course Word files into the database shape.

A module file becomes one chapter. Each numbered section (1.1, 1.2, ...) becomes
one part. The opening pages of a module become a part titled Introduction.
Quizzes become Question and QuizAnswers rows. Lesson text becomes HTML.
"""
from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

CHAPTER_TITLE_LIMIT = 100
PART_TITLE_LIMIT = 100
ANSWER_TEXT_LIMIT = 200
QUESTION_WARN_LENGTH = 200
MAX_SECTION_MINOR = 25

SECTION_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})(?!\.\d)\s+([A-Z0-9])")
SUBSECTION_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{1,2})\s+\S")
QUIZ_RE = re.compile(
    r"^(?:MCQ Assessment\b|Knowledge Check\b.*\bMCQs?\b|MCQs?\b|Multiple Choice Questions\b)",
    re.IGNORECASE,
)
DRAFT_NOTE_RE = re.compile(
    r"^(?:Absolutely\.|Next is\b|The next section\b|With Section\b|Module \d+ Complete\b)",
    re.IGNORECASE,
)
ANSWER_RE = re.compile(r"^Answer:\s*([A-D])\b", re.IGNORECASE)
MODULE_TITLE_RE = re.compile(r"Module\s+(\d+)\s*[:：]\s*(.+)", re.IGNORECASE)
QUESTION_NUM_RE = re.compile(r"^\d+\.\s+")
JAMMED_SECTION_RE = re.compile(r"\d{1,2}\.\d{1,2}")


@dataclass
class Block:
    kind: str
    text: str
    html: str
    is_list: bool = False
    list_num: str | None = None
    ordered: bool = False
    break_only: bool = False


@dataclass
class Issue:
    level: str
    filename: str
    location: str
    message: str

    def as_dict(self):
        return {
            "level": self.level,
            "filename": self.filename,
            "location": self.location,
            "message": self.message,
        }


def norm_space(value: str) -> str:
    value = (value or "").replace("\u00a0", " ").replace("\u200b", "")
    value = value.replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    return value.strip()


def clean_run_text(value: str) -> str:
    """Keep spaces that separate words when Word splits them into separate runs."""
    value = (value or "").replace("\u00a0", " ").replace("\u200b", "")
    if value.strip() == "":
        return " " if value else ""
    return re.sub(r"[ \t]{2,}", " ", value)


def _flag_on(element) -> bool:
    if element is None:
        return False
    val = element.get(qn("w:val"))
    if val is None:
        return True
    return val.lower() not in {"0", "false", "off", "none"}


def _render_run(run_elm) -> str:
    props = run_elm.find(qn("w:rPr"))
    bold = italic = underline = False
    if props is not None:
        bold = _flag_on(props.find(qn("w:b"))) or _flag_on(props.find(qn("w:bCs")))
        italic = _flag_on(props.find(qn("w:i"))) or _flag_on(props.find(qn("w:iCs")))
        underline_elm = props.find(qn("w:u"))
        underline = underline_elm is not None and (underline_elm.get(qn("w:val")) or "single") not in {
            "none",
            "0",
            "false",
        }
    chunks: list[str] = []
    for child in run_elm:
        if child.tag == qn("w:t"):
            chunks.append(html.escape(clean_run_text(child.text or ""), quote=True))
        elif child.tag == qn("w:br"):
            chunks.append("<br>")
        elif child.tag == qn("w:tab"):
            chunks.append(" ")
    rendered = "".join(chunk for chunk in chunks if chunk)
    rendered = re.sub(r"(?:<br>\s*){3,}", "<br><br>", rendered)
    if not re.sub(r"<br>", "", rendered).strip():
        return "<br>" if "<br>" in rendered else ""
    if underline:
        rendered = "<u>%s</u>" % rendered
    if italic:
        rendered = "<em>%s</em>" % rendered
    if bold:
        rendered = "<strong>%s</strong>" % rendered
    return rendered


def _paragraph_html(paragraph: Paragraph) -> str:
    pieces: list[str] = []
    for child in paragraph._p:
        if child.tag == qn("w:r"):
            pieces.append(_render_run(child))
        elif child.tag == qn("w:hyperlink"):
            link_html = "".join(_render_run(run) for run in child.findall(qn("w:r")))
            href = _hyperlink_href(paragraph, child)
            if href and link_html:
                pieces.append('<a href="%s">%s</a>' % (html.escape(href, quote=True), link_html))
            else:
                pieces.append(link_html)
    rendered = "".join(pieces).strip()
    rendered = re.sub(r"(?:<br>\s*){3,}", "<br><br>", rendered)
    return rendered


def _hyperlink_href(paragraph: Paragraph, hyperlink) -> str:
    rel_id = hyperlink.get(qn("r:id"))
    if not rel_id:
        return ""
    try:
        target = paragraph.part.rels[rel_id].target_ref
    except KeyError:
        return ""
    if target.startswith("http://") or target.startswith("https://"):
        return target
    return ""


def _ordered_num_ids(document: DocumentObject) -> set[str]:
    ordered: set[str] = set()
    try:
        numbering = document.part.numbering_part.element
    except Exception:
        return ordered
    abstracts: dict[str, bool] = {}
    for abstract in numbering.findall(qn("w:abstractNum")):
        abstract_id = abstract.get(qn("w:abstractNumId"))
        first_level = None
        for level in abstract.findall(qn("w:lvl")):
            if level.get(qn("w:ilvl")) in {None, "0"}:
                first_level = level
                break
        fmt = ""
        if first_level is not None:
            num_fmt = first_level.find(qn("w:numFmt"))
            if num_fmt is not None:
                fmt = num_fmt.get(qn("w:val")) or ""
        if abstract_id is not None:
            abstracts[abstract_id] = fmt not in {"bullet", "none", ""}
    for num in numbering.findall(qn("w:num")):
        num_id = num.get(qn("w:numId"))
        abstract_ref = num.find(qn("w:abstractNumId"))
        abstract_id = abstract_ref.get(qn("w:val")) if abstract_ref is not None else None
        if num_id and abstracts.get(abstract_id):
            ordered.add(num_id)
    return ordered


def _list_info(paragraph: Paragraph):
    props = paragraph._p.pPr
    if props is None or props.numPr is None:
        return None
    num_id_elm = props.numPr.numId
    if num_id_elm is None:
        return None
    num_id = num_id_elm.get(qn("w:val"))
    if not num_id or num_id == "0":
        return None
    level_elm = props.numPr.ilvl
    level = level_elm.get(qn("w:val")) if level_elm is not None else "0"
    return num_id, level or "0"


def _table_html(table: Table) -> str:
    rows_html: list[str] = []
    for row_index, row in enumerate(table.rows):
        cells: list[str] = []
        seen = []
        for cell in row.cells:
            # Word repeats a merged cell once per grid column. Keep the first copy.
            if seen and cell._tc is seen[-1]:
                continue
            seen.append(cell._tc)
            parts = []
            for paragraph in cell.paragraphs:
                inner = _paragraph_html(paragraph)
                plain = norm_space(paragraph.text)
                if plain or inner:
                    parts.append(inner or html.escape(plain))
            tag = "th" if row_index == 0 else "td"
            cells.append("<%s>%s</%s>" % (tag, "<br>".join(parts), tag))
        if cells:
            rows_html.append("<tr>%s</tr>" % "".join(cells))
    if not rows_html:
        return ""
    return "<table><tbody>%s</tbody></table>" % "".join(rows_html)


def read_blocks(path: str) -> list[Block]:
    document = Document(path)
    ordered_ids = _ordered_num_ids(document)
    blocks: list[Block] = []
    body = document.element.body
    for child in body:
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            text = norm_space(paragraph.text)
            inner = _paragraph_html(paragraph)
            info = _list_info(paragraph)
            break_only = (not text) and ("<br>" in inner)
            blocks.append(
                Block(
                    kind="p",
                    text=text,
                    html=inner,
                    is_list=info is not None and bool(text),
                    list_num=("%s:%s" % info) if info else None,
                    ordered=bool(info and info[0] in ordered_ids),
                    break_only=break_only,
                )
            )
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            table_html = _table_html(table)
            plain = norm_space(re.sub(r"<[^>]+>", " ", table_html))
            if table_html:
                blocks.append(Block(kind="table", text=plain, html=table_html))
    return blocks


def is_section_heading(text: str) -> re.Match | None:
    if not text or len(text) > 160:
        return None
    match = SECTION_RE.match(text)
    if not match:
        return None
    if int(match.group(2)) > MAX_SECTION_MINOR:
        return None
    if JAMMED_SECTION_RE.search(text[match.end():]):
        return None
    return match


def is_quiz_heading(text: str) -> bool:
    return bool(text and QUIZ_RE.match(text))


def looks_like_quiz_text(text: str, following_text: str = "") -> bool:
    if not text:
        return True
    if ANSWER_RE.match(text) or re.match(r"^[A-D]\.\s", text):
        return True
    if re.search(r"(?:^|\n)A\.\s", text) and re.search(r"B\.\s", text):
        return True
    if QUESTION_NUM_RE.match(text) or text.endswith("?"):
        return True
    following = following_text or ""
    if re.match(r"^[A-D]\.\s", following) or ANSWER_RE.match(following):
        return True
    if re.search(r"(?:^|\n)A\.\s", following) and re.search(r"B\.\s", following):
        return True
    return False


def _next_text(blocks, index: int) -> str:
    for later in blocks[index + 1:]:
        if later.text:
            return later.text
    return ""


def logical_lines(text: str) -> list[str]:
    return [norm_space(line) for line in text.split("\n") if norm_space(line)]


def split_options(text: str):
    """Return (question leftover lines, {letter: option text})."""
    marked = re.sub(r"(?<=\S)([A-D])\.\s*", r"\n\1. ", text)
    leftovers: list[str] = []
    options: dict[str, str] = {}
    for line in logical_lines(marked):
        match = re.match(r"^([A-D])\.\s*(.*)$", line)
        if match and match.group(1) not in options:
            options[match.group(1)] = norm_space(match.group(2))
        else:
            leftovers.append(line)
    starts_as_option = bool(re.match(r"^[A-D]\.\s*", text.strip()))
    if options and not starts_as_option and list(options) == ["A"]:
        return [text], {}
    return leftovers, options


def parse_quiz(lines: list[str], filename: str, location: str) -> tuple[list[dict], list[Issue]]:
    issues: list[Issue] = []
    questions: list[dict] = []
    current = None

    def close():
        nonlocal current
        if current is not None:
            questions.append(current)
            current = None

    for line in lines:
        if re.fullmatch(r"[\W_]+", line):
            continue
        answer = ANSWER_RE.match(line)
        if answer:
            if current is None:
                issues.append(Issue("error", filename, location, "Answer line has no question: %s" % line[:120]))
                continue
            if current["correct"]:
                issues.append(Issue("error", filename, location, "Question has two answers: %s" % current["text"][:80]))
            current["correct"] = answer.group(1).upper()
            continue
        leftovers, options = split_options(line)
        if options and not leftovers:
            if current is None:
                issues.append(Issue("error", filename, location, "Options appear before a question: %s" % line[:120]))
                continue
            for letter, option_text in options.items():
                if letter in current["options"]:
                    issues.append(Issue("error", filename, location, "Duplicate option %s in: %s" % (letter, current["text"][:80])))
                current["options"][letter] = option_text
            continue
        if options and leftovers:
            close()
            question_text = QUESTION_NUM_RE.sub("", norm_space(" ".join(leftovers)))
            current = {"text": question_text, "options": options, "correct": None}
            continue
        close()
        current = {
            "text": QUESTION_NUM_RE.sub("", line),
            "options": {},
            "correct": None,
        }
    close()

    cleaned: list[dict] = []
    for index, question in enumerate(questions, start=1):
        letters = [letter for letter in "ABCD" if letter in question["options"]]
        if letters != ["A", "B", "C", "D"]:
            issues.append(
                Issue(
                    "error",
                    filename,
                    location,
                    "Question %s does not have options A B C D (found %s): %s"
                    % (index, ", ".join(letters) or "none", question["text"][:100]),
                )
            )
        if question["correct"] not in question["options"]:
            issues.append(
                Issue(
                    "error",
                    filename,
                    location,
                    "Question %s has no matching answer letter (%s): %s"
                    % (index, question["correct"] or "missing", question["text"][:100]),
                )
            )
        if len(question["text"]) > QUESTION_WARN_LENGTH:
            issues.append(
                Issue(
                    "warning",
                    filename,
                    location,
                    "Question %s is %s characters. The admin edit form limit is %s. The course player can still show it."
                    % (index, len(question["text"]), QUESTION_WARN_LENGTH),
                )
            )
        answers = []
        for letter in "ABCD":
            option_text = question["options"].get(letter, "")
            stored = "%s. %s" % (letter, option_text) if option_text else "%s." % letter
            if len(stored) > ANSWER_TEXT_LIMIT:
                issues.append(
                    Issue(
                        "error",
                        filename,
                        location,
                        "Option %s is %s characters (limit %s): %s" % (letter, len(stored), ANSWER_TEXT_LIMIT, stored[:80]),
                    )
                )
            answers.append({"text": stored, "correct": letter == question["correct"]})
        if question["text"]:
            cleaned.append({"text": question["text"], "answers": answers})
        else:
            issues.append(Issue("error", filename, location, "Question %s has no text." % index))
    if not cleaned:
        issues.append(Issue("error", filename, location, "Quiz heading has no questions."))
    elif len(cleaned) != 5:
        issues.append(
            Issue(
                "warning",
                filename,
                location,
                "This quiz has %s questions. Most sections have 5, so check that none were merged or left out." % len(cleaned),
            )
        )
    return cleaned, issues


def render_body(blocks: list[Block], remove_blank_paragraphs: bool, remove_blank_lines: bool) -> str:
    html_parts: list[str] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if block.kind == "table":
            html_parts.append(block.html)
            index += 1
            continue
        if not block.text:
            if block.break_only and not remove_blank_lines:
                html_parts.append("<p><br></p>")
            elif not block.break_only and not remove_blank_paragraphs:
                html_parts.append("<p></p>")
            index += 1
            continue
        if block.is_list:
            group = [block]
            index += 1
            while (
                index < len(blocks)
                and blocks[index].is_list
                and blocks[index].list_num == block.list_num
                and blocks[index].text
            ):
                group.append(blocks[index])
                index += 1
            tag = "ol" if block.ordered else "ul"
            items = "".join("<li>%s</li>" % item.html for item in group)
            html_parts.append("<%s>%s</%s>" % (tag, items, tag))
            continue
        if SUBSECTION_RE.match(block.text) and len(block.text) <= 160:
            html_parts.append("<h3>%s</h3>" % (block.html or html.escape(block.text)))
        elif is_section_heading(block.text):
            html_parts.append("<h2>%s</h2>" % (block.html or html.escape(block.text)))
        elif block.text in {"Key Takeaway", "What This Means for Education Agents and Counsellors"}:
            inner = block.html if "<strong>" in block.html else "<strong>%s</strong>" % html.escape(block.text)
            html_parts.append("<p>%s</p>" % inner)
        else:
            html_parts.append("<p>%s</p>" % block.html)
        index += 1
    return "".join(html_parts)


def chapter_title_from(text: str, module_number: int) -> str:
    match = MODULE_TITLE_RE.search(text or "")
    if match:
        return "Module %s: %s" % (module_number, norm_space(match.group(2)))
    return "Module %s" % module_number


def convert_module(path: str, filename: str, module_number: int, options: dict) -> tuple[dict, list[Issue]]:
    issues: list[Issue] = []
    try:
        blocks = read_blocks(path)
    except Exception as exc:
        return {}, [Issue("error", filename, "file", "Could not read this Word file: %s" % exc)]

    headings: dict[str, list[int]] = {}
    for index, block in enumerate(blocks):
        match = is_section_heading(block.text)
        if match:
            key = "%s.%s" % (int(match.group(1)), int(match.group(2)))
            headings.setdefault(key, []).append(index)
    heading_indexes = {index for indexes in headings.values() for index in indexes}

    def next_heading(start: int):
        for later in range(start + 1, len(blocks)):
            if later in heading_indexes:
                return later
        return None

    real_indexes = set()
    for key, indexes in headings.items():
        chosen = None
        for index in indexes:
            nxt = next_heading(index)
            gap = (nxt - index) if nxt is not None else 999
            appears_again = any(later > index for later in indexes)
            # The opening list repeats every section title in a few lines.
            # A later copy of the same section, such as a blank form, stays inside the part.
            if appears_again and gap <= 8:
                continue
            chosen = index
            break
        if chosen is None:
            chosen = indexes[-1]
        real_indexes.add(chosen)
        if len(indexes) > 2:
            issues.append(
                Issue(
                    "warning",
                    filename,
                    key,
                    "Section %s appears %s times. The first full copy is the part, and later copies stay inside it."
                    % (key, len(indexes)),
                )
            )

    title_source = next((block.text for block in blocks if block.text), "")
    chapter_title = chapter_title_from(title_source, module_number)
    if len(chapter_title) > CHAPTER_TITLE_LIMIT:
        issues.append(
            Issue(
                "error",
                filename,
                "chapter",
                "Chapter title is %s characters (limit %s): %s" % (len(chapter_title), CHAPTER_TITLE_LIMIT, chapter_title),
            )
        )

    parts: list[dict] = []
    current = {"title": "Introduction", "blocks": [], "quiz_lines": [], "in_quiz": False, "quiz": None}
    table_count = 0

    def flush_quiz():
        if not current["in_quiz"]:
            return
        location = current["title"][:80]
        questions, quiz_issues = parse_quiz(current["quiz_lines"], filename, location)
        issues.extend(quiz_issues)
        if current["title"] == "Introduction":
            issues.append(Issue("error", filename, "Introduction", "A quiz appears before the first numbered section."))
        if current["quiz"] is not None:
            issues.append(Issue("error", filename, location, "This section has more than one quiz."))
        current["quiz"] = {
            "title": ("Quiz: %s" % current["title"])[:200],
            "questions": questions,
        }
        current["quiz_lines"] = []
        current["in_quiz"] = False

    def close_part():
        flush_quiz()
        html_body = render_body(
            current["blocks"],
            options["remove_blank_paragraphs"],
            options["remove_blank_lines"],
        )
        part = {
            "title": current["title"],
            "html": html_body,
            "quiz": current["quiz"],
        }
        if len(part["title"]) > PART_TITLE_LIMIT:
            issues.append(
                Issue(
                    "error",
                    filename,
                    part["title"][:40],
                    "Part title is %s characters (limit %s): %s" % (len(part["title"]), PART_TITLE_LIMIT, part["title"]),
                )
            )
        parts.append(part)

    for index, block in enumerate(blocks):
        if index in real_indexes:
            close_part()
            current = {
                "title": block.text,
                "blocks": [],
                "quiz_lines": [],
                "in_quiz": False,
                "quiz": None,
            }
            continue
        if is_quiz_heading(block.text):
            if current["in_quiz"]:
                flush_quiz()
            current["in_quiz"] = True
            continue
        if current["in_quiz"]:
            quiz_text = looks_like_quiz_text(block.text, _next_text(blocks, index))
            if block.kind == "table" or (block.text and not quiz_text):
                flush_quiz()
            elif block.text:
                current["quiz_lines"].extend(logical_lines(block.text))
                continue
            else:
                continue
        if block.kind == "table":
            table_count += 1
        if DRAFT_NOTE_RE.match(block.text) or block.text == ":::":
            issues.append(
                Issue(
                    "warning",
                    filename,
                    current["title"][:80],
                    "Drafting note was left out of the lesson. Delete it in the Word file if you rerun: %s" % block.text[:90],
                )
            )
            continue
        current["blocks"].append(block)
    close_part()

    if not any(part["title"] != "Introduction" for part in parts):
        issues.append(Issue("error", filename, "sections", "No numbered sections such as 1.1 were found."))

    teaching_parts = [part for part in parts if part["title"] != "Introduction"]
    missing_quiz = [part["title"] for part in teaching_parts if not part["quiz"]]
    if missing_quiz and len(missing_quiz) != len(teaching_parts):
        for title in missing_quiz:
            issues.append(
                Issue(
                    "warning",
                    filename,
                    title[:80],
                    "This section has no quiz. It will be imported as a reading part.",
                )
            )
    elif missing_quiz:
        issues.append(
            Issue(
                "warning",
                filename,
                "quizzes",
                "This module has no quizzes. Its sections will be imported as reading parts.",
            )
        )

    for offset, part in enumerate(parts, start=1):
        part["index"] = offset
        part.pop("blocks", None)

    chapter = {
        "index": module_number,
        "title": chapter_title,
        "source_file": filename,
        "parts": parts,
        "table_count": table_count,
    }
    return chapter, issues


def _summary_from_intro(path: str, filename: str, options: dict) -> tuple[str, str, list[Issue]]:
    try:
        blocks = read_blocks(path)
    except Exception as exc:
        return "", "", [Issue("error", filename, "intro", "Could not read the intro file: %s" % exc)]
    split_at = None
    markers = ("what this course builds", "the counsellor's journey", "the counselor's journey")
    for index, block in enumerate(blocks):
        lowered = block.text.lower()
        if any(marker in lowered for marker in markers):
            split_at = index
            break
    if split_at is None:
        intro_html = render_body(blocks, options["remove_blank_paragraphs"], options["remove_blank_lines"])
        return intro_html, "", [Issue("warning", filename, "intro", "No closing section was found. The whole intro is used as the overview text.")]
    intro_html = render_body(blocks[:split_at], options["remove_blank_paragraphs"], options["remove_blank_lines"])
    conclusion_html = render_body(blocks[split_at:], options["remove_blank_paragraphs"], options["remove_blank_lines"])
    return intro_html, conclusion_html, []


def _docx_files(folder: str) -> list[str]:
    names = []
    for name in os.listdir(folder):
        if name.startswith("~$"):
            continue
        if name.lower().endswith(".docx"):
            names.append(name)
    return sorted(names)


def _module_number(filename: str):
    match = re.search(r"module\s*(\d+)", filename, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def convert_folder(folder: str, remove_blank_paragraphs: bool = True, remove_blank_lines: bool = True) -> dict:
    folder = os.path.abspath(folder)
    options = {
        "remove_blank_paragraphs": remove_blank_paragraphs,
        "remove_blank_lines": remove_blank_lines,
    }
    issues: list[Issue] = []
    if not os.path.isdir(folder):
        issues.append(Issue("error", "", "folder", "Folder does not exist: %s" % folder))
        return _empty_result(folder, options, issues)

    names = _docx_files(folder)
    if not names:
        children = [name for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name))]
        hint = ""
        if children:
            hint = " This folder contains %s. Choose one country folder." % ", ".join(sorted(children))
        issues.append(Issue("error", "", "folder", "No Word files were found.%s" % hint))
        return _empty_result(folder, options, issues)

    modules = []
    intros = []
    indexes = []
    unknown = []
    for name in names:
        lowered = name.lower()
        if "intro" in lowered:
            intros.append(name)
        elif "index" in lowered:
            indexes.append(name)
        elif _module_number(name) is not None:
            modules.append(name)
        else:
            unknown.append(name)
    for name in unknown:
        issues.append(Issue("error", name, "filename", "File is not a module, intro, or index. Rename it or move it out of the folder."))
    if len(intros) > 1:
        issues.append(Issue("error", "", "intro", "More than one intro file: %s" % ", ".join(intros)))
    if not modules:
        issues.append(Issue("error", "", "modules", "No Module N.docx files were found."))

    chapters = []
    for name in sorted(modules, key=lambda item: _module_number(item) or 0):
        number = _module_number(name)
        chapter, chapter_issues = convert_module(os.path.join(folder, name), name, number, options)
        issues.extend(chapter_issues)
        if chapter:
            chapters.append(chapter)

    numbers = [chapter["index"] for chapter in chapters]
    if numbers and numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        issues.append(Issue("warning", "", "modules", "Module numbers are not a continuous sequence: %s" % ", ".join(str(n) for n in numbers)))
    if numbers and numbers[0] != 1:
        issues.append(Issue("warning", "", "modules", "The first module number is %s, not 1." % numbers[0]))

    intro_html = ""
    conclusion_html = ""
    if len(intros) == 1:
        intro_html, conclusion_html, intro_issues = _summary_from_intro(
            os.path.join(folder, intros[0]), intros[0], options
        )
        issues.extend(intro_issues)
    elif not intros:
        issues.append(Issue("warning", "", "intro", "No intro file was found. The overview text will be empty until you fill it in on the next step."))

    country_guess = os.path.basename(folder.rstrip(os.sep)).strip()
    display_guess = ""
    if intros:
        try:
            first = next((block.text for block in read_blocks(os.path.join(folder, intros[0])) if block.text), "")
            display_guess = first
        except Exception:
            display_guess = ""

    errors = [issue.as_dict() for issue in issues if issue.level == "error"]
    warnings = [issue.as_dict() for issue in issues if issue.level == "warning"]
    part_count = sum(len(chapter["parts"]) for chapter in chapters)
    quiz_count = sum(1 for chapter in chapters for part in chapter["parts"] if part.get("quiz"))
    question_count = sum(
        len(part["quiz"]["questions"])
        for chapter in chapters
        for part in chapter["parts"]
        if part.get("quiz")
    )
    table_count = sum(chapter.get("table_count", 0) for chapter in chapters)
    return {
        "source_folder": folder,
        "options": options,
        "country_guess": country_guess,
        "display_title_guess": display_guess,
        "intro_html": intro_html,
        "conclusion_html": conclusion_html,
        "chapters": chapters,
        "errors": errors,
        "warnings": warnings,
        "ready": not errors,
        "stats": {
            "files": len(names),
            "modules": len(chapters),
            "parts": part_count,
            "quizzes": quiz_count,
            "questions": question_count,
            "tables": table_count,
            "errors": len(errors),
            "warnings": len(warnings),
        },
    }


def _empty_result(folder: str, options: dict, issues: list[Issue]) -> dict:
    errors = [issue.as_dict() for issue in issues if issue.level == "error"]
    warnings = [issue.as_dict() for issue in issues if issue.level == "warning"]
    return {
        "source_folder": folder,
        "options": options,
        "country_guess": os.path.basename(folder.rstrip(os.sep)) if folder else "",
        "display_title_guess": "",
        "intro_html": "",
        "conclusion_html": "",
        "chapters": [],
        "errors": errors,
        "warnings": warnings,
        "ready": False,
        "stats": {
            "files": 0,
            "modules": 0,
            "parts": 0,
            "quizzes": 0,
            "questions": 0,
            "tables": 0,
            "errors": len(errors),
            "warnings": len(warnings),
        },
    }
