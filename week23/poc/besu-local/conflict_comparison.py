"""Fresh local network; preserve all private fixtures, publish only measurements."""
import json
from pathlib import Path
import native_qbft as network

network.BASE = network.ROOT / '.cache/week23/private/besu-conflict-42-v1'

def experiment(keyfile):
    source = Path(__file__).with_name('conflict_experiment.cjs')
    # Ethers and solc resolve from the existing contracts dependencies.
    code = source.read_text()
    result = json.loads(network.node_js(
        'process.env.WEEK23_KEYFILE=' + json.dumps(str(keyfile)) + ';' +
        'process.env.WEEK23_SOURCE=' + json.dumps(str(source.with_name('ConflictHistory.sol'))) + ';' +
        'process.env.WEEK23_PRIVATE=' + json.dumps(str(network.BASE)) + ';' + code))
    result.update({'host': 'one Mac arm64; four loopback validators; one operator',
                   'besu_version': '26.9.0', 'blockperiod_seconds': 2,
                   'scope': 'synthetic digest certificates and ordering; no ZKP/VK deployment, independent operators, or sensor truth'})
    (network.ROOT / 'week23/logs/conflict-comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))

if __name__ == '__main__':
    network.main(experiment)
