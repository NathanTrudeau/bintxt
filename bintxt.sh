#!/usr/bin/env bash
# =============================================================================
# bintxt.sh — Binary ↔ Text truth pipeline
#
# Drop into any repo root alongside bintxt_cfg.yaml. Run with no arguments.
#
# .txt files are the source of truth (version controlled)
# .bin files are inputs or generated artifacts (gitignored by default)
#
# https://github.com/NathanTrudeau/bintxt
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_FILE="$SCRIPT_DIR/bintxt_cfg.yaml"

# ── Pre-flight ────────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required but not found."
    echo "       Install Python 3.8+ and ensure it is in your PATH."
    read -rsp $'\nPress any key to exit...' -n 1; echo ""
    exit 1
fi

if [[ ! -f "$CFG_FILE" ]]; then
    echo "ERROR: bintxt_cfg.yaml not found."
    echo "       Expected: $CFG_FILE"
    echo "       Copy the template bintxt_cfg.yaml next to bintxt.sh."
    read -rsp $'\nPress any key to exit...' -n 1; echo ""
    exit 1
fi

# ── Pipeline ──────────────────────────────────────────────────────────────────
python3 - "$SCRIPT_DIR" "$CFG_FILE" <<'PYEOF'
import os, sys, re, zlib, hashlib, shutil
from datetime import datetime
from pathlib import Path

# Windows cp1252 fix — force UTF-8 on stdout/stderr before any output
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass  # Python < 3.7 fallback (reconfigure not available)

SCRIPT_DIR = Path(sys.argv[1])
CFG_FILE   = Path(sys.argv[2])

# ── ANSI ──────────────────────────────────────────────────────────────────────
R   = '\033[0;31m'
G   = '\033[0;32m'
Y   = '\033[1;33m'
C   = '\033[0;36m'
B   = '\033[1m'
DIM = '\033[2m'
NC  = '\033[0m'

def red(s):    return f"{R}{s}{NC}"
def green(s):  return f"{G}{s}{NC}"
def yellow(s): return f"{Y}{s}{NC}"
def cyan(s):   return f"{C}{s}{NC}"
def bold(s):   return f"{B}{s}{NC}"
def dim(s):    return f"{DIM}{s}{NC}"

# ── YAML loader ───────────────────────────────────────────────────────────────
def load_yaml(text):
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        return _minimal_yaml(text)

def _minimal_yaml(text):
    """Minimal YAML parser — stdlib only. Handles the bintxt_cfg.yaml schema."""

    def cast(s):
        s = s.strip()
        for q in ('"', "'"):
            if len(s) >= 2 and s.startswith(q) and s.endswith(q):
                return s[1:-1]
        if not s or s == '~':
            return None
        if s.lower() in ('true', 'yes', 'on'):
            return True
        if s.lower() in ('false', 'no', 'off'):
            return False
        if re.match(r'^0x[0-9a-fA-F]+$', s, re.I):
            return int(s, 16)
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
        return s

    # Strip comments and blank lines, track indent
    lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue
        # Remove trailing inline comment (not inside quotes)
        line = re.sub(r'\s+#(?!["\']).*$', '', line.rstrip())
        if line.strip():
            lines.append(line)

    idx = [0]

    def cur_ind():
        if idx[0] >= len(lines):
            return -1
        return len(lines[idx[0]]) - len(lines[idx[0]].lstrip())

    def parse_node(min_ind):
        if idx[0] >= len(lines):
            return None
        ci = cur_ind()
        if ci < min_ind:
            return None
        line = lines[idx[0]].strip()

        # ── Sequence ──────────────────────────────────────────────────────────
        if line.startswith('- '):
            result = []
            while idx[0] < len(lines):
                if cur_ind() < min_ind:
                    break
                l = lines[idx[0]].strip()
                if not l.startswith('- '):
                    break
                list_ind = cur_ind()
                idx[0] += 1
                content = l[2:].strip()

                if not content:
                    # Block sequence item on next lines
                    result.append(parse_node(list_ind + 2))
                elif ':' in content and not content.startswith(("'", '"')):
                    # Mapping inside list
                    k, _, v = content.partition(':')
                    k = k.strip(); v = v.strip()
                    item = {}
                    if v:
                        item[k] = cast(v)
                    else:
                        # Value is a nested block
                        if idx[0] < len(lines) and cur_ind() > list_ind:
                            item[k] = parse_node(cur_ind())
                        else:
                            item[k] = None
                    # Remaining k:v entries at this mapping level
                    while idx[0] < len(lines):
                        ni = cur_ind()
                        if ni <= list_ind:
                            break
                        nl = lines[idx[0]].strip()
                        if nl.startswith('- '):
                            break
                        if ':' not in nl:
                            break
                        idx[0] += 1
                        mk, _, mv = nl.partition(':')
                        mk = mk.strip(); mv = mv.strip()
                        if mv:
                            item[mk] = cast(mv)
                        else:
                            if idx[0] < len(lines) and cur_ind() > ni:
                                item[mk] = parse_node(cur_ind())
                            else:
                                item[mk] = None
                    result.append(item)
                else:
                    result.append(cast(content))
            return result

        # ── Mapping ───────────────────────────────────────────────────────────
        if ':' in line and not line.startswith(("'", '"')):
            result = {}
            while idx[0] < len(lines):
                ni = cur_ind()
                if ni < min_ind:
                    break
                l = lines[idx[0]].strip()
                if l.startswith('- '):
                    break
                if ':' not in l:
                    break
                idx[0] += 1
                k, _, v = l.partition(':')
                k = k.strip(); v = v.strip()
                if v:
                    result[k] = cast(v)
                else:
                    if idx[0] < len(lines) and cur_ind() > ni:
                        result[k] = parse_node(cur_ind())
                    else:
                        result[k] = None
            return result

        # ── Scalar ────────────────────────────────────────────────────────────
        idx[0] += 1
        return cast(line)

    return parse_node(0) or {}

