"""Small evidence selectors; no location or identifiers in returned summaries."""
import re

def permission_granted(package, permission):
    match=re.search(r'(?m)^\s*android\.permission\.'+re.escape(permission)+r': granted=(true|false)\b',package)
    if match is not None:return match.group(1)=='true'
    # Observed ASUS API24 PMS output omits ungranted, flag-free runtime states.
    # Accept only a complete dump with an entirely empty runtime section and an
    # explicit declaration. Missing/truncated/other output stays unknown.
    declared=package.split('requested permissions:',1)[-1].split('install permissions:',1)[0] if 'requested permissions:' in package else ''
    empty=re.search(r'runtime permissions:\s*\n\s*\nAsus Customized Information:',package)
    if empty and re.search(r'(?m)^\s*android\.permission\.'+re.escape(permission)+r'\s*$',declared):return False
    return None

def active_location_requests(text, package):
    # Historical records and cached last-known locations are not active app requests.
    active=text.split('Historical Records by Provider:')[0]
    return {p:bool(re.search(r'UpdateRecord\['+p+r'\s+'+re.escape(package)+r'(?=\s|\]|\(\d+\))',active)) for p in ('gps','network')}

def stored_fix_providers(fixes):
    counts={}
    for fix in fixes:
        provider=fix.get('provider')
        key=provider if provider in ('gps','network','fused','passive') else 'other_or_unknown'
        counts[key]=counts.get(key,0)+1
    return counts


def recover_private_snapshot(source, journal, destination):
    """Recover only a derived copy. Immutable raw DB/journal are retained separately."""
    import os,shutil,sqlite3
    from contextlib import closing
    shutil.copyfile(source,destination);os.chmod(destination,0o600)
    if journal is not None:
        copied=str(destination)+'-journal';shutil.copyfile(journal,copied);os.chmod(copied,0o600)
    with closing(sqlite3.connect(destination)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Derived snapshot integrity failed')
    return destination


def known_play_store_crash_close(xml):
    """Only the observed OS crash alert for Play Store; never permission dialogs."""
    import xml.etree.ElementTree as ET
    nodes=list(ET.fromstring(xml).iter('node'))
    message=any(n.get('package')=='android' and 'Google Play ストア' in n.get('text','') and '停止' in n.get('text','') for n in nodes)
    buttons=[n for n in nodes if n.get('package')=='android' and n.get('text')=='アプリを閉じる' and n.get('enabled')=='true']
    if not message or len(buttons)!=1:return None
    bounds=tuple(map(int,re.findall(r'\d+',buttons[0].get('bounds',''))))
    return bounds if len(bounds)==4 else None
