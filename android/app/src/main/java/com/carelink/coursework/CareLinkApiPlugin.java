package com.carelink.coursework;

import com.getcapacitor.*;
import com.getcapacitor.annotation.CapacitorPlugin;
import okhttp3.*;
import java.util.concurrent.TimeUnit;
import java.net.URI;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import org.json.JSONObject;

@CapacitorPlugin(name="CareLinkApi")
public class CareLinkApiPlugin extends Plugin {
    private final ExecutorService queue=Executors.newSingleThreadExecutor();
    private SessionVault vault;
    private final OkHttpClient http=new OkHttpClient.Builder().eventListenerFactory(call->{NetworkTrace trace=call.request().tag(NetworkTrace.class);return trace==null?okhttp3.EventListener.NONE:trace;}).cookieJar(CookieJar.NO_COOKIES).followRedirects(false).followSslRedirects(false).connectTimeout(8,TimeUnit.SECONDS).readTimeout(8,TimeUnit.SECONDS).callTimeout(12,TimeUnit.SECONDS).build();
    private String origin;
    private volatile boolean destroyed;
    @Override public void load(){vault=new SessionVault(getContext());origin=getContext().getSharedPreferences("carelink_public_config",0).getString("origin",null);}
    @PluginMethod public void configure(PluginCall call){queue.execute(()->{
        try{
            String next=ApiPolicy.origin(call.getString("origin","")).toString();
            if(!next.equals(origin)){vault.clear();if(!getContext().getSharedPreferences("carelink_public_config",0).edit().putString("origin",next).commit())throw new IOException();origin=next;}
            call.resolve();
        }catch(Exception e){call.reject("HTTPS endpoint configuration failed");}
    });}
    private JSONObject credential() throws Exception {
        String value=vault.read();if(value==null)return null;JSONObject stored=new JSONObject(value);
        if(!origin.equals(stored.getString("origin"))||stored.getLong("expiresAt")<=System.currentTimeMillis()){vault.clear();return null;}
        if(!stored.getString("token").matches("cl_s1_[A-Za-z0-9_-]{43}"))throw new IOException();return stored;
    }
    @PluginMethod public void request(PluginCall call){queue.execute(()->{
        String path=call.getString("path",""),method=call.getString("method","GET");
        NetworkTrace trace=new NetworkTrace();
        try{
            ApiPolicy.request(path,method);if(origin==null)throw new IOException();
            URI base=ApiPolicy.origin(origin);trace.target(base.toString(),path);trace.stage="credential_read";JSONObject stored=credential();
            // Login replaces an old identity only after confirmed server logout.
            if(path.equals("/api/login")&&stored!=null)throw new IOException();
            // An isolated no-cookie client is essential: Capacitor installs a
            // global CookieHandler for URLConnection. Never let it duplicate
            // headers or persist a plaintext copy outside the encrypted vault.
            Request.Builder request=new Request.Builder().tag(NetworkTrace.class,trace).url(base.resolve(path).toURL()).header("Accept","application/json").header("Origin",origin);
            if(stored!=null)request.header("Cookie","carelink_session="+stored.getString("token"));
            if(method.equals("POST")){
                byte[] body=call.getString("body","{}").getBytes(StandardCharsets.UTF_8);if(body.length>8192)throw new IOException();
                request.header("X-CareLink-CSRF","1").post(RequestBody.create(body,MediaType.get("application/json")));
            }
            trace.stage="network_start";
            try(okhttp3.Response response=http.newCall(request.build()).execute()){
            if(destroyed)throw new IOException();
            int status=response.code();trace.status=status;trace.stage="response_body";ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            if(response.body()!=null)try(InputStream input=response.body().byteStream()){
                byte[] buffer=new byte[4096];int size;while((size=input.read(buffer))!=-1){if(bytes.size()+size>8*1024*1024)throw new IOException();bytes.write(buffer,0,size);}
            }
            if(destroyed)throw new IOException();
            if(status==401||path.equals("/api/logout"))vault.clear();
            if(status==200&&(path.equals("/api/login")||path.equals("/api/session/rotate"))){
                trace.stage="session_response";
                List<String> cookies=new ArrayList<>();
                for(String v:response.headers("Set-Cookie"))if(v.startsWith("carelink_session="))cookies.add(v);
                if(cookies.size()!=1)throw new IOException();String[] parts=ApiPolicy.cookie(cookies.get(0)).split("\n");
                JSONObject next=new JSONObject().put("origin",origin).put("token",parts[0]).put("expiresAt",System.currentTimeMillis()+Long.parseLong(parts[1])*1000);
                trace.stage="credential_write";vault.write(next.toString());
            }
            trace.complete();
            // Deliberately omit response headers; the bridge never exposes Token/Cookie.
            call.resolve(new JSObject().put("status",status).put("body",bytes.toString(StandardCharsets.UTF_8.name())));
            }
        }catch(Exception e){
            trace.failed(e);
            if(!destroyed&&path.equals("/api/logout"))try{vault.clear();}catch(Exception ignored){}
            call.reject("Secure API request failed; check HTTPS trust, endpoint, session and storage");
        }
    });}
    @Override protected void handleOnDestroy(){
        destroyed=true;queue.shutdownNow();
        // Closing a TLS socket may send close_notify: keep network cleanup off
        // Android's main thread, including Activity recreation and app exit.
        new Thread(()->{http.dispatcher().cancelAll();http.connectionPool().evictAll();},"CareLink-HTTPS-cleanup").start();
    }
}
