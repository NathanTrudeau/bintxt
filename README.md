# bintxt

A zero-argument binary ↔ text truth pipeline. Drop two files into any repo root and version-control your binary configs.

`.txt` files are the source of truth — human-readable, diffable, version-controlled.
`.bin` files are inputs or generated artifacts — gitignored by default.

---

## Quick Start

```bash
# 1. Copy bintxt.sh and bintxt_cfg.yaml into your repo root
# 2. Edit bintxt_cfg.yaml to describe your binary format(s)
# 3. Drop .txt or .bin files into configs/
# 4. Run:
./bintxt.sh
```

That's it. No arguments. The script scans `configs/`, packs all `.txt`, unpacks all `.bin`, verifies everything, and writes a timestamped report to `logs/`.

---

## What it does

**Pack** — converts `configs/foo.txt` → `build/run_<ts>/packed/foo.bin`
If no `foo.bin` exists yet, the packed output is also written to `configs/`.

**Unpack** — converts `configs/foo.bin` → `build/run_<ts>/unpacked/foo.txt`
Labels defined in YAML are injected as `@label` markers.

**Verify** — three independent checks per file:
- `verify_pack` — packed binary matches source `.txt`
- `verify_unpack` — unpacked `.txt` matches source `.bin`
- `verify_source_pair` — `configs/foo.txt` and `configs/foo.bin` are in sync

All three run automatically. Any mismatch is reported at word-level with addresses.

---

## .txt Format

```
# comment
@label LABEL_NAME
XXXXXXXX: WW WW WW WW WW WW
XXXXXXXX: WW WW WW WW WW WW
```

| Element | Format | Example (32-bit addr, 8-bit word) |
|---------|--------|----------------------------------|
| Address | `address_bits / 4` hex chars | `00000010` |
| Word    | `word_bits / 4` hex chars    | `af` |
| Words per line | 1–6 (last line may have fewer) | `af b2 c0 11 04 fe` |

`@label` lines are injected by the script during unpack. Do not hand-edit them — define labels in `bintxt_cfg.yaml` instead.

---

## Configuration (`bintxt_cfg.yaml`)

| Field | Default | Description |
|-------|---------|-------------|
| `paths.config_dir` | `configs` | Where `.txt` and `.bin` files live |
| `paths.build_dir` | `build` | Packed/unpacked output per run |
| `paths.log_dir` | `logs` | Run logs |
| `defaults.address_bits` | `32` | `32` (8 hex digits) or `64` (16 hex digits) |
| `defaults.word_bits` | `8` | `8`, `16`, `32`, or `64` |
| `defaults.words_per_line` | `6` | 1–6 |
| `defaults.endianness` | `little` | `little` or `big` |
| `defaults.checksum_algorithm` | `crc32` | `crc32`, `md5`, or `sha256` |
| `output.keep_runs` | `10` | How many `build/run_*` dirs to keep locally |
| `output.track_checksum` | `false` | `true` = commit `.bin.crc32` sidecars to git |
| `validation.*` | `true` | Set to `false` to downgrade any rule to a warning |

Per-binary overrides go under `binaries:` — see `bintxt_cfg.yaml` for the full schema.

---

## Output structure

```
repo/
  bintxt.sh
  bintxt_cfg.yaml
  configs/
    *.txt          ← version controlled
    *.bin          ← gitignored (generated/input)
  build/
    latest/
      packed/      ← most recent pack outputs
      unpacked/    ← most recent unpack outputs
    run_20260408_013045/
      packed/
      unpacked/
  logs/
    latest.log
    2026-04-08_01PM_30_bintxtLog.txt
```

---

## Requirements

| Requirement | Notes |
|-------------|-------|
| `bash` 4.0+ | macOS/Linux native; Windows requires Git Bash or WSL |
| `python3` 3.8+ | All binary logic, YAML parsing, checksums |
| `PyYAML` | Optional — used if available, falls back to minimal stdlib parser |
