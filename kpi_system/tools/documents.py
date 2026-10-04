"""Инструмент: чтение документа стратегии (txt/md/pdf/docx) и нарезка на фрагменты."""
from pathlib import Path


def read_document(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Файл не найден: {p.name}")
    ext = p.suffix.lower()
    if ext in (".txt", ".md"):
        text = p.read_text(encoding="utf-8", errors="replace")
    elif ext == ".pdf":
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(p)).pages)
    elif ext == ".docx":
        from docx import Document
        text = "\n".join(par.text for par in Document(str(p)).paragraphs)
    else:
        raise ValueError(f"Неподдерживаемый формат: {ext}. Допустимо: txt, md, pdf, docx")
    text = text.strip()
    if len(text) < 100:
        raise ValueError("Документ пуст или слишком короткий (меньше 100 символов)")
    return text


def split_into_chunks(text: str, max_chars: int = 2500, max_chunks: int = 6) -> list[str]:
    """Режет текст по абзацам, чтобы фрагмент помещался в небольшой контекст 7B-модели."""
    chunks, current = [], ""
    for para in (p.strip() for p in text.split("\n")):
        if not para:
            continue
        if current and len(current) + len(para) + 1 > max_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n{para}" if current else para[:max_chars]
    if current:
        chunks.append(current)
    return chunks[:max_chunks]
