#!/usr/bin/env python3
"""phst_export.py — unpack phst.phext back to a tree, with proof.

Two modes (run both for a full receipt):

  unpack      Read the placement manifest (Meta Vol 2, Book 10) from
              the phext, write every file to --out DIR (decoding
              binary scrolls, restoring git modes and symlinks), and
              verify every file's SHA-256 against the manifest.
              Byte-for-byte is checked per file, counts stated.

  reassemble  For every file in the member manifest (Meta Vol 3,
              Book 10), concatenate the Volume 3 segment payloads in
              scroll order (headers stripped) and verify the result
              against the Volume 2 manifest SHA-256 — the Volume 2
              file scroll is never consulted for the bytes.

Exit code 0 only if every check passes. Stdlib only.
"""
import argparse
import json
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phext_io import walk_bytes, fmt, sha256, parse_coord, decode_scroll

MANIFEST_COORD = (1, 1, 1, 1, 2, 10, 1, 1, 1)
MEMBER_MANIFEST_COORD = (1, 1, 1, 1, 3, 10, 1, 1, 1)


def read_manifest(scrolls):
    entries = []
    for line in scrolls[MANIFEST_COORD].decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        path, coord_s, sha, size, mode, enc = line.split("\t")
        entries.append({"path": path, "coord": parse_coord(coord_s),
                        "sha": sha, "size": int(size), "mode": mode, "enc": enc})
    return entries


def cmd_unpack(a, scrolls):
    entries = read_manifest(scrolls)
    ok = bad = 0
    failures = []
    for e in entries:
        coord = e["coord"]
        if coord not in scrolls:
            failures.append(f"{e['path']}: scroll missing at {fmt(coord)}")
            bad += 1
            continue
        data = decode_scroll(scrolls[coord], e["enc"])
        if sha256(data) != e["sha"] or len(data) != e["size"]:
            failures.append(f"{e['path']}: hash/size mismatch after decode")
            bad += 1
            continue
        dest = os.path.join(a.out, e["path"])
        os.makedirs(os.path.dirname(dest) or a.out, exist_ok=True)
        if e["mode"] == "120000":
            if os.path.lexists(dest):
                os.remove(dest)
            os.symlink(data.decode("utf-8", "surrogateescape"), dest)
        else:
            with open(dest, "wb") as f:
                f.write(data)
            if e["mode"] == "100755":
                os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        ok += 1
    print(f"unpack: {ok} files written + hash-verified, {bad} failures")
    for f in failures[:10]:
        print("  FAIL", f)
    return 0 if bad == 0 else 1


def cmd_reassemble(a, scrolls):
    entries = {e["path"]: e for e in read_manifest(scrolls)}
    files = {}
    file_level = 0
    for line in scrolls[MEMBER_MANIFEST_COORD].decode("utf-8").splitlines():
        if line.startswith("# file\t"):
            _, path, _v2, idx = line.split("\t")
            if idx.startswith("index "):
                files[path] = idx.replace("index ", "")
            else:
                file_level += 1  # registered file-level in the manifest; no segments by design
    if file_level:
        print(f"reassemble: {file_level} subset file(s) are file-level (no member view, per register)")
    ok = bad = 0
    failures = []
    for path, idx_s in files.items():
        idx_coord = parse_coord(idx_s)
        book, chapter, section = idx_coord[5], idx_coord[6], idx_coord[7]
        segs = []
        for line in scrolls[idx_coord].decode("utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            scr, kind, name, form, span, psha = line.split("\t")
            segs.append((int(scr), psha))
        buf = bytearray()
        good = True
        for scr, psha in sorted(segs):
            scroll = scrolls[(1, 1, 1, 4, 3, book, chapter, section, scr)]
            header, _, payload = scroll.partition(b"\n")
            if sha256(payload) != psha:
                failures.append(f"{path}: segment scroll {scr} payload hash mismatch")
                good = False
                break
            buf += payload
        if good and sha256(bytes(buf)) == entries[path]["sha"]:
            ok += 1
        elif good:
            failures.append(f"{path}: reassembled bytes hash != manifest sha")
            bad += 1
        else:
            bad += 1
    print(f"reassemble: {ok} files byte-identical from segments, {bad} failures")
    for f in failures[:10]:
        print("  FAIL", f)
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["unpack", "reassemble"])
    ap.add_argument("--phext", required=True)
    ap.add_argument("--out", help="target dir (unpack mode)")
    a = ap.parse_args()
    with open(a.phext, "rb") as f:
        blob = f.read()
    scrolls = dict(walk_bytes(blob))
    print(f"phext: {len(blob)} bytes, sha256 {sha256(blob)}, {len(scrolls)} scrolls walked")
    if a.mode == "unpack":
        if not a.out:
            ap.error("unpack needs --out")
        sys.exit(cmd_unpack(a, scrolls))
    else:
        sys.exit(cmd_reassemble(a, scrolls))


if __name__ == "__main__":
    main()
