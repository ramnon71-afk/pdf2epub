#!/usr/bin/env python3
"""PDF to EPUB 3 using Apache Tika, with conservative text cleanup.

Version 0.6. Tika Server must have Tesseract configured for OCR.
The script preserves intermediate text and a JSON report for inspection.
"""
from __future__ import annotations
import argparse
import collections
import html
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape
import fitz
import requests

VERSION = "0.6"
FILE_URL = re.compile(r"^\s*file:///.*$", re.IGNORECASE)
PRINT_FOOTER = re.compile(r"^\s*.*\(\s*\d+\s+of\s+\d+\s*\)\s*\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}[.:]\d{2}(?:[.:]\d{2})?)?.*$", re.IGNORECASE)
PAGE_COUNTER = re.compile(r"^\s*(?:pagina\s*)?\d{1,4}\s*$", re.IGNORECASE)
NUMBERED_HEADING_INLINE = re.compile(r"^\s*(\d{1,3})[.)]\s+(.{1,100}?\.)(?:\s+)(\S.*)\s*$")
NUMBERED_HEADING_STANDALONE = re.compile(r"^\s*(\d{1,3})[.)]\s+(.{2,100}?)\s*$")
NUMBERED_HEADING_TRAILING = re.compile(
    r"^(?P<prefix>.+[.!?…][\"'»”’)]?)[ \t]+"
    r"(?P<number>\d{1,3})[.)][ \t]+"
    r"(?P<title>[A-ZÀ-ÖØ-Þ][^.!?…\n]{1,98}\.)[ \t]*$"
)
CHAPTER_HEADING = re.compile(
    r"^\s*((?:capitolo|chapter|parte|part)\s+"
    r"(?:\d+|[ivxlcdm]+|[a-zà-ÿ]+)"
    r"(?:\s*[:.\-–—]\s*.*)?)\s*$", re.IGNORECASE
)

def tika_text(pdf_bytes: bytes, server: str, ocr: bool = False, language: str = "ita") -> str:
    headers = {"Accept":"text/plain","Content-Type":"application/pdf",
        "X-Tika-PDFOcrStrategy":"ocr_only" if ocr else "no_ocr","X-Tika-OCRLanguage":language}
    response = requests.put(server.rstrip("/") + "/tika", data=pdf_bytes, headers=headers, timeout=300)
    response.raise_for_status()
    return response.text.replace("\r\n","\n").replace("\r","\n").strip()

def extract_pages(source: Path, server: str, threshold: int, language: str) -> list[dict]:
    pages = []
    with fitz.open(source) as doc:
        total = len(doc)
        for index, page in enumerate(doc):
            page_text = page.get_text("text")
            text_present = len(re.sub(r"\s+","",page_text)) >= threshold
            single = fitz.open()
            single.insert_pdf(doc, from_page=index, to_page=index)
            payload = single.tobytes()
            single.close()
            extracted = tika_text(payload,server,ocr=not text_present,language=language)
            pages.append({"number":index+1,"ocr":not text_present,"text":extracted})
            print(f"Page {index+1}/{total}: {'OCR' if not text_present else 'text'}",flush=True)
    return pages

def edge_key(line: str) -> str:
    line = re.sub(r"\d+","#",line.strip().lower())
    return re.sub(r"\s+"," ",line)

def is_browser_print_artifact(line: str) -> bool:
    s = html.unescape(line).strip()
    if not s: return False
    if FILE_URL.match(s) or PRINT_FOOTER.match(s): return True
    if s == "\f" or s.strip("\f").strip() == "": return True
    if re.fullmatch(r"\d+\s+of\s+\d+",s,re.IGNORECASE): return True
    return False

