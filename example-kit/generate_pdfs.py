#!/usr/bin/env python3
"""Write the example-kit mock PDFs (native text, no extra libraries)."""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent

# Escape PDF literal strings (Helvetica, ASCII only).
def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content_stream(lines: list[str], *, start_y: float = 720, leading: float = 14) -> bytes:
    parts = ["BT", "/F1 11 Tf", f"72 {start_y:.0f} Td"]
    first = True
    for line in lines:
        if not first:
            parts.append(f"0 {-leading:.0f} Td")
        parts.append(f"({_esc(line)}) Tj")
        first = False
    parts.append("ET")
    body = "\n".join(parts).encode("latin-1")
    return b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream\n"


def write_pdf(path: Path, lines: list[str]) -> None:
    stream = _content_stream(lines)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        stream.rstrip(b"\n"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    buf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf.extend(f"{i} 0 obj\n".encode("ascii"))
        buf.extend(obj)
        if not obj.endswith(b"\n"):
            buf.extend(b"\n")
        buf.extend(b"endobj\n")
    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    buf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    buf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    path.write_bytes(buf)


CD_MATURITY_LINES = [
    "FICTIONAL EXAMPLE -- not a real bank notice",
    "",
    "PenFed Credit Union",
    "7940 Jones Branch Drive",
    "McLean, VA 22102",
    "(800) 247-5626 | penfed.org",
    "",
    "Certificate of Deposit -- Maturity Notice",
    "",
    "Member number: ****8834",
    "Certificate number: CD-2024-11902",
    "Date of letter: August 20, 2026",
    "",
    "Dear Member,",
    "",
    "Your 12-month Certificate of Deposit will mature on September 18, 2026.",
    "",
    "Account summary",
    "Account: CD Ladder - PenFed",
    "Principal: $25,000.00",
    "Annual percentage yield (APY): 4.85%",
    "Original term: 12 months",
    "Start date: September 18, 2025",
    "Maturity date: September 18, 2026",
    "Interest: Paid at maturity",
    "",
    "Your options at maturity",
    "1. Renew -- Roll into a new term at the rate in effect on the maturity date.",
    "2. Transfer to money market -- Move proceeds to PenFed Money Market Savings.",
    "3. Withdraw -- Funds available on the business day after maturity.",
    "   No early-withdrawal penalty after the maturity date.",
    "",
    "If we do not hear from you by September 18, 2026, this certificate may",
    "renew automatically per your account agreement.",
    "",
    "Early withdrawal before maturity may cost up to 90 days of interest.",
    "",
    "Questions: call (800) 247-5626 or visit penfed.org.",
    "",
    "PenFed Credit Union",
    "Deposit Services",
]

TAX_NOTICE_LINES = [
    "FICTIONAL EXAMPLE -- not a real tax bill",
    "",
    "Anytown County Treasurer",
    "100 Government Way",
    "Anytown, ST 12345",
    "",
    "Property tax installment notice -- Tax year 2026",
    "Notice date: August 15, 2026",
    "",
    "Parcel ID: 12-3456-789",
    "Property: 456 Oak Avenue, Anytown, ST 12345",
    "",
    "Amount due: $1,200.00 (first installment)",
    "Due date: September 25, 2026",
    "",
    "Payment must be received or postmarked by September 25, 2026",
    "to avoid penalty and interest.",
    "",
    "Pay online at county.gov/treasurer, by mail to the address above,",
    "or in person weekdays 8:00 AM-4:30 PM.",
    "",
    "Make checks payable to Anytown County Treasurer.",
    "Write parcel ID on the memo line.",
    "",
    "If you have already paid, please disregard this notice.",
    "Questions: (800) 555-0200",
]


def main() -> None:
    write_pdf(OUT / "penfed-cd-maturity-notice.pdf", CD_MATURITY_LINES)
    write_pdf(OUT / "county-property-tax-notice.pdf", TAX_NOTICE_LINES)
    print("Wrote", OUT / "penfed-cd-maturity-notice.pdf")
    print("Wrote", OUT / "county-property-tax-notice.pdf")


if __name__ == "__main__":
    main()
