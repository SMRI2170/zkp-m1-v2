"""Four native loopback Besu validators; transfer/finality benchmark, no ZKP deployment."""
from pathlib import Path
import hashlib
import json
import os
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / '.cache/week23/private/besu-qbft-26.9.0-v2'
BESU = ROOT / '.cache/week23/besu-tools/besu-26.9.0/bin/besu'
ENV = {**os.environ, 'JAVA_HOME': '/opt/homebrew/opt/openjdk@26/libexec/openjdk.jdk/Contents/Home',
       'JAVA_OPTS': '-Xms128m -Xmx384m -XX:ActiveProcessorCount=2'}
CHAIN = 237023
RPC_PORTS = list(range(18545, 18549))
P2P_PORTS = list(range(30431, 30435))
os.umask(0o077)


def rpc(index, method, params=()):
    data = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': list(params)}).encode()
    request = urllib.request.Request('http://127.0.0.1:' + str(RPC_PORTS[index]), data=data,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=5) as response:
        result = json.load(response)
    if 'error' in result:
        raise RuntimeError(str(result['error']))
    return result['result']


def height(index=0):
    return int(rpc(index, 'eth_blockNumber'), 16)


def node_js(code):
    # stdout stays internal: keys/raw signed transactions are never logged.
    return subprocess.check_output(['node', '-e', code], cwd=ROOT / 'contracts', text=True)


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def main(experiment=None):
    for port in RPC_PORTS + P2P_PORTS:
        with socket.socket() as s:
            s.bind(('127.0.0.1', port))
    BASE.mkdir(mode=0o700)  # preserve previous runs; fail rather than overwrite
    wallet = json.loads(node_js("const {Wallet}=require('ethers'); const w=Wallet.createRandom(); console.log(JSON.stringify({address:w.address,key:w.privateKey}));"))
    keyfile = BASE / 'transfer-key.json'
    keyfile.write_text(json.dumps(wallet))
    config = json.loads((ROOT / 'contracts/besu-qbft/qbftConfigFile.json').read_text())
    config['genesis']['config']['chainId'] = CHAIN
    config['genesis']['gasLimit'] = '0x1c9c380'
    config['genesis']['alloc'] = {wallet['address'][2:]: {'balance': '0xad78ebc5ac6200000'}}
    cfg = BASE / 'operator.json'
    cfg.write_text(json.dumps(config))
    with (BASE / 'operator.log').open('w') as log:
        subprocess.run([str(BESU), 'operator', 'generate-blockchain-config', '--config-file=' + str(cfg),
                        '--to=' + str(BASE / 'network'), '--private-key-file-name=key'],
                       env=ENV, check=True, stdout=log, stderr=subprocess.STDOUT)
    keys = sorted((BASE / 'network/keys').iterdir())
    if len(keys) != 4:
        raise RuntimeError('wrong validator count')
    enodes = []
    for i, key in enumerate(keys):
        public = (key / 'key.pub').read_text().strip().removeprefix('0x')
        if len(public) == 130 and public.startswith('04'):
            public = public[2:]
        if len(public) != 128:
            raise RuntimeError('unexpected validator public-key format')
        enodes.append('enode://' + public + '@127.0.0.1:' + str(P2P_PORTS[i]))
    processes = []
    logs = []
    peaks = [0] * 4
    try:
        for i in range(4):
            data = BASE / ('node' + str(i + 1))
            data.mkdir(mode=0o700)
            (data / 'static-nodes.json').write_text(json.dumps([e for j, e in enumerate(enodes) if j != i]))
            log = (BASE / ('node' + str(i + 1) + '.log')).open('w')
            logs.append(log)
            command = [str(BESU), '--genesis-file=' + str(BASE / 'network/genesis.json'), '--data-path=' + str(data),
                       '--node-private-key-file=' + str(keys[i] / 'key'), '--p2p-host=127.0.0.1', '--p2p-interface=127.0.0.1',
                       '--p2p-port=' + str(P2P_PORTS[i]), '--discovery-enabled=false', '--rpc-http-enabled',
                       '--rpc-http-host=127.0.0.1', '--rpc-http-port=' + str(RPC_PORTS[i]),
                       '--rpc-http-api=ETH,NET,QBFT,WEB3', '--host-allowlist=localhost,127.0.0.1',
                       '--min-gas-price=0', '--logging=INFO']
            processes.append(subprocess.Popen(command, env=ENV, stdout=log, stderr=subprocess.STDOUT))

        def sample():
            for i, process in enumerate(processes):
                if process.poll() is None:
                    raw = subprocess.check_output(['ps', '-o', 'rss=', '-p', str(process.pid)], text=True).strip()
                    peaks[i] = max(peaks[i], int(raw or '0') * 1024)

        deadline = time.monotonic() + 90
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError('validator exited; inspect ignored node logs')
            sample()
            try:
                ready = all(height(i) >= 2 and int(rpc(i, 'net_peerCount'), 16) >= 3 for i in range(4))
            except Exception:
                ready = False
            if ready:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('validator startup timeout; inspect ignored node logs')
            time.sleep(0.5)

        validators = rpc(0, 'qbft_getValidatorsByBlockNumber', ['latest'])
        if len(validators) != 4:
            raise RuntimeError('wrong QBFT validator set')
        if experiment is not None:
            experiment(keyfile)
            return
        signing = "const fs=require('fs');const{Wallet}=require('ethers');(async()=>{const x=JSON.parse(fs.readFileSync(" + json.dumps(str(keyfile)) + "));const w=new Wallet(x.key);const a=[];for(let nonce=0;nonce<21;nonce++)a.push(await w.signTransaction({chainId:237023,nonce,to:w.address,value:0,gasLimit:21000,gasPrice:0,type:0}));console.log(JSON.stringify(a))})();"
        signed = json.loads(node_js(signing))
        samples = []
        for index, raw in enumerate(signed):
            start = time.monotonic()
            tx = rpc(0, 'eth_sendRawTransaction', [raw])
            receipt = None
            deadline = time.monotonic() + 20
            while receipt is None:
                receipt = rpc(0, 'eth_getTransactionReceipt', [tx])
                sample()
                if time.monotonic() > deadline:
                    raise RuntimeError('transfer not included')
                if receipt is None:
                    time.sleep(0.05)
            elapsed = (time.monotonic() - start) * 1000
            if int(receipt['status'], 16) != 1:
                raise RuntimeError('transfer failed')
            replicated = []
            deadline = time.monotonic() + 10
            while len(replicated) != 4:
                replicated = [i for i in range(4) if (rpc(i, 'eth_getTransactionReceipt', [tx]) or {}).get('blockHash') == receipt['blockHash']]
                if time.monotonic() > deadline:
                    raise RuntimeError('receipt did not replicate to all validators')
                if len(replicated) != 4:
                    time.sleep(0.05)
            samples.append({'warmup': index == 0, 'rpc_submit_to_receipt_ms': elapsed,
                            'gas_used': int(receipt['gasUsed'], 16), 'all_four_same_receipt_block': True})

        before = height()
        processes[3].terminate()
        processes[3].wait(timeout=30)
        deadline = time.monotonic() + 20
        while height() < before + 3 and time.monotonic() < deadline:
            sample()
            time.sleep(0.2)
        after_one = height()
        if after_one < before + 3:
            raise RuntimeError('one-validator-offline progress failed')
        processes[2].terminate()
        processes[2].wait(timeout=30)
        time.sleep(2)  # allow an already decided/in-flight block to settle
        before_two = height()
        start = time.monotonic()
        while time.monotonic() - start < 12:
            sample()
            time.sleep(0.5)
        after_two = height()
        if after_two != before_two:
            raise RuntimeError('two-validator-offline chain unexpectedly progressed')
        measurements = [s['rpc_submit_to_receipt_ms'] for s in samples if not s['warmup']]
        result = {'besu_version': '26.9.0', 'validators': 4, 'host': 'one Mac arm64; loopback; one operator',
                  'java': '26.0.2', 'heap_limit_MiB_per_validator': 384, 'blockperiod_seconds': 2,
                  'workload': 'zero-value EOA self-transfer, no ZKP/VK deployment', 'warmup': 1, 'samples': samples,
                  'submit_to_receipt_p50_ms': percentile(measurements, 0.5), 'submit_to_receipt_p95_ms': percentile(measurements, 0.95),
                  'polled_peak_rss_bytes_per_validator': peaks, 'receipt_poll_interval_ms': 50,
                  'one_offline': {'height_before': before, 'height_after': after_one, 'progress': True},
                  'two_offline': {'height_before': before_two, 'height_after': after_two, 'observation_seconds': 12, 'progress': False},
                  'scope': 'local QBFT functionality only; not independent operators, censorship resistance, ZKP gas, or sensor truth'}
        (ROOT / 'week23/logs/besu-qbft-local.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
