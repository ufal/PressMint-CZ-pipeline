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

    for p in root.iter():
      if localname(p.tag) != "p":
        continue
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
      tokens = list(s.iter())
      for tok in tokens:
        token_idx = process_token(tok, s_id, token_idx, (tok == tokens[-1]))

    # remove helper attrs
    for el in root.iter():

        for attr in ["form", "text"]:
            if attr in el.attrib:
                del el.attrib[attr]
    root.attrib.pop('xmlnsoff', None)
    etree.cleanup_namespaces(tree)
    return tree

def process_token(tok, s_id, token_idx, is_last=False):
    if localname(tok.tag) != "tok" and localname(tok.tag) != "dtok":
        return token_idx
    upos = tok.get("upos", "")
    form = tok.get("form", "") or (tok.text or "")
    old_tag = localname(tok.tag)
    new_tag = "pc" if upos in PUNCT_UPOS else "w"
    tok.tag = q(new_tag)
    # transfer attributes
    attrs = {}
    upos = tok.get("upos", "")
    if upos:
          attrs["msd"] = f"UPosTag={upos}"
    for k, v in tok.attrib.items():
         if k == "ord":
              continue
         if k == "misc":
              if "SpaceAfter=No" in v.split("|"):
                  attrs["join"] = "right"
              continue
         if k == "upos":
              continue
         if k == "xpos":
              attrs["pos"] = v
              continue
         if k == "feats":
              attrs["msd"] = (f"UPosTag={upos}|" if upos else "") + v
              continue
         if k == f"{{{XML_NS}}}id":
              continue
         if k == "lemma":
              if old_tag == "dtok":
                attrs["norm"] = v
              else:
                attrs["lemma"] = v
              continue
         print (f"Warning: Unhandled attribute {k}={v} in token {token_idx} of sentence {s_id}", flush=True)
    tok.attrib.clear()
    if not(tok.tail and tok.tail.strip() == "" and len(tok.tail) > 0) and not(is_last):
      attrs["join"] = "right"
    for k, v in attrs.items():
        tok.set(k, v)
    tok.set(f"{{{XML_NS}}}id", f"{s_id}.w{token_idx}")
      
    token_idx += 1
    return token_idx


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


def patch_text(tree):
  root = tree.getroot()
  # move child pc outside token if it is at the first position
  for pc in root.xpath("//*[local-name()='pc']/*[1][local-name()='pc']"):
    pc.getparent().addprevious(pc)
  changed = 1
  while(changed):
    changed = 0
    for xb in ('pb', 'cb', 'lb'):
      for el in root.xpath(f"//*[local-name()='pc']/*[1][local-name()='{xb}']"):
        el.getparent().addprevious(el)
        changed = 1
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
    tree = patch_text(tree)
    tree = patch_header(tree)

    write_xml(tree, args.output)


# --------------------
# ENTRY POINT
# --------------------

if __name__ == "__main__":
    main()