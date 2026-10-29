package org.carelink.monitor;

import org.json.*;
import java.time.Instant;
import java.util.*;

/** Decoded API data. Timestamps, finite numbers, patient scope and confidence are validated here. */
public final class Models {
    private Models() {}
    public static long timestamp(String value) { return Instant.parse(value).toEpochMilli(); }
    public static String required(JSONObject o,String key) throws JSONException {
        String v=o.getString(key); if(v.trim().isEmpty())throw new JSONException("Missing "+key); return v;
    }
    public static Double number(JSONObject o,String key) throws JSONException {
        if(o.isNull(key)||!o.has(key))return null;
        Object v=o.get(key); if(!(v instanceof Number)||!Double.isFinite(((Number)v).doubleValue()))throw new JSONException("Invalid "+key);
        return ((Number)v).doubleValue();
    }
    public static final class Metric {
        public Double value,display; public boolean good,held; public long lastValid; public String sampleId;
        public static Metric from(JSONObject o) throws JSONException {
            Metric m=new Metric(); m.value=number(o,"value");m.display=number(o,"displayValue");
            m.good="good".equals(o.getString("quality"))&&o.optBoolean("available",true);m.held=o.optBoolean("held",false);
            m.lastValid=o.isNull("lastValidAt")?0:timestamp(o.getString("lastValidAt"));m.sampleId=o.optString("sampleId","");return m;
        }
    }
    public static final class Prediction {
        public String state,model,label,meaning,at; public Double confidence;public boolean cnnSuspected;
        public static Prediction from(JSONObject o) throws JSONException {
            Prediction p=new Prediction();p.state=required(o,"state");p.model=o.optString("model","");p.at=o.optString("predictedAt","");
            p.confidence=number(o,"confidence");if(p.confidence!=null&&(p.confidence<0||p.confidence>1))throw new JSONException("Invalid confidence");
            Object result=o.opt("result");JSONObject r=result instanceof JSONObject?(JSONObject)result:null;
            p.label=r==null?"":r.optString("classification",r.optString("label",""));
            p.cnnSuspected=r!=null&&r.optJSONObject("cnn_fall")!=null&&r.getJSONObject("cnn_fall").optBoolean("suspected_fall",false);p.meaning=o.optString("confidenceMeaning","");if(p.state.equals("available")&&!Arrays.asList("normal","warning","critical").contains(p.label))throw new JSONException("Invalid classification");return p;
        }
    }
    public static final class Reading {
        public String patientId,deviceId,source,level="unknown";public long time,assessedAt;public boolean connected,fall,fallGood;
        public Metric hr,temp;public Prediction prediction;public List<String> reasons=new ArrayList<>();
        public static Reading from(JSONObject o) throws JSONException {
            Reading r=new Reading();r.patientId=required(o,"patientId");r.deviceId=required(o,"deviceId");r.source=required(o,"source");
            r.time=timestamp(required(o,"measuredAt"));r.connected=o.getBoolean("connected");JSONObject metrics=o.getJSONObject("metrics");
            r.hr=Metric.from(metrics.getJSONObject("hr"));r.temp=Metric.from(metrics.getJSONObject("temp"));
            JSONObject f=o.getJSONObject("fall");r.fall=f.getBoolean("active");r.fallGood="good".equals(f.getString("quality"));
            JSONObject a=o.optJSONObject("assessment");if(a!=null){r.level=a.getString("level");if(!Arrays.asList("green","yellow","red","unknown").contains(r.level))throw new JSONException("Invalid level");r.assessedAt=timestamp(a.getString("assessedAt"));JSONArray reasons=a.optJSONArray("reasons");if(reasons!=null)for(int i=0;i<reasons.length();i++)r.reasons.add(reasons.getString(i));}
            else if(r.fall){r.level="red";r.assessedAt=r.time;}
            r.prediction=Prediction.from(o.getJSONObject("ai"));return r;
        }
    }
    public static final class Patient {
        public String id,name;public Reading reading;
        public static Patient from(JSONObject o) throws JSONException {
            Patient p=new Patient();p.id=required(o,"id");p.name=required(o,"name");
            if(!o.isNull("reading")){p.reading=Reading.from(o.getJSONObject("reading"));if(!p.id.equals(p.reading.patientId))throw new JSONException("Patient ID mismatch");}return p;
        }
    }
    public static final class Session {
        public String userId,role,csrfToken;public boolean simulation;public Set<String> patients=new HashSet<>();
        public static Session from(JSONObject o) throws JSONException {
            Session s=new Session();s.userId=required(o,"userId");s.role=required(o,"role");s.csrfToken=o.optString("csrfToken",null);s.simulation=o.optBoolean("simulation",false);
            if(!Arrays.asList("clinician","patient","family").contains(s.role))throw new JSONException("Invalid role");
            JSONArray a=o.getJSONArray("patientIds");for(int i=0;i<a.length();i++)s.patients.add(a.getString(i));return s;
        }
    }
    public static final class Alert {
        public String id,patientId,severity,summary,status,time; public boolean active;
        public static Alert from(JSONObject o) throws JSONException {
            Alert a=new Alert();a.id=required(o,"id");a.patientId=required(o,"patientId");a.severity=required(o,"severity");a.summary=required(o,"summary");a.status=required(o,"status");a.time=required(o,"occurredAt");timestamp(a.time);a.active=o.getBoolean("conditionActive");return a;
        }
    }
}
