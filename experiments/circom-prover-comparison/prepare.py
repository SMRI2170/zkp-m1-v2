"""Render balanced Circom driver from preserved, hash-pinned source."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def render():
 source=ROOT/'experiments/balanced-cli/rendered/circom/bench.cjs'
 manifest=json.loads((ROOT/'week24/manifests/balanced-cli.json').read_text())
 assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['file_sha256'][str(source.relative_to(ROOT))]
 s=source.read_text()
 old='const [fixture,prover,verifier]=process.argv.slice(2);'
 assert s.count(old)==1
 s=s.replace(old,"const [fixture,prover,verifier,backend]=process.argv.slice(2);\nif(!['snarkjs','rapidsnark'].includes(backend))throw Error('unknown prover backend');")
 s=s.replace("framework:'Circom/RapidSnark'","framework:'Circom/'+backend,prover_backend:backend,verifier_backend:'RapidSnark native',snarkjs_single_thread:backend==='snarkjs'")
 s=s.replace("proof_encoding:'JSON'","proof_encoding:'JSON',proof_canonical_json_bytes:Buffer.byteLength(JSON.stringify(JSON.parse(fs.readFileSync(path.join(tmp,'proof.json')))))")
 return s
if __name__=='__main__':print(render(),end='')