# ── Config validation ─────────────────────────────────────────────────────────
def validate_cfg(cfg):
    errors = []
    if not isinstance(cfg, dict):
        return ["YAML root must be a mapping"]
    if cfg.get('version') != 1:
        errors.append("'version' must be 1")
    paths = cfg.get('paths')
    if not isinstance(paths, dict):
        errors.append("'paths' section is required and must be a mapping")
    else:
        for k in ('config_dir', 'build_dir', 'log_dir'):
            if not paths.get(k):
                errors.append(f"paths.{k} is required")
    binaries = cfg.get('binaries')
    if binaries is not None:
        if not isinstance(binaries, list):
            errors.append("'binaries' must be a sequence")
        else:
            seen = set()
            for i, entry in enumerate(binaries):
                if not isinstance(entry, dict):
                    errors.append(f"binaries[{i}] must be a mapping")
                    continue
                fname = entry.get('file')
                if not fname:
                    errors.append(f"binaries[{i}] missing 'file'")
                elif fname in seen:
                    errors.append(f"Duplicate binary entry: '{fname}'")
                else:
                    seen.add(fname)
    return errors

# ── Config accessors ──────────────────────────────────────────────────────────
def get_defaults(cfg):
    d = cfg.get('defaults') or {}
    return {
        'address_bits':       int(d.get('address_bits', 32)),
        'word_bits':          int(d.get('word_bits', 8)),
        'words_per_line':     int(d.get('words_per_line', 6)),
        'endianness':         str(d.get('endianness', 'little')),
        'checksum_algorithm': str(d.get('checksum_algorithm', 'crc32')),
    }

def get_validation(cfg):
    v = cfg.get('validation') or {}
    keys = [
        'fail_on_duplicate_addresses', 'fail_on_non_monotonic_addresses',
        'fail_on_stride_mismatch', 'fail_on_invalid_hex',
        'fail_on_invalid_word_count', 'fail_on_partial_word',
        'fail_on_missing_label_address', 'checksum_required',
    ]
    return {k: bool(v.get(k, True)) for k in keys}

def get_output_cfg(cfg):
    o = cfg.get('output') or {}
    return {
        'keep_runs':      int(o.get('keep_runs', 10)),
        'track_checksum': bool(o.get('track_checksum', False)),
    }

def get_binary_cfg(cfg, filename, defaults):
    """Return merged config for filename. Returns None if no YAML entry."""
    for entry in (cfg.get('binaries') or []):
        if entry.get('file') == filename:
            fmt = entry.get('format') or {}
            chk = entry.get('checksum') or {}
            return {
                'file':               filename,
                'label':              bool(entry.get('label', False)),
                'address_bits':       int(fmt.get('address_bits', defaults['address_bits'])),
                'word_bits':          int(fmt.get('word_bits', defaults['word_bits'])),
                'words_per_line':     int(fmt.get('words_per_line', defaults['words_per_line'])),
                'endianness':         str(fmt.get('endianness', defaults['endianness'])),
                'checksum_algorithm': str(chk.get('algorithm', defaults['checksum_algorithm'])),
                'labels':             list(entry.get('labels') or []),
            }
    return None

