import gzip,hashlib,json,tempfile,unittest
from pathlib import Path
from portable import archive

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'portable/packed').mkdir(parents=True)
        self.raw=b'exact CRLF bytes\r\n'*100
        packed=gzip.compress(self.raw,mtime=0);(self.root/'portable/packed/test.gz').write_bytes(packed)
        self.item={'target':'output/old.csv','archive':'portable/packed/test.gz','sha256':hashlib.sha256(self.raw).hexdigest(),'archive_sha256':hashlib.sha256(packed).hexdigest(),'bytes':len(self.raw)}
    def manifest(self,item=None):
        (self.root/'portable/packed-manifest.json').write_text(json.dumps({'schema':1,'files':[item or self.item]}))
    def test_restores_exact_bytes_and_is_idempotent(self):
        self.manifest();archive.restore(self.root);self.assertEqual((self.root/'output/old.csv').read_bytes(),self.raw)
        self.assertEqual(archive.restore(self.root)['already_present'],1)
    def test_never_overwrites_changed_existing_file(self):
        self.manifest();(self.root/'output').mkdir();(self.root/'output/old.csv').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'existing'):archive.restore(self.root)
        self.assertEqual((self.root/'output/old.csv').read_bytes(),b'changed')
    def test_corrupt_archive_rejects_without_creating_target(self):
        self.manifest();(self.root/'portable/packed/test.gz').write_bytes(b'bad')
        with self.assertRaises(ValueError):archive.restore(self.root)
        self.assertFalse((self.root/'output/old.csv').exists())
    def test_escape_and_absolute_paths_reject(self):
        for path in ['../escape','C:/outside','/outside','output/../../outside']:
            item=dict(self.item,target=path);self.manifest(item)
            with self.assertRaises(ValueError):archive.restore(self.root)
    def test_uncompressed_hash_mismatch_rejects(self):
        self.manifest(dict(self.item,sha256='0'*64))
        with self.assertRaises(ValueError):archive.restore(self.root)
        self.assertFalse((self.root/'output/old.csv').exists())
if __name__=='__main__':unittest.main()
