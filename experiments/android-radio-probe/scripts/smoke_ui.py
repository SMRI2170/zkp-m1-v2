"""UI-only smoke check on an isolated emulator, never physical RF evidence."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET


def main():
    p=argparse.ArgumentParser();p.add_argument('--device',required=True);p.add_argument('--apk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if not args.device.startswith('emulator-'):raise ValueError('This UI check is emulator-only, not a physical RF test')
    if subprocess.run(['git','check-ignore','--quiet',str(args.output)]).returncode:raise ValueError('Use an ignored private QA directory')
    args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    def adb(*a,binary=False):
        value=subprocess.check_output(['adb','-s',args.device,*a],timeout=20)
        return value if binary else value.decode().strip()
    if adb('shell','getprop','ro.kernel.qemu')!='1':raise ValueError('Expected an emulator')
    adb('install','-r',str(args.apk))
    for permission in ['ACCESS_COARSE_LOCATION','ACCESS_FINE_LOCATION','BLUETOOTH_SCAN','BLUETOOTH_CONNECT','NEARBY_WIFI_DEVICES']:
        adb('shell','pm','grant','org.smri.ridprobe','android.permission.'+permission)
    adb('shell','am','force-stop','org.smri.ridprobe');adb('shell','am','start','-W','-n','org.smri.ridprobe/.MainActivity')
    checks=[]
    def tree():
        adb('shell','uiautomator','dump','/sdcard/rid-probe-ui.xml')
        return ET.fromstring(adb('shell','cat','/sdcard/rid-probe-ui.xml'))
    def texts(root):return [n.get('text','') for n in root.iter('node')]
    def tap(label):
        root=tree();matches=[n for n in root.iter('node') if n.get('text')==label]
        if not matches:raise AssertionError('Missing UI label '+label)
        x1,y1,x2,y2=map(int,re.findall(r'\d+',matches[0].get('bounds')))
        adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2));time.sleep(.25)
    def screenshot(name):
        (args.output/(name+'.png')).write_bytes(adb('exec-out','screencap','-p',binary=True))
    root=tree();assert '受信開始' in texts(root) and '方向の補正' not in texts(root);checks.append('main screen separates calibration/diagnostics')
    screenshot('measurement')
    tap('受信開始');assert any(x.startswith('受信中') for x in texts(tree()));tap('停止');checks.append('start/stop UI works on emulator (no RF accuracy inference)')
    tap('記録');assert '測定履歴' in texts(tree());screenshot('history');checks.append('history navigation')
    tap('現在のCSV');tap('推定結果 CSV（対象名なし）');root=tree()
    # Android's system document picker, not a custom storage bypass.
    labels=texts(root);save=next((x for x in ('保存','SAVE','Save') if x in labels),None)
    if save is None:raise AssertionError('Document picker Save action missing')
    tap(save);time.sleep(.5)
    name=adb('shell','run-as','org.smri.ridprobe','cat','files/latest-session.txt')
    path='/sdcard/Download/rid-'+name+'.csv'
    content=adb('shell','cat',path)
    parsed=list(csv.reader(io.StringIO(content)))
    assert parsed and parsed[0][0]=='target_alias' and 'repeat_peak_difference_deg' in parsed[0]
    checks.append('Storage Access Framework writes a readable CSV with repeatability fields')
    tap('設定');assert '方向の補正' in texts(tree());screenshot('settings');checks.append('settings navigation')
    tap('機能確認');assert '測定の詳細' in texts(tree());tap('閉じる');checks.append('details dialog')
    tap('測定');root=tree();assert '受信開始' in texts(root) and '方向の補正' not in texts(root)
    result=dict(scope='Emulated UI, not Pixel hardware/RF or angle accuracy validation',passed=len(checks),checks=checks)
    (args.output/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
