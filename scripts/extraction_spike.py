"""
Extraction Spike — run this BEFORE building the full pipeline.

Tests Tesseract OCR + Claude extraction on a real invoice PDF.
Also tests Claude Vision (direct image input, no OCR step).

Usage:
    pip install pytesseract anthropic pdf2image pillow
    # Install Tesseract: sudo apt install tesseract-ocr  (Ubuntu)
    #                    brew install tesseract            (macOS)

    python scripts/extraction_spike.py path/to/invoice.pdf

Output:
    - OCR raw text quality (character count, obvious artifacts)
    - Claude extraction result (JSON)
    - Claude Vision extraction result (JSON, bypass OCR)
    - Side-by-side field comparison
    - Recommendation: use Tesseract+Claude or Claude Vision directly
"""
import json
import sys
import os
import time
from pathlib import Path


def test_tesseract(pdf_path: str) -> tuple[str, float]:
    """Run Tesseract OCR on PDF, return (raw_text, elapsed_seconds)."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image

        print("\n[1] Testing Tesseract OCR...")
        t0 = time.time()
        pages = convert_from_path(pdf_path, dpi=300)
        raw_text = ""
        for i, page in enumerate(pages):
            raw_text += pytesseract.image_to_string(page, lang="eng")
            print(f"    Page {i+1}: {len(raw_text)} chars so far")
        elapsed = time.time() - t0
        print(f"    Done in {elapsed:.1f}s")
        print(f"    First 500 chars:\n{'='*40}\n{raw_text[:500]}\n{'='*40}")
        return raw_text, elapsed
    except ImportError as e:
        print(f"    SKIP: {e}")
        return "", 0.0


def test_claude_extraction(raw_text: str, api_key: str) -> dict:
    """Pass OCR text to Claude for structured extraction."""
    import anthropic

    print("\n[2] Testing Claude Extraction (text input)...")
    client = anthropic.Anthropic(api_key=api_key)

    prompt = """Extract the following fields from this invoice text. Return ONLY valid JSON.
If a field is not found, use null. Add a "confidence" float (0.0-1.0) for each field.

Required fields:
- invoice_number, invoice_date (YYYY-MM-DD), due_date (YYYY-MM-DD or null)
- vendor_name, vendor_tax_id (or null), po_number (or null)
- currency (3-letter code), subtotal, tax_amount, freight_amount, total_amount
- line_items: array of {line_number, description, quantity, unit_price, unit, line_total, confidence}

Invoice text:
""" + raw_text[:4000]  # truncate for spike

    t0 = time.time()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    elapsed = time.time() - t0
    raw_output = response.content[0].text

    # Try to parse JSON
    try:
        # Strip markdown code fences if present
        clean = raw_output.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        result = json.loads(clean)
        print(f"    Done in {elapsed:.1f}s — {len(result.get('line_items', []))} line items extracted")
        print(f"    invoice_number: {result.get('invoice_number')} (conf: {result.get('confidence_invoice_number', '?')})")
        print(f"    total_amount:   {result.get('total_amount')} (conf: {result.get('confidence_total_amount', '?')})")
        return result
    except json.JSONDecodeError:
        print(f"    WARNING: Could not parse JSON output")
        print(f"    Raw output: {raw_output[:300]}")
        return {}


def test_claude_vision(pdf_path: str, api_key: str) -> dict:
    """Pass PDF page as image directly to Claude Vision (no OCR step)."""
    import anthropic
    import base64

    print("\n[3] Testing Claude Vision (direct image input, bypass OCR)...")
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(pdf_path, dpi=200, first_page=1, last_page=1)
        if not pages:
            print("    SKIP: Could not convert PDF to image")
            return {}

        # Convert first page to base64 PNG
        import io
        img_buffer = io.BytesIO()
        pages[0].save(img_buffer, format="PNG")
        img_b64 = base64.standard_b64encode(img_buffer.getvalue()).decode("utf-8")

        client = anthropic.Anthropic(api_key=api_key)
        prompt = """This is an invoice image. Extract the following fields and return ONLY valid JSON.
If a field is not found, use null.

Required: invoice_number, invoice_date (YYYY-MM-DD), due_date, vendor_name, vendor_tax_id,
po_number, currency, subtotal, tax_amount, freight_amount, total_amount,
line_items: [{line_number, description, quantity, unit_price, unit, line_total}]"""

        t0 = time.time()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        elapsed = time.time() - t0
        raw_output = response.content[0].text

        try:
            clean = raw_output.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:-1])
            result = json.loads(clean)
            print(f"    Done in {elapsed:.1f}s — {len(result.get('line_items', []))} line items")
            print(f"    invoice_number: {result.get('invoice_number')}")
            print(f"    total_amount:   {result.get('total_amount')}")
            return result
        except json.JSONDecodeError:
            print(f"    WARNING: Could not parse JSON: {raw_output[:300]}")
            return {}

    except ImportError as e:
        print(f"    SKIP: {e}")
        return {}


def compare_results(tesseract_result: dict, vision_result: dict):
    """Compare key fields between Tesseract+Claude vs Claude Vision."""
    if not tesseract_result and not vision_result:
        print("\n[4] No results to compare.")
        return

    print("\n[4] Field Comparison (Tesseract+Claude vs Claude Vision):")
    print(f"{'Field':<25} {'Tesseract+Claude':<30} {'Claude Vision':<30} {'Match?'}")
    print("-" * 95)

    fields = ["invoice_number", "invoice_date", "vendor_name", "total_amount", "currency"]
    for field in fields:
        a = tesseract_result.get(field, "N/A")
        b = vision_result.get(field, "N/A")
        match = "✓" if str(a) == str(b) else "✗ DIFFER"
        print(f"{field:<25} {str(a):<30} {str(b):<30} {match}")


def recommend(tesseract_text: str, tesseract_result: dict, vision_result: dict):
    """Print a recommendation based on results."""
    print("\n[5] Recommendation:")

    if not tesseract_text:
        print("    → USE CLAUDE VISION: Tesseract not available. Set USE_CLAUDE_VISION=true in .env")
        return

    # Heuristic: good OCR text has reasonable character count and common invoice keywords
    keywords_found = sum(1 for kw in ["invoice", "total", "date", "amount", "due"] if kw.lower() in tesseract_text.lower())
    artifact_ratio = tesseract_text.count("|||") + tesseract_text.count("???")

    if keywords_found >= 3 and artifact_ratio < 5 and tesseract_result:
        print("    → USE TESSERACT + CLAUDE: OCR quality looks good. Keep USE_CLAUDE_VISION=false.")
        print("      Dual-pass extraction will work well (both passes have good text input).")
    else:
        print("    → USE CLAUDE VISION: OCR text quality is poor (likely scanned invoice).")
        print("      Set USE_CLAUDE_VISION=true in .env — Claude Vision handles images directly.")
        print("      This is faster and more accurate for scanned documents.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/extraction_spike.py path/to/invoice.pdf")
        print("\nIf you don't have a real invoice, create a test PDF:")
        print("  - Download any sample invoice PDF from the web")
        print("  - Or use a scanned image saved as PDF")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Set ANTHROPIC_API_KEY environment variable first")
        sys.exit(1)

    print(f"Testing extraction on: {pdf_path}")
    print("=" * 60)

    raw_text, ocr_time = test_tesseract(pdf_path)
    tesseract_result = test_claude_extraction(raw_text, api_key) if raw_text else {}
    vision_result = test_claude_vision(pdf_path, api_key)

    compare_results(tesseract_result, vision_result)
    recommend(raw_text, tesseract_result, vision_result)

    print("\nDone. Check results above before building the full pipeline.")
