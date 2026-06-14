"""Document loading and parsing for the Paper Reader app.

Takes either a URL (arXiv abs/pdf/html links are resolved to the best readable
source: arXiv HTML -> ar5iv HTML -> arXiv PDF) or raw PDF bytes, and produces a
structured document model:

    {
        "doc_id": str,
        "title": str,
        "source": "arxiv-html" | "html" | "pdf",
        "url": str,
        "num_sentences": int,
        "blocks": [
            {"type": "heading", "level": int, "sentences": [...]},
            {"type": "paragraph", "sentences": [...]},
            {"type": "figure", "image_url": str, "sentences": [...caption...]},
        ],
    }

Each sentence is {"idx": global_index, "text": display_text, "words": [tokens],
"weights": [per-word duration weights], "spoken": tts_text}. Math is carried as
``$latex$`` tokens in the display text and expanded to spoken English (via the
repo's ``mathtex2text``) in the ``spoken`` text; the expansion length feeds the
word weight so word-highlight timing stays roughly aligned.
"""

from __future__ import annotations

import io
import ipaddress
import os
import re
import socket
import sys
import uuid
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mathtex2text import latex_to_speech_with_latexwalker  # noqa: E402

Document = dict[str, Any]
Block = dict[str, Any]
Sentence = dict[str, Any]

USER_AGENT = "PaperReaderApp/0.1 (local research tool)"
REQUEST_TIMEOUT = 30
MAX_REDIRECTS = 5
ALLOWED_SCHEMES = {"http", "https"}
MAX_DOWNLOAD_BYTES = 60 * 1024 * 1024  # cap fetched bodies (memory / zip-bomb DoS)


def _is_blocked_ip(ip_str: str) -> bool:
    """True if the address is non-public (loopback/private/link-local/etc.)."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # incl. 169.254.169.254 cloud metadata
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_public_url(url: str) -> None:
    """SSRF guard: only http(s), and the host must resolve to public IPs.

    Raises ValueError if the URL would let the server reach an internal/
    loopback/link-local address (cloud metadata, cluster services, etc.).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Only http/https URLs are allowed (got '{parsed.scheme or 'none'}')")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host")
    try:
        addrinfos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        raise ValueError(f"Could not resolve host '{host}'")
    for info in addrinfos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            raise ValueError(f"Refusing to fetch a non-public address ({host} -> {ip})")

MIN_SENTENCE_LENGTH = 30
MAX_SENTENCE_LENGTH = 280

ARXIV_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf|html|ps)/"
    r"(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)",
    re.IGNORECASE,
)

_MATH_RE = re.compile(r"\$[^$]+\$")
_ABBREV_RE = re.compile(
    r"(?:\b(?:e\.g|i\.e|et al|Fig|Figs|Eq|Eqs|Sec|Tab|cf|vs|resp|approx|Dr|Prof|No|al)\.|\b[A-Z]\.)$"
)


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------


def math_to_speech(latex: str) -> str:
    """Convert a LaTeX math snippet to spoken English, with a crude fallback."""
    try:
        spoken = latex_to_speech_with_latexwalker(latex)
        spoken = re.sub(r"\s+", " ", spoken).strip()
        if spoken:
            return spoken
    except Exception:
        pass
    return re.sub(r"[\\{}^_$]", " ", latex).strip()


