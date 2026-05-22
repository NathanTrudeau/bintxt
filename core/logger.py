"""Logger — writes to console and accumulates plain-text log for file flush."""

import re
from pathlib import Path
from .ansi import red, green, yellow, cyan, bold

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
