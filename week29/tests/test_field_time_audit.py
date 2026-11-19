import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_field_time import (Audit,clock_partitions,circular_difference,describe,epoch,
                              observation_key,packet_shape,read_jsonl,unwrap_next)


class FieldTimeTests(unittest.TestCase):
    def test_large_even_sample_median_and_mad(self):
        result=describe(list(range(10000)))
        self.assertEqual(result['median'],4999.5)
        self.assertEqual(result['mad'],2500)

    def test_year_offset_timezone_and_unknown_clock(self):
        self.assertEqual(epoch('2026-11-16T14:00:00+09:00'),epoch('2026-11-16T05:00:00Z'))
        self.assertGreater(epoch('2026-01-01T00:00:00Z')-epoch('2021-01-01T00:00:00Z'),1e8)
        self.assertIsNone(epoch('2026-01-01T00:00:00'))
        self.assertIsNone(epoch('invalid'))

    def test_hour_wrap_is_not_calendar_recovery(self):
        self.assertEqual(unwrap_next(3599,1,2),3601)
        self.assertEqual(unwrap_next(3599,1,3602),7201)
        self.assertEqual(circular_difference(3602,3599),3)

    def test_clock_jump_and_minute_bucket_boundary(self):
        def row(key,offset):return dict(key=key,node='fixture',boot='',utc=offset+100,mono=100)
        groups=clock_partitions([row('a',59.9),row('b',60.1),row('c',100)])
        self.assertEqual([len(x[3]) for x in groups],[2,1])

    def test_content_repetition_is_not_observation_duplication(self):
        row=dict(received_at_utc='2026-01-01T00:00:00Z',monotonic_time_us=1,
                 odid_payload_hex='f000',bssid='synthetic')
        self.assertNotEqual(observation_key('A',row,'x'),observation_key('B',row,'x'))
        later=dict(row,received_at_utc='2026-01-01T00:00:01Z',monotonic_time_us=1000001)
        self.assertNotEqual(observation_key('A',row,'x'),observation_key('A',later,'x'))
        self.assertEqual(observation_key('A',row,'DB'),observation_key('A',row,'JSONL'))
        missing=dict(row,monotonic_time_us=None)
        self.assertNotEqual(observation_key('A',missing,'x'),observation_key('A',missing,'y'))

    def test_packet_shape_and_unsupported_version(self):
        raw=bytes([0xf0,25,1])+bytes(25)
        self.assertTrue(packet_shape(raw.hex()))
        self.assertFalse(packet_shape(raw[:-1].hex()))
        self.assertFalse(packet_shape((bytes([0xf3])+raw[1:]).hex()))
        self.assertFalse(packet_shape('garbage'))

    def test_malformed_tail_and_nonobject(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'fixture.jsonl';p.write_text('{}\n[]\n{"cut":')
            rows=list(read_jsonl(p))
            self.assertIsNone(rows[0][2]);self.assertIsNotNone(rows[1][2])
            self.assertTrue(rows[2][2]['final_line_without_newline'])

    def test_snapshot_db_and_jsonl_dedup_preserves_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap=root/'snapshot';out=root/'out';private=root/'private'
            out.mkdir();private.mkdir()
            row=dict(received_at_utc='2026-11-16T05:00:00Z',monotonic_time_us=100,
                     bssid='synthetic',odid_payload_hex='',rid_parse_status='invalid')
            files=[]
            for release in ['old','current']:
                p=snap/'releases'/release/'captures/observations.jsonl';p.parent.mkdir(parents=True)
                p.write_text(json.dumps(row)+'\n');p.chmod(0o600);files.append(p)
            dbpath=snap/'files/observations.sqlite';dbpath.parent.mkdir(parents=True)
            db=sqlite3.connect(dbpath);db.execute('CREATE TABLE observations(id INTEGER,raw_json TEXT)')
            db.execute('INSERT INTO observations VALUES(?,?)',(1,json.dumps(dict(row,boot_scope='synthetic-boot'))))
            db.commit();db.close();dbpath.chmod(0o600);files.append(dbpath)
            manifest={str(p.relative_to(snap)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
            mp=root/'manifest.json';mp.write_text(json.dumps(manifest))
            config={'field_utc':['2026-11-16T05:00:00Z','2026-11-16T09:00:00Z']}
            audit=Audit(config,private,out)
            audit.source(dict(node='fixture',kind='android',snapshot=str(snap),manifest=str(mp),database=str(dbpath)))
            row_out=audit.db.execute('SELECT copies,boot FROM observations').fetchone()
            self.assertEqual(row_out,(2,'synthetic-boot'))
            # Synthetic decoded fixture exercises nonempty clock-group CSV output.
            payload=(bytes([0xf0,25,1])+bytes(25)).hex()
            audit.db.execute('INSERT INTO payloads VALUES (?,?,?)',
                (payload,json.dumps({'claimed_seconds_within_hour':1}),'confirmed_drone'))
            audit.db.execute('UPDATE observations SET payload=?',(payload,))
            audit.analysis()
            result=json.loads((out/'summary.json').read_text())
            self.assertEqual(result['nodes']['fixture']['canonical_observations'],1)
            self.assertEqual(len((out/'clock-groups.csv').read_text().splitlines()),2)
            for p in files:self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),manifest[str(p.relative_to(snap))])


if __name__=='__main__':unittest.main()
