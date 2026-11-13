"""CBT bulk import — parse Word/PDF, preview, and import to the bank."""
import io

from tests.test_cbt import _teacher

_DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _make_docx() -> bytes:
    from docx import Document
    doc = Document()
    for line in [
        "1. What is 2 + 2?", "A) 3", "B) 4", "C) 5", "Answer: B", "",
        "2. The earth is flat. [easy]", "A. True", "B. False", "Ans: B", "",
        "3. Pick the prime numbers. (hard)", "A) 2", "B) 4", "C) 3", "Answer: A, C",
    ]:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_parser_handles_each_type():
    from app.services.cbt_import import parse_questions
    qs = parse_questions(
        "1. 2+2?\nA) 3\nB) 4\nAnswer: B\n\n"
        "2. Sky is green.\nA) True\nB) False\nAns: B\n\n"
        "3. Capital of France?\nAnswer: Paris")
    assert [q.type for q in qs] == ["single", "boolean", "short"]
    assert qs[0].correct == "b"
    assert qs[1].correct is False
    assert qs[2].correct == ["Paris"]


async def test_upload_parse_then_import(ctx):
    client, ids = ctx
    hdr = await _teacher(client)
    data = _make_docx()

    r = await client.post("/api/cbt/bank/parse", headers=hdr,
                          files={"file": ("questions.docx", data, _DOCX_CT)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 3 and body["valid"] == 3
    # difficulty tags were picked up
    diffs = {q["difficulty"] for q in body["questions"]}
    assert "easy" in diffs and "hard" in diffs

    imp = await client.post("/api/cbt/bank/import", headers=hdr, json={
        "subject_id": ids["subject_id"], "questions": body["questions"]})
    assert imp.status_code == 200 and imp.json()["created"] == 3

    s = (await client.get(f"/api/cbt/bank/summary?subject_id={ids['subject_id']}",
                          headers=hdr)).json()
    assert s["total"] == 3


async def test_import_skips_invalid_items(ctx):
    client, ids = ctx
    hdr = await _teacher(client)
    r = await client.post("/api/cbt/bank/import", headers=hdr, json={
        "subject_id": ids["subject_id"],
        "questions": [
            {"text": "Valid?", "type": "single",
             "options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
             "correct": "a", "difficulty": "easy"},
            {"text": "", "type": "single", "options": [], "correct": None,
             "difficulty": "easy"},  # invalid — no text / options / answer
        ]})
    body = r.json()
    assert body["created"] == 1 and body["skipped"] == 1 and body["errors"]


async def test_unsupported_file_is_rejected(ctx):
    client, ids = ctx
    hdr = await _teacher(client)
    r = await client.post("/api/cbt/bank/parse", headers=hdr,
                          files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 422