def _default_bin_cfg(filename, defaults):
    return {
        'file':               filename,
        'label':              False,
        'address_bits':       defaults['address_bits'],
        'word_bits':          defaults['word_bits'],
        'words_per_line':     defaults['words_per_line'],
        'endianness':         defaults['endianness'],
        'checksum_algorithm': defaults['checksum_algorithm'],
        'labels':             [],
    }

# ── Logger ────────────────────────────────────────────────────────────────────
_ANSI_RE = re.compile(r'\033\[[0-9;]*m')

class Logger:
    def __init__(self, log_path):
        self.log_path = Path(log_path)
        self._lines = []

    def _plain(self, s):
        return _ANSI_RE.sub('', s)

    def write(self, msg='', console=True):
        if console:
            print(msg)
        self._lines.append(self._plain(msg))

    def ok(self,   msg): self.write(f"  {green('✓')} {msg}")
    def err(self,  msg): self.write(f"  {red('✗')} {msg}")
    def warn(self, msg): self.write(f"  {yellow('⚠')} {msg}")
    def info(self, msg): self.write(f"  {cyan('·')} {msg}")
    def head(self, msg): self.write(f"\n{bold(msg)}")
    def rule(self, ch='─', n=62): self.write(ch * n)

    def flush(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text('\n'.join(self._lines) + '\n', encoding='utf-8')

# ── .gitignore manager ────────────────────────────────────────────────────────
def manage_gitignore(repo_root, track_checksum, log):
    gi = Path(repo_root) / '.gitignore'
    text = gi.read_text() if gi.exists() else ''
    lines = text.splitlines()
    changed = False

    def ensure(pat):
        nonlocal changed
        if pat not in lines:
            lines.append(pat)
            changed = True

    def remove(pat):
        nonlocal changed
        if pat in lines:
            lines.remove(pat)
            changed = True

    for pat in ('configs/*.bin', 'build/', 'logs/'):
        ensure(pat)

    crc_pats = ['configs/*.crc32', 'configs/*.md5', 'configs/*.sha256']
    if track_checksum:
        for p in crc_pats:
            remove(p)
    else:
        for p in crc_pats:
            ensure(p)

    if changed:
        gi.write_text('\n'.join(lines) + '\n')
        log.info(".gitignore updated")

# ── Run directory manager ─────────────────────────────────────────────────────
def setup_run_dirs(build_dir, log_dir, keep_runs):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = build_dir / f'run_{ts}'
    for sub in ('packed', 'unpacked'):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
        (build_dir / 'latest' / sub).mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    # Prune old runs
    runs = sorted(build_dir.glob('run_*'), key=lambda p: p.stat().st_mtime)
    while len(runs) >= keep_runs:
        shutil.rmtree(runs.pop(0), ignore_errors=True)
    return run_dir, ts

# ── Checksum ──────────────────────────────────────────────────────────────────
def compute_checksum(data, algo):
    a = algo.lower().replace('-', '')
    if a == 'crc32':
        return f'{zlib.crc32(data) & 0xFFFFFFFF:08x}'
    elif a == 'md5':
        return hashlib.md5(data).hexdigest()
    elif a == 'sha256':
        return hashlib.sha256(data).hexdigest()
    else:
        raise ValueError(f"Unsupported checksum algorithm: {algo}")

def sidecar_ext(algo):
    return algo.lower().replace('-', '')

# ── Text parser ───────────────────────────────────────────────────────────────
def parse_txt(path, bin_cfg, val_cfg, log):
    """Parse .txt → list of (addr, [words]). Returns (data_lines, errors, warnings)."""
    addr_bits  = bin_cfg['address_bits']
    word_bits  = bin_cfg['word_bits']
    wpl        = bin_cfg['words_per_line']
    word_bytes = word_bits // 8
    addr_hlen  = addr_bits // 4
    word_hlen  = word_bits // 4
    stride     = word_bytes * wpl

    data_lines = []
    errors     = []
    warnings   = []
    seen_addrs = set()
    prev_addr  = None

    for lineno, raw in enumerate(Path(path).read_text().splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#'):
            continue
        if line.startswith('@label'):
            warnings.append(
                f"line {lineno}: @label found — labels are managed by bintxt_cfg.yaml, "
                f"not by hand-editing .txt files. Line ignored."
            )
            continue
        if ':' not in line:
            if val_cfg['fail_on_invalid_hex']:
                errors.append(f"line {lineno}: unrecognized format: '{line[:60]}'")
            continue

        addr_str, _, rest_str = line.partition(':')
        addr_str = addr_str.strip()
        words_raw = rest_str.strip().split()

        # Address width
        if len(addr_str) != addr_hlen:
            msg = (f"line {lineno}: address '{addr_str}' is {len(addr_str)} chars, "
                   f"expected {addr_hlen} for {addr_bits}-bit")
            if val_cfg['fail_on_invalid_hex']:
                errors.append(msg); continue
            else:
                warnings.append(msg)

        try:
            addr = int(addr_str, 16)
        except ValueError:
            errors.append(f"line {lineno}: invalid hex address '{addr_str}'")
            continue

        # Duplicate
        if addr in seen_addrs:
            msg = f"line {lineno}: duplicate address 0x{addr:0{addr_hlen}x}"
            if val_cfg['fail_on_duplicate_addresses']:
                errors.append(msg); continue
            else:
                warnings.append(msg)
        seen_addrs.add(addr)

        # Monotonic
        if prev_addr is not None and addr <= prev_addr:
            msg = (f"line {lineno}: address 0x{addr:0{addr_hlen}x} not greater than "
                   f"previous 0x{prev_addr:0{addr_hlen}x}")
            if val_cfg['fail_on_non_monotonic_addresses']:
                errors.append(msg); continue
            else:
                warnings.append(msg)

        # Stride
        if prev_addr is not None:
            expected = prev_addr + stride
            if addr != expected:
                msg = (f"line {lineno}: stride mismatch — expected "
                       f"0x{expected:0{addr_hlen}x}, got 0x{addr:0{addr_hlen}x}")
                if val_cfg['fail_on_stride_mismatch']:
                    errors.append(msg); continue
                else:
                    warnings.append(msg)

        # Word count
        if len(words_raw) == 0:
            if val_cfg['fail_on_invalid_word_count']:
                errors.append(f"line {lineno}: no words on data line"); continue
        if len(words_raw) > wpl:
            msg = f"line {lineno}: {len(words_raw)} words exceeds words_per_line={wpl}"
            if val_cfg['fail_on_invalid_word_count']:
                errors.append(msg); continue
            else:
                warnings.append(msg)
                words_raw = words_raw[:wpl]

        # Parse words
        words = []
        ok = True
        for wi, w in enumerate(words_raw):
            if len(w) != word_hlen:
                msg = (f"line {lineno}: word {wi+1} '{w}' is {len(w)} chars, "
                       f"expected {word_hlen} for {word_bits}-bit")
                if val_cfg['fail_on_invalid_hex']:
                    errors.append(msg); ok = False; break
                else:
                    warnings.append(msg)
            try:
                words.append(int(w, 16))
            except ValueError:
                errors.append(f"line {lineno}: invalid hex word '{w}'")
                ok = False; break

        if not ok:
            continue

        prev_addr = addr
        data_lines.append((addr, words))

    return data_lines, errors, warnings

# ── Pack (txt → bin) ──────────────────────────────────────────────────────────
def pack(txt_path, bin_cfg, val_cfg, log):
    name = Path(txt_path).name
    data_lines, errors, warnings = parse_txt(txt_path, bin_cfg, val_cfg, log)

    for w in warnings:
        log.warn(f"{name}: {w}")
    if errors:
        for e in errors:
            log.err(f"{name}: {e}")
        return None
    if not data_lines:
        log.err(f"{name}: no data lines found")
        return None

    word_bits  = bin_cfg['word_bits']
    word_bytes = word_bits // 8
    byteorder  = 'little' if bin_cfg['endianness'].lower().startswith('l') else 'big'

    last_addr, last_words = data_lines[-1]
    file_size = last_addr + len(last_words) * word_bytes

    if val_cfg['fail_on_partial_word'] and file_size % word_bytes != 0:
        log.err(f"{name}: file size {file_size} not aligned to {word_bytes}-byte words")
        return None

    buf = bytearray(file_size)
    for addr, words in data_lines:
        offset = addr
        for word in words:
            buf[offset:offset + word_bytes] = word.to_bytes(word_bytes, byteorder=byteorder)
            offset += word_bytes

    return bytes(buf)

# ── Unpack (bin → txt) ────────────────────────────────────────────────────────
def unpack(bin_path, bin_cfg, val_cfg, log):
    name = Path(bin_path).name
    data = Path(bin_path).read_bytes()

    word_bits  = bin_cfg['word_bits']
    word_bytes = word_bits // 8
    wpl        = bin_cfg['words_per_line']
    addr_bits  = bin_cfg['address_bits']
    addr_hlen  = addr_bits // 4
    word_hlen  = word_bits // 4
    byteorder  = 'little' if bin_cfg['endianness'].lower().startswith('l') else 'big'
    stride     = word_bytes * wpl

    if val_cfg['fail_on_partial_word'] and len(data) % word_bytes != 0:
        log.err(f"{name}: size {len(data)} not aligned to {word_bytes}-byte words")
        return None

    # Build label map
    label_map = {}
    if bin_cfg.get('label'):
        for lbl in (bin_cfg.get('labels') or []):
            addr = lbl.get('address')
            lname = lbl.get('label', '')
            if addr is not None:
                label_map[int(addr)] = lname

    lines = []
    offset = 0
    while offset < len(data):
        if offset in label_map:
            lines.append(f"@label {label_map[offset]}")

        chunk = data[offset:offset + stride]
        words = []
        for i in range(0, len(chunk), word_bytes):
            w = chunk[i:i + word_bytes]
            if len(w) < word_bytes:
                if val_cfg['fail_on_partial_word']:
                    log.err(f"{name}: partial word at offset 0x{offset+i:x}")
                    return None
                w = w + b'\x00' * (word_bytes - len(w))
            val = int.from_bytes(w, byteorder=byteorder)
            words.append(f'{val:0{word_hlen}x}')

        lines.append(f"{offset:0{addr_hlen}x}: {' '.join(words)}")
        offset += stride

    return '\n'.join(lines) + '\n'

# ── Verify ────────────────────────────────────────────────────────────────────
def _txt_to_bytes(txt_content, bin_cfg):
    """Normalize .txt content → byte stream (strips comments and @label lines)."""
    word_bits  = bin_cfg['word_bits']
    word_bytes = word_bits // 8
    byteorder  = 'little' if bin_cfg['endianness'].lower().startswith('l') else 'big'
    result = bytearray()
    for line in txt_content.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('@label'):
            continue
        if ':' not in line:
            continue
        _, _, rest = line.partition(':')
        for w in rest.strip().split():
            try:
                result += int(w, 16).to_bytes(word_bytes, byteorder=byteorder)
            except (ValueError, OverflowError):
                pass
    return bytes(result)

def verify(txt_content, bin_data, bin_cfg, label, log):
    """Compare txt content against bin bytes. Returns True if match."""
    txt_bytes = _txt_to_bytes(txt_content, bin_cfg)
    if txt_bytes == bin_data:
        log.ok(f"{label}: PASS")
        return True

    log.err(f"{label}: FAIL")
    word_bytes = bin_cfg['word_bits'] // 8
    addr_hlen  = bin_cfg['address_bits'] // 4
    word_hlen  = bin_cfg['word_bits'] // 4
    byteorder  = 'little' if bin_cfg['endianness'].lower().startswith('l') else 'big'
    mismatches = 0

    for i in range(0, max(len(txt_bytes), len(bin_data)), word_bytes):
        tb = txt_bytes[i:i + word_bytes]
        bb = bin_data[i:i + word_bytes]
        if tb == bb:
            continue
        addr = f'0x{i:0{addr_hlen}x}'
        tf   = f'{int.from_bytes(tb, byteorder):0{word_hlen}x}' if len(tb) == word_bytes else 'MISSING'
        bf   = f'{int.from_bytes(bb, byteorder):0{word_hlen}x}' if len(bb) == word_bytes else 'MISSING'
        log.write(f"    {red('MISMATCH')} @ {addr}  TXT={tf}  BIN={bf}")
        mismatches += 1
        if mismatches >= 10:
            log.write("    ... (further mismatches truncated — see full log)")
            break

    return False

# ── Main pipeline ─────────────────────────────────────────────────────────────
def main():
    # Load config
    try:
        cfg_text = CFG_FILE.read_text(encoding='utf-8')
    except Exception as e:
        print(red(f"FATAL: Cannot read {CFG_FILE}: {e}"))
        sys.exit(1)

    try:
        cfg = load_yaml(cfg_text)
    except Exception as e:
        print(red(f"FATAL: YAML parse error in {CFG_FILE}: {e}"))
        sys.exit(1)

    cfg_errors = validate_cfg(cfg)
    if cfg_errors:
        print(red("FATAL: bintxt_cfg.yaml is invalid:"))
        for e in cfg_errors:
            print(f"  • {e}")
        sys.exit(1)

    # Resolve dirs
    paths      = cfg['paths']
    config_dir = SCRIPT_DIR / paths['config_dir']
    build_dir  = SCRIPT_DIR / paths['build_dir']
    log_dir    = SCRIPT_DIR / paths['log_dir']
    defaults   = get_defaults(cfg)
    val_cfg    = get_validation(cfg)
    out_cfg    = get_output_cfg(cfg)

    # Setup run
    run_dir, ts = setup_run_dirs(build_dir, log_dir, out_cfg['keep_runs'])
    log_name    = datetime.now().strftime('%Y-%m-%d_%I%p_%M_bintxtLog.txt')
    log_file    = log_dir / log_name
    log         = Logger(log_file)

    SEP = '═' * 62
    log.write(bold(SEP))
    log.write(bold("  bintxt — Binary ↔ Text Truth Pipeline"))
    log.write(bold(f"  Run: {ts}"))
    log.write(bold(SEP))

    # Manage .gitignore
    manage_gitignore(SCRIPT_DIR, out_cfg['track_checksum'], log)

    config_dir.mkdir(parents=True, exist_ok=True)

    # ── Scan ──────────────────────────────────────────────────────────────────
    log.head("Scan")
    txt_files = sorted(config_dir.glob('*.txt'))
    bin_files = sorted(config_dir.glob('*.bin'))
    log.write(f"  {cyan(str(len(txt_files)))} .txt files")
    log.write(f"  {cyan(str(len(bin_files)))} .bin files")

    all_bases = sorted(
        set(f.stem for f in txt_files) | set(f.stem for f in bin_files)
    )

    if not all_bases:
        log.warn("No .txt or .bin files found in configs/")
        log.flush()
        shutil.copy2(log_file, log_dir / 'latest.log')
        sys.exit(0)

    # ── Per-file processing ───────────────────────────────────────────────────
    results = {'pack': {}, 'unpack': {}, 'verify_pack': {},
               'verify_unpack': {}, 'verify_source_pair': {}}
    failures = 0

    for base in all_bases:
        txt_path = config_dir / f'{base}.txt'
        bin_path = config_dir / f'{base}.bin'
        has_txt  = txt_path.exists()
        has_bin  = bin_path.exists()

        log.write("")
        log.write(bold("─" * 62))
        log.write(f"  {bold(base)}")

        # Get binary config
        bin_cfg = get_binary_cfg(cfg, f'{base}.bin', defaults)
        if bin_cfg is None:
            log.warn(f"{base}.bin has no YAML entry — using defaults, no label injection")
            bin_cfg = _default_bin_cfg(f'{base}.bin', defaults)

        # Validate label addresses
        if bin_cfg['label'] and val_cfg['fail_on_missing_label_address'] and has_bin:
            bin_data   = bin_path.read_bytes()
            wb         = bin_cfg['word_bits'] // 8
            stride     = wb * bin_cfg['words_per_line']
            valid_addrs = set(range(0, len(bin_data), stride))
            for lbl in bin_cfg['labels']:
                addr = lbl.get('address')
                if addr is not None and int(addr) not in valid_addrs:
                    log.err(f"Label '{lbl.get('label')}' at 0x{int(addr):08x} "
                            f"is not a valid line address in {base}.bin")
                    failures += 1

        packed_data  = None
        unpacked_txt = None

        # ── PACK ──────────────────────────────────────────────────────────────
        if has_txt:
            log.write(f"  PACK   {cyan(txt_path.name)} → ...")
            packed_data = pack(txt_path, bin_cfg, val_cfg, log)
            if packed_data is not None:
                # Write to build
                out_p = run_dir / 'packed' / f'{base}.bin'
                out_p.write_bytes(packed_data)
                shutil.copy2(out_p, build_dir / 'latest' / 'packed' / f'{base}.bin')

                # Write to configs/ if no .bin existed
                if not has_bin:
                    (config_dir / f'{base}.bin').write_bytes(packed_data)
                    log.warn(f"No {base}.bin in configs/ — packed output written there. "
                             f"Add a YAML entry for this file.")

                # Checksum
                algo     = bin_cfg['checksum_algorithm']
                chk      = compute_checksum(packed_data, algo)
                ext      = sidecar_ext(algo)
                sc_name  = f'{base}.bin.{ext}'
                sc_text  = f'{chk}  {base}.bin\n'

                (run_dir / 'packed' / sc_name).write_text(sc_text)
                shutil.copy2(run_dir / 'packed' / sc_name,
                             build_dir / 'latest' / 'packed' / sc_name)
                if out_cfg['track_checksum']:
                    (config_dir / sc_name).write_text(sc_text)

                log.ok(f"Packed: {base}.bin  ({len(packed_data)} bytes)  "
                       f"{algo.upper()}: {chk}")
                results['pack'][base] = 'PASS'
            else:
                log.err(f"Pack FAILED: {base}.txt")
                results['pack'][base] = 'FAIL'
                failures += 1

        # ── UNPACK ────────────────────────────────────────────────────────────
        if has_bin:
            log.write(f"  UNPACK {cyan(bin_path.name)} → ...")
            unpacked_txt = unpack(bin_path, bin_cfg, val_cfg, log)
            if unpacked_txt is not None:
                out_u = run_dir / 'unpacked' / f'{base}.txt'
                out_u.write_text(unpacked_txt)
                shutil.copy2(out_u, build_dir / 'latest' / 'unpacked' / f'{base}.txt')
                log.ok(f"Unpacked: {base}.txt  ({len(unpacked_txt.splitlines())} lines)")
                results['unpack'][base] = 'PASS'
            else:
                log.err(f"Unpack FAILED: {base}.bin")
                results['unpack'][base] = 'FAIL'
                failures += 1

        # ── VERIFY ────────────────────────────────────────────────────────────
        log.write("  Verification:")

        if has_txt and packed_data is not None:
            ok = verify(txt_path.read_text(), packed_data, bin_cfg,
                        f"verify_pack({base})", log)
            results['verify_pack'][base] = 'PASS' if ok else 'FAIL'
            if not ok:
                failures += 1

        if has_bin and unpacked_txt is not None:
            ok = verify(unpacked_txt, bin_path.read_bytes(), bin_cfg,
                        f"verify_unpack({base})", log)
            results['verify_unpack'][base] = 'PASS' if ok else 'FAIL'
            if not ok:
                failures += 1

        if has_txt and has_bin:
            ok = verify(txt_path.read_text(), bin_path.read_bytes(), bin_cfg,
                        f"verify_source_pair({base})", log)
            results['verify_source_pair'][base] = 'PASS' if ok else 'FAIL'
            if not ok:
                failures += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    log.write("")
    log.write(bold(SEP))
    log.write(bold("  Result Summary"))
    log.write(bold(SEP))

    for phase, res in results.items():
        if not res:
            continue
        log.write(f"\n  {bold(phase.upper().replace('_', ' '))}:")
        for name, status in sorted(res.items()):
            (log.ok if status == 'PASS' else log.err)(f"{name}: {status}")

    total  = sum(len(v) for v in results.values())
    passed = sum(1 for v in results.values() for r in v.values() if r == 'PASS')
    failed = total - passed

    log.write("")
    log.write(f"  {green(str(passed))} passed  |  "
              f"{(red(str(failed)) if failed else str(failed))} failed  |  "
              f"{total} total")
    log.write(f"  {dim('Log:')} {log_file.relative_to(SCRIPT_DIR)}")
    log.write(f"  {dim('Run:')} {run_dir.relative_to(SCRIPT_DIR)}")
    log.write("")

    if failures == 0:
        log.write(green("  ALL OPERATIONS PASSED ✓"))
    else:
        log.write(red(f"  {failures} FAILURE(S) — review log for details"))

    log.write(bold(SEP))
    log.flush()

    shutil.copy2(log_file, log_dir / 'latest.log')

    sys.exit(0 if failures == 0 else 1)


main()
PYEOF

EXIT_CODE=$?
echo ""
read -rsp $'Press any key to exit...\n' -n 1
echo ""
exit $EXIT_CODE
