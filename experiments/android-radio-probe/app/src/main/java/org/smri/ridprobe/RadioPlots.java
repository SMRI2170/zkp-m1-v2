package org.smri.ridprobe;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import java.util.*;

/** Native plots of measured samples. No synthetic bearings on the measurement screen. */
public final class RadioPlots extends View {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private List<RadioMath.Sample> samples=List.of();
    private double direction=Double.NaN,phoneHeading=Double.NaN;
    private final boolean compass;
    private static final int BLUE=Color.rgb(31,79,130),GRAY=Color.rgb(125,135,146);
    public RadioPlots(Context c,boolean isCompass){super(c);compass=isCompass;}
    public void update(List<RadioMath.Sample> values,double angle,double phone){
        samples=new ArrayList<>(values);direction=angle;phoneHeading=phone;invalidate();
    }
    private float dp(float value){return value*getResources().getDisplayMetrics().density;}
    private void label(Canvas c,String s,float x,float y,int size,int color){paint.setColor(color);paint.setTextSize(dp(size));paint.setStyle(Paint.Style.FILL);paint.setTextAlign(Paint.Align.CENTER);c.drawText(s,x,y,paint);}
    @Override protected void onDraw(Canvas c){super.onDraw(c);
        float w=getWidth(),h=getHeight();
        if(compass){
            float x=w/2,y=h/2,r=Math.min(w,h)/2-dp(27);
            paint.setColor(Color.rgb(220,226,233));paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(1.5f));c.drawCircle(x,y,r,paint);
            for(int deg=0;deg<360;deg+=30){double a=Math.toRadians(deg-90);c.drawLine(x+(r-dp(5))*(float)Math.cos(a),y+(r-dp(5))*(float)Math.sin(a),x+r*(float)Math.cos(a),y+r*(float)Math.sin(a),paint);}
            label(c,"北",x,y-r-dp(8),13,GRAY);label(c,"南",x,y+r+dp(20),13,GRAY);
            label(c,"西",x-r-dp(18),y+dp(5),13,GRAY);label(c,"東",x+r+dp(18),y+dp(5),13,GRAY);
            if(Double.isFinite(phoneHeading)){
                double a=Math.toRadians(phoneHeading-90);paint.setColor(GRAY);paint.setStrokeWidth(dp(4));
                c.drawLine(x+(r-dp(13))*(float)Math.cos(a),y+(r-dp(13))*(float)Math.sin(a),x+r*(float)Math.cos(a),y+r*(float)Math.sin(a),paint);
            }
            if(Double.isFinite(direction)){
                double a=Math.toRadians(direction-90);float tipx=x+(r-dp(13))*(float)Math.cos(a),tipy=y+(r-dp(13))*(float)Math.sin(a);
                paint.setColor(BLUE);paint.setStrokeWidth(dp(4));c.drawLine(x,y,tipx,tipy,paint);
                Path tip=new Path();tip.moveTo(tipx,tipy);
                tip.lineTo(tipx-dp(16)*(float)Math.cos(a-.5),tipy-dp(16)*(float)Math.sin(a-.5));
                tip.lineTo(tipx-dp(16)*(float)Math.cos(a+.5),tipy-dp(16)*(float)Math.sin(a+.5));tip.close();paint.setStyle(Paint.Style.FILL);c.drawPath(tip,paint);
                label(c,String.format(Locale.JAPAN,"%.0f°",direction),x,y+dp(35),23,BLUE);
            }else label(c,samples.isEmpty()?"データ待ち":"推定待ち",x,y+dp(6),18,GRAY);
        }else{
            float left=dp(38),right=w-dp(8),top=dp(16),bottom=h-dp(24);
            for(int db:new int[]{-100,-70,-40}){
                float y=bottom-(db+110)/100f*(bottom-top);paint.setColor(Color.rgb(229,233,238));paint.setStrokeWidth(dp(1));c.drawLine(left,y,right,y,paint);label(c,Integer.toString(db),dp(16),y+dp(4),10,GRAY);
            }
            if(samples.size()<2){label(c,"受信データ待ち",(left+right)/2,(top+bottom)/2,13,GRAY);return;}
            long first=samples.get(0).nanos(),last=samples.get(samples.size()-1).nanos();
            Path line=new Path();int stride=Math.max(1,samples.size()/240);
            for(int i=0;i<samples.size();i+=stride){RadioMath.Sample s=samples.get(i);
                float x=left+(float)((s.nanos()-first)/(double)Math.max(1,last-first))*(right-left);
                float y=bottom-(float)(Math.max(-110,Math.min(-10,s.rssi()))+110)/100*(bottom-top);
                if(i==0)line.moveTo(x,y);else line.lineTo(x,y);
            }
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(2));paint.setColor(BLUE);c.drawPath(line,paint);
            label(c,"受信強度（dBm）／時間",(left+right)/2,h-dp(5),11,GRAY);
        }
    }
}
