import os
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
import pypdf
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.doc_registry import _generate_doc_id

logger = logging.getLogger("documind.pdf")

INGESTION_VERSION = "2.0.0"

# Common section headers in technical papers, lab assignments, and reports
SECTION_PATTERNS = [
    r"^(?:abstract)\b",
    r"^(?:table\s+of\s+contents|contents|index)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:introduction|background|overview)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:analysis\s+of|existing\s+system|literature\s+review)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:proposed\s+system|system\s+design|architecture|methodology)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:the\s+redesigned\s+solution|solution\s+overview)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:implementation|technology\s+stack|project\s+structure)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:low[- ]fidelity|medium[- ]fidelity|high[- ]fidelity|prototype|prototyping)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:user\s+flow|information\s+architecture|wireframe)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:results|evaluation|testing|discussion)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:conclusion|concluding\s+remarks|summary)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:limitations|scope\s+and\s+limitations|future\s+work)\b",
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:references|bibliography|appendix)\b",
]


def detect_printed_page_number(text: str, physical_page: int) -> Optional[str]:
    """
    Extracts the printed page number from header or footer lines of a page text.
    Handles numeric formats ('Page 3', 'Page3', '- 3 -', '3') and Roman numerals ('i', 'iv').
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return None

    # Inspect top 3 lines (headers) and bottom 3 lines (footers)
    candidates = lines[:3] + lines[-3:]
    for line in candidates:
        # Match 'Page 3', 'Page3', 'Page - 3 -', '- 3 -', or standalone digit/roman
        m = re.search(r"^(?:page\s*[-–—]?\s*|[-–—]\s*)?([0-9]{1,4}|[ivxlcdm]+)(?:\s*[-–—])?$", line, re.I)
        if m:
            val = m.group(1).lower()
            return val

        # Match header containing 'Page X'
        m2 = re.search(r"\bpage\s*([0-9]{1,4})\b", line, re.I)
        if m2:
            return m2.group(1)

    return None


def is_table_of_contents_page(text: str) -> bool:
    """
    Detects if a page belongs to a Table of Contents or Index rather than substantive section text.
    Checks for TOC titles, repetitive dot leaders, and dense page index alignments.
    """
    clean = text.lower()
    if (
        "table of contents" in clean
        or "table ofcontents" in clean
        or "\ncontents\n" in clean
        or clean.startswith("contents")
    ):
        return True

    # Check for repetitive dot leaders (e.g. 'Abstract ..................... 3')
    dot_count = len(re.findall(r"\.{3,}", text))
    if dot_count >= 2:
        return True

    # Check for multiple lines structured as: Section Title ...... PageNumber
    toc_lines = len(re.findall(r"[a-zA-Z].*?[\.\s]{3,}\s*\d+", text))
    if toc_lines >= 2:
        return True

    return False


def extract_section_heading(text: str) -> Optional[str]:
    """Extracts the first prominent section heading in the given text passage."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:8]:
        for pat in SECTION_PATTERNS:
            if re.search(pat, line, re.I):
                return line.strip()
    return None


def extract_pdf_documents(
    pdf_path: str,
    chunk_size: int = 600,
    chunk_overlap: int = 120
) -> Tuple[List[Document], int, int, Dict[int, str], List[str]]:
    """
    Ingests and processes a PDF file page by page.
    Generates rich metadata for every chunk:
      - document_id
      - document_name
      - physical_page_number
      - printed_page_number (if detected)
      - section_heading
      - is_toc (boolean indicating Table of Contents chunk)
      - chunk_id
      - chunk_index
      - ingestion_version
    Returns: (documents, total_pages, total_chars, printed_pages_map, sections_found)
    """
    filename = os.path.basename(pdf_path)
    doc_id = _generate_doc_id(filename)
    logger.info(f"Extracting PDF with deep page indexing: '{filename}' (ID: {doc_id})")

    documents: List[Document] = []
    printed_pages_map: Dict[int, str] = {}
    sections_found: List[str] = []

    try:
        reader = pypdf.PdfReader(pdf_path)
    except Exception as e:
        logger.error(f"Failed to read PDF structure of '{filename}': {e}")
        return [], 0, 0, {}, []

    # Check encryption
    if reader.is_encrypted:
        try:
            decrypted = reader.decrypt("")
            if decrypted == 0:
                logger.warning(f"PDF '{filename}' is password-encrypted and cannot be decrypted with blank password.")
                return [], 0, 0, {}, []
        except Exception as e:
            logger.error(f"Error decrypting PDF '{filename}': {e}")
            return [], 0, 0, {}, []

    num_pages = len(reader.pages)
    if num_pages == 0:
        logger.warning(f"PDF '{filename}' contains 0 pages.")
        return [], 0, 0, {}, []

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    total_chars = 0
    current_section = "General"

    for page_idx, page in enumerate(reader.pages):
        physical_page = page_idx + 1
        try:
            raw_text = page.extract_text() or ""
        except Exception as e:
            logger.warning(f"Failed text extraction on physical page {physical_page} of '{filename}': {e}")
            raw_text = ""

        page_text = raw_text.strip()
        total_chars += len(page_text)

        # Detect printed page number
        printed_page = detect_printed_page_number(page_text, physical_page)
        if printed_page:
            printed_pages_map[physical_page] = printed_page

        # Detect if page is a Table of Contents
        is_toc = is_table_of_contents_page(page_text)

        # Detect section heading
        found_heading = extract_section_heading(page_text)
        if found_heading:
            current_section = found_heading
            if found_heading not in sections_found:
                sections_found.append(found_heading)

        if not page_text:
            continue

        # Split page text into metadata-tagged chunks
        chunks = text_splitter.split_text(page_text)
        for chunk_idx, chunk in enumerate(chunks):
            chunk_clean = chunk.strip()
            if not chunk_clean:
                continue

            chunk_id = f"{doc_id}_p{physical_page}_c{chunk_idx}"

            # If the chunk itself looks like TOC entries, mark it
            chunk_is_toc = is_toc or (len(re.findall(r"\.{3,}", chunk_clean)) >= 2)

            meta: Dict[str, Any] = {
                "document_id": doc_id,
                "document_name": filename,
                "source": filename,  # Retained for Chroma backwards compatibility
                "physical_page_number": physical_page,
                "page": physical_page,  # Retained for existing tests
                "printed_page_number": printed_page if printed_page else "",
                "section_heading": current_section,
                "is_toc": chunk_is_toc,
                "chunk_id": chunk_id,
                "chunk_index": chunk_idx,
                "ingestion_version": INGESTION_VERSION
            }

            documents.append(
                Document(
                    page_content=chunk_clean,
                    metadata=meta
                )
            )

    logger.info(
        f"Ingested '{filename}': {num_pages} pages, {len(documents)} chunks, "
        f"{total_chars} chars, {len(printed_pages_map)} printed pages detected, "
        f"{len(sections_found)} sections."
    )

    return documents, num_pages, total_chars, printed_pages_map, sections_found
