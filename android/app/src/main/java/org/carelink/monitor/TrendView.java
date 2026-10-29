package org.carelink.monitor;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import java.util.*;

/** Native Canvas chart. Missing/held observations break the line instead of fabricating points. */
public final class TrendView extends View {
    private final List<Monitoring.Point> points;private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);private final boolean heart;
    public TrendView(Context c,List<Monitoring.Point> points,boolean heart){super(c);this.points=points;this.heart=heart;
        int count=0;for(Monitoring.Point p:points)if(p.value!=null)count++;
        setContentDescription((heart?"Heart rate":"Temperature")+": "+count+" valid five-second chart points. Missing data leaves a gap.");
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
    }
    private float dp(float n){return n*getResources().getDisplayMetrics().density;}
    @Override protected void onDraw(Canvas c){super.onDraw(c);float left=dp(48),right=getWidth()-dp(12),top=dp(18),bottom=getHeight()-dp(32);
        double lo=Double.POSITIVE_INFINITY,hi=Double.NEGATIVE_INFINITY;for(Monitoring.Point p:points)if(p.value!=null){lo=Math.min(lo,p.value);hi=Math.max(hi,p.value);}
        if(!Double.isFinite(lo)){paint.setTextSize(dp(14));paint.setColor(Color.DKGRAY);c.drawText("Waiting for valid samples",left,top+dp(40),paint);return;}
        double margin=Math.max(heart?2:.2,(hi-lo)*.15);lo-=margin;hi+=margin;paint.setTypeface(Typeface.DEFAULT);paint.setTextSize(dp(11));
        for(int i=0;i<=3;i++){float y=top+(bottom-top)*i/3;paint.setColor(0xffdce4df);paint.setStrokeWidth(dp(1));c.drawLine(left,y,right,y,paint);paint.setColor(0xff46574b);c.drawText(String.format(Locale.US,heart?"%.0f":"%.1f",hi-(hi-lo)*i/3),dp(3),y+dp(4),paint);}
        long begin=points.get(0).time,end=points.get(points.size()-1).time;float prevX=0,prevY=0;boolean linked=false;paint.setColor(heart?0xff267352:0xffa36529);paint.setStrokeWidth(dp(2));
        for(Monitoring.Point p:points){if(p.value==null){linked=false;continue;}float x=left+(right-left)*(p.time-begin)/Math.max(5000f,end-begin);float y=bottom-(float)((p.value-lo)/(hi-lo))*(bottom-top);if(linked)c.drawLine(prevX,prevY,x,y,paint);c.drawCircle(x,y,dp(2.5f),paint);prevX=x;prevY=y;linked=true;}
        paint.setColor(0xff46574b);paint.setTextSize(dp(11));c.drawText("10 min window · 1 point / 5 s",left,getHeight()-dp(9),paint);
    }
}
