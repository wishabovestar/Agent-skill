#!/usr/bin/env python3
"""local_patch_guard.py -- verify that this machine's LOCAL (non-upstream) patches are still applied.

WHY THIS EXISTS
    `hermes update` autostashes local edits, updates, then tries to pop them back. When the pop
    conflicts, the working tree ends up CLEAN and the edits stay in a stash -- with no warning
    anywhere. Measured 2026-10-10: four local fixes silently went inactive and nobody noticed
    for days. This guard makes that loud instead of silent.

WHAT IT DOES NOT DO
    It does not auto-apply. Measured 2026-10-14: after upstream drift, 3 of the 4 stored patches
    no longer `git apply` cleanly. Blind re-application would write broken files. When a marker is
    missing the guard tells you the file, the marker, and the patch hint, and exits non-zero.

USAGE
    python local_patch_guard.py              # human report, exit 1 if anything is missing
    python local_patch_guard.py --json       # machine-readable
    python local_patch_guard.py --quiet      # only output when something is wrong (cron-friendly)

INTENDED WIRING
    Run it right after every update:
        hermes update --yes && python D:/hermes/analysis/local_patch_guard.py
    and/or as a daily cron so a regression is caught within a day.
"""
import json
import os
import sys

MANIFEST = r'D:/hermes/local-patches/manifest.json'


def load_manifest(path=MANIFEST):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def check(manifest):
    repo = manifest['repo']
    results = []
    for p in manifest['patches']:
        full = os.path.join(repo, p['file'])
        if not os.path.exists(full):
            results.append(dict(p, status='FILE-MISSING', detail='file not present'))
            continue
        try:
            txt = open(full, encoding='utf-8', errors='replace').read()
        except Exception as e:
            results.append(dict(p, status='UNREADABLE', detail=str(e)[:120]))
            continue
        marker = p.get('marker', '')
        absent = p.get('absent_marker', '')
        present = marker in txt
        # if the "absent" marker is still there, the patch is definitely gone
        still_absent = bool(absent) and absent in txt
        status = 'OK' if present else ('MISSING' if still_absent else 'MISSING?')
        results.append(dict(p, status=status))
    return repo, results


def main():
    args = set(sys.argv[1:])
    quiet = '--quiet' in args
    as_json = '--json' in args

    try:
        man = load_manifest()
    except Exception as e:
        print('local_patch_guard: cannot read manifest %s: %s' % (MANIFEST, e), file=sys.stderr)
        return 2

    repo, results = check(man)
    missing = [r for r in results if r['status'] != 'OK']

    if as_json:
        print(json.dumps({'repo': repo, 'total': len(results),
                          'missing': len(missing), 'results': results}, ensure_ascii=False, indent=1))
        return 1 if missing else 0

    if quiet and not missing:
        return 0

    print('local_patch_guard -- local (non-upstream) patch verification')
    print('  repo    : %s' % repo)
    print('  manifest: %s' % MANIFEST)
    print('  %d patch(es) declared, %d missing' % (len(results), len(missing)))
    print()
    for r in results:
        flag = {'OK': 'OK  ', 'MISSING': 'MISS', 'MISSING?': '??  ',
                'FILE-MISSING': 'NONE', 'UNREADABLE': 'ERR '}[r['status']]
        print('  [%s] %-28s %s' % (flag, r['id'], r['file']))
    if missing:
        print()
        print('  !! ACTION NEEDED -- these local patches are NOT active:')
        for r in missing:
            print('     - %s  (%s)' % (r['id'], r['what']))
            print('       file   : %s' % r['file'])
            print('       marker : %s' % r.get('marker', '')[:90])
            print('       hint   : %s' % r.get('how', '')[:150])
            print('       patch  : %s' % r.get('patch_file', '(none)'))
            print('       why    : %s' % r.get('why_it_matters', '')[:150])
        print()
        print('  A `hermes update` most likely autostashed and failed to pop these.')
        print('  They do NOT re-apply cleanly after upstream drift -- port by hand using the hint.')
        print('  Stashes can still be listed with:  git -C "%s" stash list' % repo)
    else:
        print()
        print('  all declared local patches are present.')
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