def split_sentences(
    text: str,
    min_len: int = MIN_SENTENCE_LENGTH,
    max_len: int = MAX_SENTENCE_LENGTH,
) -> list[str]:
    """Split text into readable sentence chunks, keeping $math$ segments intact."""
    protected: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        protected.append(match.group())
        return f"\x00{len(protected) - 1}\x01"

    tmp = _MATH_RE.sub(_protect, text)
    tmp = re.sub(r"\s+", " ", tmp).strip()
    if not tmp:
        return []

    parts = re.split(r"(?<=[.!?])\s+", tmp)

    # Re-join pieces that were split after an abbreviation (e.g., et al., Fig.)
    merged: list[str] = []
    for part in parts:
        if merged and _ABBREV_RE.search(merged[-1]):
            merged[-1] += " " + part
        else:
            merged.append(part)

    # Merge fragments that are too short to be worth a TTS round-trip
    joined: list[str] = []
    for part in merged:
        if joined and len(joined[-1]) < min_len and len(joined[-1]) + len(part) < max_len:
            joined[-1] += " " + part
        else:
            joined.append(part)

    # Split overly long chunks at commas / spaces
    final: list[str] = []
    for part in joined:
        while len(part) > max_len:
            cut = part.rfind(", ", min_len, max_len)
            if cut == -1:
                cut = part.find(" ", max_len)
            if cut == -1:
                break
            final.append(part[: cut + 1].strip())
            part = part[cut + 1 :].strip()
        if part:
            final.append(part)

    def _restore(chunk: str) -> str:
        return re.sub(r"\x00(\d+)\x01", lambda m: protected[int(m.group(1))], chunk)

    return [_restore(chunk) for chunk in final if chunk.strip()]


_TOKEN_RE = re.compile(r"\$[^$]+\$|\S+")


def build_sentence(text: str, idx: int) -> Sentence:
    """Tokenize a sentence into display words plus spoken text and word weights."""
    words: list[str] = []
    weights: list[float] = []
    spoken_parts: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        token = match.group()
        math_match = _MATH_RE.search(token)
        if math_match and len(math_match.group()) > 2:
            spoken_inner = math_to_speech(math_match.group()[1:-1])
            spoken_token = token[: math_match.start()] + " " + spoken_inner + " " + token[math_match.end() :]
            words.append(token)
            weights.append(float(max(len(spoken_inner), 3)))
            spoken_parts.append(spoken_token)
        else:
            words.append(token)
            weights.append(float(len(token)))
            spoken_parts.append(token)
    spoken = re.sub(r"\s+", " ", " ".join(spoken_parts)).strip()
    return {"idx": idx, "text": text, "words": words, "weights": weights, "spoken": spoken}


# --------------------------------------------------------------------------
# HTML parsing (arXiv / LaTeXML and generic pages)
# --------------------------------------------------------------------------


def _replace_math_tags(root: Tag) -> None:
    """Replace MathML <math> tags by their LaTeX alttext wrapped in $...$."""
    for math_tag in root.find_all("math"):
        alttext = math_tag.get("alttext") or ""
        alttext = alttext.replace("\n", " ").replace("%", " ").replace("&", " ")
        alttext = alttext.replace("\\begin{split}", "").replace("\\end{split}", "").strip()
        alttext = alttext.replace("$", "")
        # Strip color commands (\color(rgb){1,0,0}, \color[rgb]{..}, \color{red});
        # KaTeX rejects some forms and they would pollute the spoken text
        alttext = re.sub(r"\\(?:page)?color\s*(?:\([^)]*\)|\[[^\]]*\])?\s*\{[^{}]*\}", " ", alttext)
        if alttext:
            math_tag.replace_with(NavigableString(f" ${alttext}$ "))
        else:
            math_tag.replace_with(NavigableString(" "))


def _effective_base(soup: BeautifulSoup, page_url: str) -> str:
    """Resolve the URL base the way a browser would: honor <base href> if present.

    arXiv HTML papers are inconsistent: some ship <base href="/html/<id>v<n>/">
    with bare image srcs ("x1.png"), others have no base tag but srcs that
    already include the id directory ("<id>v<n>/x1.png"). Standard urljoin
    against this effective base handles both, as well as ar5iv's root-relative
    srcs ("/html/<id>/assets/x1.png").
    """
    base_tag = soup.find("base")
    if isinstance(base_tag, Tag) and base_tag.get("href"):
        return urljoin(page_url, base_tag["href"])
    return page_url


