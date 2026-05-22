"""State management — change detection, .bintxt_state persistence, txt reformatting."""

import hashlib
import json
import shutil
from pathlib import Path

from .ansi import yellow, cyan


_STATE_KEYS = ('word_bits', 'words_per_line', 'address_bits', 'endianness',
               'checksum_algorithm', 'label')


def cfg_fingerprint(bin_cfg):
    fp = {k: bin_cfg[k] for k in _STATE_KEYS}
    fp['labels'] = sorted(
        [str(l.get('address', '')), str(l.get('label', ''))]
        for l in (bin_cfg.get('labels') or [])
    )
    return fp


def txt_hash(txt_path):
    """SHA-256 of .txt content ignoring line endings. Returns hex string or None."""
    try:
        content = Path(txt_path).read_text(encoding='utf-8').replace('\r\n', '\n')
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    except Exception:
        return None


def has_hex_data(txt_path):
    """Return True if the .txt contains at least one hex data line (addr: words)."""
    try:
        for line in Path(txt_path).read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('@'):
                continue
            if ':' in line:
                return True
        return False
    except Exception:
        return False


def load_state(script_dir):
    p = Path(script_dir) / '.bintxt_state'
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_state(script_dir, state):
    p = Path(script_dir) / '.bintxt_state'
    p.write_text(json.dumps(state, indent=2), encoding='utf-8')


def check_cfg_change(base, bin_cfg, state, log):
    """Detect YAML settings change since last run.
    Returns (changed: bool, prev_cfg: dict|None)."""
    entry          = state.get(base)
    prev           = entry.get('config') if entry else None
    from_discovery = entry.get('from_discovery', False) if entry else False
    curr           = cfg_fingerprint(bin_cfg)
    if prev is None or prev == curr:
        return False, prev
    if from_discovery:
        log.info(f"  Applying initial YAML configuration for {base}")
        return True, prev
    log.warn(f"YAML settings changed for {base}:")
    for k in _STATE_KEYS:
        old_v = prev.get(k, '—')
        new_v = curr.get(k, '—')
        if old_v != new_v:
            log.write(f"    {k}: {yellow(str(old_v))} → {cyan(str(new_v))}")
    old_labels = prev.get('labels', [])
    new_labels = bin_cfg.get('labels') or []
    new_label_map = {str(l.get('address', '')): str(l.get('label', '')) for l in new_labels}
    old_label_map = {r[0]: r[1] for r in old_labels}
    for addr, name in old_label_map.items():
        if addr not in new_label_map:
            log.write(f"    label removed:  0x{int(addr):08x} {name}")
        elif new_label_map[addr] != name:
            log.write(f"    label renamed:  0x{int(addr):08x} {yellow(name)} → {cyan(new_label_map[addr])}")
    for addr, name in new_label_map.items():
        if addr not in old_label_map:
            log.write(f"    label added:    0x{int(addr):08x} {cyan(name)}")
    return True, prev


def reformat_txt(base, txt_path, old_state, new_cfg, val_cfg, run_dir, log):
    """Reformat an existing .txt from old settings to new settings entirely from the .txt.
    Backs up the old .txt to run_dir/rollback/ before overwriting.
    Returns True on success."""

    def _state_to_cfg(s):
        return {
            'word_bits':          int(s.get('word_bits', 8)),
            'words_per_line':     int(s.get('words_per_line', 6)),
            'address_bits':       int(s.get('address_bits', 32)),
            'endianness':         str(s.get('endianness', 'little')),
            'checksum_algorithm': str(s.get('checksum_algorithm', 'crc32')),
            'label':              bool(s.get('label', False)),
            'labels':             [],
            'file':               f'{base}.bin',
        }

    old_cfg        = _state_to_cfg(old_state)
    old_word_bytes = old_cfg['word_bits'] // 8
    old_byteorder  = 'little' if old_cfg['endianness'].lower().startswith('l') else 'big'

    raw_data = bytearray()
    try:
        for line in txt_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('@'):
                continue
            if ':' not in line:
                continue
            _, hex_part = line.split(':', 1)
            for word_hex in hex_part.split():
                val = int(word_hex, 16)
                raw_data += val.to_bytes(old_word_bytes, byteorder=old_byteorder)
    except Exception as e:
        log.err(f"  Reformat failed — could not parse {base}.txt with old settings: {e}")
        return False

    new_word_bits  = new_cfg['word_bits']
    new_word_bytes = new_word_bits // 8
    new_wpl        = new_cfg['words_per_line']
    new_addr_bits  = new_cfg['address_bits']
    new_addr_hlen  = new_addr_bits // 4
    new_word_hlen  = new_word_bits // 4
    new_byteorder  = 'little' if new_cfg['endianness'].lower().startswith('l') else 'big'
    new_stride     = new_word_bytes * new_wpl

    if len(raw_data) % new_word_bytes != 0:
        log.err(f"  Reformat failed — {len(raw_data)} bytes not aligned to new word size ({new_word_bytes} bytes)")
        return False

    label_map = {}
    if new_cfg.get('label'):
        for lbl in (new_cfg.get('labels') or []):
            addr = lbl.get('address')
            if addr is not None:
                label_map[int(addr)] = lbl.get('label', '')

    lines = []
    offset = 0
    while offset < len(raw_data):
        if offset in label_map:
            lines.append(f"@label {label_map[offset]}")
        chunk = raw_data[offset:offset + new_stride]
        words = []
        for i in range(0, len(chunk), new_word_bytes):
            w = chunk[i:i + new_word_bytes]
            if len(w) < new_word_bytes:
                w = w + b'\x00' * (new_word_bytes - len(w))
            val = int.from_bytes(w, byteorder=new_byteorder)
            words.append(f'{val:0{new_word_hlen}x}')
        lines.append(f"{offset:0{new_addr_hlen}x}: {' '.join(words)}")
        offset += new_stride

    new_txt = '\n'.join(lines) + '\n'

    rollback_dir = run_dir / 'rollback'
    rollback_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(txt_path, rollback_dir / f'{base}.txt')
    log.info(f"  Backed up old {base}.txt → build/run_<ts>/rollback/")

    txt_path.write_text(new_txt, encoding='utf-8')
    log.ok(f"  Reformatted {base}.txt — review diff before committing")
    return True
