#!/usr/bin/env python3
"""phst_members.py — importer v2: member grain for the named subset.

Mirrors phcc's importer v3 (import_fn.py) one-for-one in structure:
reads the v1 (file-grain) phext, inherits every scroll
byte-identical, and ADDS:

  Collection 4 (Source), Volume 3 — mirrors the file's Volume 2
  placement (same Book/Chapter/Section) for each subset file:
    Scroll 1      = the file's index/header scroll (segment table)
    Scrolls 2..   = segment scrolls in source order, tiling the file
                    bytes exactly: member segments (top-level Rust
                    items) and gap segments (everything else)
  Collection 1 (Meta), Volume 3, Book 10, Ch 1:
    Sec 1 = rebind manifest (Vol-2 file address -> member addresses)
    Sec 2 = layout notes
    Sec 3 = degradation register (subset files kept file-level, why)

Parser: tree-sitter Rust grammar over raw bytes (spans are original
byte offsets by construction). Losslessness never depends on parse
quality: segments tile [0, size) by construction, asserted per file.
Attribute items directly preceding an item are folded into that
item's span (attributes are part of the item's text in Rust source).

Run with a venv python that has tree-sitter + tree-sitter-rust:
  venv/bin/python tools/phst_members.py --base PHEXT --out PHEXT \
      --subset compiler/rustc_lexer [--subset ...]
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phext_io import walk_bytes, implode, fmt, sha256, parse_coord

from tree_sitter import Language, Parser
import tree_sitter_rust

PARSER = Parser(Language(tree_sitter_rust.language()))
try:
    import importlib.metadata as _md
    TS_VERSION = (f"tree-sitter-rust {_md.version('tree-sitter-rust')} / "
                  f"tree-sitter {_md.version('tree-sitter')}")
except Exception:
    TS_VERSION = "tree-sitter-rust (version unrecorded)"

# node type -> (kind, form). Name extraction below.
ITEM_KINDS = {
    "function_item": ("function", "def"),
    "struct_item": ("type", "struct"),
    "enum_item": ("type", "enum"),
    "union_item": ("type", "union"),
    "trait_item": ("type", "trait"),
    "type_item": ("type", "alias"),
    "impl_item": ("impl", "def"),
    "const_item": ("object", "const"),
    "static_item": ("object", "static"),
    "mod_item": ("mod", None),          # form: def if body else decl
    "macro_definition": ("object", "macro"),
    "use_declaration": ("object", "use"),
    "extern_crate_declaration": ("object", "extern-crate"),
    "foreign_mod_item": ("object", "extern-block"),
}


def node_text(data, node):
    return data[node.start_byte:node.end_byte].decode("utf-8", "replace")


def item_name(data, node):
    t = node.type
    if t == "impl_item":
        ty = node.child_by_field_name("type")
        if ty is not None:
            txt = " ".join(node_text(data, ty).split())
            return f"impl {txt[:60]}"
        return "impl ?"
    if t == "use_declaration":
        txt = " ".join(node_text(data, node).split())
        return txt[:60]
    name = node.child_by_field_name("name")
    if name is not None:
        return node_text(data, name)
    return "?"


def classify(data, node):
    """Return (kind, name, form, start, end) for a top-level node,
    or None -> gap material."""
    if node.type not in ITEM_KINDS:
        return None
    kind, form = ITEM_KINDS[node.type]
    if node.type == "mod_item":
        form = "def" if node.child_by_field_name("body") is not None else "decl"
    return (kind, item_name(data, node), form, node.start_byte, node.end_byte)


def top_level_nodes(root):
    return list(root.children)


def error_spans(node, acc):
    if node.type == "ERROR":
        acc.append((node.start_byte, node.end_byte))
        return
    for c in node.children:
        error_spans(c, acc)


def segment_file(data):
    """Parse one .rs file; return (segments, n_members, err_bytes)
    where segments = [(kind, name, form, start, end)] tiling
    [0, len(data)). Leading attribute_item runs fold into the
    following member's span."""
    tree = PARSER.parse(data)
    members = []
    pending_attr_start = None
    for node in top_level_nodes(tree.root_node):
        if node.type == "attribute_item":
            if pending_attr_start is None:
                pending_attr_start = node.start_byte
            continue
        c = classify(data, node)
        if c is not None:
            kind, name, form, s, e = c
            if pending_attr_start is not None:
                s = pending_attr_start
            members.append((kind, name, form, s, e))
            pending_attr_start = None
        else:
            pending_attr_start = None
    members.sort(key=lambda m: m[3])
    clean, last_end = [], -1
    for m in members:
        if m[3] >= last_end:
            clean.append(m)
            last_end = m[4]
    segments, cur = [], 0
    for kind, name, form, s, e in clean:
        if s > cur:
            segments.append(("gap", "-", "-", cur, s))
        segments.append((kind, name, form, s, e))
        cur = e
    if cur < len(data):
        segments.append(("gap", "-", "-", cur, len(data)))
    if not segments:
        segments = [("gap", "-", "-", 0, len(data))]
    assert segments[0][3] == 0 and segments[-1][4] == len(data)
    for x, y in zip(segments, segments[1:]):
        assert x[4] == y[3], "tiling hole"
    eb = []
    error_spans(tree.root_node, eb)
    err_bytes = 0
    for s, e in eb:
        inside = sum(m[4] - m[3] for m in clean if m[3] >= s and m[4] <= e)
        err_bytes += (e - s) - inside
    return segments, len(clean), err_bytes


