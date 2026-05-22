"""YAML loader — tries PyYAML, falls back to minimal stdlib parser."""

import re


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

    lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue
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
                    result.append(parse_node(list_ind + 2))
                elif ':' in content and not content.startswith(("'", '"')):
                    k, _, v = content.partition(':')
                    k = k.strip(); v = v.strip()
                    item = {}
                    if v:
                        item[k] = cast(v)
                    else:
                        if idx[0] < len(lines) and cur_ind() > list_ind:
                            item[k] = parse_node(cur_ind())
                        else:
                            item[k] = None
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

        idx[0] += 1
        return cast(line)

    return parse_node(0) or {}
