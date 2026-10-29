package org.carelink.monitor;

import java.util.*;
import static org.carelink.monitor.Models.*;

/** Presentation policy only. Classification remains on the authenticated Python API. */
public final class Monitoring {
    private Monitoring() {}
    public static boolean fresh(Reading r,long now){return r!=null&&r.connected&&now-r.time>=-5000&&now-r.time<=30000;}
    public static boolean valid(Metric m){return m!=null&&m.good&&!m.held&&m.value!=null;}
    public static boolean incomplete(Reading r,long now){return !fresh(r,now)||!valid(r.hr)||!valid(r.temp)||!r.fallGood||now-r.assessedAt>30000||r.assessedAt>now+5000;}
    public static String level(Reading r,long now){if(r==null)return "unknown";return "green".equals(r.level)&&incomplete(r,now)?"unknown":r.level;}
    public static String label(String level){switch(level){case "green":return "NORMAL";case "yellow":return "WARNING";case "red":return "CRITICAL";default:return "WAITING FOR DATA";}}
    public static Double current(Reading r,Metric m,long now){return fresh(r,now)&&valid(m)?m.value:null;}
    public static Double retainedHeart(Reading r,long now){
        if(r==null||r.hr==null)return null;Metric m=r.hr;long at=m.lastValid>0?m.lastValid:r.time;
        if(now-at<0||now-at>30000)return null;
        if(m.display!=null)return m.display;
        return !fresh(r,now)&&valid(m)?m.value:null;
    }
    public static final class Point {public final long time;public final Double value;public Point(long t,Double v){time=t;value=v;}}
    public static List<Point> chart(List<Reading> readings,boolean heart,long now){
        long end=now/5000*5000,first=end;Map<Long,List<Double>> buckets=new TreeMap<>();Set<String> seen=new HashSet<>();
        List<Reading> sorted=new ArrayList<>(readings);sorted.sort(Comparator.comparingLong(r->r.time));
        for(Reading r:sorted){long bucket=r.time/5000*5000;if(r.time<end-600000||bucket>=end)continue;first=Math.min(first,bucket);Metric m=heart?r.hr:r.temp;if(!valid(m))continue;
            String id=m.sampleId.isEmpty()?r.deviceId+":"+r.time:m.sampleId;if(!seen.add(id))continue;
            List<Double> v=buckets.get(bucket);if(v==null){v=new ArrayList<>();buckets.put(bucket,v);}v.add(m.value);
        }
        List<Point> result=new ArrayList<>();for(long t=first;t<end;t+=5000){List<Double> v=buckets.get(t);Double median=null;
            if(v!=null&&!v.isEmpty()){Collections.sort(v);int n=v.size();median=n%2==1?v.get(n/2):(v.get(n/2-1)+v.get(n/2))/2;}result.add(new Point(t,median));}return result;
    }
}
