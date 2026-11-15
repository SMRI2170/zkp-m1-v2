#!/usr/bin/env python3
"""Bounded experimental ODID Beacon AP, isolated from the managed interface.

Root is needed for the temporary AP. Never stops existing hostapd processes,
never changes the managed station channel, and never embeds credentials.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import time


def run(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=10, **kwargs)


def validate_ie(text, counter):
    data = bytes.fromhex(text.strip())
    if len(data) < 10 or data[0] != 221 or data[1] != len(data) - 2:
        raise ValueError('invalid Vendor IE length')
    if data[2:6] != bytes.fromhex('fa0bbc0d') or data[6] != counter:
        raise ValueError('ODID prefix/counter mismatch')
    pack = data[7:]
    if pack[0:2] != bytes([0xf2, 25]) or not 1 <= pack[2] <= 9 or len(pack) != 3 + 25 * pack[2]:
        raise ValueError('invalid protocol-v2 Message Pack')
    return data


def test_identity(ie, uas_id=None, mac=None, diagnostic_invalid=False):
    """Only visibly synthetic session IDs; no manufacturer identity cloning."""
    data=bytearray(ie)
    if uas_id is not None:
        if not re.fullmatch(r'(PI-RID-|TEST-DRONE-)[A-Z0-9_-]+',uas_id) or len(uas_id)>20:
            raise ValueError('use a 1..20-byte PI-RID-* or TEST-DRONE-* test marker')
        found=False
        for offset in range(10,len(data),25):  # IE header + OUI/type/counter + pack header
            if data[offset]>>4==0:
                data[offset+1]=(4<<4)|(data[offset+1]&15)  # Specific Session ID, not serial number
                data[offset+2:offset+22]=uas_id.encode('ascii').ljust(20,b'\0')
                if diagnostic_invalid:data[offset]=(data[offset]&0xf0)|3
                found=True
        if not found:raise ValueError('Basic ID fixture missing')
    elif diagnostic_invalid:
        raise ValueError('diagnostic invalid fixture requires an explicit test ID')
    if mac is not None:
        if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',mac):raise ValueError('invalid test BSSID')
        first=int(mac[:2],16)
        if first&1 or not first&2:raise ValueError('test BSSID must be locally administered unicast')
    return bytes(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--encoder', type=Path)
    p.add_argument('--id-only',action='store_true',help='study ID marker only; no Location or invented coordinates')
    p.add_argument('--station', default='wlan0')
    p.add_argument('--ap', default='ridtx0')
    p.add_argument('--run-id', required=True)
    p.add_argument('--counter', type=int, required=True)
    p.add_argument('--lat', type=float)
    p.add_argument('--lon', type=float)
    p.add_argument('--alt', type=float)
    p.add_argument('--duration', type=int, default=90)
    p.add_argument('--uas-id', help='synthetic PI-RID-* or TEST-DRONE-* session marker, maximum 20 ASCII bytes')
    p.add_argument('--tx-mac', help='distinct locally administered unicast BSSID for simultaneous lab sources')
    p.add_argument('--diagnostic-invalid', action='store_true', help='test-only unsupported message version to exercise raw fallback')
    p.add_argument('--beacon-only-compat', action='store_true',
                   help='legacy radio settings, with an empty accept-list denying all associations')
    args = p.parse_args()
    if os.getuid() != 0 or not re.fullmatch('[a-zA-Z0-9_-]{1,40}', args.run_id):
        p.error('root and a bounded opaque run ID required')
    if not 1 <= args.duration <= 120 or not 0 <= args.counter <= 255:
        p.error('duration 1..120 and counter 0..255 required')
    if args.id_only:
        if not args.uas_id:p.error('ID-only marker needs an explicit test ID')
    elif args.encoder is None or args.lat is None or args.lon is None or args.alt is None or not (-90 <= args.lat <= 90 and -180 <= args.lon <= 180 and -1000 <= args.alt <= 30000):
        p.error('Location fixture requires encoder and explicit bounded test coordinates')
    if args.ap == args.station or not re.fullmatch('[a-zA-Z0-9_-]{1,15}', args.ap):
        p.error('AP must be a separate safe interface name')
    if Path('/sys/class/net', args.ap).exists():
        p.error('AP interface already exists; inspect rather than reuse/delete it')
    if subprocess.run(['pgrep', '-x', 'hostapd'], stdout=subprocess.DEVNULL).returncode == 0:
        p.error('another hostapd is running; leave it untouched')
    info = run(['/usr/sbin/iw', 'dev', args.station, 'info']).stdout
    match = re.search(r'channel (\d+) \((\d+) MHz\)', info)
    if not match:
        p.error('station channel is not known')
    channel, frequency = map(int, match.groups())
    # Explicitly restrict this experiment to the existing 2.4GHz association.
    if not 1 <= channel <= 13 or not 2412 <= frequency <= 2472:
        p.error('this experiment needs an already-associated 2.4GHz station')
    if args.id_only:
        body=bytes.fromhex('fa0bbc0d')+bytes([args.counter,0xf2,25,1,2])+bytes(24)
        ie=validate_ie((bytes([221,len(body)])+body).hex(),args.counter)
    else:
        ie = validate_ie(run([str(args.encoder), str(args.counter), str(args.lat), str(args.lon), str(args.alt)]).stdout, args.counter)
    try:ie=test_identity(ie,args.uas_id,args.tx_mac,args.diagnostic_invalid)
    except ValueError as exc:p.error(str(exc))
    os.umask(0o077)
    directory = Path('/run') / ('zkp-beacon-' + args.run_id)
    directory.mkdir(mode=0o700)
    status = dict(run_id=args.run_id, status='PREPARING', counter=args.counter,
                  frequency_mhz=frequency, channel=channel, duration_s=args.duration,
                  vendor_content_sha256=hashlib.sha256(ie[2:]).hexdigest(),
                  source_type='controlled_real_rf_test', synthetic_claim=True,
                  test_uas_id=args.uas_id, diagnostic_invalid=args.diagnostic_invalid,id_only=args.id_only,
                  ap_policy='deny_all_associations' if args.beacon_only_compat else 'random_wpa2_key',
                  physical_packet_match='unconfirmed')
    (directory / 'receipt.json').write_text(json.dumps(status, indent=2))
    created = False
    child = None
    stop = False

    def request_stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        run(['/usr/sbin/iw', 'dev', args.station, 'interface', 'add', args.ap, 'type', '__ap'])
        created = True
        run(['nmcli', 'device', 'set', args.ap, 'managed', 'no'])
        # NM/supplicant may finish releasing a newly created interface after
        # nmcli returns. Reassert AP mode only on our own interface afterwards.
        time.sleep(2)
        run(['/usr/sbin/ip', 'link', 'set', args.ap, 'down'])
        run(['/usr/sbin/iw', 'dev', args.ap, 'set', 'type', '__ap'])
        mac = bytes.fromhex(args.tx_mac.replace(':','')) if args.tx_mac else (bytes.fromhex('021122334455') if args.beacon_only_compat else bytes([2]) + secrets.token_bytes(5))
        run(['/usr/sbin/ip', 'link', 'set', args.ap, 'address', ':'.join(f'{b:02x}' for b in mac)])
        run(['/usr/sbin/ip', 'link', 'set', args.ap, 'up'])
        access = ['wpa=2', 'wpa_key_mgmt=WPA-PSK', 'rsn_pairwise=CCMP',
                  f'wpa_passphrase={secrets.token_hex(16)}']
        if args.beacon_only_compat:
            # The legacy transmitter only needed Beacon broadcasts. No clients
            # are needed: an empty explicit accept-list denies every station.
            accept = directory / 'accept-macs'
            accept.write_text('')
            access = ['ieee80211n=1', 'wmm_enabled=1', 'ignore_broadcast_ssid=0',
                      'auth_algs=1', 'macaddr_acl=1', f'accept_mac_file={accept}']
        config = '\n'.join([
            f'interface={args.ap}', 'driver=nl80211', 'country_code=JP',
            f'ssid=ODID-RESEARCH-{args.run_id}', 'hw_mode=g', f'channel={channel}',
            'beacon_int=100', f'ctrl_interface={directory}/ctrl',
            *access, f'vendor_elements={ie.hex()}', ''])
        conf = directory / 'hostapd.conf'
        conf.write_text(config)
        with (directory / 'hostapd.log').open('w') as log:
            child = subprocess.Popen(['/usr/sbin/hostapd', str(conf)], stdout=log, stderr=subprocess.STDOUT)
            for _ in range(40):
                if child.poll() is not None:
                    raise RuntimeError('hostapd exited during AP startup')
                if 'AP-ENABLED' in (directory / 'hostapd.log').read_text():
                    break
                if stop:
                    raise RuntimeError('stopped before AP enabled')
                time.sleep(.25)
            else:
                raise RuntimeError('AP did not become enabled')
            actual = run(['/usr/sbin/iw', 'dev', args.ap, 'info']).stdout
            if not re.search(r'^\s*type AP\s*$', actual, re.M):
                raise RuntimeError('hostapd enabled but kernel interface is not AP')
            status['kernel_interface_type'] = 'AP'
            status.update(status='AP_ENABLED', enabled_at_utc=datetime.now(timezone.utc).isoformat())
            (directory / 'receipt.json').write_text(json.dumps(status, indent=2))
            deadline = time.monotonic() + args.duration
            while not stop and time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError('hostapd exited during test')
                time.sleep(.25)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        status.update(status='FAILED', error_type=type(exc).__name__, reason=str(exc))
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        cleanup = False
        if created:
            cleanup = subprocess.run(['/usr/sbin/iw', 'dev', args.ap, 'del'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0
        status['temporary_ap_removed'] = cleanup
        status['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        if status['status'] == 'AP_ENABLED':
            status['status'] = 'STOPPED_AFTER_BOUNDED_TEST'
        (directory / 'receipt.json').write_text(json.dumps(status, indent=2))
        print(json.dumps(status))
    return 0 if status['status'] == 'STOPPED_AFTER_BOUNDED_TEST' and status['temporary_ap_removed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
