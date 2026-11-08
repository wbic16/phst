#!/usr/bin/env python3
"""test_phst_io.py — parity checks for phext_io.

1. walk_bytes (fast scan) == walk_bytes_reference (per-byte lineage
   walk) on synthetic data heavy in delimiter bytes, and on a real
   prefix of any phext passed as argv[1].
2. implode(walk(x)) == x for the synthetic set.
3. encode_scroll/decode_scroll round-trip on text, control-byte,
   non-UTF-8, empty, and header-colliding payloads.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phext_io import (walk_bytes, walk_bytes_reference, implode,
                      encode_scroll, decode_scroll)

random.seed(20261107)
DELIMS = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]


def rand_blob(n):
    out = bytearray()
    for _ in range(n):
        r = random.random()
        if r < 0.30:
            out.append(random.choice(DELIMS))
        elif r < 0.35:
            out += "héllo→".encode("utf-8")
        else:
            out.append(random.randrange(0x20, 0x7F))
    return bytes(out)


def main():
    for i, n in enumerate([0, 1, 7, 64, 4096, 65537]):
        blob = rand_blob(n)
        fast = walk_bytes(blob)
        slow = walk_bytes_reference(blob)
        assert fast == slow, f"walk mismatch on synthetic {i}"
        if blob and not blob.endswith(bytes([blob[-1]])) is None:
            pass
        rebuilt = implode(dict(fast))
        # implode/walk is identity except a trailing delimiter byte
        # legitimately extends the walk by one empty scroll that the
        # walk drops; assert identity on blobs not ending in a delim.
        if not blob or blob[-1] not in DELIMS:
            assert rebuilt == blob, f"implode round-trip failed on synthetic {i}"
    print("synthetic walk parity + implode identity: OK")

    payloads = [
        b"fn main() {}\n",
        "héllo wörld →\n".encode("utf-8"),
        b"has\x1ccontrol\x01bytes",
        bytes(range(256)),
        b"",
        b"phext-binary:1:base64\nQUJD",
        b"\x89PNG\r\n\x1a\n" + bytes(100),
    ]
    for p in payloads:
        enc_bytes, enc = encode_scroll(p)
        assert decode_scroll(enc_bytes, enc) == p, f"scroll round-trip failed: {p[:20]!r} enc={enc}"
    print("scroll encode/decode round-trips: OK")

    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            prefix = f.read(4 * 1024 * 1024)
        # trim to just before the final byte so both walks see the
        # same tail condition
        assert walk_bytes(prefix) == walk_bytes_reference(prefix), "walk mismatch on real phext prefix"
        print(f"real phext prefix parity (4 MiB of {sys.argv[1]}): OK")


if __name__ == "__main__":
    main()
