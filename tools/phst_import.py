#!/usr/bin/env python3
"""phst_import.py — importer v1: upstream rust tree -> ONE phext.

phst carries rust-lang/rust the way phcc carries TinyCC (Slice 0
pattern): the full tree at FILE grain, a placement manifest binding
every file to its coordinate + SHA-256, byte-exact round-trip as the
exit test. Member grain is a separate pass (phst_members.py),
mirroring phcc's importer v3.

Layout of the produced phext (outer Library.Shelf.Series = 1.1.1):
  Collection 1 (Meta), Vol 1, Book 1, Ch 1, Sec 1, Scroll 1
      = identity scroll: phst, upstream repo + pinned commit,
        inventory headline.
  Collection 1 (Meta), Vol 2, Book 10, Ch 1:
      Sec 1 = placement manifest (path -> coordinate, SHA-256,
              size, git mode, encoding)
      Sec 2 = layout notes
      Sec 3 = exclusions register (gitlinks/submodules with their
              pinned SHAs; anything not placed, with reason)
  Collection 4 (Source), Vol 2 — the file-grain import:
      Book    = top-level area: 1 compiler/, 2 library/, 3 src/,
                4 tests/, 5 everything else (root files, .github/,
                LICENSES/, ...)
      Chapter = second-level component within the book (sorted;
                files sitting directly in an area root form the
                first component, "")
      Section = file, sequential within chapter, path-sorted
      Scroll 1 = the file's bytes (verbatim, or a canonical
                phext-binary base64 scroll — see phext_io)
  Collection 10 (Proofs), Vol 99, Book 99, Ch 99, Sec 99, Scroll 99
      = endmark scroll. Guarantees the phext's last placed scroll is
        never the trailing byte (a trailing empty scroll is not
        representable in the walk). One structural scroll, counted
        separately in every receipt.

Import scope = `git ls-files` of the upstream tree. Gitlinks
(submodules) are recorded in the exclusions register with the SHA
the superproject pins; their content belongs to other repos and is
not imported (the phcc monolith.phext exclusion is the precedent:
what cannot or should not be contained is registered, not silently
dropped). Symlinks are placed: scroll content = target bytes, git
mode 120000 in the manifest, restored as symlinks on export.

Stdlib only. Usage:
  phst_import.py --repo DIR --out FILE.phext --stats FILE.json
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phext_io import walk_bytes, implode, fmt, sha256, encode_scroll

BOOKS = {"compiler": 1, "library": 2, "src": 3, "tests": 4}
ENDMARK = (1, 1, 1, 10, 99, 99, 99, 99, 99)
MANIFEST_COORD = (1, 1, 1, 1, 2, 10, 1, 1, 1)
NOTES_COORD = (1, 1, 1, 1, 2, 10, 1, 2, 1)
EXCL_COORD = (1, 1, 1, 1, 2, 10, 1, 3, 1)
IDENT_COORD = (1, 1, 1, 1, 1, 1, 1, 1, 1)

LAYOUT_NOTES = """# phst.phext — Volume 2 layout notes (importer v1, file grain)

Source (Collection 4), Volume 2 carries the entire upstream tree at
file grain — the bridge form, exactly as phcc's Volume 2 carries
TinyCC. Book = top-level area (1 compiler/, 2 library/, 3 src/,
4 tests/, 5 everything else incl. repository-root files). Chapter =
second-level component within the book, assigned in sorted order;
files directly under an area root are the first component ("").
Section = one file, sequential within its chapter, path-sorted.
Scroll 1 = the file itself.

A scroll holds the file's bytes verbatim when they are valid UTF-8
with no phext delimiter byte; otherwise it holds the canonical
binary form (header line 'phext-binary:1:base64' + base64), and the
manifest's encoding column says which. The manifest (Meta Vol 2,
Book 10, Ch 1, Sec 1) is authoritative: path, coordinate, SHA-256 of
the ORIGINAL bytes, size, git mode, encoding.

Member grain (importer v2, phst_members.py) mirrors this volume at
Volume 3 for the named subset, phcc importer-v3 style; Volume 2 is
never rewritten by that pass.

Exclusions (Meta Vol 2, Book 10, Ch 1, Sec 3): gitlinks — the 13
submodules rust-lang/rust pins (src/llvm-project, src/tools/cargo,
the doc books, ...) — are registered with their pinned SHAs. Their
content lives in other repositories; registering the pin keeps the
carried tree honest about what it does not contain.
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, check=True).stdout


