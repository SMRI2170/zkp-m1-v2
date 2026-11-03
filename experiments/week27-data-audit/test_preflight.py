import io
import hashlib
import unittest
from preflight import probe, get_json, MAX_METADATA

class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data); self.status = status; self.headers = headers or {}

class PreflightTests(unittest.TestCase):
    def test_ignored_range_never_reads_large_response(self):
        class NoRead(Response):
            def read(self, *args): raise AssertionError('Must not consume full archive')
        result = probe('https://example.invalid/data', 8_000_000_000,
                       opener=lambda *a, **kw: NoRead(b''))
        self.assertEqual(result['reason'], 'range_not_honored')
        self.assertEqual(result['bytes_read'], 0)

    def test_wrong_range_is_rejected(self):
        result = probe('https://example.invalid/data', 50000,
                       opener=lambda *a, **kw: Response(b'x'*1024, 206, {'Content-Range':'bytes 1024-2047/50000'}))
        self.assertEqual(result['reason'], 'range_not_honored')

    def test_prefix_does_not_pass_data_gate(self):
        body=b'PK'+b'x'*1022
        result=probe('https://example.invalid/data',50000,
                     opener=lambda *a, **kw:Response(body,206,{'Content-Range':'bytes 0-1023/50000'}))
        self.assertFalse(result['verified'])
        self.assertTrue(result['zip_prefix'])

    def test_small_file_requires_exact_hash(self):
        good=hashlib.sha256(b'readme').hexdigest()
        self.assertTrue(probe('https://example.invalid/readme',6,good,
                            opener=lambda *a, **kw:Response(b'readme'))['verified'])
        self.assertFalse(probe('https://example.invalid/readme',6,good,
                             opener=lambda *a, **kw:Response(b'broken'))['verified'])

    def test_metadata_bound(self):
        with self.assertRaises(ValueError):
            get_json('/api/v2/test',opener=lambda *a, **kw:Response(b' '* (MAX_METADATA+1)))

if __name__ == '__main__': unittest.main()