LAYOUT_NOTES = """# phst.phext — Volume 3 layout notes (importer v2, member grain)

The phext-native rule (Will, D6 reversed on phcc, carried here):
Source is structured below the file. Volume 2 remains the
bridge/legacy path — file import, Scroll 1 = whole file bytes,
untouched. Volume 3 (Collection 4, Source) mirrors Volume 2
placement path-for-path (same Book/Chapter/Section) and splits each
subset file at its own address:

- Scroll 1: index/header scroll — path, Volume-2 coordinate, file
  SHA-256/size, parse status, and the segment table.
- Scrolls 2..: segment scrolls in source order, tiling the file
  bytes exactly. kind = function, type (struct/enum/union/trait/
  alias), object (const/static/use/macro/extern), impl, mod,
  gap (everything else: comments, whitespace, unclassifiable
  constructs, parse-error regions). Each segment scroll = one
  '#phst-member' header line (kind/name/form/span/sha256 of
  payload) + the segment's exact bytes.
- Reassembly = concatenate segment payloads in scroll order; the
  Volume-2 scroll is never consulted.

v0 subset: the files named in the rebind manifest (Meta Vol 3,
Book 10, Ch 1, Sec 1). Widening the subset is a re-run of this
tool with more --subset prefixes; Volume 3 addresses for files
already segmented never move.
"""


