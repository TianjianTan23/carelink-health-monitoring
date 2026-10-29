package org.carelink.monitor.tests;

import android.app.*;
import android.os.Bundle;
import android.graphics.*;
import android.view.View;
import java.io.*;
import java.util.*;
import org.json.JSONObject;
import org.carelink.monitor.*;
import org.carelink.monitor.Models.*;

/** Android-runtime checks only: no UI automation or simulated user input. */
public final class RuntimeChecks extends Instrumentation {
    private Bundle args;private int count;
    @Override public void onCreate(Bundle arguments){args=arguments;start();}
    private void check(boolean condition,String message){if(!condition)throw new AssertionError(message);count++;}
    private Reading fixture(String name)throws Exception{try(InputStream in=getContext().getAssets().open(name+".json");ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);return Reading.from(new JSONObject(out.toString("UTF-8")));}}
    @Override public void onStart(){Bundle result=new Bundle();try{
        for(String[] c:new String[][]{{"normal","green"},{"warning","yellow"},{"critical","red"},{"missing","unknown"},{"held","unknown"},{"fall","red"},{"cnn","yellow"}}){Reading r=fixture(c[0]);check(Monitoring.level(r,r.time+1000).equals(c[1]),"Classification "+c[0]);}
        ApiClient api=new ApiClient(args.getString("url"));Session s=api.login(args.getString("user"),args.getString("password"));check(s!=null,"Login");List<Patient> patients=api.patients();check(!patients.isEmpty(),"Cookie-authenticated readings");String id=patients.get(0).id;
        List<Reading> readings=api.history(id);check(!readings.isEmpty(),"History decoding");check(!api.predictions(id).isEmpty(),"Prediction decoding");api.alerts();check(true,"Alert decoding");
        final Throwable[] drawFailure={null};runOnMainSync(()->{try{TrendView v=new TrendView(getTargetContext(),Monitoring.chart(readings,true,System.currentTimeMillis()),true);v.measure(View.MeasureSpec.makeMeasureSpec(720,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(400,View.MeasureSpec.EXACTLY));v.layout(0,0,720,400);Bitmap bitmap=Bitmap.createBitmap(720,400,Bitmap.Config.ARGB_8888);v.draw(new Canvas(bitmap));bitmap.recycle();}catch(Throwable e){drawFailure[0]=e;}});check(drawFailure[0]==null,"Android Canvas chart draws offscreen");
        boolean rejected=false;try{api.history("other-patient");}catch(ApiClient.Failure e){rejected=e.status==403;}check(rejected,"Patient scope");api.logout();rejected=false;try{api.patients();}catch(ApiClient.Failure e){rejected=e.status==401;}check(rejected,"Logout clears session");
        result.putString("stream",count+" Android runtime checks passed (native JSON, HTTP, cookies, classification, Canvas).\n");finish(Activity.RESULT_OK,result);
    }catch(Throwable e){result.putString("stream","FAILED: "+e.toString());finish(Activity.RESULT_CANCELED,result);}}
}
