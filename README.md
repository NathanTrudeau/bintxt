# bintxt

**Binary configs belong in version control. bintxt makes that practical.**

bintxt is a zero-argument build/verify pipeline you drop into any repo alongside your config files. Run it before every commit: it packs your `.txt` sources to binary, unpacks any `.bin` inputs to readable text, and runs three independent verification checks on every file — all in one pass. If something is out of sync, it tells you exactly where and why.

It's not an explorer or an editor. It's a pipeline. It runs the same way every time, produces a timestamped log, manages your `.gitignore`, and keeps your `.txt` sources as the unambiguous source of truth.

> If you need to **interactively explore or hand-edit** a binary file, see [bintxt_tool](https://github.com/NathanTrudeau/bintxt_tool).

---

## Requirements

| Requirement | Notes |
|-------------|-------|
| `bash` 4.0+ | macOS/Linux native; Windows requires Git Bash or WSL |
| `python3` 3.8+ | All binary logic, YAML parsing, checksums |
| `PyYAML` | Optional — used if available, falls back to minimal stdlib parser |

---

## Quick Start

### Step 1 — Create the folder structure

Drop `bintxt.sh` and `bintxt_cfg.yaml` into your repo root. Create a folder for your binary files — name it whatever fits your project. Put your `.bin` files in there.

```
your_project/
  ├── bintxt.sh
  ├── bintxt_cfg.yaml
  └── hw_configs/          ← name this whatever you want
        ├── boot_cfg.bin
        ├── gpio_map.bin
        └── nvmem.bin
```

---

### Step 2 — Set your folder name in the YAML

Open `bintxt_cfg.yaml` and update `config_dir` to match your folder. Leave format defaults as-is for now — bintxt will scan your binaries and generate a filled skeleton in the next step.

```yaml
version: 1

paths:
  config_dir: hw_configs   # ← your folder name here
  build_dir:  build
  log_dir:    logs

defaults:
  address_bits:       32
  word_bits:          8
  words_per_line:     6
  endianness:         little
  checksum_algorithm: crc32

output:
  generate_yaml_example: true   # keep this on for now
```

---

### Step 3 — Run bintxt (first scan)

```bash
./bintxt.sh
```

bintxt doesn't know your binary formats yet, so this first run:

- **Unpacks every `.bin` with defaults** → writes a `.txt` hex dump into your configs folder so you can inspect the raw content immediately
- **Generates `bintxt_cfg.example.yaml`** next to the script — one skeleton entry per binary, with every format field that's using a default flagged as `# UPDATE DEFAULT`
- **Exits with errors** — expected, no YAML entries exist yet

---

### Step 4 — Fill out your binary configs

Open `bintxt_cfg.example.yaml`. For each binary, verify or update the fields marked `# UPDATE DEFAULT` to match the actual format of that file, then add any labels you want injected during unpack:

```yaml
binaries:

  - file: boot_cfg.bin
    label: true                   # set true to inject @label markers on unpack
    format:
      address_bits:   32
      word_bits:      32          # UPDATE DEFAULT ← change to match your binary
      words_per_line: 4           # UPDATE DEFAULT ← change to match your binary
      endianness:     little
    checksum:
      algorithm: crc32
    labels:
      - address: 0x00000000
        label: BOOT_IDENTITY
      - address: 0x00000010
        label: MEMORY_MAP
```

Copy the completed `binaries:` section into your real `bintxt_cfg.yaml`.

---

### Step 5 — Re-run for the full pipeline

```bash
./bintxt.sh
```

With YAML entries in place, bintxt runs the complete pipeline on every file — pack, unpack, and three-way verification. All green means your `.txt` sources and `.bin` files are in sync.

Your final repo structure — `.gitignore` managed automatically:

```
your_project/
  ├── bintxt.sh
  ├── bintxt_cfg.yaml
  ├── bintxt_cfg.example.yaml    ← regenerated each run, safe to ignore/delete
  └── hw_configs/
        ├── boot_cfg.txt         ✓ commit — source of truth
        ├── gpio_map.txt         ✓ commit
        ├── nvmem.txt            ✓ commit
        ├── boot_cfg.bin         ✗ gitignored
        ├── gpio_map.bin         ✗ gitignored
        └── nvmem.bin            ✗ gitignored
```

`.gitignore` is managed automatically by bintxt on every run — no manual setup needed.

---

## Configuration

Edit `bintxt_cfg.yaml` to match your binary format(s). All fields have sensible defaults.

| Field | Default | Description |
|-------|---------|-------------|
| `paths.config_dir` | `configs` | Folder containing `.txt` and `.bin` files |
| `paths.build_dir` | `build` | Per-run packed/unpacked output |
| `paths.log_dir` | `logs` | Run logs |
| `defaults.address_bits` | `32` | `32` (8 hex digits) or `64` (16 hex digits) |
| `defaults.word_bits` | `8` | `8`, `16`, `32`, or `64` |
| `defaults.words_per_line` | `6` | 1–6 words per `.txt` data line |
| `defaults.endianness` | `little` | `little` or `big` |
| `defaults.checksum_algorithm` | `crc32` | `crc32`, `md5`, or `sha256` |
| `output.keep_runs` | `10` | How many `build/run_*` dirs to retain locally |
| `output.track_checksum` | `false` | `true` = commit `.bin.crc32` sidecars to git |
| `output.generate_yaml_example` | `true` | Write `bintxt_cfg.example.yaml` after each run — one skeleton entry per discovered binary, format fields filled in. Fields that fell back to global defaults are marked `# UPDATE DEFAULT` so you know what to verify before copying into your actual config. Set to `false` to suppress. |
| `validation.*` | `true` | Set to `false` to downgrade any rule to a warning |

Per-binary format overrides and label definitions go under `binaries:` — see the full example at the bottom.

---

## Output Structure

```
your_project/
  build/
    latest/
      packed/         ← most recent pack outputs (.bin) — always current
    run_20260408_013045/
      packed/         ← .bin outputs for this run
      <base>.bin      ← .bin files moved out of configs/ this run (if any were present)
      rollback/       ← .txt snapshots before any reformatting (created only if YAML changed)
  logs/
    latest.log
    2026-04-08_01PM_30_bintxtLog.txt
```

`.txt` files are written directly to `configs/` — they are the source of truth and are not copied into `build/`. `rollback/` is created lazily and only appears when bintxt reformats a `.txt` due to a YAML settings change.

Old `build/run_*` directories are pruned automatically based on `output.keep_runs`.

---

## What it does

**Pack** — converts `configs/foo.txt` → `build/run_<ts>/packed/foo.bin` and `build/latest/packed/foo.bin`

**Unpack** — converts `configs/foo.bin` → `configs/foo.txt` (source of truth, written in place)
Labels defined in `bintxt_cfg.yaml` are injected as `@label` markers automatically.
The original `.bin` is moved to `build/run_<ts>/` — bins don't belong in configs.

**YAML change detection** — if you update format settings or labels in `bintxt_cfg.yaml`, bintxt detects the change on the next run and automatically reformats the `.txt` to match the new settings — no binary needed. It reads the existing `.txt` using the old settings (tracked in `.bintxt_state`), extracts the raw bytes, and re-serializes them under the new format with new labels injected. The old `.txt` is backed up to `build/run_<ts>/rollback/` before overwriting.

**Verify** — three independent checks per file:
- `verify_pack` — packed binary matches source `.txt`
- `verify_unpack` — unpacked `.txt` matches source `.bin`
- `verify_source_pair` — `configs/foo.txt` and `configs/foo.bin` are in sync

Any mismatch is reported at word-level with addresses. All three run on every invocation.

---

---

## .txt Format

Each `.txt` file represents one binary. Lines are either comments, label markers, or data.

```
# This is a comment — ignored by bintxt
@label SECTION_NAME
XXXXXXXX: WW WW WW WW WW WW
XXXXXXXX: WW WW WW WW WW WW
```

| Element | Format | Example (32-bit addr, 8-bit word, 6 wpl) |
|---------|--------|------------------------------------------|
| Comment | `# ...` | `# boot config v1` |
| Label | `@label NAME` | `@label BOOT_FLAGS` |
| Address | `address_bits ÷ 4` hex chars | `00000010` |
| Word | `word_bits ÷ 4` hex chars | `af` |
| Words/line | 1–6 (last line may have fewer) | `af b2 c0 11 04 fe` |

### Labels

**Define labels in `bintxt_cfg.yaml`, not in `.txt` files.**

During unpack, bintxt injects `@label` markers automatically at the addresses you specify.
During pack, `@label` lines are silently skipped — the binary is built purely from hex data.

If a `@label` is found in a `.txt` that has no matching entry in your YAML, bintxt will warn you — which means it will be lost the next time you unpack.

Label addresses must align to a line boundary:
```
stride = (word_bits / 8) × words_per_line
address % stride == 0   ← required
```

---

## Full Example

### `bintxt_cfg.yaml`

```yaml
version: 1

paths:
  config_dir: configs
  build_dir:  build
  log_dir:    logs

validation:
  fail_on_duplicate_addresses:     true
  fail_on_non_monotonic_addresses: true
  fail_on_stride_mismatch:         true
  fail_on_invalid_hex:             true
  fail_on_invalid_word_count:      true
  fail_on_partial_word:            true
  fail_on_missing_label_address:   true
  checksum_required:               true

defaults:
  address_bits:       32
  word_bits:          8
  words_per_line:     6
  endianness:         little
  checksum_algorithm: crc32

output:
  keep_runs:      10
  track_checksum: false

binaries:

  # 32-bit LE, 4 words/line → stride = 16 bytes
  - file: boot_cfg.bin
    label: true
    format:
      address_bits:   32
      word_bits:      32
      words_per_line: 4
      endianness:     little
    checksum:
      algorithm: crc32
    labels:
      - address: 0x00000000
        label: BOOT_IDENTITY
      - address: 0x00000010
        label: MEMORY_MAP
      - address: 0x00000020
        label: SECURITY_AND_CANARY

  # 8-bit, 8 words/line → stride = 8 bytes (one GPIO port per line)
  - file: gpio_map.bin
    label: true
    format:
      address_bits:   32
      word_bits:      8
      words_per_line: 8
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

  # 8-bit big-endian, 2 words/line → stride = 2 bytes (one register pair per line)
  - file: nvmem.bin
    label: true
    format:
      address_bits:   32
      word_bits:      8
      words_per_line: 2
      endianness:     big
    checksum:
      algorithm: sha256
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

---

### `configs/boot_cfg.txt`
*32-bit LE · 4 words/line · stride = 16 bytes*

```
@label BOOT_IDENTITY
00000000: deadbeef 00010003 00000007 00000004
@label MEMORY_MAP
00000010: 00001388 08000000 20000000 00008000
@label SECURITY_AND_CANARY
00000020: 00000001 ffffffff ffffffff 5a5a5a5a
```

---

### `configs/gpio_map.txt`
*8-bit LE · 8 words/line · stride = 8 bytes · one GPIO port per line*

```
@label PORT_A
00000000: 01 01 05 01 00 00 02 02
@label PORT_B
00000008: 02 02 02 02 03 03 01 00
@label PORT_C
00000010: 11 11 00 00 01 01 01 01
@label PORT_D
00000018: 02 02 00 00 00 04 00 00
```

---

### `configs/nvmem.txt`
*8-bit BE · 2 words/line · stride = 2 bytes · one register pair per line*

```
@label DEVICE_MAGIC
00000000: be ef
00000002: ca fe
@label HW_REV_AND_PRODUCT_ID
00000004: 01 02
00000006: 00 07
@label ADC_CAL
00000008: 80 7f
0000000a: ff fe
@label TEMP_AND_OSC_TRIM
0000000c: 32 00
0000000e: 01 f4
@label SERIAL_NUMBER
00000010: de ad
00000012: be ef
00000014: 00 00
00000016: 00 2a
@label RESERVED_AND_CRC
00000018: ff ff
0000001a: ff ff
0000001c: ff ff
0000001e: ff ff
```
