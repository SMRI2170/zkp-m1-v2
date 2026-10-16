"""Issue #58: public protocol metadata, never private assignments or proof bodies."""
from collections import Counter
import math
import statistics

VERSION = 'distance-u16-balanced-v1'
CASES = 7
REPEATS = 3
WARMUPS = 7
EXPECTED = 21

def schedule():
    return [dict(sample_id=i, case_id=i % CASES, warmup=i < WARMUPS,
                 repetition=None if i < WARMUPS else (i-WARMUPS)//CASES)
            for i in range(WARMUPS + EXPECTED)]

def stats(values):
    values = list(values)
    return {'n': len(values), 'mean': statistics.mean(values) if values else None,
            'median': statistics.median(values) if values else None,
            'sd': statistics.stdev(values) if len(values)>1 else None,
            'min': min(values) if values else None, 'max': max(values) if values else None}

def validate_samples(rows, require_complete=False):
    """A prefix may be partial; duplicates, gaps or false success are invalid evidence."""
    expected = schedule()
    if len(rows)>len(expected): raise ValueError('too many samples')
    for actual, spec in zip(rows, expected):
        if any(type(actual.get(k)) is not type(v) or actual[k] != v for k,v in spec.items()):
            raise ValueError('sample ordering / warmup / repetition mismatch')
        if actual.get('verified') is not True: raise ValueError('unverified sample')
        for key in ('prove_ms','verify_ms'):
            v=actual.get(key)
            if type(v) not in (int,float) or not math.isfinite(v) or v<0:
                raise ValueError('missing or invalid phase duration: '+key)
        for key in ('witness_ms','proof_bytes'):
            if key in actual and (type(actual[key]) not in (int,float) or not math.isfinite(actual[key]) or actual[key]<0):
                raise ValueError('invalid metric: '+key)
    measured=[r for r in rows if not r['warmup']]
    balanced = Counter(r['case_id'] for r in measured)==Counter({i:REPEATS for i in range(CASES)})
    complete = len(rows)==len(expected) and balanced
    if require_complete and not complete: raise ValueError('incomplete 7 warmup + 21 measured protocol')
    return complete
