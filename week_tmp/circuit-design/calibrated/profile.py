"""Conservative integer envelopes for a FROZEN, NOT ADOPTED horizontal log model."""
import hashlib,json,math
from decimal import Decimal,localcontext,ROUND_FLOOR,ROUND_CEILING
from pathlib import Path
BINS=8
MAX_COORD=(1<<20)-1
MAX_SQUARED=3*(4*MAX_COORD)**2

def build(baseline):
    source=json.loads(Path(baseline).read_text());dmin,dmax=map(Decimal,map(str,source['training_claimed_distance_range_m']))
    lo=math.ceil((dmin*100)**2);hi=math.floor((dmax*100)**2)+1
    # Six model bins plus unsupported near/far bins. No test-data fitting.
    boundaries=[0]+[round(math.exp(math.log(lo)+(math.log(hi)-math.log(lo))*i/6)) for i in range(7)]+[MAX_SQUARED+1]
    boundaries[1]=lo;boundaries[-2]=hi
    a=Decimal(str(source['model_intercept_dbm']));n=Decimal(str(source['horizontal_proxy_n']));tau=Decimal(str(source['threshold_db']))
    if n<=0 or tau<0 or any(x>=y for x,y in zip(boundaries,boundaries[1:])):raise ValueError('Invalid frozen model/bins')
    def f(s):
        with localcontext() as ctx:
            ctx.prec=80
            return (a-10*n*(Decimal(s).sqrt()/100).log10())*100+16000
    out=dict(bounds=boundaries,outer_low=[],outer_high=[],inner_low=[],inner_high=[],supported=[],inner_valid=[])
    for i in range(BINS):
        supported=0<i<BINS-1
        if not supported:
            vals=(0,16000,0,0,0)
        else:
            # f decreases; evaluate the exclusive upper boundary as a safe superset.
            high=f(boundaries[i]);low=f(boundaries[i+1]);eps=Decimal(1)
            ol=math.floor(low-100*tau-eps);oh=math.ceil(high+100*tau+eps)
            il=math.ceil(high-100*tau+eps);ih=math.floor(low+100*tau-eps)
            ol=max(0,ol);oh=min(16000,oh);valid=max(0,il)<=min(16000,ih)
            if ol>oh:raise ValueError('Outer range outside represented RSSI domain')
            il,ih=(max(0,il),min(16000,ih)) if valid else (0,0)
            vals=(ol,oh,il,ih,int(valid))
        for k,v in zip(['outer_low','outer_high','inner_low','inner_high','inner_valid'],vals):out[k].append(v)
        out['supported'].append(int(supported))
    return dict(format='frozen_log_envelope_2d_v1',adoption='NOT_ADOPTED_REFERENCE_MODEL',profile=out,
        baseline_sha256=hashlib.sha256(Path(baseline).read_bytes()).hexdigest(),a=str(a),n=str(n),threshold_db=str(tau),
        arithmetic='squared centimetres; RSSI=100*dBm+16000; integer inclusive RSSI endpoints; half-open distance bins',
        supported_squared_distance_cm2=[lo,hi],coefficient_source='frozen Week29 training/calibration only',numeric_margin_cdb=1,
        domain='horizontal integer geometry only; no time/altitude/source authentication')

def geometry(row):
    lo=hi=0;radius=row['receiver_radius_cm']+row['claim_radius_cm']
    for q,o in zip(row['claim'],row['observer']):
        if not 0<=q<=MAX_COORD or not 0<=o<=MAX_COORD:raise ValueError('Coordinate range')
        d=abs(q-o);lo+=max(0,d-radius)**2;hi+=(d+radius)**2
    return lo,hi

def decision(card,row):
    lo,hi=geometry(row);p=card['profile'];bins=[i for i in range(BINS) if hi>=p['bounds'][i] and lo<p['bounds'][i+1]]
    if not row['eligible'] or not bins or any(not p['supported'][i] for i in bins):return 2
    r=row['rssi'];all_inner=all(p['inner_valid'][i] and p['inner_low'][i]<=r<=p['inner_high'][i] for i in bins)
    any_outer=any(p['outer_low'][i]<=r<=p['outer_high'][i] for i in bins)
    return 0 if all_inner else 1 if not any_outer else 2

def continuous_oracle(card,row):
    lo,hi=geometry(row);domain=card['supported_squared_distance_cm2']
    if not row['eligible'] or lo<domain[0] or hi>=domain[1] or lo<=0:return 2
    # Independent high-precision continuous reference on the SAME squared interval.
    with localcontext() as ctx:
        ctx.prec=80;a=Decimal(card['a']);n=Decimal(card['n']);tau=Decimal(card['threshold_db'])*100
        f=lambda s:(a-10*n*(Decimal(s).sqrt()/100).log10())*100+16000
        pl,ph=f(hi),f(lo);r=Decimal(row['rssi'])
        if r<pl-tau or r>ph+tau:return 1
        if ph-tau<=r<=pl+tau:return 0
        return 2
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(build(a.baseline),indent=2)+'\n')
