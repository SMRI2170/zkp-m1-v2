import io,tempfile,unittest
from pathlib import Path
from loraiq_iq_metadata import RangeArchive,private_write,metadata_fields

class Response(io.BytesIO):
    def __init__(self,body,status,content_range):
        super().__init__(body);self.status=status;self.headers={'Content-Range':content_range}

class IQMetadataTests(unittest.TestCase):
    def test_metadata_comment_values_not_exported(self):
        paths,keys=metadata_fields({'global':{'core:datatype':'cf32_le'},'annotations':[{'core:comment':'latitude\tPRIVATE\nsnr\t12'}]})
        self.assertEqual(keys,['latitude','snr']);self.assertNotIn('PRIVATE',str((paths,keys)))

    def test_exact_range_seek_and_reuse(self):
        body=b'abcdef';calls=[]
        def opener(request,timeout):
            calls.append(request.get_header('Range'));return Response(body,206,'bytes 0-5/6')
        with tempfile.TemporaryDirectory() as d:
            archive=RangeArchive(Path(d),opener,size=6)
            self.assertEqual(archive.read(2),b'ab');archive.seek(-2,2)
            self.assertEqual(archive.read(2),b'ef');self.assertEqual(len(calls),1)
            self.assertEqual((Path(d)/'range-0-5.bin').stat().st_mode&0o077,0)
    def test_ignored_range_or_wrong_identity_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for status,header in [(200,'bytes 0-5/6'),(206,'bytes 0-5/7')]:
                archive=RangeArchive(Path(d),lambda *a,**k:Response(b'abcdef',status,header),size=6)
                with self.assertRaises(ValueError):archive.read(2)
            self.assertEqual(list(Path(d).iterdir()),[])
    def test_truncated_range_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            archive=RangeArchive(Path(d),lambda *a,**k:Response(b'ab',206,'bytes 0-5/6'),size=6)
            with self.assertRaises(ValueError):archive.read(2)
    def test_private_write_preserves_existing_different_data(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture';private_write(p,b'old')
            with self.assertRaises(ValueError):private_write(p,b'new')
            self.assertEqual(p.read_bytes(),b'old')

if __name__=='__main__':unittest.main()
