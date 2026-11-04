package org.smri.ridprobe;

import java.util.*;

public final class RadioMathTest {
    private static int passed=0;
    private static void check(boolean value,String label){if(!value)throw new AssertionError(label);passed++;}
    private static List<RadioMath.Sample> sweep(double peak,boolean attack){
        List<RadioMath.Sample> samples=new ArrayList<>();
        for(int i=0;i<144;i++){
            double angle=i*5%360,seconds=i*.5;
            double rssi=-65+5*Math.cos(Math.toRadians(angle-peak))+.03*seconds+.2*Math.sin(Math.toRadians(angle*3));
            if(attack)rssi+=12*Math.cos(Math.toRadians(angle-220));
            samples.add(new RadioMath.Sample((long)(seconds*1e9),angle,rssi));
        }return samples;
    }
    public static void main(String[] args){
        RadioMath.Result fit=RadioMath.fit(sweep(75,false));
        check(fit.status().equals("EXPERIMENTAL_PEAK"),"good synthetic sweep fits");
        check(Math.abs(RadioMath.error(fit.peakHeadingDeg(),75))<1,"known synthetic peak recovered despite linear time drift");
        check(Math.abs(RadioMath.error(359,1))==2,"circular angle error");
        check(RadioMath.fit(sweep(75,false).subList(0,20)).status().equals("INSUFFICIENT_ROTATION"),"short arc is not direction");
        List<RadioMath.Sample> flat=new ArrayList<>();for(int i=0;i<144;i++)flat.add(new RadioMath.Sample(i*500000000L,i*5%360,-65));
        check(RadioMath.fit(flat).status().equals("WEAK_DIRECTIONAL_SIGNAL"),"constant RSSI has no usable directional signal");
        check(RadioMath.fit(List.of()).status().equals("INSUFFICIENT_ROTATION"),"empty is unknown rather than north");
        List<RadioMath.Heading> history=List.of(new RadioMath.Heading(1000000000L,359,true),new RadioMath.Heading(1100000000L,1,true));
        check(RadioMath.nearest(history,1050000000L,100000000L)!=null,"join matching clock timestamps");
        check(RadioMath.nearest(history,2000000000L,250000000L)==null,"stale cached scan cannot use current pose");
        check(RadioMath.nearest(List.of(new RadioMath.Heading(1L,90,false)),1,10)==null,"unreliable or tilted heading rejected");
        byte[] message=new byte[25];message[0]=2;
        check(RadioMath.messageCount(message)==1,"single structural ODID");
        byte[] ie=new byte[30];ie[0]=(byte)0xfa;ie[1]=0x0b;ie[2]=(byte)0xbc;ie[3]=0x0d;System.arraycopy(message,0,ie,5,25);
        check(RadioMath.wifiRidCount(221,ie)==1,"WiFi vendor OUI/type/counter framing");
        check(RadioMath.wifiRidCount(1,ie)==0,"ordinary IE is not RID");
        check(RadioMath.wifiRidCount(221,Arrays.copyOf(ie,29))==0,"truncated payload rejected");
        byte[] pack=new byte[53];pack[0]=(byte)0xf2;pack[1]=25;pack[2]=2;pack[3]=2;pack[28]=0x12;
        check(RadioMath.messageCount(pack)==2,"message pack length and types");
        pack[2]=3;check(RadioMath.messageCount(pack)==0,"inconsistent message count rejected");
        RadioMath.Result attacked=RadioMath.fit(sweep(75,true));
        check(attacked.status().equals("EXPERIMENTAL_PEAK") && Math.abs(RadioMath.error(attacked.peakHeadingDeg(),75))>60,
            "power correlated with rotation can spoof an apparently good fit; quality is not security");
        RadioMath.Repeatability repeated=RadioMath.repeatability(sweep(75,false));
        check(repeated.completedTurns()==2 && repeated.usableTurns()==2,"two disjoint full sweeps detected");
        check(repeated.lastTwoDifferenceDeg()<3,"stable synthetic pattern repeats");
        check(!Double.isFinite(RadioMath.repeatability(sweep(75,false).subList(0,72)).lastTwoDifferenceDeg()),"one sweep does not fabricate a repeatability error of zero");
        List<RadioMath.Sample> changed=sweep(75,false),other=sweep(200,false);
        for(int i=72;i<144;i++)changed.set(i,other.get(i));
        check(RadioMath.repeatability(changed).lastTwoDifferenceDeg()>70,"independent sweep change is reported");
        List<RadioMath.Sample> oscillation=new ArrayList<>();
        for(int i=0;i<200;i++)oscillation.add(new RadioMath.Sample(i*500000000L,45+30*Math.sin(i*.2),-70));
        check(RadioMath.repeatability(oscillation).completedTurns()==0,"back-and-forth small arc is not a full turn");
        check(RadioMath.repeatability(sweep(75,true)).lastTwoDifferenceDeg()<5,"repeatable biased result is still not true-direction accuracy");
        System.out.println(passed+" math/framing checks passed (synthetic only)");
    }
}
