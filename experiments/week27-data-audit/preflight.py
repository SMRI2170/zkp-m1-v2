"""Bounded, read-only audit of AADM's advertised public metadata/downloads.

Does not bypass download restrictions or treat metadata as measured data.
"""
import argparse
import datetime
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

BASE = 'https://datadryad.org'
DATASET = '/api/v2/datasets/doi%3A10.5061%2Fdryad.7d7wm3898'
MAX_METADATA = 256 * 1024


def get_json(path, opener=urllib.request.urlopen):
    if not path.startswith('/api/v2/') or '..' in path:
        raise ValueError('Unexpected API path')
    with opener(BASE + path, timeout=20) as response:
        data = response.read(MAX_METADATA + 1)
    if len(data) > MAX_METADATA:
        raise ValueError('Metadata exceeds limit')
    return json.loads(data)


def probe(url, size, expected_sha256=None, opener=urllib.request.urlopen):
    """Read a whole small README, or exactly the first 1KiB of a large file."""
    large = size > 32768
    req = urllib.request.Request(url, headers={'Range': 'bytes=0-1023'} if large else {})
    try:
        with opener(req, timeout=20) as response:
            status = response.status
            # Never consume a multi-GB response if the server ignores Range.
            if large and (status != 206 or response.headers.get('Content-Range') != f'bytes 0-1023/{size}'):
                return {'status': status, 'verified': False, 'reason': 'range_not_honored', 'bytes_read': 0}
            if not large and status != 200:
                return {'status': status, 'verified': False, 'reason': 'unexpected_status', 'bytes_read': 0}
            limit = 1024 if large else size
            body = response.read(limit + 1)
            if len(body) != limit:
                return {'status': status, 'verified': False, 'reason': 'unexpected_length', 'bytes_read': len(body)}
            if large:
                return {'status': status, 'verified': False, 'reason': 'prefix_only_not_dataset_audit',
                        'bytes_read': len(body), 'zip_prefix': body.startswith(b'PK')}
            digest = hashlib.sha256(body).hexdigest()
            return {'status': status, 'verified': digest == expected_sha256,
                    'reason': 'small_file_hash_check', 'bytes_read': len(body), 'sha256': digest}
    except urllib.error.HTTPError as error:
        return {'status': error.code, 'verified': False, 'reason': 'http_error', 'bytes_read': 0}
    except (OSError, ValueError) as error:
        return {'status': None, 'verified': False, 'reason': type(error).__name__, 'bytes_read': 0}


def run():
    dataset = get_json(DATASET)
    version_path = dataset['_links']['stash:version']['href']
    version = get_json(version_path)
    listing = get_json(version['_links']['stash:files']['href'])
    if listing.get('total') != len(listing['_embedded']['stash:files']):
        raise ValueError('Incomplete file listing; inspect pagination first')
    files = []
    for item in listing['_embedded']['stash:files']:
        advertised = BASE + item['_links']['stash:download']['href']
        file_id = item['_links']['self']['href'].rsplit('/', 1)[1]
        files.append({
            'name': item['path'], 'size_bytes': item['size'],
            'published_digest_type': item.get('digestType'), 'published_digest': item.get('digest'),
            'api_download': probe(advertised, item['size'], item.get('digest')),
            'web_download': probe(BASE + '/downloads/file_stream/' + file_id, item['size'], item.get('digest')),
        })
    return {
        'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'doi': dataset['identifier'], 'license': dataset.get('license'),
        'version_path': version_path, 'version_number': dataset.get('versionNumber'),
        'version_status': dataset.get('versionStatus'), 'curation_status': dataset.get('curationStatus'),
        'metadata_access': 'available', 'files': files,
        'data_gate': ('BLOCKED_ACCESS' if any(f['name'].endswith('.zip') and f['api_download']['status'] in (401, 403) and f['web_download']['status'] in (401, 403) for f in files) else 'NOT_AUDITED'),
        'residual_analysis': 'NOT_RUN',
        'reason': 'Metadata and at most a 1KiB ZIP prefix do not establish measured-data quality.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'data_gate': report['data_gate'], 'residual_analysis': report['residual_analysis'],
                      'files': [{'name': f['name'], 'api': f['api_download']['status'],
                                 'web': f['web_download']['status']} for f in report['files']]}, indent=2))
