package com.carelink.coursework;
import static org.junit.Assert.*;
import org.junit.Test;
public class ApiPolicyTest {
    @Test public void httpsLanAndEmulator() throws Exception {assertEquals("https://10.0.2.2:18445",ApiPolicy.origin("https://10.0.2.2:18445").toString());}
    @Test public void explicitUsbEndpoint() throws Exception {assertEquals("https://127.0.0.1:19443",ApiPolicy.origin("https://127.0.0.1:19443").toString());assertThrows(Exception.class,()->ApiPolicy.origin("https://127.0.0.1:19444"));assertThrows(Exception.class,()->ApiPolicy.origin("https://localhost:19443"));}
    @Test public void httpAndPhoneLoopbackRefused(){for(String value:new String[]{"http://10.0.2.2:18445","https://localhost:8443","https://127.0.0.1","https://user@10.0.2.2","https://10.0.2.2/path","https://10.0.2.2?q=x"})assertThrows(Exception.class,()->ApiPolicy.origin(value));}
    @Test public void authenticatedGatewayMetadata(){ApiPolicy.request("/api/gateway","GET");assertThrows(Exception.class,()->ApiPolicy.request("/api/gateway","POST"));}
    @Test public void exactApiContract(){ApiPolicy.request("/api/patients/ttj/readings?minutes=1440","GET");ApiPolicy.request("/api/session/rotate","POST");ApiPolicy.request("/api/logout","POST");}
    @Test public void traversalAndDevicePathsRefused(){for(String path:new String[]{"https://evil.invalid/api/session","//evil.invalid/api/session","/api/../sensor-data","/sensor-data","/api/patients/%2e%2e/readings","/api/session#x"})assertThrows(Exception.class,()->ApiPolicy.request(path,"GET"));}
    @Test public void methodsRefused(){assertThrows(Exception.class,()->ApiPolicy.request("/api/login","GET"));assertThrows(Exception.class,()->ApiPolicy.request("/api/session","POST"));}
    private String safe(){return "carelink_session=cl_s1_"+"a".repeat(43)+"; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800";}
    @Test public void secureCookieAccepted(){assertTrue(ApiPolicy.cookie(safe()).endsWith("\n28800"));}
    @Test public void cookiePolicyCannotBeRelaxed(){for(String flag:new String[]{"; Secure","; HttpOnly","; SameSite=Lax","; Path=/","; Max-Age=28800"})assertThrows(Exception.class,()->ApiPolicy.cookie(safe().replace(flag,"")));}
    @Test public void expiryAndDomainRefused(){assertThrows(Exception.class,()->ApiPolicy.cookie(safe().replace("28800","28801")));assertThrows(Exception.class,()->ApiPolicy.cookie(safe()+"; Domain=evil.invalid"));}
}
