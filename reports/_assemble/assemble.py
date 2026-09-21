import base64
import gzip
import json
import pathlib


def restore(b64_path, dest):
    b64 = pathlib.Path(b64_path).read_text().strip()
    data = gzip.decompress(base64.b64decode(b64))
    obj = json.loads(data)
    pathlib.Path(dest).write_bytes(data)
    print(
        dest,
        'bytes',
        len(data),
        'roster',
        len(obj.get('roster') or []),
        'articles',
        len(obj.get('articles') or []),
        'social',
        len(obj.get('social_items') or []),
        'signals',
        len(obj.get('signals') or []),
        'assessments',
        len(obj.get('assessments') or []),
        'XI',
        len((obj.get('lineup') or {}).get('starting_xi') or []),
    )


def main():
    restore(
        'reports/_assemble/psv_compact.json.gz.b64',
        'reports/sample_psv_eindhoven_live.json',
    )
    restore(
        'reports/_assemble/barca_compact.json.gz.b64',
        'reports/sample_barcelona_demo.json',
    )


if __name__ == '__main__':
    main()