def remove_running_furniture(pages: list[dict]) -> tuple[list[str], int, int]:
    normalized_lines=[]; counts=collections.Counter(); removed_artifacts=0
    for page in pages:
        text=html.unescape(page["text"]).replace("\f","\n")
        lines=[line.rstrip() for line in text.splitlines()]
        kept=[]
        for line in lines:
            if is_browser_print_artifact(line): removed_artifacts+=1
            else: kept.append(line)
        lines=kept; normalized_lines.append(lines)
        nonempty=[line.strip() for line in lines if line.strip()]
        for line in nonempty[:2]+nonempty[-2:]:
            if len(line)<=100: counts[edge_key(line)]+=1
    cutoff=max(3,round(len(pages)*0.25))
    recurring={key for key,count in counts.items() if count>=cutoff}
    cleaned_pages=[]; removed_edges=0
    for lines in normalized_lines:
        nonempty_indices=[i for i,line in enumerate(lines) if line.strip()]
        edge_indices=set(nonempty_indices[:2]+nonempty_indices[-2:])
        output=[]
        for i,raw in enumerate(lines):
            line=raw.strip()
            if not line: output.append(""); continue
            if is_browser_print_artifact(raw): continue
            if i in edge_indices and (edge_key(line) in recurring or PAGE_COUNTER.fullmatch(line)):
                removed_edges+=1; continue
            output.append(line)
        cleaned_pages.append("\n".join(output).strip())
    return cleaned_pages,removed_edges,removed_artifacts

def heading_or_split(line: str):
    """Return (heading, remainder) for confidently recognized chapter starts."""
    s=re.sub(r"[ \t]+"," ",line).strip()
    recognition_text=re.sub(r"^(\s*\d{1,3})\\\.",r"\1.",s)
    s=recognition_text
    match=CHAPTER_HEADING.fullmatch(s)
    if match: return match.group(1).strip(),None
    match=NUMBERED_HEADING_INLINE.fullmatch(s)
    if match:
        number,title,remainder=match.groups()
        return f"{number}. {title.strip()}",remainder.strip()
    match=NUMBERED_HEADING_STANDALONE.fullmatch(s)
    if match:
        number,title=match.groups(); title=title.strip()
        if len(title)<=100 and not re.search(r"[!?].+",title):
            return f"{number}. {title}",None
    return None

PARAGRAPH_CANDIDATE=re.compile(r'(?<=[.!?])[ \t]{2,}(?=["“«\'\(]?[A-ZÀ-ÖØ-Þ])')

def split_readable_paragraphs(text: str) -> list[str]:
    return [re.sub(r"[ \t]+"," ",p).strip() for p in PARAGRAPH_CANDIDATE.split(text) if p.strip()]

def reconstruct(pages: list[str]) -> tuple[list[tuple[str,str]],int]:
    text="\n\n".join(pages)
    text=text.replace("\u00ad","")
    text,hyphen_joins=re.subn(r"(?<=\w)[\-‐]\n(?=\w)","",text)
    items: list[tuple[str,str]]=[]; current: list[str]=[]
    def flush():
        if current:
            paragraph="  ".join(current).strip()
            for part in split_readable_paragraphs(paragraph): items.append(("paragraph",part))
            current.clear()
    for raw in text.splitlines():
        line=raw.strip()
        if not line: flush(); continue
        trailing=NUMBERED_HEADING_TRAILING.fullmatch(line)
        if trailing:
            prefix=trailing.group("prefix").strip()
            if prefix: current.append(prefix)
            flush()
            title=f"{trailing.group('number')}. {trailing.group('title').strip()}"
            items.append(("heading",title)); continue
        heading=heading_or_split(raw)
        if heading:
            flush(); title,remainder=heading; items.append(("heading",title))
            if remainder:
                original=re.sub(r"^(\s*\d{1,3})\\\.",r"\1.",raw)
                prefix=re.match(r"^\s*\d{1,3}[.)]\s+",original)
                body_start=original[prefix.end():] if prefix else original
                marker=body_start.find(title.split(". ",1)[1])
                if marker>=0: current.append(body_start[marker+len(title.split(". ",1)[1]):].strip())
                else: current.append(remainder)
            continue
        if current and re.match(r"^[«“„—–]",line) and re.search(r"[.!?…][»”]?$",current[-1]): flush()
        current.append(line)
    flush()
    return items,hyphen_joins

