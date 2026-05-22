"""Config validation and accessor helpers."""


def validate_cfg(cfg):
    errors = []
    if not isinstance(cfg, dict) or not cfg:
        return ["bintxt_cfg.yaml is empty or not a valid mapping — copy the template and configure it"]
    if cfg.get('version') != 1:
        errors.append(f"'version' must be 1 (got: {cfg.get('version')!r})")
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
        'keep_runs':             int(o.get('keep_runs', 10)),
        'track_checksum':        bool(o.get('track_checksum', False)),
        'generate_yaml_example': bool(o.get('generate_yaml_example', True)),
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


def default_bin_cfg(filename, defaults):
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
