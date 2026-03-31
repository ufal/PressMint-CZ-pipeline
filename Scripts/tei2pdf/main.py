import argparse
from pathlib import Path
from tei2pdf.pdf_builder import PDFBuilder


from tei2pdf.task_factory import create_task
from tei2pdf.config import load_config
from tei2pdf.style_resolver import StyleResolver
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")

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

    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to YAML configuration file (default: {DEFAULT_CONFIG_PATH}).",
    )

    parser.add_argument(
        "--profile",
        help="Profile name to use instead of active_profile from YAML.",
    )    
    return parser.parse_args()

# --------------------
# MAIN
# --------------------
def main():
    args = parse_args()
    tasks_config, styles_config = load_config(args.config, args.profile)
    tasks = [create_task(task_cfg) for task_cfg in tasks_config]
    styles = StyleResolver(styles_config)
    pdf = PDFBuilder(tei_path=args.tei, cache_dir=args.cache, tasks=tasks, styles = styles)
    pdf.build_pdf(args.output)

# --------------------
# ENTRY POINT
# --------------------
if __name__ == "__main__":
    main()
