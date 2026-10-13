"""Integer oracle for SYNTHETIC u16 coordinates, never a field capture."""
from math import isqrt

CASES = [(0,0,0,0), (0,0,3,4), (3,4,0,0), (0,0,1,1),
         (0,0,65535,65535), (65535,0,0,65535), (100,100,101,100)]

def distance(a):
    if len(a) != 4 or any(type(v) is not int or not 0 <= v < 65536 for v in a):
        raise ValueError('four u16 coordinates required')
    d2 = (a[0]-a[2])**2 + (a[1]-a[3])**2
    return d2, isqrt(d2)

if __name__ == '__main__':
    import json
    print(json.dumps([{'case_id': i, 'synthetic_coordinates': a, 'd2': distance(a)[0],
                       'r': distance(a)[1]} for i,a in enumerate(CASES)], indent=2))
