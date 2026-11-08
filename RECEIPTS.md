# RECEIPTS.md — phst v0, measured 2026-11-07 on aletheia-core

Environment: aletheia-core (x86_64, Linux), rustc/cargo 1.94.0,
python3 stdlib importers; member parser tree-sitter 0.26.0 /
tree-sitter-rust 0.24.2 (venv). Node Tctl 33.6 °C during the work —
no thermal holds.

## Upstream

- Fresh clone (shallow, submodules uninitialized) of
  rust-lang/rust @ **29f282561639932ad8c56c11ef6313ffbc9bdb05**.
- Inventory (tools/phst_inventory.py): **64,301 files** placed
  (+13 gitlinks registered, content not imported), **230,266,834
  bytes**, 6,395,265 lines, of which 4,105,594 lines in 39,589
  .rs files. compiler/ 2,989 files; library/ 2,343; src/ 13,635;
  tests/ 45,272; root+other 62. 5 symlinks, 61 empty files.

## Import (importer v1, file grain)

- 64,301 scrolls placed: **64,228 raw + 73 binary**
  (`phext-binary:1:base64`), 0 placement failures, 0 exclusions
  beyond the 13 registered gitlinks.
- phst-v1.phext: 242,793,685 bytes, SHA-256
  `eef8b014e34d245d1b674373a13a0a5fe796534332293fdbded71b2e1a5e5c73`.
- Every scroll verified byte-identical after a walk of the
  written file, inside the importer run itself.

## Member grain (importer v2, subset compiler/rustc_lexer)

- Base re-emission check: implode(walk(v1 phext)) == v1 phext,
  byte-identical (64,813 scrolls walked).
- Subset: 3 files — src/lib.rs and src/tests.rs structured,
  Cargo.toml file-level by design (not Rust source; degradation
  register says so).
- **49 members**: 28 function, 9 type, 9 object, 2 impl, 1 mod;
  99 segments total (50 gap), **0 parse-error bytes**, 104 scrolls
  added; every inherited scroll byte-identical in the result.
- Final phst.phext: **242,884,645 bytes**, SHA-256
  `87d98c51f1e312d71758063a4f6086fa461269e09f89c30e18688a6d4b3e57db`.

## Round-trip proofs (from the final phext)

- **Unpack: 64,301 files written, 64,301 SHA-256 verified,
  0 failures** (tools/phst_export.py unpack), modes and the 5
  symlinks restored.
- **Reassembly: 2/2 segmented files byte-identical** rebuilt from
  segment payloads alone (the Vol 2 file scroll never consulted);
  every segment payload hash checked against its file index.
- **Independent check:** `diff -r --no-dereference` of the
  unpacked tree against the fresh upstream clone: **0 content
  differences**. Only deltas: the 13 empty submodule directories
  (upstream side, registered gitlinks) and `target/` (unpacked
  side — created by the build smoke below, after unpack).
- phext_io parity: fast walk == lineage per-byte walk on
  synthetic delimiter-heavy data and on a 4 MiB prefix of the
  real phst.phext (tools/test_phst_io.py).

## Build smoke (from the unpacked tree)

- `cargo check -p rustc_lexer --locked` — **pass** (memchr,
  unicode-ident, unicode-properties, rustc_lexer; 3.86 s).
- `cargo test -p rustc_lexer --locked` — **pass: 17 passed,
  0 failed**.
- No full rustc bootstrap was attempted; DESIGN.md §3 states why
  and what it would take.

## Seal

- `xz -6` (libphext seal preset): **phst.phext.xz = 31,156,684
  bytes**, SHA-256
  `be94216d0c097dc5f18d9d73feca345c974d009fe63dd6cc685c6162286153a3`.
- Verified: `xz -t` clean; decompressed SHA-256 ==
  87d98c51… (the plain phext above).
- The plain phext (242,884,645 B) exceeds GitHub's 100 MB file
  limit, so the repo ships the seal; the plain form is generated
  on demand and checkable against the hash on this page.
