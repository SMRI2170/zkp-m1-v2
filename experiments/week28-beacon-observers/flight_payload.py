"""ODID v2 study marker. Not aircraft authentication or a compliant RID replacement."""
import math
import re
import struct


def rounded(value):return int(math.copysign(math.floor(abs(value)+.5),value))


def altitude(value):
    # opendroneid-core-c INV_ALT=-1000 -> raw 0. Legacy code's FFFF is not used.
    if value is None or not math.isfinite(value) or not -1000<value<=31767.5:return 0
    return rounded((value+1000)*2)


def build_ie(uas_id,counter,sensor,now):
    if not re.fullmatch(r'PI-RID-[A-Z0-9_-]{1,13}',uas_id) or len(uas_id)>20:raise ValueError('research session ID required')
    basic=bytes([0x02,0x40])+uas_id.encode().ljust(20,b'\0')+bytes(3)
    messages=[basic];reason='GPS_UNAVAILABLE';included=False
    if sensor is not None and 0<=now-sensor.get('host_monotonic_s',-1)<=2:
        gps=sensor.get('gps',{})
        if gps.get('valid') and 0<=now-gps.get('received_monotonic_s',-1)<=2:
            lat=gps.get('latitude');lon=gps.get('longitude')
            if lat is None or lon is None or not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
                raise ValueError('invalid GPS position')
            b=sensor.get('bme280',{});baro=None
            if b.get('valid') and 0<=now-b.get('measurement_monotonic_s',-1)<=2:baro=b.get('pressure_altitude_isa_m')
            seconds=gps.get('seconds_within_hour');stamp=0xffff if seconds is None else rounded(seconds*10)
            if stamp!=0xffff and not 0<=stamp<36000:raise ValueError('invalid GPS time')
            # Undeclared flight status, unknown direction/speeds/height/accuracies.
            location=struct.pack('<BBBBbiiHHHBBHBB',0x12,3,181,255,126,rounded(lat*1e7),rounded(lon*1e7),
                altitude(baro),altitude(gps.get('altitude_ellipsoid_m')),0,0,0,stamp,0,0)
            messages.append(location);included=True;reason=None
        else:reason=gps.get('reason') or 'STALE_GPS'
    elif sensor is not None:reason='STALE_SENSOR_SNAPSHOT'
    body=bytes.fromhex('fa0bbc0d')+bytes([counter&255,0xf2,25,len(messages)])+b''.join(messages)
    return bytes([221,len(body)])+body,dict(location_included=included,location_missing_reason=reason,
        gps_altitude_reference='WGS84_ellipsoid_if_geoid_available',baro_altitude_reference='ISA_1013.25_hPa',
        identity_verified=False)
