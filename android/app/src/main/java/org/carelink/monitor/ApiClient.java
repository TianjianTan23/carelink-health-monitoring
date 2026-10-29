package org.carelink.monitor;

import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static org.carelink.monitor.Models.*;

/** Per-client cookie storage stays in memory. No passwords or auth tokens enter preferences/logs. */
public final class ApiClient {
    private final URI base;private final CookieManager cookies=new CookieManager(null,CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    private Session session;
    public static final class Failure extends IOException {public final int status;Failure(String message,int status){super(message);this.status=status;}}
    public ApiClient(String address){
        base=URI.create(address.trim().replaceAll("/+$",""));String host=base.getHost();
        if(host==null||base.getUserInfo()!=null||base.getQuery()!=null||base.getFragment()!=null)throw new IllegalArgumentException("Enter a server URL without credentials, query or fragment.");
        boolean local=host.equals("localhost")||host.equals("::1")||host.equals("[::1]")||host.endsWith(".local");
        if(host.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+")){
            String[] parts=host.split("\\.");int[] ip=new int[4];boolean valid=true;
            for(int i=0;i<4;i++){try{ip[i]=Integer.parseInt(parts[i]);}catch(NumberFormatException e){valid=false;}if(ip[i]>255)valid=false;}
            local=valid&&(ip[0]==10||ip[0]==127||(ip[0]==192&&ip[1]==168)||(ip[0]==172&&ip[1]>=16&&ip[1]<=31));
        }
        if(!"https".equals(base.getScheme())&&!("http".equals(base.getScheme())&&local))throw new IllegalArgumentException("Use a local HTTP server address, such as http://192.168.1.10:8000.");
    }
    private synchronized String request(String path,String method,JSONObject payload) throws Exception {
        URI uri=URI.create(base.toString()+path);HttpURLConnection c=(HttpURLConnection)uri.toURL().openConnection();
        c.setConnectTimeout(8000);c.setReadTimeout(8000);c.setInstanceFollowRedirects(false);c.setRequestMethod(method);c.setRequestProperty("Accept","application/json");c.setRequestProperty("Cache-Control","no-store");
        for(Map.Entry<String,List<String>> h:cookies.get(uri,Collections.emptyMap()).entrySet())c.setRequestProperty(h.getKey(),String.join("; ",h.getValue()));
        if(session!=null&&session.csrfToken!=null&&!method.equals("GET"))c.setRequestProperty("X-CSRF-Token",session.csrfToken);
        try{
            if(payload!=null){c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");try(OutputStream out=c.getOutputStream()){out.write(payload.toString().getBytes(StandardCharsets.UTF_8));}}
            int code=c.getResponseCode();cookies.put(uri,c.getHeaderFields());if(code<200||code>=300)throw new Failure(code==401?"Session expired or invalid credentials":code==403?"This account cannot access that data":"API HTTP "+code,code);
            try(InputStream in=c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>4*1024*1024)throw new IOException("API response too large");}return new String(out.toByteArray(),StandardCharsets.UTF_8);}
        }finally{c.disconnect();}
    }
    public Session login(String user,String password) throws Exception {session=Session.from(new JSONObject(request("/api/login","POST",new JSONObject().put("username",user).put("password",password))));return session;}
    public void logout() throws Exception {try{request("/api/logout","POST",null);}finally{session=null;cookies.getCookieStore().removeAll();}}
    private void scope(String id) throws Failure {if(session==null||!session.patients.contains(id))throw new Failure("Patient is outside authenticated scope",403);}
    private static String encode(String id) throws Exception {return URLEncoder.encode(id,"UTF-8");}
    public List<Patient> patients() throws Exception {if(session==null)throw new Failure("Sign in first",401);JSONArray a=new JSONArray(request("/api/patients","GET",null));List<Patient> out=new ArrayList<>();for(int i=0;i<a.length();i++){Patient p=Patient.from(a.getJSONObject(i));scope(p.id);out.add(p);}return out;}
    public List<Reading> history(String id) throws Exception {scope(id);JSONArray a=new JSONArray(request("/api/patients/"+encode(id)+"/readings?minutes=10","GET",null));List<Reading> out=new ArrayList<>();for(int i=0;i<a.length();i++){Reading r=Reading.from(a.getJSONObject(i));if(!id.equals(r.patientId))throw new JSONException("Reading scope mismatch");out.add(r);}return out;}
    public List<Prediction> predictions(String id) throws Exception {scope(id);JSONArray a=new JSONArray(request("/api/patients/"+encode(id)+"/predictions","GET",null));List<Prediction> out=new ArrayList<>();for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);if(!id.equals(o.getString("patientId")))throw new JSONException("Prediction scope mismatch");out.add(Prediction.from(o));}return out;}
    public List<Alert> alerts() throws Exception {JSONArray a=new JSONArray(request("/api/alerts","GET",null));List<Alert> out=new ArrayList<>();for(int i=0;i<a.length();i++){Alert v=Alert.from(a.getJSONObject(i));scope(v.patientId);out.add(v);}return out;}
    public void acknowledge(String id) throws Exception {if(session==null||!"clinician".equals(session.role))throw new Failure("Caregiver access required",403);Alert a=Alert.from(new JSONObject(request("/api/alerts/"+encode(id)+"/acknowledgement","POST",new JSONObject())));scope(a.patientId);if(!id.equals(a.id)||"new".equals(a.status))throw new JSONException("Acknowledgement was not confirmed");}
}
