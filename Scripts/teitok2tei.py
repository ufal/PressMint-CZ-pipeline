#!/usr/bin/env python3

from lxml import etree
import argparse
import re
import sys
import copy

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


def is_tokenish(el):
    """token or inline element (name) containing tokens"""
    if not isinstance(el.tag, str):
        return False
    ln = localname(el.tag)
    return ln == "tok" or (ln == "name" and bool(el.xpath(".//*[local-name()='tok']")))


def detach_keep_tail(el):
    """remove element from tree, its tail text stays in place"""
    parent = el.getparent()
    if el.tail:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + el.tail
        else:
            parent.text = (parent.text or "") + el.tail
    parent.remove(el)


def has_space_after(el):
    """
    Is token followed by whitespace? Looks at the following text in document order,
    lb/cb/pb without break="no" counts as whitespace.
    """
    node = el
    while True:
        if node.tail:
            return node.tail[:1].isspace()
        nxt = node.getnext()
        while nxt is None:
            node = node.getparent()
            if node is None or localname(node.tag) == "p":
                return True
            if node.tail:
                return node.tail[:1].isspace()
            nxt = node.getnext()
        if localname(nxt.tag) in ("lb", "cb", "pb"):
            if nxt.get("break") != "no":
                return True
            node = nxt
            continue
        if nxt.text:
            return nxt.text[:1].isspace()
        return False


