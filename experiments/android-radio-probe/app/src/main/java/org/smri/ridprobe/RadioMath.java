package org.smri.ridprobe;

import java.util.*;

/** Platform-independent research math. Peak phone heading is not an AoA. */
public final class RadioMath {
    public static double wrap(double deg) { return (deg % 360 + 360) % 360; }
    public static double error(double a, double b) { return (wrap(a-b)+180)%360-180; }
    public record Sample(long nanos, double heading, double rssi) {}
    public record Heading(long nanos, double degrees, boolean usable) {}
    public record Result(String status, int count, int bins, double coverageDeg,
                         double peakHeadingDeg, double amplitudeDb, double directionalR2, double residualSdDb) {}
    public record Repeatability(int completedTurns, int usableTurns, double lastTwoDifferenceDeg) {}

    /** Separate complete sweeps. Agreement is repeatability, never true angle accuracy. */
    public static Repeatability repeatability(List<Sample> samples) {
        if(samples.size()<24)return new Repeatability(0,0,Double.NaN);
        List<Double> peaks=new ArrayList<>();int start=0,turns=0;double travel=0;
        for(int i=1;i<samples.size();i++){
            travel+=error(samples.get(i).heading(),samples.get(i-1).heading());
            if(Math.abs(travel)>=330){
                List<Sample> sweep=samples.subList(start,i+1);Result r=fit(sweep);
                if(r.coverageDeg()>=270){turns++;if(r.status().equals("EXPERIMENTAL_PEAK"))peaks.add(r.peakHeadingDeg());
                    start=i+1;travel=0;if(start+1<samples.size())i=start;}
            }
        }
        double disagreement=peaks.size()>=2?Math.abs(error(peaks.get(peaks.size()-1),peaks.get(peaks.size()-2))):Double.NaN;
        return new Repeatability(turns,peaks.size(),disagreement);
    }

    public static Heading nearest(List<Heading> history, long stamp, long toleranceNanos) {
        Heading best=null;long delta=Long.MAX_VALUE;
        for (int i=history.size()-1;i>=0;i--) {
            Heading h=history.get(i);long d=Math.abs(h.nanos()-stamp);
            if(d<delta){best=h;delta=d;}
            if(h.nanos()<stamp-toleranceNanos) break;
        }
        return best!=null && delta<=toleranceNanos && best.usable()?best:null;
    }
    private static double[] solve(double[][] mat, double[] rhs) {
        int n=rhs.length;double[][] a=new double[n][n+1];
        for(int i=0;i<n;i++){System.arraycopy(mat[i],0,a[i],0,n);a[i][n]=rhs[i];}
        for(int col=0;col<n;col++){
            int pivot=col;for(int i=col+1;i<n;i++)if(Math.abs(a[i][col])>Math.abs(a[pivot][col]))pivot=i;
            if(Math.abs(a[pivot][col])<1e-8)return null;
            double[] tmp=a[col];a[col]=a[pivot];a[pivot]=tmp;
            double div=a[col][col];for(int j=col;j<=n;j++)a[col][j]/=div;
            for(int i=0;i<n;i++)if(i!=col){double f=a[i][col];for(int j=col;j<=n;j++)a[i][j]-=f*a[col][j];}
        }
        double[] beta=new double[n];for(int i=0;i<n;i++)beta[i]=a[i][n];return beta;
    }
    public static Result fit(List<Sample> samples) {
        int n=samples.size();int[] bins=new int[8];List<Double> angles=new ArrayList<>();
        for(Sample s:samples){bins[(int)(wrap(s.heading())/45)]++;angles.add(wrap(s.heading()));}
        int occupied=0;for(int x:bins)if(x>0)occupied++;
        Collections.sort(angles);double maxGap=360;
        if(n>1){maxGap=angles.get(0)+360-angles.get(n-1);for(int i=1;i<n;i++)maxGap=Math.max(maxGap,angles.get(i)-angles.get(i-1));}
        double coverage=360-maxGap;
        if(n<24 || occupied<6 || coverage<270)return new Result("INSUFFICIENT_ROTATION",n,occupied,coverage,Double.NaN,0,0,0);
        double t0=samples.get(0).nanos()/1e9;double meanT=0;
        for(Sample s:samples)meanT+=s.nanos()/1e9-t0;meanT/=n;
        double[][] a=new double[4][4],a0=new double[2][2];double[] b=new double[4],b0=new double[2];
        for(Sample s:samples){
            double theta=Math.toRadians(s.heading()),t=(s.nanos()/1e9-t0-meanT)/60;
            double[] x={1,Math.cos(theta),Math.sin(theta),t},z={1,t};double w=1.0/bins[(int)(wrap(s.heading())/45)];
            for(int i=0;i<4;i++){b[i]+=w*x[i]*s.rssi();for(int j=0;j<4;j++)a[i][j]+=w*x[i]*x[j];}
            for(int i=0;i<2;i++){b0[i]+=w*z[i]*s.rssi();for(int j=0;j<2;j++)a0[i][j]+=w*z[i]*z[j];}
        }
        double[] beta=solve(a,b),nullBeta=solve(a0,b0);
        if(beta==null || nullBeta==null)return new Result("DEGENERATE_FIT",n,occupied,coverage,Double.NaN,0,0,0);
        double sse=0,sse0=0,sw=0;
        for(Sample s:samples){
            double theta=Math.toRadians(s.heading()),t=(s.nanos()/1e9-t0-meanT)/60;
            double pred=beta[0]+beta[1]*Math.cos(theta)+beta[2]*Math.sin(theta)+beta[3]*t;
            double w=1.0/bins[(int)(wrap(s.heading())/45)];
            sse+=w*Math.pow(s.rssi()-pred,2);sse0+=w*Math.pow(s.rssi()-nullBeta[0]-nullBeta[1]*t,2);sw+=w;
        }
        double amplitude=Math.hypot(beta[1],beta[2]);double r2=sse0>1e-8?1-sse/sse0:0;
        String status=amplitude>=2 && r2>=.35?"EXPERIMENTAL_PEAK":"WEAK_DIRECTIONAL_SIGNAL";
        return new Result(status,n,occupied,coverage,wrap(Math.toDegrees(Math.atan2(beta[2],beta[1]))),amplitude,r2,Math.sqrt(sse/sw));
    }
    /** Only syntactic ODID framing validation. Not identity, signature or truth validation. */
    public static int messageCount(byte[] payload) {
        if(payload.length<1)return 0;int type=(payload[0]&255)>>>4;
        if(type<=5)return payload.length==25?1:0;
        if(type!=15 || payload.length<3 || (payload[1]&255)!=25)return 0;
        int count=payload[2]&255;if(count<1 || count>9 || payload.length!=3+25*count)return 0;
        for(int i=0;i<count;i++)if(((payload[3+25*i]&255)>>>4)>5)return 0;
        return count;
    }
    public static int wifiRidCount(int ieId,byte[] body) {
        if(ieId!=221 || body.length<6 || (body[0]&255)!=0xfa || (body[1]&255)!=0x0b ||
           (body[2]&255)!=0xbc || (body[3]&255)!=0x0d)return 0;
        return messageCount(Arrays.copyOfRange(body,5,body.length));
    }
}
