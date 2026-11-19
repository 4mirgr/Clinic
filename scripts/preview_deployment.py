"""Prepare a reviewed, pinned read-only Worker upload; never deploys or enables billing."""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(revision):
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('A full reviewed Git commit is required')
    def read(path):
        return subprocess.check_output(['git','show',revision+':'+path],cwd=ROOT,text=True)
    manifest=json.loads(read('deploy/preview/public/manifest.json'))
    for route,asset in manifest.items():
        if not route.startswith('/clinic/') or '..' in asset['path'].split('/') or not asset['path'].startswith(('deploy/preview/public/','static/clinic/','docs/previews/education-demo.pdf','deploy/preview/preview.')):
            raise ValueError('Unreviewed public preview path')
    main="import {createPreviewWorker} from './worker.mjs';\nimport {withAccountEntry} from './account-entry.mjs';\nconst manifest="+json.dumps(manifest,separators=(',',':'))+";\nexport default withAccountEntry(createPreviewWorker(manifest,'"+revision+"'),manifest);\n"
    return {'revision':revision,'modules':{'preview.mjs':main,'worker.mjs':read('deploy/preview/worker.mjs'),'account-entry.mjs':read('deploy/preview/account-entry.mjs')}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh output file')
    args.output.write_text(json.dumps(prepare(args.revision),ensure_ascii=False))
    print('Prepared a pinned shared-identity gate around the read-only synthetic preview; nothing deployed.')