def wrap_orphan_tokens(root):
    """
    Sentences crossing <p> boundary are encoded by TEITOK/flexipipe as an empty <s/>
    milestone followed by bare tokens (and the rest of the sentence at the beginning
    of the next paragraph without any <s>).
    Wrap every run of tokens that is not inside <s> into <s> (reusing the milestone if present).
    Returns list of (s, s_next) pairs - parts of the same sentence split by paragraph boundary.
    """
    links = []
    pending = None  # sentence part that continues in the next paragraph

    def flush(group, milestone, leading, last):
        nonlocal pending
        idx = [i for i, n in enumerate(group) if is_tokenish(n)]
        if not idx:
            if milestone is not None:
                print(f"  [PATCH] Removing empty sentence {milestone.get('id')}", flush=True)
                detach_keep_tail(milestone)
            if last:
                pending = None
            return
        first, last_tok = group[idx[0]], group[idx[-1]]
        if milestone is not None:
            detach_keep_tail(milestone)
            wrapper = milestone
        else:
            wrapper = etree.Element(q("s"))
        print(f"  [PATCH] Wrapping {len(idx)} orphan tokens into sentence {wrapper.get('id')}", flush=True)
        first.addprevious(wrapper)
        tail = last_tok.tail
        last_tok.tail = None
        for n in group[idx[0]:idx[-1] + 1]:
            wrapper.append(n)
        wrapper.tail = tail
        if leading and pending is not None:
            links.append((pending, wrapper))
        elif leading:
            print(f"WARN: orphan tokens at the beginning of paragraph {wrapper.getparent().get(f'{{{XML_NS}}}id')} without preceding sentence", flush=True)
        if last:
            pending = wrapper if (milestone is not None or leading) else None
        else:
            pending = None

    for p in list(root.iter()):
        if not isinstance(p.tag, str):
            continue
        if localname(p.tag) in ("s", "tok") or p.xpath("ancestor::*[local-name()='s' or local-name()='tok']"):
            continue
        children = [c for c in p if isinstance(c.tag, str)]
        if not any(localname(c.tag) == "s" or is_tokenish(c) for c in children):
            continue
        group = []
        milestone = None
        leading = True
        for c in list(p):
            if isinstance(c.tag, str) and localname(c.tag) == "s":
                flush(group, milestone, leading, False)
                group = []
                leading = False
                is_empty = len(c) == 0 and not (c.text or "").strip()
                milestone = c if is_empty else None
                continue
            group.append(c)
        flush(group, milestone, leading, True)
    return links


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

    s_links = wrap_orphan_tokens(root)

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

    # link parts of sentences split by paragraph boundary
    for s_prev, s_next in s_links:
        prev_id = s_prev.get(f"{{{XML_NS}}}id")
        next_id = s_next.get(f"{{{XML_NS}}}id")
        print(f"WARN: sentence {prev_id} overlaps paragraph boundary, continues as {next_id}", flush=True)
        s_prev.set("next", f"#{next_id}")
        s_next.set("prev", f"#{prev_id}")

    for s in list(root.iter()):
      if localname(s.tag) != "s":
        continue
      s_id = s.get(f"{{{XML_NS}}}id")
      print(f"\n[SENTENCE] {s_id}",flush=True)

      # if (pc or lb or ...) is first or last in the token, then put outside the token
            # 1. Move to the left (First child check)
      while True:
        elem = s.xpath("(.//*[local-name()='tok']/*[local-name()!='dtok'][not(preceding-sibling::node())])[1]")
        if not elem:
          break
        target = elem[0]
        parent = target.getparent()
        print(f"  [PATCH] Moving tei:element() {target.get(f'{{{XML_NS}}}id')} to the left of its parent token", flush=True)
        # If target has a tail, it belongs to the token text remaining inside
        if target.tail:
            parent.text = (parent.text or "") + target.tail
            target.tail = None
        parent.addprevious(target)
        # Clean up parent if it became an empty token shell
        if not parent.text and len(parent) == 0:
            parent.getparent().remove(parent)
        print(f"  [PATCH] patched {xml_to_string_no_attr(s)}", flush=True)

      # 2. Move to the right (Last child check)
      while True:
        elem = s.xpath("(.//*[local-name()='tok']/*[local-name()!='dtok'][not(following-sibling::node())])[last()]")
        if not elem:
          break
        target = elem[0]
        parent = target.getparent()
        print(f"  [PATCH] Moving tei:element() {target.get(f'{{{XML_NS}}}id')} to the right of its parent token", flush=True)
        # If target has a tail, that text belongs inside the token before moving the element out
        if target.tail:
            # Shift the tail text into the parent's terminal text or preceding child's tail
            siblings = target.xpath("preceding-sibling::*")
            if siblings:
                siblings[-1].tail = (siblings[-1].tail or "") + target.tail
            else:
                parent.text = (parent.text or "") + target.tail
            target.tail = None
        parent.addnext(target)
        # Clean up parent if it became an empty token shell
        if not parent.text and len(parent) == 0:
            parent.getparent().remove(parent)
        print(f"  [PATCH] patched {xml_to_string_no_attr(s)}", flush=True)
      
      # patch interval tokens (and maybe some others):
      # <tok xml:id="w-10134" ord="1-3">10—1<dtok ord="1" form="10" lemma="10" upos="NUM" xpos="C=-------------" feats="NumForm=Digit|NumType=Card" /><dtok ord="2" form="—" lemma="—" upos="PUNCT" xpos="Z:-------------" /><dtok ord="3" form="1" lemma="1" upos="NUM" xpos="C=-------------" feats="NumForm=Digit|NumType=Card" /></tok>
      # should be converted to:
      # <tok ord="1" lemma="10" upos="NUM" xpos="C=-------------" feats="NumForm=Digit|NumType=Card">10</tok><tok ord="2" lemma="—" upos="PUNCT" xpos="Z:-------------">—</tok><tok ord="3" lemma="1" upos="NUM" xpos="C=-------------" feats="NumForm=Digit|NumType=Card">1</tok>
      # if tok contains dtok children, that is PUNCT
      while token := s.xpath(".//*[local-name()='tok'][*[local-name()='dtok'][@upos='PUNCT' or @upos='SYM']]"):
        tokens = list(token[0].iter())
        print(f"  [PATCH] Splitting token {token[0].get(f'{{{XML_NS}}}id')} into {len(tokens)} tokens", flush=True)
        for tok in tokens:
          if localname(tok.tag) == "dtok":
            new_tok = etree.Element(q("tok"))
            for k, v in tok.attrib.items():
              new_tok.set(k, v)
            new_tok.text = tok.get("form", "")
            ##new_tok.remove("form")
            token[0].addprevious(new_tok)
        if token[0].tail:
          token[0].getprevious().tail = token[0].tail
          token[0].tail = None
        token[0].getparent().remove(token[0])


      token_idx = 1
      # convert tok -> w / pc
      tokens = list(s.iter())
      for tok in tokens:
        token_idx = process_token(tok, s_id, token_idx)
      
      # postprocess patching - move space tailing last token in name element to the name tail element itself
      for name in s.xpath(".//*[local-name()='name']"):
        last_tok = name.xpath(".//*[last()][local-name()='w' or local-name()='pc']")
        if not last_tok:
          continue
        last_tok = last_tok[0]
        if last_tok.tail and last_tok.tail.strip() == "":
          print(f"  [PATCH] Moving tail space from token {last_tok.get(f'{{{XML_NS}}}id')} to name {name.get(f'{{{XML_NS}}}id')}", flush=True)
          print(f"  [PATCH] patching {xml_to_string_no_attr(s)}", flush=True)
          name.tail = (name.tail or "") + last_tok.tail
          last_tok.tail = None
          print(f"  [PATCH] patched {xml_to_string_no_attr(s)}", flush=True)

    # remove helper attrs
    for el in root.iter():

        for attr in ["form", "text"]:
            if attr in el.attrib:
                del el.attrib[attr]
        if localname(el.tag) == "p":
            el.attrib.pop("cont", None)
    root.attrib.pop('xmlnsoff', None)
    etree.cleanup_namespaces(tree)
    return tree

def process_token(tok, s_id, token_idx):
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
         if k == "form":
              if old_tag == "dtok":
                attrs["norm"] = v
              continue
         if k == "lemma":
              attrs["lemma"] = v
              continue
         print (f"WARN: Unhandled attribute {k}={v} in token {token_idx} of sentence {s_id}", flush=True)
    tok.attrib.clear()
    # dtok (part of contraction) has no own surface form -> no join
    if old_tag == "tok" and not has_space_after(tok):
      attrs["join"] = "right"
    elif old_tag == "dtok":
      attrs.pop("join", None)
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


def xml_to_string_no_attr(elem):
    e = copy.deepcopy(elem)
    e.attrib.clear()
    for ch in e.iter():
        ch.attrib.clear()
    return etree.tostring(e, encoding="utf-8", xml_declaration=False).decode("utf-8")


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