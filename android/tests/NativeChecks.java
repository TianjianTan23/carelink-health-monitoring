package org.carelink.monitor;

import org.json.*;
import java.nio.file.*;
import java.util.*;
import static org.carelink.monitor.Models.*;

public final class NativeChecks {
    private static int checks=0;
    private static void check(boolean ok,String name){if(!ok)throw new AssertionError(name);checks++;System.out.println("PASS "+name);}
    private static Reading read(String name)throws Exception{return Reading.from(new JSONObject(new String(Files.readAllBytes(Paths.get("tests/fixtures/"+name+".json")),"UTF-8")));}
    public static void main(String[] args)throws Exception{
        for(String[] c:new String[][]{{"normal","green"},{"warning","yellow"},{"critical","red"},{"missing","unknown"},{"held","unknown"},{"fall","red"},{"cnn","yellow"}}){Reading r=read(c[0]);check(Monitoring.level(r,r.time+1000).equals(c[1]),c[0]+" backend classification");}
        check(read("cnn").prediction.cnnSuspected,"CNN suspicion reaches the fall card");
        Reading r=read("normal");check(Monitoring.label(Monitoring.level(r,r.time+1000)).equals("NORMAL"),"One current label");
        check(Monitoring.level(r,r.time+31000).equals("unknown"),"Stale normal is not shown as safe");
        check(Monitoring.current(r,r.hr,r.time+1000)!=null,"Current valid heart rate");
        check(Monitoring.current(r,r.hr,r.time+31000)==null,"Stale heart rate excluded");
        r=read("held");check(Monitoring.retainedHeart(r,r.time+1000)==76,"Labelled last valid display");
        check(Monitoring.current(r,r.hr,r.time+1000)==null,"Held heart rate excluded from current readings");
        check(Monitoring.retainedHeart(r,r.time+26000)==null,"Held display expires after 30 seconds");
        r=read("critical");check(Monitoring.level(r,r.time+40000).equals("red")&&Monitoring.incomplete(r,r.time+40000),"Retained alarm marked stale");
        List<Reading> readings=new ArrayList<>();long now=1_800_000_100_000L;
        for(int i=0;i<3;i++){Reading a=read("normal");a.time=now-20000+i*1000;a.hr.value=new double[]{70,80,200}[i];a.hr.sampleId="beat-"+i;readings.add(a);}
        List<Monitoring.Point> points=Monitoring.chart(readings,true,now);check(points.size()==4&&points.get(0).value==80,"Five-second median");check(points.get(1).value==null,"Missing bucket leaves a gap");
        Reading dup=read("normal");dup.time=now-14000;dup.hr.sampleId="beat-0";readings.add(dup);check(Monitoring.chart(readings,true,now).get(1).value==null,"Repeated accepted beat is not counted again");
        Reading held=read("held");held.time=now-13000;readings.add(held);check(Monitoring.chart(readings,true,now).get(1).value==null,"Held samples never fill chart gaps");
        Reading old=read("normal");old.time=now-700000;readings.add(old);check(Monitoring.chart(readings,true,now).size()==4,"Historical range limited to 10 minutes");
        JSONObject invalid=new JSONObject(new String(Files.readAllBytes(Paths.get("tests/fixtures/normal.json")),"UTF-8"));invalid.getJSONObject("ai").put("confidence",2);
        boolean rejected=false;try{Reading.from(invalid);}catch(JSONException e){rejected=true;}check(rejected,"Invalid model confidence rejected");
        rejected=false;try{new ApiClient("http://example.com");}catch(IllegalArgumentException e){rejected=true;}check(rejected,"Remote cleartext HTTP rejected");
        check(new ApiClient("http://10.0.2.2:8000")!=null,"HTTP emulator address accepted");
        System.out.println(checks+" Android core checks passed.");
        if(args.length>0){String user=System.getenv("CARELINK_TEST_USER"),password=System.getenv("CARELINK_TEST_PASSWORD");if(user==null||password==null)throw new IllegalArgumentException("Supply test credentials through environment variables");
            ApiClient api=new ApiClient(args[0]);Session s=api.login(user,password);check(s.userId.equals(user),"HTTP login");List<Patient> p=api.patients();check(!p.isEmpty(),"Authenticated cookie request");String id=p.get(0).id;
            check(!api.history(id).isEmpty(),"Decode real history JSON");check(!api.predictions(id).isEmpty(),"Decode real classification JSON");api.alerts();check(true,"Decode alert history JSON");
            rejected=false;try{api.history("other-patient");}catch(ApiClient.Failure e){rejected=e.status==403;}check(rejected,"Cross-patient request rejected");api.logout();rejected=false;try{api.patients();}catch(ApiClient.Failure e){rejected=e.status==401;}check(rejected,"Sign-out clears authorization");
            System.out.println(checks+" total checks including live HTTP passed.");}
    }
}
