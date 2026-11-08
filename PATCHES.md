# PATCHES.md — the phst fork delta

phst is a fork of rust-lang/rust carried in a phext. This file is
the complete record of how the carried tree differs from upstream:
every fork change is a row here, with its reason and its
verification, from day one. No row, no change — a difference
between the carried tree and the pin that is not recorded here is
a defect, not a detail.

## Upstream pin

| field | value |
|---|---|
| repo | https://github.com/rust-lang/rust |
| commit | `29f282561639932ad8c56c11ef6313ffbc9bdb05` |
| commit date | 2026-11-07 |
| carried as | phst.phext (sealed: phst.phext.xz), importer v1 + v2 |
| submodule pins | 13 gitlinks registered in the phext's exclusions register (Meta Vol 2, Book 10, Ch 1, Sec 3); content not carried |

## Patch table

| ID | Files / scrolls | Delta | What & why | Verification |
|---|---|---|---|---|
| — | — | — | *no patches yet: at the v0 pin the carried tree is byte-identical to upstream (RECEIPTS.md)* | unpack 64,301/64,301 SHA-256 verified; `diff -r` vs fresh clone: 0 content differences |

## Rules (inherited from phcc's fork discipline)

- Rows are numbered P1, P2, … in landing order and never reused.
- A row names its verification; a change whose verification has
  not been re-run on the changed phext is not landed.
- Moving the upstream pin is recorded here as a row of its own:
  old pin, new pin, and which P-rows re-applied, changed, or
  retired in the move.
- The phext is rebuilt (or its manifests regenerated) in the same
  change as any content edit, so this file and the artifact never
  describe different trees.
