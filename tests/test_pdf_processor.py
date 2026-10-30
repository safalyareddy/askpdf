import pytest
from core.pdf_processor import (
    detect_printed_page_number,
    is_table_of_contents_page,
    extract_section_heading
)


def test_detect_printed_page_number():
    # Numeric with Page prefix
    text1 = "ListLocal | UI/UX Design Project Report\nPage 3\nAbstract\nCraigslist is..."
    assert detect_printed_page_number(text1, 3) == "3"

    # Numeric without space
    text2 = "ListLocal | UI/UX Design Project Report\nPage4\nTable of Contents"
    assert detect_printed_page_number(text2, 4) == "4"

    # Footer style: - 12 -
    text3 = "This is a body paragraph discussing the architecture.\n- 12 -"
    assert detect_printed_page_number(text3, 14) == "12"

    # Standalone digit footer
    text4 = "Some conclusion text here.\n\n7"
    assert detect_printed_page_number(text4, 8) == "7"

    # Roman numeral
    text5 = "Preface and Acknowledgments\n\niv"
    assert detect_printed_page_number(text5, 2) == "iv"

    # Empty text
    assert detect_printed_page_number("", 1) is None


def test_is_table_of_contents_page():
    # Explicit title
    toc_text1 = "Table of Contents\n1. Introduction ........ 4\n2. Design .......... 8"
    assert is_table_of_contents_page(toc_text1) is True

    # Contents title
    toc_text2 = "CONTENTS\n1. Overview 2\n2. Tools 3\n3. Prototyping 5"
    assert is_table_of_contents_page(toc_text2) is True

    # Repeated dot leaders
    toc_text3 = "Abstract...............................................3\nIntroduction..........................................6"
    assert is_table_of_contents_page(toc_text3) is True

    # Regular substantive section text
    body_text = (
        "Abstract\n\n"
        "Craigslist is one of the best-known online classified platforms, yet its Chennai page still "
        "presents visitors with a dense, text-only directory of several hundred links. "
        "This project redesigns that experience as ListLocal."
    )
    assert is_table_of_contents_page(body_text) is False


def test_extract_section_heading():
    text1 = "Abstract\nCraigslist is one of the best known platforms."
    assert extract_section_heading(text1) == "Abstract"

    text2 = "1. Introduction\n1.1 Background\nOnline classifieds let people trade goods."
    assert extract_section_heading(text2) == "1. Introduction"

    text3 = "LOW FIDELITY – Screen 01 / 08 — Home page\nHeader with logo."
    heading3 = extract_section_heading(text3)
    assert heading3 is not None
    assert "LOW FIDELITY" in heading3
