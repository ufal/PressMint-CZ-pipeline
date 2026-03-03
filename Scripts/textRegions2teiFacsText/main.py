#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path


from textRegions2teiFacsText.tei_facs_text_builder import process_task


# --------------------
# ARGPARSE
# --------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description=""
    )

    parser.add_argument(
        "-x", "--ocr-xml-dir",
        default="",
        type=Path,
        help="folder containing PageXML files"
    )

    parser.add_argument(
        "-r", "--regions-dir",
        required=True,
        type=Path,
        help="Path to directory with jsonl file encoded regions (one file per task)"
    )

    parser.add_argument(
        "-p", "--page-order-dir",
        required=True,
        type=Path,
        help="Path to page order folder with jsonl files (one file per task)"
    )

    parser.add_argument(
        "-t", "--tasks",
        type=Path,
        help="File with list of tasks (relative paths to files/folders), if not set, the stdin is used"
    )

    parser.add_argument(
        "-o", "--output-dir",
        required=True,
        type=Path,
        help="Output directory"
    )

    args = parser.parse_args()
    return args

def iter_lines(task_file=None):
    if task_file:
        with open(task_file, "r", encoding="utf-8") as f:
            for line in f:
                yield line.rstrip("\n")
    else:
        for line in sys.stdin:
            yield line.rstrip("\n")


# --------------------
# MAIN
# --------------------
def main():
    args = parse_args()
    for line in iter_lines(args.tasks):
        if not line:
            continue
        tei_id = line.split('/')[-1]
        print(f"INFO: component = {line}")
        print(f"INFO: id = {tei_id}")
        process_task(
          pagesFile=args.page_order_dir / f"{line}.jsonl",
          pagexmlDir=args.ocr_xml_dir / line,
          regionsFile=args.regions_dir /  f"{line}.jsonl",
          outFile=args.output_dir / f"{line}.xml",
          tei_id=tei_id
        )

if __name__ == "__main__":
    main()