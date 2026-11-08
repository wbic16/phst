#!/usr/bin/env python3
"""phext_io.py — byte-exact phext read/write helpers for phst.

Behaviour copied from the phcc importer lineage (Slice 0
tools/import_phcc.py, via phcc-migrate/phext_io.py) so phst's phext
stays byte-format consistent with phcc's. Stdlib only.

Coordinate tuple order: (library, shelf, series, collection, volume,
book, chapter, section, scroll).

walk_bytes() is a regex-scanned equivalent of the lineage's per-byte
dead-reckoning walk — same state machine, same outputs; the per-byte
original is kept as walk_bytes_reference() and the two are asserted
equal by tools/test_phst_io.py on synthetic data and on a prefix of
the real phst.phext. The scan exists because phst's tree is ~10x
phcc's; the format is unchanged.
"""
import base64
import hashlib
import re

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)
DELIM_TO_LEVEL = {b: i for i, b in enumerate(LEVEL_BYTES)}
_DELIM_RE = re.compile(rb"[\x01\x17-\x1f]")

BINARY_HEADER = b"phext-binary:1:base64"


def fmt(coord):
    return f"{coord[0]}.{coord[1]}.{coord[2]}/{coord[3]}.{coord[4]}.{coord[5]}/{coord[6]}.{coord[7]}.{coord[8]}"


def parse_coord(s):
    a, b, c = s.split("/")
    parts = []
    for grp in (a, b, c):
        parts += [int(x) for x in grp.split(".")]
    return tuple(parts)


def walk_bytes_reference(data):
    """The lineage per-byte walk, verbatim in behaviour. Reference
    for walk_bytes(); do not use on full-size phexts (slow by
    design)."""
    coord = [1] * 9
    buf = bytearray()
    out = []
    for b in data:
        lvl = DELIM_TO_LEVEL.get(b)
        if lvl is None:
            buf.append(b)
        else:
            out.append((tuple(coord), bytes(buf)))
            buf = bytearray()
            coord[lvl] += 1
            for j in range(lvl + 1, 9):
                coord[j] = 1
    out.append((tuple(coord), bytes(buf)))
    if out and out[-1][1] == b"":
        out.pop()
    return out


def walk_bytes(data):
    """Dead-reckoning byte walk — yields (coord_tuple, bytes) so
    scrolls stay byte-exact. Semantically identical to
    walk_bytes_reference(); scans delimiters at C speed."""
    coord = [1] * 9
    out = []
    pos = 0
    for m in _DELIM_RE.finditer(data):
        out.append((tuple(coord), data[pos:m.start()]))
        lvl = DELIM_TO_LEVEL[m.group()[0]]
        coord[lvl] += 1
        for j in range(lvl + 1, 9):
            coord[j] = 1
        pos = m.end()
    out.append((tuple(coord), data[pos:]))
    if out and out[-1][1] == b"":
        out.pop()
    return out


def implode(scrolls):
    """scrolls: dict coord_tuple -> bytes. Same emitter as the phcc
    lineage (build_tasks_phext.py / import_phcc.py)."""
    out = bytearray()
    state = [1] * 9
    for target in sorted(scrolls):
        for lvl in range(9):
            while state[lvl] < target[lvl]:
                out.append(LEVEL_BYTES[lvl])
                state[lvl] += 1
                for j in range(lvl + 1, 9):
                    state[j] = 1
        assert tuple(state) == target, (state, target)
        out += scrolls[target]
    return bytes(out)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_phext(path):
    with open(path, "rb") as f:
        return dict(walk_bytes(f.read()))


# ------------------------------------------------------- binary scrolls
def encode_scroll(data):
    """Return (scroll_bytes, encoding) for one file's bytes.

    encoding 'raw': data is valid UTF-8, contains no phext delimiter
    byte, and does not itself begin with the binary header line —
    placed verbatim. Otherwise 'binary': the canonical libphext
    binary format (scroll = header line 'phext-binary:1:base64' +
    LF + RFC 4648 base64, padding required, no wrapping). This
    follows the standing ingestion rule: non-UTF-8 data observed in
    an incoming scroll is encoded base64 verbatim.
    """
    if not data.startswith(BINARY_HEADER) and _DELIM_RE.search(data) is None:
        try:
            data.decode("utf-8")
            return data, "raw"
        except UnicodeDecodeError:
            pass
    return BINARY_HEADER + b"\n" + base64.b64encode(data), "binary"


def decode_scroll(scroll, encoding):
    """Inverse of encode_scroll. The manifest's encoding column is
    authoritative; 'binary' scrolls are base64-decoded after the
    header line, anything else is returned verbatim."""
    if encoding == "binary":
        assert scroll.startswith(BINARY_HEADER + b"\n"), "binary scroll missing header"
        return base64.b64decode(scroll[len(BINARY_HEADER) + 1:])
    return scroll
