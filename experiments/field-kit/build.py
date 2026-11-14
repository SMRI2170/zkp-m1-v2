#!/usr/bin/env python3
"""Build a portable research kit from explicit code-only allowlists, never captures/keys."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
ROOT=Path(__file__).resolve().parents[2]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(paths,target):
    hashes={}
    with tarfile.open(target,'w:gz') as tar:
        for p in sorted(paths):
            if p.is_symlink() or not p.is_file():raise ValueError('non-regular source rejected')
            name=str(p.relative_to(ROOT));hashes[name]=digest(p);tar.add(p,arcname=name,recursive=False)
    return hashes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--build-android',action='store_true');a=p.parse_args()
    out=a.output.resolve()
    if out.exists():p.error('new output directory required; previous artifacts retained')
    out.mkdir(parents=True)
    mobile=ROOT/'experiments/kmp-rid-observer'
    if a.build_android:
        with (out/'android-build.log').open('w') as f:
            subprocess.run([str(mobile/'gradlew'),'-p',str(mobile),':shared:jvmTest',':shared:testAndroidHostTest',':androidApp:assembleDebug',':androidApp:assembleDebugAndroidTest',':androidApp:lintDebug','--no-daemon','--max-workers=1'],stdout=f,stderr=subprocess.STDOUT,check=True)
    names=['observer_capture.py','wifi_scan_capture.py','wifi_beacon_capture.py','source_labels.py','adaptive_scan.py','test_wifi_beacon_capture.py','test_wifi_scan_capture.py']
    pi=[ROOT/'uav'/n for n in names]+list((ROOT/'experiments/week28-beacon-observers').glob('*.py'))+[ROOT/'experiments/week28-beacon-observers/README.md',ROOT/'AGENTS.md']
    android=[f for f in mobile.rglob('*') if f.is_file() and
        ('src' in f.relative_to(mobile).parts and not any(x in f.relative_to(mobile).parts for x in ['build','.gradle','.kotlin']) and f.suffix in ['.kt','.xml'])]
    android += [mobile/n for n in ['gradlew','gradlew.bat','gradle.properties','settings.gradle.kts','build.gradle.kts','androidApp/build.gradle.kts','shared/build.gradle.kts','replay/build.gradle.kts','gradle/wrapper/gradle-wrapper.jar','gradle/wrapper/gradle-wrapper.properties','README.md']]
    sources=dict(pi=archive(pi,out/'pi-source.tar.gz'),android=archive(android,out/'android-source.tar.gz'))
    shutil.copyfile(Path(__file__).with_name('install_pi.py'),out/'install_pi.py')
    shutil.copyfile(Path(__file__).with_name('README.md'),out/'README.md')
    if a.build_android:shutil.copyfile(mobile/'androidApp/build/outputs/apk/debug/androidApp-debug.apk',out/'rid-observer-debug.apk')
    payloads={f.name:dict(sha256=digest(f),bytes=f.stat().st_size) for f in out.iterdir() if f.is_file() and f.name!='android-build.log'}
    manifest=dict(format='rid_field_kit_v1',source_hash=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest(),sources=sources,payloads=payloads,
                  research_poc=True,aircraft_authentication=False,android_apk='debug_test_only' if a.build_android else 'not_built',private_field_data_included=False)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('FIELD_KIT_CREATED '+str(out))


if __name__=='__main__':main()
