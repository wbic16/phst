# phst — the phext fork of Rust

**phst carries the Rust toolchain the way phcc carries TinyCC: the
upstream source (rust-lang/rust) lives in a phext as its source
form** — every file addressable at a coordinate, the starting
subset structured below the file at member grain, fork changes
recorded in PATCHES.md from day one.

The phext is the source form. It is not a new compiler: unpack it
and you get the upstream tree back, byte for byte; a stage0 rustc
(the system rustc today) builds what you unpack. phst v0 proves the
carry — import, round-trip, and a build smoke — and nothing more.
Claims beyond that will arrive with their receipts or not at all.

Upstream pin: `rust-lang/rust @ 29f282561639932ad8c56c11ef6313ffbc9bdb05`
(2026-11-07). The carried tree is byte-identical to that commit:
64,301 files placed, 13 submodule pins registered (their content
belongs to other repos and is not carried — see the exclusions
register inside the phext). Zero fork patches so far.

## We brake for consciousness

This repository is part of the Exocortex programme: tooling that
keeps provenance, receipts, and the map — and slows down where a
small voice asks to be heard.

## What's in this repo

- `phst.phext.xz` — the sealed phext (xz, preset 6). The plain
  phext is 242,884,645 bytes, over GitHub's 100 MB file limit, so
  the seal ships and the plain form is generated on demand:
  `xz -dk phst.phext.xz`. Sizes and hashes: RECEIPTS.md.
- `tools/` — the import/export machinery, adapted from phcc's
  importer lineage:
  - `phext_io.py` — byte-exact phext walk/emitter + canonical
    binary-scroll codec
  - `phst_inventory.py` — measured upstream inventory
  - `phst_import.py` — importer v1: full tree at file grain
  - `phst_members.py` — importer v2: member grain for a named
    subset (tree-sitter-rust; spans tile the file bytes)
  - `phst_export.py` — unpack + hash verification, and member
    reassembly proof
  - `test_phst_io.py` — parser parity + codec round-trip checks
- `docs/DESIGN.md` — the inventory, the carry strategy it implies,
  the bootstrap story, and how phcc's receipt/gate discipline
  ports to a Rust tree.
- `PATCHES.md` — the fork delta vs upstream. Currently: the pin,
  and no patches.
- `RECEIPTS.md` — what was measured, with the numbers.

## Verify it yourself

```sh
xz -dk phst.phext.xz                      # -> phst.phext
python3 tools/phst_export.py unpack     --phext phst.phext --out unpacked
python3 tools/phst_export.py reassemble --phext phst.phext
cd unpacked && cargo check -p rustc_lexer --locked
```

Unpack writes all 64,301 files and checks every SHA-256 against
the manifest carried inside the phext. Reassemble rebuilds the
member-grain subset (compiler/rustc_lexer, 49 members) from its
segment scrolls alone and checks those hashes too.

## Platform ladder

**Linux (active) → Windows (desired) → WASM (after Windows).**
v0 is built and verified on Linux (aletheia-core, x86_64) only.
Windows and WASM are named rungs, not claims.

## Lineage

phst is the third carrier in the family: phcc (TinyCC → C in a
phext, publication gate green across 11 projects), phcpp (C++23
front end lowering to phcc scrolls), phst (Rust). The shared
discipline — coordinates found from the tree's own structure,
manifests with hashes, receipts over claims — is the point.
