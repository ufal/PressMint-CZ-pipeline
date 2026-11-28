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

usage: ads2back.py [-j N] [-v] FILE_OR_DIR...   (directories are searched for *.xml recursively,
       -j N parallel worker processes, -v lists every patched file)
"""
import argparse
import multiprocessing
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


def patch_safe(path):
    """for the worker pool: (path, moved, error message)"""
    try:
        return path, patch(path), None
    except (etree.XMLSyntaxError, OSError) as e:
        return path, 0, str(e)


def iter_files(paths):
    for arg in paths:
        p = Path(arg)
        if p.is_dir():
            yield from sorted(p.rglob("*.xml"))
        else:
            yield p


def main():
    ap = argparse.ArgumentParser(description="Move advertisements from text/body to text/back.")
    ap.add_argument("paths", nargs="+", metavar="FILE_OR_DIR",
                    help="TEI files or directories (searched for *.xml recursively)")
    ap.add_argument("-j", "--jobs", type=int, default=1,
                    help="number of parallel worker processes (default 1, 0 = all CPUs)")
    ap.add_argument("-v", "--verbose", action="store_true", help="list every patched file")
    args = ap.parse_args()
    jobs = args.jobs or os.cpu_count() or 1
    files = list(iter_files(args.paths))
    n_patched = n_ads = n_err = 0
    if jobs > 1 and len(files) > 1:
        pool = multiprocessing.Pool(min(jobs, len(files)))
        results = pool.imap_unordered(patch_safe, files, chunksize=8)
    else:
        pool = None
        results = map(patch_safe, files)
    try:
        for i, (f, m, err) in enumerate(results, 1):
            if err:
                print(f"ERROR: {f}: {err}", file=sys.stderr)
                n_err += 1
            elif m:
                n_patched += 1
                n_ads += m
                if args.verbose:
                    print(f"INFO: {f}: {m} advertisement(s) moved to back")
            if i % 10000 == 0:
                print(f"INFO: {i}/{len(files)} files done", file=sys.stderr)
    finally:
        if pool:
            pool.close()
            pool.join()
    print(f"INFO: {len(files)} files, {n_patched} patched, {n_ads} advertisements moved, "
          f"{n_err} errors ({jobs} jobs)", file=sys.stderr)
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
