"""Extract CBT questions from an uploaded Word (.docx) or PDF document.

Expected document shape (tolerant of spacing and of A)/A./(A) markers):

    1. What is 2 + 2?
    A) 3
    B) 4
    C) 5
    Answer: B

    2. The earth is flat. [easy]
    A. True
    B. False
    Ans: B

A line may tag difficulty in brackets, e.g. "[easy]" / "(hard)". Multiple
correct letters (e.g. "Answer: A, C") make it a multiple-choice question;
True/False options make it a boolean; a question with an answer but no options
becomes a short-answer with that text accepted.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

_Q_START = re.compile(r"^\s*(?:q(?:uestion)?\s*)?(\d+)\s*[\.\)\:]\s*(.*)$", re.I)
_OPTION = re.compile(r"^\s*\(?([A-Ha-h1-8])[\.\)]\s*(.+?)\s*$")
_ANSWER = re.compile(r"^\s*(?:ans(?:wer)?|correct(?:\s*answer)?|key)\s*[:\-\.]?\s*(.+?)\s*$", re.I)
_DIFF = re.compile(r"[\[\(]\s*(easy|medium|hard)\s*[\]\)]", re.I)
_TOPIC = re.compile(r"[\[\(]\s*topic\s*[:\-]\s*([^\]\)]+)[\]\)]", re.I)


@dataclass
class ParsedQuestion:
    text: str
    type: str
    options: list[dict]
    correct: object
    difficulty: str = "medium"
    topic: str = ""
    marks: float = 1.0
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "text": self.text, "type": self.type, "options": self.options,
            "correct": self.correct, "difficulty": self.difficulty,
            "topic": self.topic, "marks": self.marks, "issues": self.issues,
        }


# -------------------------------------------------------------------- text
def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return _docx_text(data)
    if name.endswith(".pdf"):
        return _pdf_text(data)
    if name.endswith(".doc"):
        raise ValueError("Old .doc files aren't supported — please re-save as "
                         ".docx or PDF and upload again.")
    raise ValueError("Unsupported file — upload a Word (.docx) or PDF (.pdf) file.")


def _docx_text(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    lines = [p.text for p in doc.paragraphs]
    for table in doc.tables:                       # some banks are laid out in tables
        for row in table.rows:
            for cell in row.cells:
                lines.append(cell.text)
    return "\n".join(lines)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        raise ValueError("No text could be read from this PDF — it may be a "
                         "scan/image. Use a text PDF or a Word file.")
    return text


# ----------------------------------------------------------------- parsing
def parse_questions(text: str) -> list[ParsedQuestion]:
    # group lines into blocks, each beginning at a numbered question
    blocks: list[list[str]] = []
    cur: list[str] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if _Q_START.match(line):
            cur = [line]
            blocks.append(cur)
        elif cur is not None:
            cur.append(line)
    return [_block_to_question(b) for b in blocks if any(s.strip() for s in b)]


def _block_to_question(lines: list[str]) -> ParsedQuestion:
    first = _Q_START.match(lines[0])
    stem_parts: list[str] = [first.group(2).strip()] if first and first.group(2).strip() else []
    options: list[dict] = []
    marker_map: dict[str, str] = {}       # original marker (upper) -> option id
    answer_raw: str | None = None
    difficulty = "medium"
    topic = ""

    def grab_tags(s: str) -> str:
        nonlocal difficulty, topic
        md = _DIFF.search(s)
        if md:
            difficulty = md.group(1).lower()
            s = _DIFF.sub("", s)
        mt = _TOPIC.search(s)
        if mt:
            topic = mt.group(1).strip()
            s = _TOPIC.sub("", s)
        return s.strip()

    stem_parts = [grab_tags(p) for p in stem_parts]

    for line in lines[1:]:
        if not line.strip():
            continue
        am = _ANSWER.match(line)
        if am:
            answer_raw = am.group(1).strip()
            continue
        om = _OPTION.match(line)
        if om:
            marker = om.group(1).upper()
            oid = chr(ord("a") + len(options))     # sequential a, b, c, …
            marker_map[marker] = oid
            options.append({"id": oid, "text": grab_tags(om.group(2).strip())})
            continue
        # a non-option, non-answer line before any option extends the stem
        if not options:
            stem_parts.append(grab_tags(line.strip()))

    stem = " ".join(p for p in stem_parts if p).strip()
    return _assemble(stem, options, marker_map, answer_raw, difficulty, topic)


def _assemble(stem, options, marker_map, answer_raw, difficulty, topic) -> ParsedQuestion:
    issues: list[str] = []
    # resolve the correct answer markers/text to option ids
    correct_ids: list[str] = []
    if answer_raw:
        for tok in re.split(r"[,\s/]+", answer_raw):
            tok = tok.strip()
            if not tok:
                continue
            up = tok.upper().rstrip(").")
            if up in marker_map:
                correct_ids.append(marker_map[up])
            else:
                hit = next((o["id"] for o in options
                            if o["text"].lower() == tok.lower()), None)
                if hit:
                    correct_ids.append(hit)
    correct_ids = list(dict.fromkeys(correct_ids))  # dedupe, keep order

    # decide the type
    texts = [o["text"].strip().lower() for o in options]
    is_bool = len(options) == 2 and set(texts) <= {"true", "false"}

    if not options and answer_raw:
        qtype, correct = "short", [answer_raw]
    elif is_bool:
        qtype = "boolean"
        correct = (len(correct_ids) == 1
                   and options[["a", "b"].index(correct_ids[0])]["text"].strip().lower() == "true")
    elif len(correct_ids) > 1:
        qtype, correct = "multiple", correct_ids
    else:
        qtype, correct = "single", (correct_ids[0] if correct_ids else None)

    # validation
    if not stem:
        issues.append("Missing question text")
    if qtype in ("single", "multiple") and len(options) < 2:
        issues.append("Needs at least two options")
    if qtype in ("single", "multiple", "boolean") and not correct_ids:
        issues.append("Couldn't find the correct answer")
    if qtype == "short" and not answer_raw:
        issues.append("Missing the accepted answer")

    return ParsedQuestion(text=stem, type=qtype, options=options, correct=correct,
                          difficulty=difficulty, topic=topic, issues=issues)


def parse_document(filename: str, data: bytes) -> list[ParsedQuestion]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("File is too large (max 5 MB).")
    return parse_questions(extract_text(filename, data))
