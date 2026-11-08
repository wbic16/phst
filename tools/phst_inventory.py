#!/usr/bin/env python3
"""phst_inventory.py — measured inventory of an upstream rust tree.

Walks `git ls-files` in the given repo and reports, per top-level
area: file counts, bytes on disk, line counts (all files that decode
as UTF-8), and .rs line counts. Also: extension histogram, symlink
and gitlink counts, largest files, and the same stats for any
candidate subset directories named with --subset.

Output: JSON to --out plus a human summary on stdout. Stdlib only.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, check=True).stdout


def area_of(path):
    parts = path.split("/")
    if len(parts) == 1:
        return "(root)"
    return parts[0] + "/"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--subset", action="append", default=[])
    a = ap.parse_args()

    head = git(a.repo, "rev-parse", "HEAD").decode().strip()
    entries = []  # (mode, sha, path)
    raw = git(a.repo, "ls-files", "-s", "-z")
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, sha = meta.decode().split()[:2]
        entries.append((mode, sha, path.decode("utf-8", "surrogateescape")))

    areas = defaultdict(lambda: {"files": 0, "bytes": 0, "lines": 0, "rs_lines": 0, "rs_files": 0})
    exts = Counter()
    gitlinks, symlinks = [], []
    largest = []
    subsets = {s: {"files": 0, "bytes": 0, "lines": 0, "rs_lines": 0, "rs_files": 0}
               for s in a.subset}
    total = {"files": 0, "bytes": 0, "lines": 0, "rs_lines": 0, "rs_files": 0}

    for mode, sha, path in entries:
        if mode == "160000":
            gitlinks.append({"path": path, "sha": sha})
            continue
        full = os.path.join(a.repo, path)
        if mode == "120000":
            symlinks.append(path)
            data = os.readlink(full).encode()
            size = len(data)
            lines = 0
        else:
            with open(full, "rb") as f:
                data = f.read()
            size = len(data)
            try:
                text = data.decode("utf-8")
                lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            except UnicodeDecodeError:
                lines = 0
        ar = areas[area_of(path)]
        is_rs = path.endswith(".rs")
        for tgt in (ar, total):
            tgt["files"] += 1
            tgt["bytes"] += size
            tgt["lines"] += lines
            if is_rs:
                tgt["rs_lines"] += lines
                tgt["rs_files"] += 1
        ext = os.path.splitext(path)[1].lower() or "(none)"
        exts[ext] += 1
        largest.append((size, path))
        for s in a.subset:
            if path == s or path.startswith(s.rstrip("/") + "/"):
                st = subsets[s]
                st["files"] += 1
                st["bytes"] += size
                st["lines"] += lines
                if is_rs:
                    st["rs_lines"] += lines
                    st["rs_files"] += 1

    largest.sort(reverse=True)
    report = {
        "upstream_commit": head,
        "total": total,
        "areas": {k: areas[k] for k in sorted(areas)},
        "extensions_top20": exts.most_common(20),
        "gitlinks": gitlinks,
        "symlinks": symlinks,
        "largest_files": [{"path": p, "bytes": s} for s, p in largest[:15]],
        "subsets": subsets,
    }
    with open(a.out, "w") as f:
        json.dump(report, f, indent=1)

    def mib(b):
        return f"{b / 1048576:.1f} MiB"

    print(f"upstream commit: {head}")
    print(f"TOTAL: {total['files']} files, {mib(total['bytes'])}, "
          f"{total['lines']:,} lines ({total['rs_lines']:,} in {total['rs_files']} .rs files)")
    for k in sorted(areas):
        v = areas[k]
        print(f"  {k:12s} {v['files']:6d} files  {mib(v['bytes']):>10s}  "
              f"{v['lines']:>10,} lines  rs {v['rs_lines']:,}")
    print(f"gitlinks (submodules, content not imported): {len(gitlinks)}")
    for g in gitlinks:
        print(f"  {g['path']} @ {g['sha']}")
    print(f"symlinks: {len(symlinks)}")
    for s, v in subsets.items():
        print(f"subset {s}: {v['files']} files, {mib(v['bytes'])}, "
              f"{v['lines']:,} lines ({v['rs_lines']:,} rs in {v['rs_files']} files)")
    print("largest files:")
    for lf in report["largest_files"][:8]:
        print(f"  {mib(lf['bytes']):>10s}  {lf['path']}")


if __name__ == "__main__":
    main()
