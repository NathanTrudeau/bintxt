"""Main pipeline — called by bintxt.sh.

Usage:
    python core/pipeline.py <script_dir> <cfg_file> [exclude ...]
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

# Windows cp1252 fix — force UTF-8 on stdout/stderr before any output
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

from .ansi import red, green, yellow, cyan, bold, dim
from .yaml_loader import load_yaml
from .config import (
    validate_cfg, get_defaults, get_validation, get_output_cfg,
    get_binary_cfg, default_bin_cfg,
)
from .state import (
    cfg_fingerprint, txt_hash, has_hex_data,
    load_state, save_state, check_cfg_change, reformat_txt,
)
from .logger import Logger
from .operations import pack, unpack, verify, compute_checksum, sidecar_ext
from .fs import manage_gitignore, setup_run_dirs, write_yaml_example


def main(script_dir: Path, cfg_file: Path, exclude_set: set):
    # ── Load config ───────────────────────────────────────────────────────────
    try:
        cfg_text = cfg_file.read_text(encoding='utf-8')
    except Exception as e:
        print(red(f"FATAL: Cannot read {cfg_file}: {e}"))
        sys.exit(1)

    try:
        cfg = load_yaml(cfg_text)
    except Exception as e:
        print(red(f"FATAL: YAML parse error in {cfg_file}: {e}"))
        sys.exit(1)

    cfg_errors = validate_cfg(cfg)
    if cfg_errors:
        print(red("FATAL: bintxt_cfg.yaml is invalid:"))
        for e in cfg_errors:
            print(f"  • {e}")
        sys.exit(1)

    paths      = cfg['paths']
    config_dir = script_dir / paths['config_dir']
    build_dir  = script_dir / paths['build_dir']
    log_dir    = script_dir / paths['log_dir']
    defaults   = get_defaults(cfg)
    val_cfg    = get_validation(cfg)
    out_cfg    = get_output_cfg(cfg)

    # ── Setup run ─────────────────────────────────────────────────────────────
    run_dir, ts = setup_run_dirs(build_dir, log_dir, out_cfg['keep_runs'])
    log_name    = datetime.now().strftime('%Y-%m-%d_%I%p_%M_bintxtLog.txt')
    log_file    = log_dir / log_name
    log         = Logger(log_file)

    SEP = '═' * 62
    log.write(bold(SEP))
    log.write(bold("  bintxt — Binary ↔ Text Truth Pipeline"))
    log.write(bold(f"  Run: {ts}"))
    if cfg_file.name != 'bintxt_cfg.yaml':
        log.write(bold(f"  Config: {cfg_file}"))
    if exclude_set:
        log.write(bold(f"  Excluding: {', '.join(sorted(exclude_set))}"))
    log.write(bold(SEP))

    manage_gitignore(script_dir, out_cfg['track_checksum'], log)
    config_dir.mkdir(parents=True, exist_ok=True)

    run_state = load_state(script_dir)
    new_state  = dict(run_state)

    # ── Scan ──────────────────────────────────────────────────────────────────
    log.head("Scan")
    txt_files = sorted(config_dir.glob('*.txt'))
    bin_files = sorted(config_dir.glob('*.bin'))
    log.write(f"  {cyan(str(len(txt_files)))} .txt files")
    log.write(f"  {cyan(str(len(bin_files)))} .bin files")

    all_bases = sorted(
        set(f.stem for f in txt_files) | set(f.stem for f in bin_files)
    )

    if exclude_set:
        excluded  = [b for b in all_bases if b in exclude_set]
        all_bases = [b for b in all_bases if b not in exclude_set]
        unknown   = exclude_set - {Path(f).stem for f in
                        [e.get('file', '') for e in (cfg.get('binaries') or [])] +
                        [f.name for f in list(txt_files) + list(bin_files)]}
        for b in excluded:
            log.info(f"  Excluded (this run): {b}")
        for u in sorted(unknown):
            log.warn(f"  --exclude '{u}' — no matching file found in configs/")

    for entry in (cfg.get('binaries') or []):
        fname = entry.get('file', '')
        base  = Path(fname).stem
        if base and base not in all_bases:
            log.warn(f"  YAML references '{fname}' but no .txt or .bin found in configs/ — skipping")

    if not all_bases:
        log.warn("No .txt or .bin files found in configs/")
        log.flush()
        shutil.copy2(log_file, log_dir / 'latest.log')
        sys.exit(0)

    # ── Per-file processing ───────────────────────────────────────────────────
    results = {'pack': {}, 'unpack': {}, 'verify_pack': {},
               'verify_unpack': {}, 'verify_source_pair': {}}
    failures    = 0
    discoveries = []

    for base in all_bases:
        txt_path = config_dir / f'{base}.txt'
        bin_path = config_dir / f'{base}.bin'
        has_txt  = txt_path.exists()
        has_bin  = bin_path.exists()

        log.write("")
        log.write(bold("─" * 62))
        log.write(f"  {bold(base)}")

        if has_txt:
            curr_hash  = txt_hash(txt_path)
            prev_entry = run_state.get(base)
            prev_hash  = prev_entry.get('txt_hash') if prev_entry else None
            known_file = prev_entry is not None
            if not known_file:
                log.info(f"  source: new")
            elif prev_hash is not None and curr_hash != prev_hash:
                log.warn(f"  source: modified since last run")

        bin_cfg_check = get_binary_cfg(cfg, f'{base}.bin', defaults)
        if has_txt and not has_bin and not has_hex_data(txt_path):
            if bin_cfg_check is None:
                log.warn(f"  {base}.txt — skipped (no hex data, likely a non-binary file)")
            else:
                log.err(f"  {base}.txt — no hex data found but has a YAML entry")
                failures += 1
            continue

        bin_cfg       = get_binary_cfg(cfg, f'{base}.bin', defaults)
        no_yaml_entry = bin_cfg is None
        if no_yaml_entry:
            log.warn(f"{base}.bin — no YAML entry (discovery mode)")
            log.write(f"    Unpacking with defaults for inspection.")
            log.write(f"    See bintxt_cfg.example.yaml to add a configured entry.")
            bin_cfg = default_bin_cfg(f'{base}.bin', defaults)
            discoveries.append(base)
        else:
            cfg_changed, prev_state = check_cfg_change(base, bin_cfg, run_state, log)
            if cfg_changed and has_txt and prev_state:
                log.write(f"  Reformatting {base}.txt to match new YAML settings...")
                reformat_txt(base, txt_path, prev_state, bin_cfg, val_cfg, run_dir, log)

        if bin_cfg['label'] and val_cfg['fail_on_missing_label_address'] and has_bin:
            bin_data    = bin_path.read_bytes()
            wb          = bin_cfg['word_bits'] // 8
            stride      = wb * bin_cfg['words_per_line']
            valid_addrs = set(range(0, len(bin_data), stride))
            for lbl in bin_cfg['labels']:
                addr = lbl.get('address')
                if addr is not None and int(addr) not in valid_addrs:
                    log.err(f"Label '{lbl.get('label')}' at 0x{int(addr):08x} "
                            f"is not a valid line address in {base}.bin")
                    failures += 1

        packed_data  = None
        unpacked_txt = None

        # PACK
        if has_txt and not no_yaml_entry:
            log.write(f"  PACK   {cyan(txt_path.name)} → ...")
            packed_data = pack(txt_path, bin_cfg, val_cfg, log)
            if packed_data is not None:
                out_p = run_dir / 'packed' / f'{base}.bin'
                out_p.write_bytes(packed_data)
                shutil.copy2(out_p, build_dir / 'latest' / 'packed' / f'{base}.bin')

                algo    = bin_cfg['checksum_algorithm']
                chk     = compute_checksum(packed_data, algo)
                ext     = sidecar_ext(algo)
                sc_name = f'{base}.bin.{ext}'
                sc_text = f'{chk}  {base}.bin\n'

                (run_dir / 'packed' / sc_name).write_text(sc_text, encoding='utf-8')
                shutil.copy2(run_dir / 'packed' / sc_name,
                             build_dir / 'latest' / 'packed' / sc_name)
                if out_cfg['track_checksum']:
                    (config_dir / sc_name).write_text(sc_text, encoding='utf-8')

                log.ok(f"Packed: {base}.bin  ({len(packed_data)} bytes)  "
                       f"{algo.upper()}: {chk}")
                results['pack'][base] = 'PASS'
            else:
                log.err(f"Pack FAILED: {base}.txt")
                results['pack'][base] = 'FAIL'
                failures += 1

        # UNPACK
        if has_bin:
            log.write(f"  UNPACK {cyan(bin_path.name)} → ...")
            unpacked_txt = unpack(bin_path, bin_cfg, val_cfg, log)
            if unpacked_txt is not None:
                if not has_txt:
                    (config_dir / f'{base}.txt').write_text(unpacked_txt, encoding='utf-8')
                    log.info(f"First run: wrote {base}.txt → configs/ for inspection")

                moved_bin = run_dir / f'{base}.bin'
                shutil.move(str(bin_path), str(moved_bin))
                bin_path = moved_bin

                log.ok(f"Unpacked: {base}.txt  ({len(unpacked_txt.splitlines())} lines)")
                results['unpack'][base] = 'PASS'
            else:
                log.err(f"Unpack FAILED: {base}.bin")
                results['unpack'][base] = 'FAIL'
                failures += 1

        # VERIFY
        if not no_yaml_entry:
            log.write("  Verification:")

            if has_txt and packed_data is not None:
                ok = verify(txt_path.read_text(encoding='utf-8'), packed_data, bin_cfg,
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
                ok = verify(txt_path.read_text(encoding='utf-8'), bin_path.read_bytes(), bin_cfg,
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
        label = phase.replace('_', ' ').title()
        log.write(f"\n  {bold(label)}:")
        for name, status in sorted(res.items()):
            (log.ok if status == 'PASS' else log.err)(f"{name}: {status}")

    total  = sum(len(v) for v in results.values())
    passed = sum(1 for v in results.values() for r in v.values() if r == 'PASS')
    failed = total - passed

    log.write("")
    log.write(f"  {green(str(passed))} passed  |  "
              f"{(red(str(failed)) if failed else str(failed))} failed  |  "
              f"{total} total")
    log.write(f"  {dim('Log:')} {log_file.relative_to(script_dir)}")
    log.write(f"  {dim('Run:')} {run_dir.relative_to(script_dir)}")
    log.write("")

    if failures == 0 and not discoveries:
        log.write(green("  ALL OPERATIONS PASSED ✓"))
    elif failures == 0 and discoveries:
        log.write(yellow(f"  DISCOVERY RUN — {len(discoveries)} file(s) have no YAML entry:"))
        for d in sorted(discoveries):
            log.write(f"    • {d}.bin")
        log.write("")
        log.write(f"  Next steps:")
        log.write(f"    1. Open bintxt_cfg.example.yaml (generated below)")
        log.write(f"    2. Copy entries into bintxt_cfg.yaml and configure format/labels")
        log.write(f"    3. Re-run — full pack + verify pipeline will run")
    else:
        log.write(red(f"  {failures} FAILURE(S) — review log for details"))
        if discoveries:
            log.write(yellow(f"  {len(discoveries)} file(s) in discovery mode (not counted as failures):"))
            for d in sorted(discoveries):
                log.write(f"    • {d}.bin")

    if out_cfg['generate_yaml_example']:
        log.head("Generate YAML Example")
        write_yaml_example(all_bases, cfg, defaults, script_dir, log)

    # ── Save state ────────────────────────────────────────────────────────────
    for base in all_bases:
        bc           = get_binary_cfg(cfg, f'{base}.bin', defaults)
        is_discovery = base in discoveries
        fp           = cfg_fingerprint(bc) if bc is not None \
                       else cfg_fingerprint(default_bin_cfg(f'{base}.bin', defaults))
        txt_p        = config_dir / f'{base}.txt'
        new_state[base] = {
            'config':         fp,
            'txt_hash':       txt_hash(txt_p) if txt_p.exists() else None,
            'from_discovery': is_discovery,
        }
    save_state(script_dir, new_state)

    log.write(bold(SEP))
    log.flush()
    shutil.copy2(log_file, log_dir / 'latest.log')

    sys.exit(0 if failures == 0 else 1)


if __name__ == '__main__':
    _script_dir  = Path(sys.argv[1])
    _cfg_file    = Path(sys.argv[2])
    _exclude_set = {Path(x).stem for x in sys.argv[3:]}
    main(_script_dir, _cfg_file, _exclude_set)
