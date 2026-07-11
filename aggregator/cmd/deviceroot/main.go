package main
import (
  "encoding/json"; "fmt"; "math/big"; "os"
  "uav/aggregator/membership"
)
func main(){
  base:="../zk-distance/build/uav_witness_attestation"
  leaves:=make([]*big.Int, membership.N)
  for i:=0;i<membership.N;i++{
    var pub []string
    b,_:=os.ReadFile(fmt.Sprintf("%s/proofs/input_dev%d_public.json",base,i))
    json.Unmarshal(b,&pub)
    ax,_:=new(big.Int).SetString(pub[11],10); ay,_:=new(big.Int).SetString(pub[12],10)
    leaves[i]=membership.MimcHash(ax,ay)
  }
  root,_,_:=membership.BuildTree(leaves)
  fmt.Println(root.String())
}
