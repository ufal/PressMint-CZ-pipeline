import argparse
from pathlib import Path
from tei2pdf.pdf_builder import PDFBuilder


# --------------------
# ARGPARSE
# --------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert TEI XML to a multipage searchable PDF"
    )

    parser.add_argument(
        "-t", "--tei",
        required=True,
        type=Path,
        help="TEI XML file"
    )

    parser.add_argument(
      "-o", "--output",
      required=True,
      type=Path,
      help="Output PDF file"
    )

    parser.add_argument(
      "-c", "--cache",
      type=Path,
      help="Directory to cache downloaded images (optional)"
    )
    return parser.parse_args()

# --------------------
# MAIN
# --------------------
def main():
    args = parse_args()
    pdf = PDFBuilder(tei_path=args.tei, cache_dir=args.cache)
    pdf.build_pdf(args.output)

# --------------------
# ENTRY POINT
# --------------------
if __name__ == "__main__":
    main()
