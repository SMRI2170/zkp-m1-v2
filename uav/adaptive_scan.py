"""Bounded scan-frequency learning; broad discovery is retained for other RID sources."""

class AdaptiveScanPlan:
    def __init__(self,discovery_interval=30,max_frequencies=4,ttl=90):
        self.period=discovery_interval;self.maximum=max_frequencies;self.ttl=ttl
        self.known={};self.last_broad=None

    def learn(self,row,now):
        freq=row.get('frequency_mhz')
        if row.get('cache_stale') or not isinstance(freq,int) or not 2400<=freq<=7125:return
        self.known[freq]=now
        if len(self.known)>self.maximum:
            self.known.pop(min(self.known,key=self.known.get))

    def choose(self,now):
        self.known={f:t for f,t in self.known.items() if now-t<=self.ttl}
        if not self.known or self.last_broad is None or now-self.last_broad>=self.period:return None
        return tuple(sorted(self.known))

    def accepted(self,frequencies,now):
        if frequencies is None:self.last_broad=now
