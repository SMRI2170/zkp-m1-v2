pragma circom 2.2.0;
// Self-contained bit range constraint. No witness-only assertions.
template Bits(n) {
    signal input in;
    signal bit[n];
    var sum=0;
    for (var i=0; i<n; i++) {
        bit[i] <-- (in >> i) & 1;
        bit[i]*(bit[i]-1) === 0;
        sum += bit[i]*(1 << i);
    }
    sum === in;
}
template Euclidean() {
    signal input x1; signal input y1; signal input x2; signal input y2;
    signal input d2; signal input r;
    component coords[4];
    coords[0]=Bits(16); coords[0].in <== x1;
    coords[1]=Bits(16); coords[1].in <== y1;
    coords[2]=Bits(16); coords[2].in <== x2;
    coords[3]=Bits(16); coords[3].in <== y2;
    component db=Bits(33); db.in <== d2;
    component rb=Bits(17); rb.in <== r;
    signal dx2; signal dy2;
    dx2 <== (x1-x2)*(x1-x2);
    dy2 <== (y1-y2)*(y1-y2);
    d2 === dx2+dy2;
    component lower=Bits(18); lower.in <== d2-r*r;
    component upper=Bits(18); upper.in <== (r+1)*(r+1)-d2-1;
}
component main {public [d2,r]} = Euclidean();
