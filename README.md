# bintxt

**Version-control your binary config files as readable text.**

Drop `bintxt.sh` and `bintxt_cfg.yaml` into any repo. Run it before every commit: packs `.txt` → `.bin`, verifies everything is in sync, and tracks what changed since your last run.

> For interactive binary exploration and hand-editing, see [bintxt_tool](https://github.com/NathanTrudeau/bintxt_tool).

---

## Requirements

| | |
|---|---|
| `bash` 4.0+ | macOS/Linux native; Windows requires Git Bash |
| `python3` 3.8+ | All binary logic and YAML parsing |
| `PyYAML` | Optional — falls back to stdlib parser |

---

## Quick Start

**1. Drop files into your repo root**

```
your_project/
  ├── bintxt.sh
  ├── bintxt_cfg.yaml
  └── hw_configs/
        ├── boot_cfg.bin
        └── gpio_map.bin
```

Set `config_dir` in `bintxt_cfg.yaml` to match your folder name.

---

**2. First run — discovery**

```bash
./bintxt.sh
```

No YAML entries yet, so bintxt unpacks every `.bin` to `.txt` using defaults and generates `bintxt_cfg.example.yaml` — one skeleton entry per binary, with fields that fell back to global defaults flagged `# UPDATE DEFAULT`.

---

**3. Configure**

Copy entries from `bintxt_cfg.example.yaml` into `bintxt_cfg.yaml`. Set correct format fields, add labels if needed:

```yaml
binaries:
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
```

---

**4. Re-run — full pipeline**

```bash
./bintxt.sh
```

bintxt detects the format change, reformats every `.txt` to match the new settings (no binary needed — pure `.txt` reformat), then runs pack + verify. All green = sources and outputs are in sync.

From here: edit hex content or labels in `.txt`, re-run, get updated `.bin` outputs. That's the loop.

---

## Configuration

| Field | Default | |
|---|---|---|
| `paths.config_dir` | `configs` | Folder for `.txt` and `.bin` files |
| `paths.build_dir` | `build` | Per-run outputs |
| `paths.log_dir` | `logs` | Run logs |
| `defaults.address_bits` | `32` | `32` or `64` |
| `defaults.word_bits` | `8` | `8`, `16`, `32`, or `64` |
| `defaults.words_per_line` | `6` | 1–6 words per line |
| `defaults.endianness` | `little` | `little` or `big` |
| `defaults.checksum_algorithm` | `crc32` | `crc32`, `md5`, or `sha256` |
| `output.keep_runs` | `10` | Run dirs to retain in `build/` |
| `output.track_checksum` | `false` | Commit `.bin.crc32` sidecars to git |
| `output.generate_yaml_example` | `true` | Write `bintxt_cfg.example.yaml` each run |
| `validation.*` | `true` | Set to `false` to downgrade any rule to a warning |

---

## Output Structure

```
build/
  latest/
    packed/               ← most recent .bin outputs, always current
  2026-04-11_09-49-07AM_000/
    packed/               ← .bin outputs for this run
    <base>.bin            ← input .bins moved out of configs/ (if any)
    rollback/             ← .txt snapshots before reformat (if YAML changed)
logs/
  latest.log
  2026-04-11_09AM_49_bintxtLog.txt
```

`.txt` files live in `configs/` only — they are the source of truth and are never duplicated into `build/`. `rollback/` appears only when a reformat runs.

---

## What it does

**Pack** — `configs/foo.txt` → `build/<run>/packed/foo.bin` + `build/latest/packed/foo.bin`

**Unpack** — `configs/foo.bin` → `configs/foo.txt` (in place). Labels injected from YAML. Binary moved to `build/<run>/`.

**Verify** — three independent checks per file:
- `verify_pack` — packed binary matches source `.txt`
- `verify_unpack` — unpacked `.txt` matches source `.bin`
- `verify_source_pair` — `configs/foo.txt` and `configs/foo.bin` are in sync

**YAML change detection** — format or label changes trigger automatic `.txt` reformat using old settings (from `.bintxt_state`) to extract raw bytes, then re-serializes under new settings with new labels. Old `.txt` backed up to `rollback/` first.

**Source tracking** — `.txt` files are hashed after each run. Next run reports `source: modified` if you've changed any hex content.

`.bintxt_state` is local-only (gitignored). Fresh clone = no state = no warnings, just pack and go.

---

## .txt Format

```
# comment
@label SECTION_NAME
XXXXXXXX: WW WW WW WW
```

| Element | Format |
|---|---|
| Comment | `# ...` |
| Label | `@label NAME` — injected by bintxt during unpack, skipped during pack |
| Address | hex, `address_bits ÷ 4` chars wide |
| Word | hex, `word_bits ÷ 4` chars wide |

Label addresses must align to line boundaries: `address % (word_bytes × words_per_line) == 0`

---

## Full Example

### `bintxt_cfg.yaml`

```yaml
version: 1

paths:
  config_dir: configs
  build_dir:  build
  log_dir:    logs

defaults:
  address_bits:       32
  word_bits:          8
  words_per_line:     6
  endianness:         little
  checksum_algorithm: crc32

output:
  keep_runs:             10
  track_checksum:        false
  generate_yaml_example: true

binaries:

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
      - address: 0x00000008
        label: ADC_CAL
```

### `configs/boot_cfg.txt`

```
@label BOOT_IDENTITY
00000000: deadbeef 00010003 00000007 00000004
@label MEMORY_MAP
00000010: 00001388 08000000 20000000 00008000
@label SECURITY_AND_CANARY
00000020: 00000001 ffffffff ffffffff 5a5a5a5a
```
