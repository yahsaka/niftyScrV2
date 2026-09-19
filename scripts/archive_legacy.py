"""Preserve a legacy ledger in ignored local storage; never import it as verified.

This utility only manages working-tree files. It does not remove Git history.
"""
from pathlib import Path
import argparse
import hashlib
import shutil

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'data/paper_trades.json')
    parser.add_argument('--remove-working-copy',action='store_true')
    args=parser.parse_args()
    if not args.source.is_file():
        raise SystemExit('Source ledger was not found. Nothing was changed.')
    payload=args.source.read_bytes()
    sha=hashlib.sha256(payload).hexdigest()
    folder=ROOT/'.local/legacy-unvalidated'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'paper-trades-{sha[:12]}.json'
    if target.exists() and target.read_bytes()!=payload:
        raise SystemExit('Archive destination has different bytes. Refusing to overwrite it.')
    if not target.exists():
        shutil.copy2(args.source,target)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=sha:
        raise SystemExit('Archive verification failed. Original source was not removed.')
    (folder/f'{target.name}.sha256').write_text(f'{sha}  {target.name}\n')
    if args.remove_working_copy:
        if args.source.resolve()==target.resolve():
            raise SystemExit('Source is the archive itself. Nothing was removed.')
        args.source.unlink()
    print(f'Legacy/unvalidated copy verified: {target}\nSHA256: {sha}')
    print('Keep this directory private. No records were imported into the corrected account.')
    print('Deleting a working copy does not remove it from existing Git history.')


if __name__=='__main__':main()
