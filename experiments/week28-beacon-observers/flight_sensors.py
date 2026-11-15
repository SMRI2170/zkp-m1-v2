#!/usr/bin/env python3
"""GPS/BME280 research telemetry; missing/stale samples never become fake positions."""
import argparse
from datetime import datetime,timezone
import glob
import json
import math
import os
from pathlib import Path
import signal
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]


def finite(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (TypeError,ValueError):return None


def nmea_fields(line):
    text=line.strip()
    if not text.startswith('$') or '*' not in text:raise ValueError('NMEA checksum required')
    body,check=text[1:].rsplit('*',1);checksum=0
    for b in body.encode('ascii'):checksum^=b
    if len(check)!=2 or checksum!=int(check,16):raise ValueError('NMEA checksum mismatch')
    return body.split(',')


def degrees(text,hemi,latitude):
    number=finite(text)
    if number is None or number<0 or hemi not in ('NS' if latitude else 'EW'):raise ValueError('invalid coordinate')
    deg=int(number//100);minutes=number-deg*100
    value=deg+minutes/60
    if not 0<=minutes<60 or value>(90 if latitude else 180):raise ValueError('coordinate range')
    return -value if hemi in 'SW' else value


def parse_gga(line):
    f=nmea_fields(line)
    if len(f)<15 or len(f[0])!=5 or f[0][2:]!='GGA':raise ValueError('not GGA')
    quality=int(f[6] or 0)
    if quality==0:return dict(valid=False,reason='NO_FIX',fix_quality=0)
    if not 1<=quality<=8:return dict(valid=False,reason='UNSUPPORTED_FIX_QUALITY',fix_quality=quality)
    lat=degrees(f[2],f[3],True);lon=degrees(f[4],f[5],False)
    msl=finite(f[9]) if f[10]=='M' else None
    geoid=finite(f[11]) if f[12]=='M' else None
    utc=f[1];seconds=None
    if len(utc)>=6:
        hour=finite(utc[:2]);minute=finite(utc[2:4]);second=finite(utc[4:])
        if hour is not None and minute is not None and second is not None and 0<=hour<24 and 0<=minute<60 and 0<=second<60:
            seconds=minute*60+second
    return dict(valid=True,reason=None,latitude=lat,longitude=lon,fix_quality=quality,
                satellites=int(f[7] or 0),hdop=finite(f[8]),altitude_msl_m=msl,geoid_separation_m=geoid,
                altitude_ellipsoid_m=msl+geoid if msl is not None and geoid is not None else None,
                nmea_utc_time=utc,seconds_within_hour=seconds)


def pressure_height(pressure,reference):
    if pressure is None or reference is None or not 300<=pressure<=1100 or not 300<=reference<=1100:return None
    return 44330*(1-(pressure/reference)**(1/5.255))


def gps_snapshot(sample,now,max_age=2.0):
    if sample is None:return dict(valid=False,reason='GPS_UNAVAILABLE',age_s=None)
    age=now-sample['received_monotonic_s']
    if not 0<=age<=max_age:
        return dict(valid=False,reason='STALE_GPS',age_s=age,fix_quality=sample.get('fix_quality'))
    return dict(sample,age_s=age)


def atomic_json(path,data):
    path=Path(path);tmp=path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f,allow_nan=False);f.write('\n')
    tmp.replace(path)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gps-port');p.add_argument('--baud',type=int,default=9600)
    p.add_argument('--interval',type=float,default=.2);p.add_argument('--duration',type=float,default=0)
    a=p.parse_args()
    if not math.isfinite(a.interval) or not .1<=a.interval<=5 or a.duration<0:p.error('interval 0.1..5 seconds')
    a.output=Path(os.path.abspath(a.output))
    if not a.output.is_relative_to(ROOT/'captures'):raise ValueError('sensor output must be inside release captures')
    for parent in [a.output,*a.output.parents]:
        if parent==ROOT:break
        if parent.is_symlink():raise ValueError('sensor output symlink rejected')
    os.umask(0o077);a.output.mkdir(mode=0o700,parents=True,exist_ok=True)
    if a.output.is_symlink() or a.output.stat().st_mode&0o077:raise ValueError('private output required')
    stop=threading.Event();lock=threading.Lock();latest=None;gps_port=None;gps_error='GPS_PORT_MISSING'
    def request_stop(*_):stop.set()
    for s in [signal.SIGTERM,signal.SIGINT]:signal.signal(s,request_stop)
    def reader():
        nonlocal latest,gps_port,gps_error
        import serial
        while not stop.is_set():
            ports=[a.gps_port] if a.gps_port else sorted(glob.glob('/dev/ttyACM*')+glob.glob('/dev/ttyUSB*'))
            if not ports:gps_error='GPS_PORT_MISSING';stop.wait(1);continue
            try:
                with serial.Serial(ports[0],a.baud,timeout=.2,exclusive=True) as stream:
                    gps_port=ports[0];gps_error=None
                    while not stop.is_set():
                        raw=stream.readline(256)
                        if b'GGA,' not in raw:continue
                        try:record=parse_gga(raw.decode('ascii'))
                        except (ValueError,UnicodeError):gps_error='INVALID_NMEA';continue
                        gps_error=None
                        record['received_monotonic_s']=time.monotonic()
                        with lock:latest=record
            except Exception as exc:gps_error=type(exc).__name__;stop.wait(1)
    threading.Thread(target=reader,daemon=True).start()
    bus=params=bme=None;bme_error=None;reference=None
    try:
        import smbus2,bme280
        bus=smbus2.SMBus(1)
        if bus.read_byte_data(0x76,0xd0)!=0x60:raise ValueError('not BME280')
        params=bme280.load_calibration_params(bus,0x76);bme=bme280
    except Exception as exc:bme_error=type(exc).__name__
    sensor_session=uuid.uuid4().hex
    started=time.monotonic();sequence=0;file=None;next_tick=started;file_started=0;next_budget=started
    try:
        while not stop.is_set() and (a.duration==0 or time.monotonic()-started<a.duration):
            now=time.monotonic()
            # No auto-deletion. Leave room for SSH/OS and stop before filling the card.
            import shutil
            if now>=next_budget:
                files=[x for x in a.output.rglob('*') if x.is_file()]
                if len(files)>10000 or sum(x.stat().st_size for x in files)>192*1024**2 or shutil.disk_usage(a.output).free<512*1024**2:
                    raise RuntimeError('sensor capture budget/headroom reached')
                next_budget=now+10
            with lock:gps=gps_snapshot(latest,now)
            baro=dict(valid=False,reason=bme_error or 'READ_FAILED',pressure_hpa=None,temperature_c=None,humidity_percent=None)
            if bme is not None:
                try:
                    value=bme.sample(bus,0x76,params);pressure=finite(value.pressure)
                    if pressure is None or not 300<=pressure<=1100:raise ValueError('pressure range')
                    if reference is None:reference=pressure
                    baro=dict(valid=True,reason=None,pressure_hpa=pressure,temperature_c=finite(value.temperature),humidity_percent=finite(value.humidity),
                        pressure_altitude_isa_m=pressure_height(pressure,1013.25),relative_boot_height_m=pressure_height(pressure,reference),
                        reference_pressure_hpa=reference,reference_kind='first_valid_pressure_since_service_start_not_takeoff',measurement_monotonic_s=time.monotonic())
                except Exception as exc:baro['reason']=type(exc).__name__
            record=dict(schema='flight_sensor_v1',sensor_session=sensor_session,source_type='real_sensor_read',sequence=sequence,
                host_utc=datetime.now(timezone.utc).isoformat(),host_monotonic_s=time.monotonic(),
                gps=gps,gps_device_status=gps_error,gps_port=gps_port,bme280=baro,
                sensor_honesty_verified=False,physical_position_verified=False)
            if file is None or now-file_started>=60:
                if file:file.close()
                name='telemetry-'+uuid.uuid4().hex+'.jsonl';fd=os.open(a.output/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                file=os.fdopen(fd,'w',buffering=1);file_started=now
            file.write(json.dumps(record,allow_nan=False)+'\n');file.flush()
            atomic_json(a.output/'latest.json',record);sequence+=1
            next_tick+=a.interval;stop.wait(max(0,next_tick-time.monotonic()))
    finally:
        stop.set()
        if file:file.close()
        if bus:bus.close()


if __name__=='__main__':main()
