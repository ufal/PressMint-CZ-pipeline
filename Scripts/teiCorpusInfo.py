#!/usr/bin/env python3
"""
Print information from root file (teiCorpus) of PressMint corpus:
  components  - hrefs of included components (teiCorpus/xi:include)
  includes    - hrefs of files included in teiHeader (taxonomies, ...)
  lang        - teiCorpus/@xml:lang
"""

import argparse
import sys
import xml.etree.ElementTree as ET

TEI = "{http://www.tei-c.org/ns/1.0}"
XI = "{http://www.w3.org/2001/XInclude}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def main():
    parser = argparse.ArgumentParser(description="Print information from teiCorpus root file.")
    parser.add_argument("what", choices=["components", "includes", "lang"])
    parser.add_argument("root", help="root file PressMint-XX.xml")
    args = parser.parse_args()

    root = ET.parse(args.root).getroot()
    if root.tag != f"{TEI}teiCorpus":
        sys.exit(f"ERROR: {args.root}: root element is not teiCorpus")

    if args.what == "components":
        values = [x.get("href") for x in root.findall(f"{XI}include")]
    elif args.what == "includes":
        values = [x.get("href") for x in root.findall(f"{TEI}teiHeader//{XI}include")]
    else:
        values = [root.get(XML_LANG)]
    for v in values:
        if v:
            print(v)


if __name__ == "__main__":
    main()
