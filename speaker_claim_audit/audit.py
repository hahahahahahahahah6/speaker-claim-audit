"""Static claim matching and provider resolution; audited code is never run."""
import ast
import fnmatch
import re
from pathlib import Path
from .phrases import SPEAKER, NOSPEAKER


def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().replace("n't", ' not').replace('-', ' ')).strip()


def pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r')\b')


def claims(text):
    paragraphs, current = [], []
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        if not line.strip():
            paragraphs.append(' '.join(current))
            current = []
        else:
            current.append(line)
    paragraphs.append(' '.join(current))
    positive = negative = False
    for paragraph in paragraphs:
        text = normalize(paragraph)
        negative |= bool(pattern(NOSPEAKER).search(text))
        positive |= bool(pattern(SPEAKER).search(pattern(NOSPEAKER).sub(' ', text)))
    return positive, negative


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + '.' + node.attr if base else ''
    return ''


def evidence(source):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    aliases, imported = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for item in node.names:
                if item.name != '*':
                    local = item.asname or item.name
                    aliases[local] = node.module + '.' + item.name
                    imported.add(local)

    def resolve(node):
        path = dotted(node)
        first, sep, rest = path.partition('.')
        return aliases.get(first, first) + (sep + rest if sep else '')

    def provider(path, base):
        return path == base or path.startswith(base + '.')

    def constructor(node):
        if not isinstance(node, ast.Call):
            return None
        path = resolve(node.func)
        if provider(path, 'pygame') and path.endswith('.mixer.Sound'):
            return 'sound'
        if provider(path, 'simpleaudio') and (path.endswith('.WaveObject') or path.endswith('.WaveObject.from_wave_file')):
            return 'wave'
        if provider(path, 'pyaudio') and path.endswith('.PyAudio'):
            return 'engine'
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'open':
            receiver = node.func.value
            is_engine = provider(resolve(receiver), 'pyaudio') or bindings.get(dotted(receiver)) == 'engine' or constructor(receiver) == 'engine'
            if is_engine and any(k.arg == 'output' and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                return 'stream'
        return None

    bindings = {}
    assignments = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    # Fixed point permits module-local bindings located in separate methods.
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            kind = constructor(node.value)
            if kind:
                for target in node.targets:
                    name = dotted(target)
                    if name and bindings.get(name) != kind:
                        bindings[name] = kind
                        changed = True
        if not changed:
            break
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        path = resolve(func)
        leaf = path.rsplit('.', 1)[-1]
        direct = isinstance(func, ast.Name) and func.id in imported
        route = None
        if any(provider(path, p) for p in ('playsound', 'playsound2')) and (direct or isinstance(func, ast.Attribute) and func.attr == 'playsound'):
            route = 'playsound'
        elif provider(path, 'sounddevice') and leaf == 'play':
            route = 'sounddevice'
        elif provider(path, 'winsound') and leaf in ('PlaySound', 'Beep', 'MessageBeep'):
            route = 'winsound'
        elif direct and provider(path, 'pydub.playback') and leaf == 'play':
            route = 'pydub'
        elif isinstance(func, ast.Attribute):
            receiver = func.value
            kind = bindings.get(dotted(receiver)) or constructor(receiver)
            music = resolve(receiver)
            if func.attr == 'play' and (kind in ('sound', 'wave') or provider(music, 'pygame') and music.endswith('.mixer.music')):
                route = 'pygame' if kind != 'wave' else 'simpleaudio'
            elif func.attr == 'write' and kind == 'stream':
                route = 'pyaudio'
        if route:
            found.append({'line': node.lineno, 'route': route})
    return sorted(found, key=lambda item: item['line'])


def audit(root, ignores=(), fail_on='HIGH'):
    root = Path(root)
    if not root.is_dir() or not root.stat().st_mode & 0o444 or not root.stat().st_mode & 0o111:
        raise ValueError('root must be a readable directory')
    positive = negative = False
    prod, tests = [], []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        parts = relative.parts
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root) or not path.is_file():
            continue
        if any(fnmatch.fnmatch(relative.as_posix(), glob) for glob in ignores):
            continue
        is_doc = relative.as_posix() == 'README.md' or path.suffix.lower() == '.md' and 'docs' in parts[:-1]
        if not is_doc and path.suffix != '.py':
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        if is_doc:
            yes, no = claims(text)
            positive |= yes
            negative |= no
        else:
            test = 'tests' in parts[:-1] or path.name.startswith('test_') or path.name.endswith('_test.py')
            excluded = any(p in ('fixtures', 'docs', 'examples') for p in parts[:-1])
            if excluded:
                continue
            for hit in evidence(text):
                (tests if test else prod).append(dict(hit, path=relative.as_posix()))
    findings = []
    if positive and not prod:
        findings.append({'rule': 'documented-speaker-claim-false', 'severity': 'MEDIUM' if tests else 'HIGH', 'message': 'Local-emission promise lacks production evidence.'})
    if negative and prod:
        findings.append({'rule': 'documented-no-speaker-claim-false', 'severity': 'HIGH', 'message': 'Local-emission denial conflicts with production evidence.'})
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return {'verdict': 'FAIL' if failed else 'PASS', 'findings': findings, 'evidence': prod, 'test_evidence': tests, 'claims': {'positive': positive, 'negative': negative}}
