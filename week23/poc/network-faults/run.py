"""Actual four-validator Besu over controllable 12-edge TCP proxies."""
from pathlib import Path
import json
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'besu-local'))
import native_qbft as network
from proxy import FaultNetwork

network.BASE=network.ROOT/'.cache/week23/private/besu-network-faults-v1'
transport=None

def topology(source,enodes):
    return [enode.rsplit(':',1)[0]+':'+str(transport.port(source,target)) for target,enode in enumerate(enodes) if source!=target]

def experiment(keyfile):
    # Reuse the actual evidence receipt hashes, deploy only a signature/digest history contract.
    script=Path(__file__).with_name('submit.cjs')
    source=Path(__file__).parents[1]/'besu-local/ConflictHistory.sol'
    inputs=json.loads((network.ROOT/'week23/logs/integrated-history.json').read_text())
    hashes={r['kind']:r['evidence_sha256'] for r in inputs['verified_certificates']}
    env={'KEYFILE':str(keyfile),'PRIVATE':str(network.BASE),'SOURCE':str(source),'X':hashes['normal'],'Y':hashes['outlier']}
    prefix=''.join('process.env.FAULT_'+k+'='+json.dumps(v)+';' for k,v in env.items())
    # Prepare signed transactions once; raw bytes and signing keys remain private.
    prepared=json.loads(network.node_js(prefix+script.read_text()))
    raw=json.loads((network.BASE/'signed-transactions.json').read_text())
    rows=[]
    def send(i,r):return network.rpc(i,'eth_sendRawTransaction',[r])
    def get(i,tx):return network.rpc(i,'eth_getTransactionReceipt',[tx])
    def receipt(tx,nodes,timeout=50):
        start=time.monotonic();end=start+timeout
        while time.monotonic()<end:
            rs=[get(i,tx) for i in nodes]
            if all(rs) and len({r['blockHash'] for r in rs})==1:
                return rs,(time.monotonic()-start)*1000
            time.sleep(.1)
        raise RuntimeError('receipt convergence timeout')
    def settle(seconds):
        # Each individual sleep is bounded; test total observation windows are explicit.
        end=time.monotonic()+seconds
        while time.monotonic()<end:time.sleep(.25)
    def same_history():
        logs=[network.rpc(i,'eth_getLogs',[{'address':prepared['address'],'fromBlock':'0x0','toBlock':'latest'}]) for i in range(4)]
        clean=lambda ls:[{k:l[k] for k in ('blockHash','transactionHash','logIndex','topics','data')} for l in ls]
        assert all(clean(ls)==clean(logs[0]) for ls in logs[1:])
        return len(logs[0])
    tx=send(0,raw[0]);rs,ms=receipt(tx,range(4));assert int(rs[0]['status'],16)==1
    rows.append({'case':'normal','receipt_ms':ms,'all_four_same_receipt':True})
    transport.configure(groups=[0,0,1,1]);settle(6)
    before=[network.height(i) for i in range(4)]
    tx=send(0,raw[1]);settle(12)
    after=[network.height(i) for i in range(4)]
    assert before==after,('partition bypass or unexpected progress',before,after)
    assert all(get(i,tx) is None for i in range(4))
    rows.append({'case':'partition-2-2','height_before':before,'height_after':after,'observation_seconds':12,'pending_no_receipt':True})
    transport.configure();rs,ms=receipt(tx,range(4),60);assert int(rs[0]['status'],16)==1
    rows.append({'case':'heal-2-2','all_four_same_receipt':True,'recovery_receipt_ms':ms})
    transport.configure(groups=[0,0,0,1]);settle(4)
    minority_before=network.height(3);majority_before=network.height(0)
    tx=send(0,raw[2]);rs,ms=receipt(tx,[0,1,2],60);assert int(rs[0]['status'],16)==1
    assert get(3,tx) is None
    rows.append({'case':'partition-3-1','majority_progress':network.height(0)>majority_before,'minority_height_before':minority_before,'minority_height_after':network.height(3),'majority_receipt_ms':ms,'minority_no_receipt':True})
    transport.configure();rs,ms=receipt(tx,range(4),60)
    rows.append({'case':'heal-3-1','all_four_same_receipt':True,'catchup_receipt_ms':ms})
    transport.configure(delay=.2)
    tx=send(0,raw[3]);rs,ms=receipt(tx,range(4),60);assert int(rs[0]['status'],16)==1
    rows.append({'case':'p2p-delay-200ms-per-read','all_four_same_receipt':True,'receipt_ms':ms})
    transport.configure()
    # Replay the exact raw tx: Besu may reject as already known or return the same hash.
    try:
        replay=send(1,raw[3]);assert replay==tx;outcome='same transaction hash'
    except RuntimeError as error:outcome='RPC rejection: '+str(error)
    assert same_history()==4
    rows.append({'case':'raw-transaction-replay','outcome':outcome,'no_extra_decision_event':True})
    # A conflicting fresh nonce is included but the slot policy reverts it.
    conflict=send(0,raw[4]);rs,ms=receipt(conflict,range(4));assert int(rs[0]['status'],16)==0
    rows.append({'case':'competing-valid-receipt','status':0,'all_four_same_receipt':True,'receipt_ms':ms})
    # Controlled ingress refusal: a request is deliberately discarded BEFORE eth_sendRawTransaction.
    # Compare its locally signed tx hash with every node, then bypass the refusing ingress.
    class RefusingIngress(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(403);self.end_headers();self.wfile.write(b'controlled ingress refusal')
        def log_message(self, *args): pass
    gateway=ThreadingHTTPServer(('127.0.0.1',0),RefusingIngress)
    thread=threading.Thread(target=gateway.serve_forever,daemon=True);thread.start()
    try:
        request=urllib.request.Request('http://127.0.0.1:'+str(gateway.server_port),data=json.dumps({'jsonrpc':'2.0','id':1,'method':'eth_sendRawTransaction','params':[raw[5]]}).encode(),headers={'Content-Type':'application/json'})
        try:
            urllib.request.urlopen(request,timeout=5)
            raise AssertionError('refusing gateway accepted request')
        except urllib.error.HTTPError as error: assert error.code==403
    finally:gateway.shutdown();gateway.server_close();thread.join(timeout=5)
    denied_hash=prepared['denied_tx_hash'];assert all(network.rpc(i,'eth_getTransactionByHash',[denied_hash]) is None for i in range(4))
    rows.append({'case':'ingress-refusal','http_status':403,'forwarded_to_besu':False,'all_four_no_transaction':True,'proof_status':'VALID_OFFCHAIN_PRECONDITION'})
    tx=send(2,raw[5]);rs,ms=receipt(tx,range(4));assert tx==denied_hash and int(rs[0]['status'],16)==1
    rows.append({'case':'alternate-ingress-after-refusal','all_four_same_receipt':True,'receipt_ms':ms})
    count=same_history();assert count==5
    result={'host':'one Mac arm64; one operator; actual four Besu 26.9.0 processes','transport':'12 directed loopback TCP proxies; static peers, discovery disabled','tests':rows,'all_four_same_event_history':True,'decision_events':count,'proxied_bytes':transport.bytes,'denied_connection_attempts':transport.blocked,'inputs':'same normal/outlier verified evidence digests as integrated-history; fresh unanimous 3/3 signature fixture for history-only comparison','limits':['200ms delay applies per TCP read/chunk, not a calibrated per-packet WAN delay','Ingress refusal is controlled harness policy, not a Byzantine Besu validator attack','No malicious validator signing/QBFT fork attack or independent organizations','No ZKP/proof/VK deployed; signatures do not prove RF truth or complete observations']}
    (network.ROOT/'week23/logs/besu-network-faults.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

def main():
    global transport
    transport=FaultNetwork()
    try:network.main(experiment,static_nodes=topology)
    finally:transport.close()

if __name__=='__main__':main()