def _clean_arxiv_article(article: Tag, base_url: str) -> None:
    for selector in [
        "nav",
        ".ltx_bibliography",
        ".ltx_note_outer",
        ".ltx_authors",
        ".ltx_role_affiliationtext",
        ".ltx_tag_equation",
        ".ltx_eqn_eqno",
        ".ltx_pagination",
        "footer",
    ]:
        for tag in article.select(selector):
            tag.decompose()
    for cite_tag in article.find_all("cite"):
        cite_tag.decompose()
    for img_tag in article.find_all("img"):
        src = img_tag.get("src", "")
        if src and not src.startswith(("http://", "https://", "data:")):
            img_tag["src"] = urljoin(base_url, src)
    _replace_math_tags(article)


def _element_text(tag: Tag) -> str:
    text = tag.get_text(separator=" ", strip=True)
    text = text.replace("[", "(").replace("]", ")")
    return re.sub(r"\s+", " ", text).strip()


def parse_arxiv_html(html: str, base_url: str) -> tuple[str, list[Block]]:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article")
    if article is None:
        raise ValueError("No <article> tag found in HTML")

    _clean_arxiv_article(article, _effective_base(soup, base_url))

    title_tag = article.find(class_="ltx_title_document")
    title = _element_text(title_tag) if isinstance(title_tag, Tag) else (soup.title.get_text(strip=True) if soup.title else "Untitled")

    blocks: list[Block] = []
    candidates = article.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "figure", "table"])
    for el in candidates:
        if not isinstance(el, Tag):
            continue
        if el.name in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            if el.find_parent("figure") or el.find_parent("table"):
                continue
            text = _element_text(el)
            if not text:
                continue
            if el.name == "p":
                blocks.append({"type": "paragraph", "raw_text": text})
            else:
                if title_tag is not None and el is title_tag:
                    continue
                blocks.append({"type": "heading", "level": int(el.name[1]), "raw_text": text})
        elif el.name == "table":
            classes = el.get("class", []) or []
            if el.find_parent("figure") or el.find_parent("table"):
                continue
            if any(cls in {"ltx_equation", "ltx_equationgroup", "ltx_eqn_table"} for cls in classes):
                text = _element_text(el)
                if text:
                    blocks.append({"type": "paragraph", "raw_text": text})
            # non-equation tables are skipped (not readable)
        elif el.name == "figure":
            if el.find_parent("figure"):
                continue
            img = el.find("img")
            caption = el.find("figcaption")
            caption_text = _element_text(caption) if isinstance(caption, Tag) else ""
            if img is None and not caption_text:
                continue
            blocks.append(
                {
                    "type": "figure",
                    "image_url": img.get("src", "") if isinstance(img, Tag) else "",
                    "raw_text": caption_text,
                }
            )
    return title, blocks


def parse_generic_html(html: str, base_url: str) -> tuple[str, list[Block]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    base_url = _effective_base(soup, base_url)
    title = soup.title.get_text(strip=True) if soup.title else "Untitled"
    h1 = container.find("h1")
    if isinstance(h1, Tag):
        h1_text = _element_text(h1)
        if h1_text:
            title = h1_text

    blocks: list[Block] = []
    for el in container.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "figure"]):
        if not isinstance(el, Tag):
            continue
        if el.name == "figure":
            img = el.find("img")
            caption = el.find("figcaption")
            caption_text = _element_text(caption) if isinstance(caption, Tag) else ""
            if img is None:
                continue
            src = img.get("src", "")
            if src and not src.startswith(("http://", "https://", "data:")):
                src = urljoin(base_url, src)
            blocks.append({"type": "figure", "image_url": src, "raw_text": caption_text})
            continue
        if el.find_parent(["figure", "table"]):
            continue
        if el.name == "li" and el.find(["p", "li"]):
            continue
        text = _element_text(el)
        if not text or len(text) < 3:
            continue
        if el.name.startswith("h"):
            if el is h1:
                continue
            blocks.append({"type": "heading", "level": int(el.name[1]), "raw_text": text})
        else:
            blocks.append({"type": "paragraph", "raw_text": text})
    return title, blocks


# --------------------------------------------------------------------------
# PDF parsing
# --------------------------------------------------------------------------


