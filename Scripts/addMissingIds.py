#!/usr/bin/env python3
"""
Add missing xml:id to text elements of PressMint TEI component files (p, head, ...),
so that sentence/word ids of annotated version can be derived from them.

Id format is the same as the fallback in teitok2tei.py:
    {TEI/@xml:id}.{element name}{position of element among elements with same name in text}
e.g. PressMint-AT_1863-07-01.p2, PressMint-AT_1863-07-01.head1

Existing ids are kept. Files are rewritten only if some id was added.
"""

from lxml import etree
import argparse
import re
import sys

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def localname(tag):
    return etree.QName(tag).localname


def set_id_first(el, value):
    """set xml:id as the first attribute"""
    attrs = list(el.attrib.items())
    el.attrib.clear()
    el.set(XML_ID, value)
    for k, v in attrs:
        el.set(k, v)


def add_missing_ids(tree, elements):
    root = tree.getroot()
    doc_id = re.sub(r"\.ana$", "", root.get(XML_ID) or "")
    if not doc_id:
        print("ERROR: missing TEI/@xml:id", file=sys.stderr)
        return 0
    existing_ids = {el.get(XML_ID) for el in root.iter() if isinstance(el.tag, str) and el.get(XML_ID)}
    name_idx = {}
    added = 0
    for el in root.xpath("//*[local-name()='text']//*"):
        name = localname(el.tag)
        name_idx[name] = name_idx.get(name, 0) + 1
        if name not in elements or el.get(XML_ID):
            continue
        new_id = f"{doc_id}.{name}{name_idx[name]}"
        while new_id in existing_ids:
            new_id += "_"
        set_id_first(el, new_id)
        existing_ids.add(new_id)
        added += 1
    return added


def write_xml(tree, path, newline=b"\n", final_newline=True):
    data = b'<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(tree, encoding="UTF-8", xml_declaration=False)
    if final_newline:
        data += b"\n"
    # XML parser normalizes line endings, keep the original ones (e.g. CRLF)
    if newline != b"\n":
        data = data.replace(b"\n", newline)
    with open(path, "wb") as f:
        f.write(data)


def parse_args():
    parser = argparse.ArgumentParser(description="Add missing xml:id to text elements of TEI files (in place).")
    parser.add_argument("files", nargs="+", help="TEI component files")
    parser.add_argument("-e", "--elements", default="p,head",
                        help="comma separated list of element names (default: p,head)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="only report, do not rewrite files")
    return parser.parse_args()


def main():
    args = parse_args()
    elements = {e.strip() for e in args.elements.split(",") if e.strip()}
    parser = etree.XMLParser(remove_blank_text=False)
    for path in args.files:
        with open(path, "rb") as f:
            raw = f.read()
        newline = b"\r\n" if b"\r\n" in raw[:4096] else b"\n"
        final_newline = raw.endswith(b"\n")
        tree = etree.parse(path, parser)
        if localname(tree.getroot().tag) != "TEI":
            print(f"INFO: skipping {path} (root is not TEI)")
            continue
        added = add_missing_ids(tree, elements)
        if added and not args.dry_run:
            write_xml(tree, path, newline, final_newline)
        print(f"INFO: {path}: {added} id(s) added{' (dry run)' if args.dry_run and added else ''}")


if __name__ == "__main__":
    main()
