#!/usr/bin/env python3

from lxml import etree
import argparse
import re
import sys


TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NSMAP = {None: TEI_NS}

PUNCT_UPOS = {
    "PUNCT",
    "SYM",
}


# --------------------
# HELPERS
# --------------------

def q(tag):
    return f"{{{TEI_NS}}}{tag}"


def localname(tag):
    return etree.QName(tag).localname


def make_xml_id(parent_id, token_id, kind):
    """
    Example:
        w-XX -> parent.w1
    """
    num = re.sub(r"^[a-zA-Z-]+", "", token_id)
    return f"{parent_id}.{kind}{num}"


# --------------------
# TRANSFORM
# --------------------

def transform_text(tree):
    root = tree.getroot()

    # rebuild root with proper TEI namespace
    new_root = etree.Element(q("TEI"), nsmap=NSMAP)

    for k, v in root.attrib.items():
        new_root.attrib[k] = v

    for child in root:
        new_root.append(child)

    root = new_root
    tree._setroot(root)

    # convert id -> xml:id
    for el in root.iter():
        if "id" in el.attrib:
            value = el.attrib.pop("id")
            el.set(f"{{{XML_NS}}}id", value)

    for p in root.iter(q("p")):
      p_id = p.get(f"{{{XML_NS}}}id")
      print(f"\n[PARAGRAPH] {p_id}",flush=True)
      sentence_idx = 1
      for child in p:

        if localname(child.tag) != "s":
            continue

        child.set(
            f"{{{XML_NS}}}id",
            f"{p_id}.s{sentence_idx}"
        )

        sentence_idx += 1

    for s in list(root.iter()):
      if localname(s.tag) != "s":
        continue
      s_id = s.get(f"{{{XML_NS}}}id")
      print(f"\n[SENTENCE] {s_id}",flush=True)

      token_idx = 1
      # convert tok -> w / pc
      for tok in list(s.iter()):
        if localname(tok.tag) != "tok":
          continue
        print(f"\n[TOKEN] {token_idx} {tok.text}",flush=True)

        upos = tok.get("upos", "")
        form = tok.get("form", "") or (tok.text or "")

        new_tag = "pc" if upos in PUNCT_UPOS else "w"

        new_el = etree.Element(q(new_tag))

        # transfer attributes
        upos = tok.get("upos", "")
        if upos:
            new_el.set("msd", f"UPosTag={upos}")
        for k, v in tok.attrib.items():

            if k == "ord":
                continue

            if k == "misc":
                if "SpaceAfter=No" in v.split("|"):
                    new_el.set("join", "right") 
                continue

            if k == "upos":
                continue

            if k == "xpos":
                new_el.set("pos", v)
                continue

            if k == "feats":
                new_el.set("msd", (f"UPosTag={upos}|" if upos else "") + v)
                continue

            if k == f"{{{XML_NS}}}id":
                continue

            new_el.set(k, v)
        new_el.set(
                f"{{{XML_NS}}}id",
                f"{s_id}.w{token_idx}"
            )
        
        # set token text
        new_el.text = form

        # preserve whitespace after token
        new_el.tail = tok.tail

        tok.getparent().replace(tok, new_el)
        token_idx += 1

    # remove helper attrs
    for el in root.iter():

        for attr in ["form", "text"]:
            if attr in el.attrib:
                del el.attrib[attr]

    return tree

def patch_header(tree):
    root = tree.getroot()
    for remove in root.xpath("//*[local-name()='change' and @who='flexipipe']"):
        parent = remove.getparent()
        if parent is not None:
            print(f"Removing change element with id: {etree.tostring(remove, encoding='unicode')}", flush=True)
            parent.remove(remove)
            while parent is not None and len(parent) == 0:
                remove = parent
                name = localname(remove.tag)
                parent = remove.getparent()
                if parent is not None:
                    print(f"Removing change element with id: {etree.tostring(remove, encoding='unicode')}", flush=True)
                    parent.remove(remove)
                    if name == "teiHeader":
                        break
    return tree
# --------------------
# IO
# --------------------

def load_xml(path=None):

    parser = etree.XMLParser(remove_blank_text=False)

    if path:
        return etree.parse(path, parser)

    return etree.parse(sys.stdin.buffer, parser)


def write_xml(tree, path=None):

    if path:
        tree.write(
            path,
            encoding="utf-8",
            pretty_print=True,
            xml_declaration=True,
        )
        return

    output = etree.tostring(
        tree,
        encoding="utf-8",
        pretty_print=True,
        xml_declaration=True,
    )

    sys.stdout.buffer.write(output)


# --------------------
# CLI
# --------------------

def parse_args():

    parser = argparse.ArgumentParser(
        description="Convert TEITOK format to PressMint TEI XML."
    )

    parser.add_argument(
        "-i",
        "--input",
        help="Input XML file (default: stdin)"
    )

    parser.add_argument(
        "-o",
        "--output",
        help="Output XML file (default: stdout)"
    )

    return parser.parse_args()


# --------------------
# MAIN
# --------------------

def main():

    args = parse_args()

    tree = load_xml(args.input)

    tree = transform_text(tree)
    tree = patch_header(tree)

    write_xml(tree, args.output)


# --------------------
# ENTRY POINT
# --------------------

if __name__ == "__main__":
    main()