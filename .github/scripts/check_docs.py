"""Offline checks for explicitly listed repository documents. Never reads credentials."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

LINK = re.compile(r'\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)(?:\s+["\'][^\n]*?["\'])?\)')
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def check(root, files, tracked):
    root=Path(root).resolve()
    problems=[]
    for name in files:
        path=root/name
        if not path.resolve().is_relative_to(root):
            problems.append(f'{name}: document escapes repository')
            continue
        if not path.is_file():
            problems.append(f'{name}: required document missing')
            continue
        text=path.read_text(encoding='utf-8-sig')
        if SECRET.search(text):
            problems.append(f'{name}: credential-shaped content requires private review')
        prose=re.sub(r'(?ms)^```[^\n]*\n.*?^```[^\n]*(?:\n|$)', '', text)
        for match in LINK.finditer(prose):
            target=match.group(1).strip('<>')
            parts=urlsplit(target)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            decoded=unquote(parts.path)
            resolved=(root/decoded.lstrip('/') if decoded.startswith('/') else path.parent/decoded).resolve()
            if not resolved.is_relative_to(root):
                problems.append(f'{name}: link escapes repository: {target}')
                continue
            relative=resolved.relative_to(root).as_posix()
            if relative not in tracked and not any(p.startswith(relative.rstrip('/')+'/') for p in tracked):
                problems.append(f'{name}: missing local link: {target}')
    return sorted(set(problems))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    args=parser.parse_args()
    config=json.loads((args.root/'repository-checks.json').read_text(encoding='utf-8'))
    raw=subprocess.check_output(['git','-C',str(args.root),'ls-files','--cached','--others','--exclude-standard','-z'],timeout=30)
    tracked={p.decode('utf-8') for p in raw.split(b'\0') if p}
    errors=check(args.root,config['documents'],tracked)
    for error in errors:
        print(error)
    print(f"Checked {len(config['documents'])} documents; {len(errors)} issue(s). External URLs and fragment anchors are not validated.")
    return 1 if errors else 0


if __name__=='__main__':
    raise SystemExit(main())