MIN_PDF_IMAGE_BYTES = 8_000  # skip logos / decorations

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(data:image/(\w+);base64,([A-Za-z0-9+/=\s]+?)\)")
_MD_HEADING_RE = re.compile(r"(#{1,6})\s+(.*)")
_MD_IMG_PLACEHOLDER_RE = re.compile(r"@@IMG(\d+)@@")
# pymupdf4llm dumps text found inside pictures (diagram labels, axis ticks, ...)
# between marker lines; that is unreadable label soup, so drop it wholesale.
_MD_PICTURE_TEXT_RE = re.compile(
    r"\**-{2,}\s*Start of picture text\s*-{2,}\**.*?\**-{2,}\s*End of picture text\s*-{2,}\**(?:<br>)?",
    re.IGNORECASE | re.DOTALL,
)
# "**==> picture [432 x 319] intentionally omitted <==**" placeholders
_MD_PICTURE_OMITTED_RE = re.compile(r"\**==>[^\n]*?<==\**")


def parse_pdf(pdf_bytes: bytes, title_hint: str = "") -> tuple[str, list[Block], list[dict[str, Any]]]:
    """Parse a PDF into blocks plus extracted embedded images.

    Returns (title, blocks, images); figure blocks reference images by
    ``image_index`` into the returned ``images`` list of {"mime", "data"}.

    Uses pymupdf4llm (layout-aware: real headings from font sizes, multi-column
    text, images at their true positions, OCR for image-only pages) and falls
    back to a simple pypdf line-heuristic parser if that fails.
    """
    try:
        return _parse_pdf_pymupdf(pdf_bytes, title_hint)
    except Exception as exc:
        print(f"[parsing] pymupdf4llm parse failed ({exc!r}); falling back to pypdf")
        return _parse_pdf_basic(pdf_bytes, title_hint)


def _strip_md_inline(text: str) -> str:
    """Remove markdown inline formatting, keeping the readable text."""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # stray images
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)  # links -> label
    text = re.sub(r"_\[[^\]]*\]_", " ", text)  # footnote markers like _[*]_
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<!\w)_([^_\s][^_]*)_(?!\w)", r"\1", text)  # _italics_
    return re.sub(r"\s+", " ", text).strip()


def _parse_pdf_pymupdf(pdf_bytes: bytes, title_hint: str = "") -> tuple[str, list[Block], list[dict[str, Any]]]:
    import base64

    import fitz  # PyMuPDF
    import pymupdf4llm

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    md = pymupdf4llm.to_markdown(doc, embed_images=True)
    if not md.strip():
        raise ValueError("empty markdown")

    md = _MD_PICTURE_TEXT_RE.sub(" ", md)
    md = _MD_PICTURE_OMITTED_RE.sub(" ", md)

    # Pull embedded data-URI images out of the markdown, keep position markers
    images: list[dict[str, Any]] = []

    def _extract_image(match: re.Match[str]) -> str:
        mime, b64 = match.group(1), match.group(2)
        try:
            data = base64.b64decode(b64)
        except Exception:
            return " "
        if len(data) < MIN_PDF_IMAGE_BYTES:
            return " "
        images.append({"mime": f"image/{mime}", "data": data})
        return f"\n\n@@IMG{len(images) - 1}@@\n\n"

    md = _MD_IMAGE_RE.sub(_extract_image, md)

    blocks: list[Block] = []
    paragraph_lines: list[str] = []

    def _flush() -> None:
        if paragraph_lines:
            text = _strip_md_inline(" ".join(paragraph_lines))
            if len(text) > 2:
                blocks.append({"type": "paragraph", "raw_text": text})
            paragraph_lines.clear()

    for raw_line in md.split("\n"):
        line = raw_line.strip()
        line = re.sub(r"^(?:>\s*)+", "", line)  # unwrap blockquote (footnote) markers
        if not line or re.fullmatch(r"[-*_]{3,}", line):  # blank / page rule
            _flush()
            continue
        img_match = _MD_IMG_PLACEHOLDER_RE.fullmatch(line)
        if img_match:
            _flush()
            blocks.append({"type": "figure", "image_index": int(img_match.group(1)), "raw_text": ""})
            continue
        heading_match = _MD_HEADING_RE.fullmatch(line)
        if heading_match:
            _flush()
            text = _strip_md_inline(heading_match.group(2))
            if text:
                level = min(len(heading_match.group(1)) + 1, 4)
                blocks.append({"type": "heading", "level": level, "raw_text": text})
            continue
        if line.startswith("|") or line.startswith("```"):  # tables / code fences
            _flush()
            continue
        if re.fullmatch(r"\d+", line):  # bare page numbers
            continue
        paragraph_lines.append(line)
    _flush()

    # Attach "Figure N: ..." paragraphs as captions of the preceding figure
    merged: list[Block] = []
    for block in blocks:
        if (
            block["type"] == "paragraph"
            and merged
            and merged[-1]["type"] == "figure"
            and not merged[-1]["raw_text"]
            and re.match(r"(Figure|Fig\.|Table)\s*\d", block["raw_text"])
        ):
            merged[-1]["raw_text"] = block["raw_text"]
        else:
            merged.append(block)
    blocks = merged

    title = ((doc.metadata or {}).get("title") or "").strip()
    first_heading = next((b for b in blocks if b["type"] == "heading"), None)
    if len(title) < 4:
        if first_heading is not None:
            title = first_heading["raw_text"]
        else:
            title = title_hint or "PDF document"
    # Don't read the title twice (shown separately above the article)
    if first_heading is not None and first_heading["raw_text"] == title:
        blocks.remove(first_heading)
    return title, blocks, images


