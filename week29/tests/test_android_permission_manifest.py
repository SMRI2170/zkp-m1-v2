import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from summarize_android_permissions import device_specs

class DeviceManifestTests(unittest.TestCase):
    def test_two_os_generations_remain_separate_and_input_is_not_modified(self):
        spec={'devices':[dict(node='Device-1',model='Pixel 6 Pro',sdk=31,android_release='12'),dict(node='Device-2',model='Pixel 8',sdk=37,android_release='17')]}
        self.assertEqual([x['sdk'] for x in device_specs(spec)],[31,37]);self.assertNotIn('serial',spec['devices'][0])
    def test_private_fields_and_path_escape_are_rejected(self):
        base=dict(node='Device-1',model='fixture',sdk=31,android_release='12')
        for changed in ({**base,'serial':'PRIVATE'},{**base,'node':'../outside'}):
            with self.assertRaises(ValueError):device_specs({'devices':[changed]})
    def test_empty_and_duplicate_manifests_are_rejected(self):
        with self.assertRaises(ValueError):device_specs({'devices':[]})
        a=dict(node='Device-1',model='fixture',sdk=31,android_release='12')
        with self.assertRaises(ValueError):device_specs({'devices':[a,a]})

if __name__=='__main__':unittest.main()
