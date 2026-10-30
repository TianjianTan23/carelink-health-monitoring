package com.carelink.coursework;
import static org.junit.Assert.*;
import org.junit.Test;
import java.security.cert.CertPathValidatorException;
import javax.net.ssl.SSLHandshakeException;

public class NetworkTraceTest {
    @Test public void diagnosticsExcludeExceptionMessagesAndIncludeCauseTypes(){
        SSLHandshakeException error=new SSLHandshakeException("synthetic-password-cookie-token");
        error.initCause(new CertPathValidatorException("synthetic-secret"));
        String result=NetworkTrace.exceptionTypes(error);
        assertEquals("javax.net.ssl.SSLHandshakeException <- java.security.cert.CertPathValidatorException",result);
        assertFalse(result.contains("synthetic"));
    }
    @Test public void cyclicCausesAreBounded(){
        Exception a=new Exception(),b=new Exception();a.initCause(b);b.initCause(a);
        assertEquals(6,NetworkTrace.exceptionTypes(a).split(" <- ").length);
    }
}
