"""PR6 declared geometry and private schedules; no detector truth interface."""
import hashlib
import hmac
import json
import math
from pathlib import Path
import random

from observer_attack import attack_spec,attack_ini,audit_attack
from normalize import read_vectors,write_csv
from scene import ini_for,layout_positions,run_scene

DIRECTIONS=['x','toward','away','tangent','vertical','equidistant']
NODES=[0,2,3,4,5]


def claim_position(p,anchor,direction,distance):
    if direction not in DIRECTIONS or not math.isfinite(distance) or distance<0:raise ValueError('Invalid claim direction/distance')
    if distance==0:return list(p)
    q=list(p)
    if direction=='x':q[0]+=distance
    elif direction=='vertical':q[2]+=distance
    else:
        x=p[0]-anchor[0];y=p[1]-anchor[1];rho=math.hypot(x,y)
        if not math.isfinite(rho) or rho<1e-6:raise ValueError('Undefined horizontal direction')
        if direction=='equidistant':
            if distance>2*rho:raise ValueError('Requested chord exceeds diameter')
            theta=2*math.asin(distance/(2*rho));q[0]=anchor[0]+x*math.cos(theta)-y*math.sin(theta);q[1]=anchor[1]+x*math.sin(theta)+y*math.cos(theta)
        else:
            ux,uy=(-y/rho,x/rho) if direction=='tangent' else (x/rho,y/rho)
            sign=-1 if direction=='toward' else 1;q[0]+=sign*distance*ux;q[1]+=sign*distance*uy
    if any(not math.isfinite(v) or not 0<=v<=500 for v in q):raise ValueError('Claim outside simulation box')
    return q


def selection(key,seed,kind,count):
    if kind=='round_robin':return [NODES[i%len(NODES)] for i in range(count)]
    if kind!='private_random' or len(key)!=32:raise ValueError('Private schedule key/selector required')
    output=[]
    for i in range(count):
        # Rejection sampling avoids modulo bias. Domain does not include cell:
        # every factor comparison uses the same flight's private schedule.
        attempt=0
        while True:
            value=int.from_bytes(hmac.new(key,f'flight:{seed}:packet:{i}:try:{attempt}'.encode(),hashlib.sha256).digest()[:8],'big')
            if value<(2**64//5)*5:break
            attempt+=1
        output.append(NODES[value%5])
    return output


def spec_for(cell,seed,case,offset,key,count=20):
    schedule=selection(key,seed,cell['schedule'],count)
    spec=attack_spec(seed,case,offset,'strong',cell['bound_db'],(-80,23),count,schedule)
    spec.update(layout=cell['layout'],claim_direction=cell['direction'],claim_distance_m=offset,profile=cell['profile'],
                attack_n=cell['attack_n'],catalog_override=layout_positions(cell['layout']),schedule_kind=cell['schedule'])
    return spec


def render(spec):
    text=attack_ini(spec).replace('*.host[1].typename = "Issue75PowerHost"','*.host[1].typename = "Issue77PowerHost"')
    prefix='*.host[1].wlan[0].mgmt.'
    text+=f'{prefix}claimDirection = "{spec["claim_direction"]}"\n{prefix}claimDistance = {spec["claim_distance_m"]}m\n{prefix}attackN = {spec["attack_n"]}\n'
    return text


def run_external(spec,workspace,directory):
    rows,tx,audit=run_scene(spec,workspace,directory,ini_renderer=render)
    ledger=audit_attack(read_vectors(directory/'run.vec'),tx,rows,spec)
    error=0.;norm_error=0.
    for t in tx:
        q=claim_position(t['true_tx_xyz'],layout_positions(spec['layout'])[0],spec['claim_direction'],spec['claim_distance_m'])
        error=max(error,math.dist(q,t['claimed_xyz']));norm_error=max(norm_error,abs(math.dist(t['true_tx_xyz'],t['claimed_xyz'])-spec['claim_distance_m']))
    if error>1e-8 or norm_error>1e-8:raise ValueError('Native claim geometry differs from declared displacement')
    write_csv(directory/'external-truth-ledger.csv',ledger)
    (directory/'external-truth-ledger.json').write_text(json.dumps(ledger)+'\n')
    audit.update(claim_max_error_m=error,displacement_norm_max_error_m=norm_error,layout=spec['layout'],claim_direction=spec['claim_direction'])
    (directory/'external-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    return rows,tx,audit,ledger
