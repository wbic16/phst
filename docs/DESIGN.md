# phst — design

phst is the phext fork of Rust: rust-lang/rust carried in a phext
as its source form, the way phcc carries TinyCC. This document
records the measured inventory the carry strategy rests on, the
strategy itself, the bootstrap story, and how the receipt/gate
discipline ports from phcc. Everything quantitative here was
measured on aletheia-core on 2026-11-07; the raw numbers live in
RECEIPTS.md.

## 1. Upstream inventory (measured)

Upstream: `rust-lang/rust @ 29f282561639932ad8c56c11ef6313ffbc9bdb05`
(2026-11-07, shallow clone, submodules uninitialized).

| scope | files | content | lines | .rs lines |
|---|---|---|---|---|
| **whole tree** | **64,301** | **219.6 MiB** | **6,395,265** | **4,105,594** (39,589 files) |
| compiler/ | 2,989 | 34.3 MiB | 926,141 | 891,377 |
| library/ | 2,343 | 53.8 MiB | 1,668,182 | 1,093,920 |
| src/ | 13,635 | 74.3 MiB | 2,144,387 | 1,280,790 |
| tests/ | 45,272 | 55.7 MiB | 1,623,501 | 839,507 |
| root + other | 62 | 1.4 MiB | 32,754 | 0 |

Plus 13 gitlinks (submodule pins — src/llvm-project, src/gcc,
src/tools/cargo, src/tools/enzyme, src/tools/rustc-perf,
src/tpde, library/backtrace, and six doc books) and 5 symlinks.
70% of the files are tests. For scale: TinyCC, phcc's whole
upstream, is 558 files / ~135K LOC. This tree is ~115× the files
and ~47× the lines.

## 2. The carry decision the numbers imply

**Full tree at file grain; member grain for one named subset.**

- File grain scales by construction: placement is a deterministic
  function of the path list (Book = top-level area, Chapter =
  second-level component, Section = file, path-sorted), the
  manifest carries path/coordinate/SHA-256/size/mode/encoding for
  every file, and unpack is a hash-checked projection back to a
  tree. 64,301 files is a bigger manifest (~13 MB of scroll), not a
  different problem. Nothing in the format or the tooling needs the
  tree to be small.
- Member grain everywhere on day one would be the opposite
  decision: ~4.1M lines of Rust segmented before the segmentation
  machinery has proven itself on this grammar, producing a Volume 3
  nobody has verified the tiling of at scale. phcc earned member
  grain in slices (importer v3 after two file-grain slices); phst
  follows the same order.
- **Starting subset: `compiler/rustc_lexer`** — 3 files, 1,666 .rs
  lines (src/lib.rs 1,295 + src/tests.rs 371; Cargo.toml rides
  file-level). The numbers argue for it: it is the smallest
  compiler crate that is a real compiler component; its manifest
  is fully standalone (no workspace inheritance); its only
  dependencies are three crates.io packages; upstream designs it
  for reuse outside rustc. Segmentation extracted 49 members
  (28 function, 9 type, 9 object, 2 impl, 1 mod) with zero
  parse-error bytes — small enough that every member can be
  eyeballed, real enough to prove tiling, reassembly, and the
  build smoke end to end.
- Named next steps, also measured: `compiler/rustc_parse`
  (27 files, 33,060 .rs lines — member grain once the lexer pass
  is trusted; its build smoke needs the compiler-crate graph),
  then `library/core` (325 files, 178,181 .rs lines — the first
  subset where member grain pays for navigation, not proof).

Layout (importer v1/v2 docstrings are the normative text):
Collection 1 (Meta) Vol 1 = identity + pin; Vol 2 Book 10 =
placement manifest, layout notes, exclusions register; Collection 4
(Source) Vol 2 = file grain; Vol 3 = member grain mirroring Vol 2
addresses for the subset (Scroll 1 index, Scrolls 2+ segments with
`#phst-member` headers, bytes tiling exactly); Collection 10 Vol 99
= a one-scroll endmark so the last placed scroll is never the
phext's trailing byte.

Files whose bytes are not valid UTF-8, contain a phext delimiter
byte, or begin with the binary header line are placed as canonical
binary scrolls (`phext-binary:1:base64` + base64). At this pin
that is 73 of 64,301 files; the other 64,228 sit verbatim.

## 3. Bootstrap story (honest)

The phext is the **source form**. Building is ordinary Rust
building, done by a stage0 rustc that does not come from the
phext:

1. `xz -d` the seal → `phst.phext`; unpack (hash-verified) → tree.
2. The tree is byte-identical to upstream at the pin (RECEIPTS.md
   shows this three ways: manifest hashes, segment reassembly, and
   an independent `diff -r` against a fresh clone).
3. stage0 = the system rustc (1.94.0 on aletheia-core at v0 time)
   builds from that tree. v0's smoke: `cargo check` and
   `cargo test` of the member-grain subset, both green.

What v0 does **not** do: a full rustc bootstrap (`./x build`).
Two honest blockers, both recorded rather than elided: a real
bootstrap wants the submodule content (LLVM above all), which phst
registers as pins but does not carry; and upstream's bootstrap
expects its own pinned stage0 snapshot and a long build — a
programme of work, not a smoke. When that work happens it will be
its own task with its own receipts. Until then: **phst v0 is a
carried source tree with proofs, not a self-hosting compiler.**

## 4. How the phcc discipline ports

phcc's programme ran on: PATCHES.md as the complete fork delta,
every change gated by receipts re-issued on the changed content,
and a strict rule that a claim without a clean-tree receipt is not
a claim (the F23 lesson). phst adopts the same discipline, with
the Rust-shaped gate:

- Any fork change lands as a PATCHES.md entry (P-rows) naming the
  scrolls/files it touches and its verification.
- After any change to carried content: the phext is rebuilt (or
  the scroll edited with manifests regenerated), the unpack
  round-trip proof re-runs (64,301/64,301 hashes), the member
  reassembly proof re-runs for every segmented file, and the
  affected crates are rebuilt from the **unpacked** tree
  (`cargo check`/`cargo test -p <crate>`) — never from a
  hand-patched side tree.
- Upstream tracking is per-pin: a new pin is a re-import, and the
  manifest diff between pins is the review surface. PATCHES rows
  must re-apply or be retired at each pin move, in the open.
- Conformance, when it comes, will be differential against
  upstream rustc behaviour on the same inputs (the phcc oracle
  pattern), not assertion.

## 5. Platform ladder

**Linux (active) → Windows (desired) → WASM (after Windows)** —
Will's ordering, 2026-11-07. v0 builds and verifies on Linux
x86_64 only. The carry itself is platform-blind (the phext and the
tools are bytes and Python), but no Windows or WASM receipt exists
yet, so neither is claimed.

## 6. What ships where (measured)

- Plain phext: 242,884,645 bytes — over GitHub's 100 MB per-file
  hard limit. **Does not ship.**
- Seal (`xz -6`, the libphext seal preset): 31,156,684 bytes,
  SHA-256 `be94216d…`. **Ships** as `phst.phext.xz`; the plain
  form is generated on demand (`xz -dk phst.phext.xz`) and its
  SHA-256 is in RECEIPTS.md so the generated form is checkable.
- Tools, docs, manifests' human-readable summaries: in the repo.
  The full placement manifest lives inside the phext (Meta Vol 2)
  where it belongs — it is 64,301 rows about the phext's own
  scrolls.