def placement(entries):
    """entries: list of paths (files only). Returns {path: coord}."""
    # group: (book, component) -> [paths]
    groups = {}
    for path in entries:
        parts = path.split("/")
        area = parts[0] if len(parts) > 1 else "(root)"
        book = BOOKS.get(area, 5)
        if book == 5:
            comp = parts[0] if len(parts) > 1 else ""
        else:
            comp = parts[1] if len(parts) > 2 else ""
        groups.setdefault((book, comp), []).append(path)
    # chapter numbers per book, components sorted ("" first: it is
    # the empty string, sorts before any name)
    books = {}
    for (book, comp) in groups:
        books.setdefault(book, set()).add(comp)
    chapter_of = {}
    for book, comps in books.items():
        for i, comp in enumerate(sorted(comps)):
            chapter_of[(book, comp)] = i + 1
    coords = {}
    for (book, comp), paths in groups.items():
        ch = chapter_of[(book, comp)]
        for i, path in enumerate(sorted(paths)):
            coords[path] = (1, 1, 1, 4, 2, book, ch, i + 1, 1)
    return coords


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--inventory", help="inventory JSON from phst_inventory.py (headline scroll)")
    a = ap.parse_args()

    head = git(a.repo, "rev-parse", "HEAD").decode().strip()
    raw = git(a.repo, "ls-files", "-s", "-z")
    files, gitlinks = [], []
    modes = {}
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, sha = meta.decode().split()[:2]
        path = path.decode("utf-8", "surrogateescape")
        if mode == "160000":
            gitlinks.append((path, sha))
        else:
            files.append(path)
            modes[path] = mode
    files.sort()
    coords = placement(files)

    scrolls = {}
    man_lines = ["# phst placement manifest — importer v1 (file grain)",
                 f"# upstream: rust-lang/rust @ {head}",
                 "# columns: path <TAB> coordinate <TAB> sha256 <TAB> size <TAB> mode <TAB> encoding"]
    stats = {"upstream_commit": head, "files": 0, "bytes": 0,
             "raw_scrolls": 0, "binary_scrolls": 0, "symlinks": 0,
             "empty_files": 0, "per_book": {}}
    for path in files:
        full = os.path.join(a.repo, path)
        mode = modes[path]
        if mode == "120000":
            data = os.readlink(full).encode()
            stats["symlinks"] += 1
        else:
            with open(full, "rb") as f:
                data = f.read()
        coord = coords[path]
        scroll, enc = encode_scroll(data)
        assert coord not in scrolls, f"coordinate collision: {path}"
        scrolls[coord] = scroll
        sha = sha256(data)
        man_lines.append(f"{path}\t{fmt(coord)}\t{sha}\t{len(data)}\t{mode}\t{enc}")
        stats["files"] += 1
        stats["bytes"] += len(data)
        stats["raw_scrolls" if enc == "raw" else "binary_scrolls"] += 1
        if len(data) == 0:
            stats["empty_files"] += 1
        bk = stats["per_book"].setdefault(str(coord[5]), {"files": 0, "bytes": 0})
        bk["files"] += 1
        bk["bytes"] += len(data)

    excl_lines = ["# phst exclusions register — importer v1",
                  "# gitlinks: submodule pins recorded, content NOT imported (belongs to other repos)",
                  "# columns: path <TAB> pinned-sha <TAB> kind"]
    for path, sha in sorted(gitlinks):
        excl_lines.append(f"{path}\t{sha}\tgitlink")

    inv_headline = ""
    if a.inventory:
        with open(a.inventory) as f:
            inv = json.load(f)
        t = inv["total"]
        inv_headline = (f"Inventory at import: {t['files']} files placed "
                        f"(+ {len(gitlinks)} gitlinks registered), {t['bytes']} bytes, "
                        f"{t['lines']} lines ({t['rs_lines']} in .rs files).")

    ident = ("# phst — the phext fork of Rust (phext native Rust)\n"
             f"# upstream: https://github.com/rust-lang/rust @ {head}\n"
             "# carry model: the phext is the source form; stage0 rustc\n"
             "# builds the carried tree. See docs/DESIGN.md in wbic16/phst.\n"
             f"# {inv_headline}\n")
    scrolls[IDENT_COORD] = ident.encode()
    scrolls[MANIFEST_COORD] = ("\n".join(man_lines) + "\n").encode()
    scrolls[NOTES_COORD] = LAYOUT_NOTES.encode()
    scrolls[EXCL_COORD] = ("\n".join(excl_lines) + "\n").encode()
    scrolls[ENDMARK] = "# phst endmark — importer v1 (structural; see layout notes)\n".encode()

    blob = implode(scrolls)
    with open(a.out, "wb") as f:
        f.write(blob)
    stats["phext_bytes"] = len(blob)
    stats["phext_sha256"] = sha256(blob)
    stats["scrolls_total"] = len(scrolls)

    # verify the written artifact itself: every scroll back intact
    back = dict(walk_bytes(blob))
    bad = [k for k, v in scrolls.items() if back.get(k) != v]
    assert not bad, f"scrolls altered/missing after walk: {bad[:3]}"
    stats["verify"] = "all scrolls byte-identical after walk of written phext"
    print(f"imported {stats['files']} files, {stats['bytes']} bytes "
          f"({stats['raw_scrolls']} raw + {stats['binary_scrolls']} binary scrolls, "
          f"{stats['symlinks']} symlinks, {stats['empty_files']} empty)")
    print(f"phext: {a.out}  {len(blob)} bytes  sha256 {stats['phext_sha256']}")
    with open(a.stats, "w") as f:
        json.dump(stats, f, indent=1)


if __name__ == "__main__":
    main()