def _parse_pdf_basic(pdf_bytes: bytes, title_hint: str = "") -> tuple[str, list[Block], list[dict[str, Any]]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))

    title = title_hint
    try:
        meta_title = reader.metadata.title if reader.metadata else None
    except Exception:
        meta_title = None
    if meta_title and len(str(meta_title).strip()) > 3:
        title = str(meta_title).strip()

    blocks: list[Block] = []
    images: list[dict[str, Any]] = []
    paragraph_lines: list[str] = []
    any_text = False

    def _flush() -> None:
        if paragraph_lines:
            paragraph = " ".join(paragraph_lines).strip()
            if len(paragraph) > 2:
                blocks.append({"type": "paragraph", "raw_text": paragraph})
            paragraph_lines.clear()

    heading_re = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+)?[A-Z][^.!?]{0,70}$")

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        # Undo hyphenation at line breaks, normalise whitespace per line
        text = re.sub(r"-\n(?=[a-z])", "", text)
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
        if text.strip():
            any_text = True
        if not title:
            for line in lines:
                if len(line) > 15:
                    title = line[:200]
                    break

        for line in lines:
            if not line:
                _flush()
                continue
            # Short title-like lines (numbered sections, ALL CAPS, Title Case) become headings
            if len(line) < 72 and heading_re.match(line) and (line.isupper() or re.match(r"^\d", line) or len(line.split()) <= 6):
                _flush()
                blocks.append({"type": "heading", "level": 2, "raw_text": line})
                continue
            paragraph_lines.append(line)
            # Heuristic paragraph break: sentence-final line in an already-long paragraph
            if line.endswith((".", "!", "?")) and sum(len(l) for l in paragraph_lines) > 500:
                _flush()
        _flush()

        # Embedded images of this page become figure blocks at the page boundary
        try:
            page_images = list(page.images)
        except Exception:
            page_images = []
        for img in page_images:
            try:
                data = img.data
            except Exception:
                continue
            if not data or len(data) < MIN_PDF_IMAGE_BYTES:
                continue
            ext = os.path.splitext(img.name or "")[1].lower().lstrip(".") or "png"
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
            images.append({"mime": mime, "data": data})
            blocks.append(
                {
                    "type": "figure",
                    "image_index": len(images) - 1,
                    "raw_text": f"(Image from page {page_num})",
                }
            )

    if not any_text:
        raise ValueError("Could not extract any text from the PDF (it may be scanned images)")
    return title or "PDF document", blocks, images


