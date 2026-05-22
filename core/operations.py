"""Core binary operations — parse_txt, pack, unpack, verify, checksum."""

import hashlib
import zlib
from pathlib import Path

from .ansi import red


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

    try:
        raw_text = Path(path).read_text(encoding='utf-8')
    except (UnicodeDecodeError, PermissionError) as e:
        return [], [f"cannot read file: {e}"], []

    for lineno, raw in enumerate(raw_text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#'):
            continue
        if line.startswith('@label'):
            lname = line[6:].strip()
            if lname and bin_cfg.get('label') and bin_cfg.get('labels'):
                yaml_names = {str(l.get('label', '')) for l in bin_cfg['labels']}
                if lname not in yaml_names:
                    warnings.append(
                        f"line {lineno}: @label '{lname}' is not defined in "
                        f"bintxt_cfg.yaml — add it under binaries.labels or it "
                        f"will be lost on next unpack"
                    )
            continue
        if ':' not in line:
            if val_cfg['fail_on_invalid_hex']:
                errors.append(f"line {lineno}: unrecognized format: '{line[:60]}'")
            continue

        addr_str, _, rest_str = line.partition(':')
        addr_str  = addr_str.strip()
        words_raw = rest_str.strip().split()

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

        if addr in seen_addrs:
            msg = f"line {lineno}: duplicate address 0x{addr:0{addr_hlen}x}"
            if val_cfg['fail_on_duplicate_addresses']:
                errors.append(msg); continue
            else:
                warnings.append(msg)
        seen_addrs.add(addr)

        if prev_addr is not None and addr <= prev_addr:
            msg = (f"line {lineno}: address 0x{addr:0{addr_hlen}x} not greater than "
                   f"previous 0x{prev_addr:0{addr_hlen}x}")
            if val_cfg['fail_on_non_monotonic_addresses']:
                errors.append(msg); continue
            else:
                warnings.append(msg)

        if prev_addr is not None:
            expected = prev_addr + stride
            if addr != expected:
                msg = (f"line {lineno}: stride mismatch — expected "
                       f"0x{expected:0{addr_hlen}x}, got 0x{addr:0{addr_hlen}x}")
                if val_cfg['fail_on_stride_mismatch']:
                    errors.append(msg); continue
                else:
                    warnings.append(msg)

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

        words = []
        ok    = True
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


# ── Pack ──────────────────────────────────────────────────────────────────────

def pack(txt_path, bin_cfg, val_cfg, log):
    """Parse .txt and return packed bytes, or None on failure."""
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


# ── Unpack ────────────────────────────────────────────────────────────────────

def unpack(bin_path, bin_cfg, val_cfg, log):
    """Read .bin and return unpacked .txt string, or None on failure."""
    name = Path(bin_path).name
    try:
        data = Path(bin_path).read_bytes()
    except (PermissionError, OSError) as e:
        log.err(f"{name}: cannot read binary — {e}")
        return None

    if len(data) == 0:
        log.err(f"{name}: file is empty (0 bytes)")
        return None

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

    label_map = {}
    if bin_cfg.get('label'):
        for lbl in (bin_cfg.get('labels') or []):
            addr  = lbl.get('address')
            lname = lbl.get('label', '')
            if addr is not None:
                label_map[int(addr)] = lname

    lines  = []
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
    """Normalise .txt content → byte stream (strips comments and @label lines)."""
    word_bits  = bin_cfg['word_bits']
    word_bytes = word_bits // 8
    byteorder  = 'little' if bin_cfg['endianness'].lower().startswith('l') else 'big'
    result     = bytearray()
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
