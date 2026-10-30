package com.carelink.coursework;
import java.net.URI;
import java.util.Locale;

final class ApiPolicy {
    static URI origin(String text) throws Exception {
        URI u=new URI(text).normalize();
        if(!"https".equals(u.getScheme())||u.getHost()==null||u.getUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null
            ||!(u.getPath().isEmpty()||u.getPath().equals("/"))||u.getPort()==0||u.getPort() < -1||u.getPort()>65535)throw new IllegalArgumentException("HTTPS origin required");
        boolean usbTunnel=u.getHost().equals("127.0.0.1")&&u.getPort()==19443;
        if((u.getHost().equalsIgnoreCase("localhost")||u.getHost().equals("127.0.0.1")||u.getHost().equals("[::1]"))&&!usbTunnel)throw new IllegalArgumentException("Use the Mac LAN HTTPS address or the explicit ADB USB endpoint");
        return new URI(u.getScheme(),null,u.getHost(),u.getPort(),null,null,null);
    }
    static void request(String path,String method){
        if(!path.matches("/api/(gateway|login|logout|session(?:/rotate)?|patients(?:/[A-Za-z0-9_-]+(?:/(readings|predictions))?)?|alerts(?:/[A-Za-z0-9_-]+/acknowledgement)?|classify)(?:\\?minutes=[0-9]{1,5})?"))throw new IllegalArgumentException("API path refused");
        if(!method.equals("GET")&&!method.equals("POST"))throw new IllegalArgumentException("API method refused");
        boolean mutation=path.equals("/api/login")||path.equals("/api/logout")||path.equals("/api/session/rotate")||path.equals("/api/classify")||path.endsWith("/acknowledgement");
        if(mutation!=method.equals("POST"))throw new IllegalArgumentException("API method refused");
    }
    static String cookie(String header) {
        // Require backend's Secure/HttpOnly/SameSite/Path/Max-Age contract.
        String[] fields=header.split(";");if(!fields[0].startsWith("carelink_session="))throw new IllegalArgumentException("Session response invalid");
        String token=fields[0].substring("carelink_session=".length());
        boolean secure=false,httpOnly=false,sameSite=false,path=false;long seconds=-1;
        for(int i=1;i<fields.length;i++){
            String f=fields[i].trim(),lower=f.toLowerCase(Locale.ROOT);
            if(lower.equals("secure"))secure=true;if(lower.equals("httponly"))httpOnly=true;
            if(lower.equals("samesite=lax")||lower.equals("samesite=strict"))sameSite=true;
            if(lower.equals("path=/"))path=true;
            if(lower.startsWith("max-age="))seconds=Long.parseLong(f.substring(8));
            if(lower.startsWith("domain="))throw new IllegalArgumentException("Session domain refused");
        }
        if(!secure||!httpOnly||!sameSite||!path||seconds<1||seconds>28800||!token.matches("cl_s1_[A-Za-z0-9_-]{43}"))throw new IllegalArgumentException("Session response invalid");
        return token+"\n"+seconds;
    }
}
