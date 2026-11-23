#!/usr/bin/env python3
"""Move advertisements from TEI/text/body to TEI/text/back (patch of existing TEI files).

text/body/div[@type=advertisement] (direct children of body) are moved, in document order,
to text/back (created right after body when missing), so the text is
<front>? <body> <back>. Works on tei-text, tei-text.TT and tei-text.ana files (the moved divs
keep their content incl. annotation and ids). Advertisements are the last children of body
(analysis2tei.py writes the ads stream last), so the document order of divs and their
position based ids are kept.

Files are rewritten in place (atomically) only when something was moved, so it is safe
to run repeatedly.

usage: ads2back.py [-v] FILE_OR_DIR...   (directories are searched for *.xml recursively,
       -v lists every patched file)
"""
import os
import sys
import tempfile
from pathlib import Path

from lxml import etree

def child(el, name):
    """first child element with the local name (TEI namespace or none: flexipipe writes
    tei-text.TT without the namespace, as xmlnsoff)"""
    return next(iter(children(el, name)), None)


def children(el, name):
    return [c for c in el if isinstance(c.tag, str) and etree.QName(c).localname == name]


def patch(path):
    """returns number of moved advertisements"""
    tree = etree.parse(str(path))
    moved = 0
    for text in tree.getroot().iter("{*}text"):
        body = child(text, "body")
        if body is None:
            continue
        ads = [d for d in children(body, "div") if d.get("type") == "advertisement"]
        if not ads:
            continue
        back = child(text, "back")
        if back is None:
            ns = etree.QName(body).namespace
            back = etree.Element(f"{{{ns}}}back" if ns else "back")
            back.text = body.text
            back.tail = body.tail
            body.addnext(back)
        last_tail = body[-1].tail if len(body) else None
        for d in ads:
            back.append(d)        # the div's tail moves with it
            moved += 1
        # keep the closing tags indented as before
        if len(body):
            body[-1].tail = last_tail
        back[-1].tail = last_tail
    if moved:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        os.close(fd)
        try:
            tree.write(tmp, encoding="utf-8", xml_declaration=True)
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise
    return moved


def main():
    args = sys.argv[1:]
    verbose = "-v" in args
    args = [a for a in args if a != "-v"]
    if not args:
        sys.exit(__doc__)
    n_files = n_patched = n_ads = n_err = 0
    for arg in args:
        p = Path(arg)
        files = sorted(p.rglob("*.xml")) if p.is_dir() else [p]
        for f in files:
            n_files += 1
            try:
                m = patch(f)
            except etree.XMLSyntaxError as e:
                print(f"ERROR: {f}: {e}", file=sys.stderr)
                n_err += 1
                continue
            if m:
                n_patched += 1
                n_ads += m
                if verbose:
                    print(f"INFO: {f}: {m} advertisement(s) moved to back")
    print(f"INFO: {n_files} files, {n_patched} patched, {n_ads} advertisements moved, {n_err} errors",
          file=sys.stderr)
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
