# pdf2epub

A small Python command-line tool that converts text-based or scanned PDFs into EPUB 3 ebooks. It uses Apache Tika Server for text extraction and OCR, then applies conservative heuristics to remove common browser-print artifacts, identify chapter headings, reconstruct paragraphs, and create an EPUB with a table of contents.

**Current version:** 0.6 (experimental). PDF-to-EPUB conversion is inherently imperfect; always review the generated text and chapter structure.

## Features

- Extracts text page by page through Apache Tika Server.
- Uses OCR for pages whose locally extractable text falls below a configurable threshold (Tika must be configured with Tesseract and the required language data).
- Removes selected browser-print headers, footers, page counters, and confidently repeated edge lines.
- Detects common numbered and named chapter headings.
- Reconstructs paragraphs using conservative heuristics, including punctuation followed by two or more spaces and an uppercase letter.
- Writes an EPUB 3 file, intermediate `.raw.txt` and `.clean.txt` files, and a JSON report.

## Requirements

- Python 3.10 or newer.
- Apache Tika Server reachable over HTTP (default: `http://localhost:9998`).
- Tesseract and suitable OCR language data configured in Tika if scanned pages need OCR.

Python dependencies are listed in `requirements.txt`.

## Installation

Create and activate a virtual environment, then install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
```

Start Apache Tika Server separately and make sure it is reachable from the machine running the converter.

## Usage

```bash
python pdf2epub.py input.pdf \\
  --tika http://localhost:9998 \\
  --title "Book title" \\
  --author "Author name" \\
  --language eng
```

The output EPUB defaults to `input.epub`. Choose another destination with `--output`:

```bash
python pdf2epub.py input.pdf --output output/book.epub
```

Available options:

- `--tika`: Tika Server base URL (default `http://localhost:9998`).
- `--title`: ebook title (defaults to the PDF filename).
- `--author`: author metadata (defaults to `Autore sconosciuto` in this version).
- `--language`: language code passed to Tika and EPUB metadata (default `ita`). For OCR, use a language installed in the Tika/Tesseract environment.
- `--ocr-threshold`: minimum amount of locally extractable text used to decide whether a page needs OCR (default `30`).
- `--output`: destination EPUB path.

Alongside the EPUB, the tool writes files with the same base name and the suffixes `.raw.txt`, `.clean.txt`, and `.report.json`. These files can contain the complete extracted text of the input document; handle them accordingly.

## Tests

Run the unit tests from the project directory:

```bash
python -m unittest discover -s tests -v
```

The tests cover selected heading and paragraph reconstruction cases. They do not constitute an end-to-end test against a running Tika Server.

## Limitations

- Cleanup and chapter detection are heuristic and may make mistakes. Inspect the clean text and the headings in the JSON report before relying on the EPUB.
- Paragraph breaks inferred from punctuation, multiple spaces, and uppercase letters may split a single paragraph.
- Line-end hyphen joining can be wrong in some words.
- Images, original typography, footnotes, and emphasis are not preserved in version 0.6.
- The tool is not a substitute for proofreading and does not establish that you have permission to convert or distribute a source work.

## License

This project is released under the MIT License. See `LICENSE`.
