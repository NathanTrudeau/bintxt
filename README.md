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
Labels defined in `bintxt_cfg.yaml` are injected as `@label` markers automatically.

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

### Labels

**Do not hand-write `@label` lines.** Define labels in `bintxt_cfg.yaml` and let bintxt manage them. During unpack, the script injects `@label` markers automatically at the addresses you specify. During pack, `@label` lines are silently ignored — the binary is built purely from the hex data lines.

This means you can freely unpack a `.bin`, edit the hex values in the resulting `.txt`, and re-pack — the labels will survive untouched.

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

Per-binary overrides and label definitions go under `binaries:` — see the full example below.

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

---

## Full `bintxt_cfg.yaml` Example

A complete, annotated config covering all options. This example describes a small SoC firmware image with three binary files, each using a different format.

```yaml
version: 1

# ── Directories ───────────────────────────────────────────────────────────────
# All paths relative to the directory containing bintxt.sh.
paths:
  config_dir: configs    # .txt sources and .bin inputs live here
  build_dir:  build      # packed/unpacked outputs per run
  log_dir:    logs       # timestamped run logs

# ── Validation rules ──────────────────────────────────────────────────────────
# Set any flag to false to downgrade it from an error to a warning.
# Errors skip the affected file; warnings are logged and execution continues.
validation:
  fail_on_duplicate_addresses:     true   # same address appears twice in a .txt
  fail_on_non_monotonic_addresses: true   # addresses not strictly increasing
  fail_on_stride_mismatch:         true   # gap between addresses != stride
  fail_on_invalid_hex:             true   # bad hex in address or word columns
  fail_on_invalid_word_count:      true   # more words than words_per_line
  fail_on_partial_word:            true   # file size not aligned to word width
  fail_on_missing_label_address:   true   # label address doesn't land on a line boundary
  checksum_required:               true   # compute and write checksum sidecar on pack

# ── Format defaults ───────────────────────────────────────────────────────────
# Applied to any binary not listed under binaries:.
# Any field can be overridden per file in the binaries: section.
defaults:
  address_bits:       32       # 32 or 64
  word_bits:          8        # 8, 16, 32, or 64
  words_per_line:     6        # 1–6 words per .txt data line
  endianness:         little   # little or big
  checksum_algorithm: crc32    # crc32, md5, or sha256

# ── Output behavior ───────────────────────────────────────────────────────────
output:
  keep_runs:      10      # how many build/run_* directories to retain locally
  track_checksum: false   # false = gitignore .bin.crc32 sidecars (default)
                          # true  = commit sidecars alongside .txt files

# ── Binary definitions ────────────────────────────────────────────────────────
# List every binary you want format overrides or label injection for.
# Unlisted files are processed using the defaults above with no label injection.
#
# Label rules:
#   - Define labels here, not in .txt files
#   - label: true enables @label injection during unpack
#   - Each label address must align to a line boundary (address % stride == 0)
#   - stride = (word_bits / 8) * words_per_line
#
binaries:

  # boot_cfg.bin — 32-bit little-endian, 4 words per line
  # Boot ROM register block: magic, version, memory map, security config
  - file: boot_cfg.bin
    label: true
    format:
      address_bits:   32
      word_bits:      32
      words_per_line: 4      # stride = 16 bytes per .txt line
      endianness:     little
    checksum:
      algorithm: crc32
    labels:
      - address: 0x00000000
        label: BOOT_IDENTITY       # magic word, version, boot flags, clock divider
      - address: 0x00000010
        label: MEMORY_MAP          # watchdog timeout, boot vector, SRAM base, SRAM size
      - address: 0x00000020
        label: SECURITY_AND_CANARY # secure boot enable, reserved, reserved, CRC canary

  # gpio_map.bin — 8-bit, 8 words per line, little-endian
  # One byte per GPIO pin: bits[1:0]=mode, bit2=pullup, bit3=pulldown, bit4=open-drain
  - file: gpio_map.bin
    label: true
    format:
      address_bits:   32
      word_bits:      8
      words_per_line: 8      # stride = 8 bytes per .txt line (one port per line)
      endianness:     little
    checksum:
      algorithm: crc32
    labels:
      - address: 0x00000000
        label: PORT_A
      - address: 0x00000008
        label: PORT_B
      - address: 0x00000010
        label: PORT_C
      - address: 0x00000018
        label: PORT_D

  # nvmem.bin — 8-bit big-endian, 2 words per line
  # Factory NV memory: device identity, calibration constants, serial number
  - file: nvmem.bin
    label: true
    format:
      address_bits:   32
      word_bits:      8
      words_per_line: 2      # stride = 2 bytes per .txt line (one register pair per line)
      endianness:     big    # big-endian: most significant byte first
    checksum:
      algorithm: sha256      # stronger checksum for factory-calibration data
    labels:
      - address: 0x00000000
        label: DEVICE_MAGIC
      - address: 0x00000004
        label: HW_REV_AND_PRODUCT_ID
      - address: 0x00000008
        label: ADC_CAL
      - address: 0x0000000c
        label: TEMP_AND_OSC_TRIM
      - address: 0x00000010
        label: SERIAL_NUMBER
      - address: 0x00000018
        label: RESERVED_AND_CRC
```
