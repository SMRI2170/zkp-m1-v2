import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from monitor_a_storage import numeric,read_health,resources


class StorageMonitorTests(unittest.TestCase):
    def test_receiver_only_waiting_does_not_require_sensor_or_transmitter(self):
        def runner(argv,**kwargs):
            roles=argv[argv.index('--roles')+1:]
            return MagicMock(returncode=0,stdout=json.dumps(dict(phase='WAITING',roles={r:{'phase':'WAITING'} for r in roles})))
        result,code=read_health(Path('/synthetic-release'),['receiver'],runner=runner)
        self.assertEqual(result['phase'],'WAITING');self.assertEqual(code,0)
        self.assertEqual(set(result['roles']),{'receiver'})

    def test_missing_cgroup_memory_remains_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'captures').mkdir();mem=root/'meminfo';mem.write_text('MemAvailable: 1024 kB\nSwapFree: 0 kB\n')
            runner=MagicMock(return_value=MagicMock(returncode=0,stdout='ActiveState=active\nMemoryCurrent=[not set]\nCPUUsageNSec=100\nNRestarts=0\n'))
            result=resources(root,['receiver'],meminfo=mem,runner=runner)
            self.assertEqual(result['memory_available_bytes'],1024**2)
            self.assertIsNone(result['services']['receiver']['memory_bytes'])
            self.assertEqual(result['services']['receiver']['cpu_ns'],100)
            self.assertEqual(result['swap_free_bytes'],0)

    def test_failed_resource_query_is_unknown(self):
        runner=MagicMock(return_value=MagicMock(returncode=1,stdout=''))
        result=resources(Path('/synthetic-missing'),['receiver'],meminfo=Path('/synthetic-missing'),runner=runner)
        self.assertIsNone(result['memory_available_bytes']);self.assertIsNone(result['disk_free_bytes'])
        self.assertIsNone(result['services']['receiver']['cpu_ns'])
        self.assertIsNone(numeric('-1'));self.assertIsNone(numeric(None))


if __name__=='__main__':unittest.main()