def parse_manifest(scrolls):
    coord = (1, 1, 1, 1, 2, 10, 1, 1, 1)
    entries = []
    for line in scrolls[coord].decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        path, coord_s, sha, size, mode, enc = line.split("\t")
        entries.append({"path": path, "coord": parse_coord(coord_s),
                        "sha": sha, "size": int(size), "mode": mode, "enc": enc})
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--subset", action="append", required=True,
                    help="path prefix of the member-grain subset (repeatable)")
    a = ap.parse_args()

    base_bytes = open(a.base, "rb").read()
    scrolls = dict(walk_bytes(base_bytes))
    assert implode(scrolls) == base_bytes, "BASE ROUND-TRIP FAILED: implode(walk(base)) != base"
    print(f"base: {len(base_bytes)} bytes, {len(scrolls)} scrolls, re-emission byte-identical OK")

    entries = parse_manifest(scrolls)
    subset = [e for e in entries
              if any(e["path"] == s or e["path"].startswith(s.rstrip("/") + "/")
                     for s in a.subset)]
    print(f"manifest: {len(entries)} files; subset: {len(subset)} files")

    new_scrolls = {}
    map_lines = ["# phst rebind manifest — importer v2 (Volume 2 file address -> Volume 3 member addresses)",
                 f"# base phext sha256 {sha256(base_bytes)}",
                 "# columns: path <TAB> vol2-coordinate <TAB> member-coordinate <TAB> kind <TAB> name <TAB> form <TAB> span <TAB> sha256"]
    reg_lines = ["# degradation register — importer v2",
                 "# columns: path <TAB> status <TAB> reason"]
    stats = {"subset_files": len(subset), "files_structured": 0, "files_file_level": 0,
             "files_partial": 0,
             "members": {"function": 0, "type": 0, "object": 0, "impl": 0, "mod": 0},
             "segments_total": 0, "gap_segments": 0, "degraded": [], "partial": []}

    for e in subset:
        path, v2 = e["path"], e["coord"]
        from phext_io import decode_scroll
        data = decode_scroll(scrolls[v2], e["enc"])
        assert sha256(data) == e["sha"], f"base scroll hash mismatch: {path}"
        book, chapter, section = v2[5], v2[6], v2[7]
        if not path.endswith(".rs"):
            reg_lines.append(f"{path}\tfile-level\tnot Rust source; bridge path only")
            map_lines.append(f"# file\t{path}\t{fmt(v2)}\tfile-level (not Rust source)")
            stats["files_file_level"] += 1
            stats["degraded"].append({"path": path, "reason": "not Rust source"})
            continue
        segments, n_members, err_bytes = segment_file(data)
        if n_members == 0:
            reg_lines.append(f"{path}\tfile-level\tzero members extracted; bridge path only")
            map_lines.append(f"# file\t{path}\t{fmt(v2)}\tfile-level (zero members extracted)")
            stats["files_file_level"] += 1
            stats["degraded"].append({"path": path, "reason": "zero members extracted"})
            continue
        err_pct = 100.0 * err_bytes / max(len(data), 1)
        if err_bytes > 0:
            stats["files_partial"] += 1
            reg_lines.append(f"{path}\tpartial\ttree-sitter error regions cover {err_bytes} bytes ({err_pct:.1f}%); unclassified bytes are gap segments")
            stats["partial"].append({"path": path, "error_bytes": err_bytes, "error_pct": round(err_pct, 1)})
        stats["files_structured"] += 1

        idx_coord = (1, 1, 1, 4, 3, book, chapter, section, 1)
        idx_lines = ["# phst file index — importer v2",
                     f"# path: {path}",
                     f"# volume2: {fmt(v2)}",
                     f"# sha256: {e['sha']}  size: {len(data)}",
                     f"# parse: {TS_VERSION}; members={n_members} error-bytes={err_bytes} ({err_pct:.1f}%)",
                     "# columns: scroll <TAB> kind <TAB> name <TAB> form <TAB> span <TAB> sha256"]
        map_lines.append(f"# file\t{path}\t{fmt(v2)}\tindex {fmt(idx_coord)}")
        for i, (kind, name, form, s, en) in enumerate(segments):
            scr = i + 2
            payload = data[s:en]
            psha = sha256(payload)
            header = f"#phst-member\tkind={kind}\tname={name}\tform={form}\tspan={s}-{en}\tsha256={psha}\n".encode()
            new_scrolls[(1, 1, 1, 4, 3, book, chapter, section, scr)] = header + payload
            idx_lines.append(f"{scr}\t{kind}\t{name}\t{form}\t{s}-{en}\t{psha}")
            stats["segments_total"] += 1
            if kind == "gap":
                stats["gap_segments"] += 1
            else:
                stats["members"][kind] += 1
                mcoord = (1, 1, 1, 4, 3, book, chapter, section, scr)
                map_lines.append(f"{path}\t{fmt(v2)}\t{fmt(mcoord)}\t{kind}\t{name}\t{form}\t{s}-{en}\t{psha}")
        new_scrolls[idx_coord] = ("\n".join(idx_lines) + "\n").encode()

    new_scrolls[(1, 1, 1, 1, 3, 10, 1, 1, 1)] = ("\n".join(map_lines) + "\n").encode()
    new_scrolls[(1, 1, 1, 1, 3, 10, 1, 2, 1)] = LAYOUT_NOTES.encode()
    new_scrolls[(1, 1, 1, 1, 3, 10, 1, 3, 1)] = ("\n".join(reg_lines) + "\n").encode()

    merged = dict(scrolls)
    for k, v in new_scrolls.items():
        assert k not in merged, f"coordinate collision with inherited scroll: {k}"
        merged[k] = v
    blob = implode(merged)
    with open(a.out, "wb") as f:
        f.write(blob)
    back = dict(walk_bytes(blob))
    bad = [k for k, v in scrolls.items() if back.get(k) != v]
    assert not bad, f"inherited scrolls altered: {bad[:3]}"
    bad_new = [k for k, v in new_scrolls.items() if back.get(k) != v]
    assert not bad_new, f"added scrolls altered/missing: {bad_new[:3]}"
    stats["phext_bytes"] = len(blob)
    stats["phext_sha256"] = sha256(blob)
    stats["scrolls_added"] = len(new_scrolls)
    print(f"output: {a.out}  {len(blob)} bytes  sha256 {stats['phext_sha256']}")
    print(f"scrolls: {len(back)} total ({len(new_scrolls)} added); inherited byte-identical OK")
    print(json.dumps({k: v for k, v in stats.items() if k not in ("degraded", "partial")}, indent=1))
    print(f"degraded: {len(stats['degraded'])}  partial: {len(stats['partial'])}")
    with open(a.stats, "w") as f:
        json.dump(stats, f, indent=1)


if __name__ == "__main__":
    main()