# --------------------------------------------------------------------------
# Document assembly + source resolution
# --------------------------------------------------------------------------


def _assemble(
    title: str,
    blocks: list[Block],
    source: str,
    url: str,
    images: Optional[list[dict[str, Any]]] = None,
) -> Document:
    doc_id = uuid.uuid4().hex[:12]
    out_blocks: list[Block] = []
    idx = 0
    for block in blocks:
        # PDF-extracted images are served by the backend under the doc id
        if "image_index" in block:
            block["image_url"] = f"/api/doc/{doc_id}/img/{block.pop('image_index')}"
        raw_text = block.pop("raw_text", "")
        if block["type"] == "heading":
            chunks = [raw_text] if raw_text else []
        else:
            chunks = split_sentences(raw_text)
        sentences = []
        for chunk in chunks:
            sentences.append(build_sentence(chunk, idx))
            idx += 1
        if not sentences and block["type"] != "figure":
            continue
        block["sentences"] = sentences
        out_blocks.append(block)
    doc: Document = {
        "doc_id": doc_id,
        "title": title,
        "source": source,
        "url": url,
        "num_sentences": idx,
        "blocks": out_blocks,
    }
    if images:
        doc["_images"] = images  # binary; stripped by the server before JSON
    return doc


def _fetch(url: str) -> requests.Response:
    """Fetch a URL with SSRF protection, validating every redirect hop.

    Redirects are followed manually so an attacker can't bounce a public URL to
    an internal one (each Location is re-validated before we connect to it).
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _validate_public_url(current)
        resp = requests.get(
            current,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            stream=True,
        )
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                break
            current = urljoin(current, location)
            continue
        # Enforce a size cap while streaming (covers lying/absent Content-Length
        # and decompression bombs, since iter_content yields decoded bytes).
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > MAX_DOWNLOAD_BYTES:
            resp.close()
            raise ValueError("Document exceeds the size limit")
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(64 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                resp.close()
                raise ValueError("Document exceeds the size limit")
            chunks.append(chunk)
        resp._content = b"".join(chunks)  # populate .content/.text for callers
        resp.raise_for_status()
        return resp
    raise ValueError("Too many redirects")


def load_document(url: Optional[str] = None, pdf_bytes: Optional[bytes] = None, filename: str = "") -> Document:
    """Load and parse a document from a URL or uploaded PDF bytes."""
    if pdf_bytes is not None:
        title, blocks, images = parse_pdf(pdf_bytes, title_hint=os.path.splitext(filename)[0])
        return _assemble(title, blocks, "pdf", filename or "(uploaded PDF)", images=images)

    if not url:
        raise ValueError("Either a url or pdf bytes must be provided")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    arxiv_match = ARXIV_ID_RE.search(url)
    if arxiv_match:
        arxiv_id = arxiv_match.group(1)
        # Try official arXiv HTML first, then ar5iv, then fall back to the PDF
        for html_url in (f"https://arxiv.org/html/{arxiv_id}", f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}"):
            try:
                resp = _fetch(html_url)
                if "<article" in resp.text:
                    title, blocks = parse_arxiv_html(resp.text, resp.url)
                    return _assemble(title, blocks, "arxiv-html", resp.url)
            except Exception:
                continue
        resp = _fetch(f"https://arxiv.org/pdf/{arxiv_id}")
        title, blocks, images = parse_pdf(resp.content, title_hint=arxiv_id)
        return _assemble(title, blocks, "pdf", resp.url, images=images)

    resp = _fetch(url)
    content_type = resp.headers.get("Content-Type", "").lower()
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        title, blocks, images = parse_pdf(resp.content, title_hint=os.path.basename(url))
        return _assemble(title, blocks, "pdf", url, images=images)

    if "<article" in resp.text and "ltx_" in resp.text:
        title, blocks = parse_arxiv_html(resp.text, resp.url)
        return _assemble(title, blocks, "arxiv-html", resp.url)

    title, blocks = parse_generic_html(resp.text, resp.url)
    return _assemble(title, blocks, "html", resp.url)