def build_epub(items: list[tuple[str,str]], destination: Path, title: str, author: str, language: str) -> int:
    from ebooklib import epub
    lang=language.split("+")[0].split(",")[0]
    book=epub.EpubBook()
    book.set_identifier("urn:pdf2epub:"+destination.stem); book.set_title(title); book.set_language(lang); book.add_author(author)
    css=epub.EpubItem(uid="style",file_name="style/book.css",media_type="text/css",
        content="body { line-height: 1.45; } p { text-indent: 1.2em; margin: 0 0 .35em; } h1 { text-align: center; margin: 2em 0 1em; font-size: 1.35em; }")
    book.add_item(css)
    chapters=[]; current_title=title; body=[]
    def save_chapter():
        nonlocal body
        if not body: return
        number=len(chapters)+1
        chapter=epub.EpubHtml(title=current_title,file_name=f"chapter_{number:03}.xhtml",lang=lang)
        chapter.content=(f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{escape(lang)}">'
            f"<head><title>{escape(current_title)}</title></head>"
            f"<body><h1>{escape(current_title)}</h1>{''.join(body)}</body></html>")
        chapter.add_item(css); book.add_item(chapter); chapters.append(chapter); body=[]
    for kind,text in items:
        if kind=="heading": save_chapter(); current_title=text
        else: body.append(f"<p>{escape(text)}</p>")
    save_chapter()
    if not chapters: raise ValueError("No text to write into EPUB")
    book.toc=tuple(chapters); book.spine=["nav",*chapters]
    book.add_item(epub.EpubNcx()); book.add_item(epub.EpubNav())
    epub.write_epub(str(destination),book)
    return len(chapters)

def main() -> int:
    parser=argparse.ArgumentParser(description="Extract PDF via Tika, clean print artifacts, and build EPUB 3")
    parser.add_argument("pdf",type=Path); parser.add_argument("--tika",default="http://localhost:9998")
    parser.add_argument("--title"); parser.add_argument("--author",default="Autore sconosciuto")
    parser.add_argument("--language",default="ita"); parser.add_argument("--ocr-threshold",type=int,default=30)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.pdf.is_file(): parser.error(f"PDF not found: {args.pdf}")
    output=args.output or args.pdf.with_suffix(".epub"); output.parent.mkdir(parents=True,exist_ok=True)
    pages=extract_pages(args.pdf,args.tika,args.ocr_threshold,args.language)
    raw_text="\n\n\f\n\n".join(page["text"] for page in pages)
    output.with_suffix(".raw.txt").write_text(raw_text,encoding="utf-8")
    cleaned_pages,removed_edges,removed_artifacts=remove_running_furniture(pages)
    items,hyphen_joins=reconstruct(cleaned_pages)
    clean_text="\n\n".join(text for _,text in items)
    output.with_suffix(".clean.txt").write_text(clean_text,encoding="utf-8")
    section_count=build_epub(items,output,args.title or args.pdf.stem,args.author,args.language)
    headings=[text for kind,text in items if kind=="heading"]
    report={"version":VERSION,"input":str(args.pdf),"output":str(output),"pages":len(pages),
        "ocr_pages":[page["number"] for page in pages if page["ocr"]],"removed_edge_lines":removed_edges,
        "removed_print_artifacts":removed_artifacts,"paragraphs":sum(1 for kind,_ in items if kind=="paragraph"),
        "headings":headings,"epub_sections":section_count,"line_end_hyphens_joined":hyphen_joins,
        "warnings":["Heuristic cleanup: inspect clean.txt, especially dialogue and paragraph breaks.",
            "Only explicit soft hyphens are unconditionally removed; line-end hyphen joins remain heuristic.",
            "Images, typography, footnotes and original emphasis are not preserved in v0.6.",
            "Paragraph breaks at punctuation + 2+ spaces + uppercase are heuristic and may over-split.",
            "Chapter recognition is heuristic; check the headings list in this report, especially numbered headings embedded in prose."]}
    output.with_suffix(".report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
