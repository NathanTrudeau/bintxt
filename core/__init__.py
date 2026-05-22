"""bintxt core — public API for bintxt_ui and other consumers.

Quick import example:
    from bintxt.core import pack, unpack, verify, load_yaml, Logger
    from bintxt.core.config import validate_cfg, get_defaults, get_binary_cfg
"""

from .yaml_loader import load_yaml
from .config import (
    validate_cfg,
    get_defaults,
    get_validation,
    get_output_cfg,
    get_binary_cfg,
    default_bin_cfg,
)
from .state import (
    load_state,
    save_state,
    check_cfg_change,
    cfg_fingerprint,
    txt_hash,
    has_hex_data,
    reformat_txt,
)
from .logger import Logger
from .operations import pack, unpack, verify, parse_txt, compute_checksum, sidecar_ext
from .fs import manage_gitignore, setup_run_dirs, write_yaml_example

__all__ = [
    'load_yaml',
    'validate_cfg', 'get_defaults', 'get_validation', 'get_output_cfg',
    'get_binary_cfg', 'default_bin_cfg',
    'load_state', 'save_state', 'check_cfg_change', 'cfg_fingerprint',
    'txt_hash', 'has_hex_data', 'reformat_txt',
    'Logger',
    'pack', 'unpack', 'verify', 'parse_txt', 'compute_checksum', 'sidecar_ext',
    'manage_gitignore', 'setup_run_dirs', 'write_yaml_example',
]
