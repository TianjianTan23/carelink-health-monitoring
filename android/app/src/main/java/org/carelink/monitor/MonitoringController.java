package org.carelink.monitor;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.carelink.monitor.Models.*;

/** Controller owns asynchronous data flow. Views receive snapshots; API code never touches UI. */
public final class MonitoringController {
    public static final class State {
        public Session session;public Patient patient;public List<Reading> history=Collections.emptyList();
        public List<Prediction> predictions=Collections.emptyList();public List<Alert> alerts=Collections.emptyList();
        public String error="";public boolean busy;public long refreshedAt;
        State copy(){State s=new State();s.session=session;s.patient=patient;s.history=history;s.predictions=predictions;s.alerts=alerts;s.error=error;s.busy=busy;s.refreshedAt=refreshedAt;return s;}
    }
    public interface Listener {void changed(State state);}
    private final ExecutorService worker=Executors.newSingleThreadExecutor();private final ScheduledExecutorService timer=Executors.newSingleThreadScheduledExecutor();
    private ScheduledFuture<?> polling;private final AtomicInteger generation=new AtomicInteger();private final AtomicBoolean fetching=new AtomicBoolean();
    private final Listener listener;private final State state=new State();private ApiClient api;
    public MonitoringController(Listener listener){this.listener=listener;}
    private void emit(int revision){if(revision==generation.get())listener.changed(state.copy());}
    public void login(String url,String user,String password){final int revision=generation.incrementAndGet();worker.execute(()->{
        state.busy=true;state.error="";emit(revision);
        try{ApiClient client=new ApiClient(url);Session session=client.login(user,password);if(revision!=generation.get())return;api=client;state.session=session;load(revision);}
        catch(Exception e){state.error=message(e);state.session=null;}finally{state.busy=false;emit(revision);}
    });}
    private static String message(Exception e){String s=e.getMessage();return s==null?e.getClass().getSimpleName():s;}
    private void load(int revision)throws Exception{
        List<Patient> patients=api.patients();if(revision!=generation.get())return;state.patient=patients.isEmpty()?null:patients.get(0);emit(revision);
        if(state.patient!=null){String id=state.patient.id;List<Reading> h=api.history(id);List<Prediction> p=api.predictions(id);List<Alert> a=api.alerts();
            if(revision!=generation.get())return;state.history=h;state.predictions=p;state.alerts=a;}
        else{state.history=Collections.emptyList();state.predictions=Collections.emptyList();state.alerts=Collections.emptyList();}
        state.refreshedAt=System.currentTimeMillis();state.error="";
    }
    public void refresh(){if(!fetching.compareAndSet(false,true))return;final int revision=generation.get();worker.execute(()->{
        try{if(state.session!=null&&revision==generation.get())load(revision);}
        catch(Exception e){state.error=message(e);if(e instanceof ApiClient.Failure&&((ApiClient.Failure)e).status==401){state.session=null;state.patient=null;state.history=Collections.emptyList();state.predictions=Collections.emptyList();state.alerts=Collections.emptyList();}}
        finally{fetching.set(false);emit(revision);}
    });}
    public void acknowledge(String id){final int revision=generation.get();worker.execute(()->{try{api.acknowledge(id);load(revision);}catch(Exception e){state.error=message(e);}emit(revision);});}
    public void logout(){final int revision=generation.incrementAndGet();listener.changed(new State());worker.execute(()->{try{if(api!=null)api.logout();}catch(Exception ignored){}api=null;state.session=null;state.patient=null;state.history=Collections.emptyList();state.predictions=Collections.emptyList();state.alerts=Collections.emptyList();state.error="";emit(revision);});}
    public synchronized void resume(){if(polling==null)polling=timer.scheduleWithFixedDelay(this::refresh,0,5,TimeUnit.SECONDS);}
    public synchronized void pause(){if(polling!=null){polling.cancel(false);polling=null;}}
    public void close(){generation.incrementAndGet();pause();timer.shutdownNow();worker.shutdownNow();}
}
