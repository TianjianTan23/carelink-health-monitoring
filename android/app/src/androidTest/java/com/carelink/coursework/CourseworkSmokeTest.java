package com.carelink.coursework;

import android.content.Context;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.net.ssl.HttpsURLConnection;
import java.net.URL;
import org.json.JSONObject;

@RunWith(AndroidJUnit4.class)
public class CourseworkSmokeTest {
    private static final String ORIGIN=InstrumentationRegistry.getArguments().getString("gatewayOrigin","https://10.0.2.2:19443");
    private String js(ActivityScenario<MainActivity> scenario,String code) throws Exception {
        AtomicReference<String> result=new AtomicReference<>();CountDownLatch latch=new CountDownLatch(1);
        scenario.onActivity(a->a.getBridge().getWebView().evaluateJavascript(code,s->{result.set(s);latch.countDown();}));
        assertTrue("JavaScript callback",latch.await(10,TimeUnit.SECONDS));return result.get();
    }
    private void text(ActivityScenario<MainActivity> scenario,String value) throws Exception {
        long deadline=System.currentTimeMillis()+20000;
        while(System.currentTimeMillis()<deadline){if(js(scenario,"document.body.innerText").contains(value))return;Thread.sleep(250);}
        fail("Expected named UI state not shown: "+value+"; public error="+js(scenario,"document.querySelector(\"[role=alert]\")?.innerText || \"none\""));
    }
    private void role(ActivityScenario<MainActivity> s,String expected) throws Exception {
        // Mobile CSS hides the desktop workspace caption. Assert the actual
        // authenticated role view, not text that is intentionally invisible.
        long until=System.currentTimeMillis()+20000;
        while(System.currentTimeMillis()<until){if(js(s,"Boolean(document.querySelector('.desktop."+expected+"'))").equals("true"))return;Thread.sleep(200);}
        fail("Authenticated role view missing: "+expected+"; public error="+js(s,"document.querySelector(\"[role=alert]\")?.innerText || \"none\""));
    }
    private void offline(ActivityScenario<MainActivity> s) throws Exception {
        text(s,"Offline demo");js(s,"Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Offline demo')).click()");text(s,"Open nurse demo");
    }
    @Test public void actualKeystoreEncryptsPersistsRejectsTamperingAndClears() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();SessionVault vault=new SessionVault(context);vault.clear();
        String marker="synthetic-storage-test-only";vault.write(marker);
        for(Object value:context.getSharedPreferences("carelink_encrypted_session",0).getAll().values())assertFalse(String.valueOf(value).contains(marker));
        assertEquals(marker,new SessionVault(context).read());
        context.getSharedPreferences("carelink_encrypted_session",0).edit().putString("ciphertext","AAAA").commit();
        assertThrows(Exception.class,()->new SessionVault(context).read());vault.clear();assertNull(vault.read());
    }
    @Test public void packagedReactOpensBothClearlySimulatedRoles() throws Exception {
        try(ActivityScenario<MainActivity> s=ActivityScenario.launch(MainActivity.class)){
            offline(s);js(s,"Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Open nurse demo').click()");role(s,"pro");text(s,"Readings");
            js(s,"document.querySelector('.sidebar-bottom button').click()");text(s,"Open patient demo");
            js(s,"Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Open patient demo').click()");role(s,"basic");
        }
    }
    private void bridge(ActivityScenario<MainActivity> s,String expression,int expected) throws Exception {
        js(s,"window.__courseResult='waiting';("+expression+").then(r=>window.__courseResult=String(r.status)).catch(()=>window.__courseResult='ERROR');true");
        long until=System.currentTimeMillis()+15000;String value="";
        while(System.currentTimeMillis()<until){value=js(s,"window.__courseResult");if(!value.contains("waiting"))break;Thread.sleep(100);}
        assertEquals("Native API HTTP status (no secrets logged)","\""+expected+"\"",value);
    }
    private int oldSessionStatus(String token) throws Exception {
        okhttp3.OkHttpClient client=new okhttp3.OkHttpClient.Builder().cookieJar(okhttp3.CookieJar.NO_COOKIES).followRedirects(false).build();
        okhttp3.Request request=new okhttp3.Request.Builder().url(ORIGIN+"/api/session").header("Cookie","carelink_session="+token).build();
        try(okhttp3.Response response=client.newCall(request).execute()){return response.code();}

    }
    @Test public void nativeHttpsLoginPersistsRotatesAndRevokes() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();SessionVault vault=new SessionVault(context);vault.clear();
        try(ActivityScenario<MainActivity> s=ActivityScenario.launch(MainActivity.class)){
            offline(s);
            String api="window.Capacitor.Plugins.CareLinkApi";
            bridge(s,api+".configure({origin:'"+ORIGIN+"'}).then(()=>"+api+".request({path:'/api/login',method:'POST',body:JSON.stringify({username:'demo-clinician',password:'coursework-demo'})}))",200);
            String webCookie=android.webkit.CookieManager.getInstance().getCookie(ORIGIN);
            assertTrue("Session must not leak into WebView Cookie storage",webCookie==null||!webCookie.contains("carelink_session="));
            String old=new JSONObject(vault.read()).getString("token");
            assertNotNull(new SessionVault(context).read());
            bridge(s,api+".request({path:'/api/session',method:'GET'}).then(r=>{if(JSON.parse(r.body).role!=='clinician')throw new Error('Wrong role');return r})",200);
            bridge(s,api+".request({path:'/api/session/rotate',method:'POST',body:'{}'})",200);
            assertEquals(401,oldSessionStatus(old));
            String rotated=new JSONObject(vault.read()).getString("token");
            bridge(s,api+".request({path:'/api/logout',method:'POST',body:'{}'})",200);
            assertEquals(401,oldSessionStatus(rotated));assertNull(vault.read());
            bridge(s,api+".request({path:'/api/session',method:'GET'})",401);
        }finally{vault.clear();}
    }
    private void fill(ActivityScenario<MainActivity> s,String selector,String value) throws Exception {
        js(s,"(()=>{const input=document.querySelector('"+selector+"');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'"+value+"');input.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
    }
    @Test public void actualLiveUiRestoresAfterActivityRestartAndLogout() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();SessionVault vault=new SessionVault(context);vault.clear();
        try(ActivityScenario<MainActivity> s=ActivityScenario.launch(MainActivity.class)){
            offline(s);fill(s,"[aria-label=\"Mac HTTPS API\"]",ORIGIN);
            js(s,"Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Connect')).click()");
            text(s,"LIVE · Mac");Thread.sleep(500);
            fill(s,"#login-user","demo-clinician");fill(s,"#login-password","coursework-demo");
            js(s,"Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Sign in').click()");role(s,"pro");
            String old=new JSONObject(vault.read()).getString("token");
            s.recreate();role(s,"pro");
            js(s,"document.querySelector('.sidebar-bottom button').click()");text(s,"Sign in to CareLink");
            assertNull(vault.read());assertEquals(401,oldSessionStatus(old));offline(s);
        }finally{vault.clear();}
    }

    @Test public void sameStoredSnapshotAsWebAndExplicitSimulationSource() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();SessionVault vault=new SessionVault(context);vault.clear();
        try(ActivityScenario<MainActivity> s=ActivityScenario.launch(MainActivity.class)){
            offline(s);String api="window.Capacitor.Plugins.CareLinkApi";
            bridge(s,api+".configure({origin:'"+ORIGIN+"'}).then(()=>"+api+".request({path:'/api/login',method:'POST',body:JSON.stringify({username:'demo-clinician',password:'coursework-demo'})}))",200);
            String device=InstrumentationRegistry.getArguments().getString("expectedDeviceId");
            String timestamp=InstrumentationRegistry.getArguments().getString("expectedTimestamp");
            assertNotNull("Web snapshot expected timestamp must be provided",timestamp);
            bridge(s,api+".request({path:'/api/patients',method:'GET'}).then(r=>{const v=JSON.parse(r.body)[0].reading;if(v.deviceId!=="+JSONObject.quote(device)+"||v.receivedAt!=="+JSONObject.quote(timestamp)+"||v.source!=='mock'||v.metrics.spo2.value!==97)throw new Error('Web/native snapshot differs');return r})",200);
            bridge(s,api+".request({path:'/api/gateway',method:'GET'}).then(r=>{const v=JSON.parse(r.body);if(v.mode!=='hardware'||v.hasAutomaticSimulator)throw new Error('Wrong gateway mode');return r})",200);
            bridge(s,api+".request({path:'/api/logout',method:'POST',body:'{}'})",200);
        }finally{vault.clear();}
    }
    @Test public void wrongServerIdentityRefusedWithoutDemoOrCredentialsFallback() throws Exception {
        String bad=InstrumentationRegistry.getArguments().getString("badGatewayOrigin","https://10.0.2.2:19444");
        try(ActivityScenario<MainActivity> s=ActivityScenario.launch(MainActivity.class)){
            offline(s);
            js(s,"window.__badTls='waiting';window.Capacitor.Plugins.CareLinkApi.configure({origin:'"+bad+"'}).then(()=>window.Capacitor.Plugins.CareLinkApi.request({path:'/api/session',method:'GET'})).then(()=>window.__badTls='UNSAFE').catch(()=>window.__badTls='REFUSED');true");
            long deadline=System.currentTimeMillis()+15000;String result="";
            while(System.currentTimeMillis()<deadline){result=js(s,"window.__badTls");if(!result.contains("waiting"))break;Thread.sleep(100);}
            assertEquals("Wrong SAN must fail TLS, even though its CA is trusted","\"REFUSED\"",result);
            assertNull(new SessionVault(InstrumentationRegistry.getInstrumentation().getTargetContext()).read());
        }
    }

}
