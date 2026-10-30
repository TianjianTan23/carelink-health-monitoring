package com.carelink.coursework;

import android.util.Log;
import java.net.InetSocketAddress;
import java.net.Proxy;
import okhttp3.Call;
import okhttp3.EventListener;
import okhttp3.Handshake;
import okhttp3.Request;

/** Diagnostic metadata only: never log headers, bodies, exception messages or stacks. */
final class NetworkTrace extends EventListener {
    volatile String stage="validation";
    volatile int status=0;
    private String origin="unconfigured",operation="other";
    private final long started=System.nanoTime();
    void target(String validatedOrigin,String path){
        origin=validatedOrigin;
        operation=path.equals("/api/login")?"login":path.equals("/api/session")?"session":"other";
    }
    @Override public void connectStart(Call call,InetSocketAddress address,Proxy proxy){stage="connect";}
    @Override public void secureConnectStart(Call call){stage="tls_handshake";}
    @Override public void secureConnectEnd(Call call,Handshake handshake){stage="tls_verified";}
    @Override public void requestHeadersEnd(Call call,Request request){stage="request_headers_sent";}
    @Override public void requestBodyEnd(Call call,long count){stage="request_body_sent";}
    static String exceptionTypes(Throwable error){
        StringBuilder types=new StringBuilder();
        for(int i=0;error!=null&&i<6;i++,error=error.getCause()){
            if(i>0)types.append(" <- ");
            types.append(error.getClass().getName());
        }
        return types.toString();
    }
    private String metadata(){return "operation="+operation+" origin="+origin+" stage="+stage+" status="+status+" elapsedMs="+elapsedMillis();}
    private long elapsedMillis(){return (System.nanoTime()-started)/1000000;}
    void failed(Exception error){Log.w("CareLinkNetwork",metadata()+" exceptionTypes="+exceptionTypes(error));}
    void complete(){if(operation.equals("login")||operation.equals("session"))Log.i("CareLinkNetwork",metadata()+" result=complete");}
}
