import hashlib,json,tempfile,unittest
from pathlib import Path
import numpy as np,pandas as pd
from portable import sources

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_farm_same_transform_as_frozen_seven_product_loader(self):
        from data.struct_inputs import load_agri_price_mm
        path=Path('data/cz_agri_prices_raw.csv')
        expected=load_agri_price_mm();actual=sources.farm_series(path.read_bytes())
        pd.testing.assert_series_equal(actual,expected)
    def test_duplicate_farm_observation_rejected(self):
        from data.struct_inputs import AGRI_BASKET
        raw=pd.DataFrame({'CASMKMQR':['2026-01','2026-01'],'UZ02HU.KRAJ':[None,None],'Reprezentant':[AGRI_BASKET[0]]*2,'Hodnota':[1.,2.]})
        with self.assertRaisesRegex(ValueError,'duplicate'):sources.farm_series(raw.to_csv(index=False).encode())
    def test_farm_nonpositive_rejected(self):
        from data.struct_inputs import AGRI_BASKET
        raw=pd.DataFrame({'CASMKMQR':['2026-01'],'UZ02HU.KRAJ':[None],'Reprezentant':[AGRI_BASKET[0]],'Hodnota':[0.]})
        with self.assertRaisesRegex(ValueError,'positive'):sources.farm_series(raw.to_csv(index=False).encode())
    def test_farm_source_hash_and_clock_required(self):
        p=self.root/'farm.csv';p.write_bytes(b'x');meta={'sha256':hashlib.sha256(b'x').hexdigest(),'source':'https://data.csu.gov.cz/test','retrieved_at':'2026-09-22T18:00:00Z','completed_at':'2026-09-22T19:00:00Z'}
        Path(str(p)+'.metadata.json').write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError,'available'):sources.load_farm(p,'2026-09-22T18:30:00Z')
        p.write_bytes(b'y')
        with self.assertRaisesRegex(ValueError,'hash'):sources.load_farm(p,'2026-09-22T20:00:00Z')
    def test_capture_path_cannot_overwrite_an_existing_directory(self):
        with self.assertRaises(FileExistsError):sources.capture_farm(self.root)
if __name__=='__main__':unittest.main()
