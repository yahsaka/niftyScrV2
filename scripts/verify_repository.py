"""Reject known personal/credential files in the publishing tree or Git index.

A focused guard, not a complete secret scanner. In Git, tracked files are checked
including already-tracked files that .gitignore alone cannot protect.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_EXACT={'.env','.streamlit/secrets.toml','data/paper_trades.json','data/backtest_history.json'}
IGNORED_DIRS={'.git','.venv','venv','__pycache__','.pytest_cache','node_modules','test-results'}


def candidates():
    if (ROOT/'.git').exists():
        try:
            tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
            return [ROOT/name for name in tracked if name]
        except (OSError,subprocess.CalledProcessError):
            raise SystemExit('Could not inspect the Git index. Safety check did not pass.')
    return [p for p in ROOT.rglob('*') if p.is_file() and not any(part in IGNORED_DIRS for part in p.relative_to(ROOT).parts)]


def main():
    errors=[]
    for path in candidates():
        rel=path.relative_to(ROOT).as_posix()
        name=path.name.lower()
        private=(rel in FORBIDDEN_EXACT or rel.startswith(('.local/','legacy-private/')) or
                 'private' in name and path.suffix.lower() in {'.json','.zip','.csv','.xlsx'} or
                 name.endswith(('.sqlite3','.db','.sqlite3-wal','.sqlite3-shm')) or
                 (rel.startswith('data/') and name.startswith(('holdings','portfolio'))) or
                 (name.startswith('.env.') and name != '.env.example') or
                 path.suffix.lower() in {'.ttf','.otf','.woff','.woff2'})
        if private:
            errors.append(f'Private/unexpected publishing file: {rel}')
        if path.suffix.lower() in {'.py','.toml','.yaml','.yml','.env'} and path.exists():
            source=path.read_text(errors='replace')
            patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{40,}']
            if any(re.search(pattern,source) for pattern in patterns):
                errors.append(f'Possible credential in {rel}; inspect before publishing.')
    if errors:
        print('\n'.join(errors));raise SystemExit(1)
    print('Repository publishing guard passed: no known personal data files, credentials or font binaries detected.')
    print('This does not inspect earlier Git history or replace a complete secret/privacy review.')

if __name__=='__main__':main()
