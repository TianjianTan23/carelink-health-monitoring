package org.carelink.monitor;

import android.app.Activity;
import android.os.*;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import static org.carelink.monitor.Models.*;

/** Native Android Views with a separate controller, API adapter and tested presentation model. */
public final class MainActivity extends Activity {
    private MonitoringController controller;private MonitoringController.State state=new MonitoringController.State();
    private final Handler main=new Handler(Looper.getMainLooper());private SharedPreferences prefs;
    private boolean zh=true,auto=true,logged=false;private String page="readings";private LinearLayout root,body,statusBox;private ScrollView scroll;
    private TextView statusLabel,statusNote,errorText,heartValue,heartNote,tempValue,tempNote,fallValue,loginError;private EditText urlInput,userInput,passwordInput;private Button loginButton;
    private final Runnable ticker=new Runnable(){public void run(){if(logged)updateReadings();main.postDelayed(this,1000);}};
    private String t(String cn,String en){return zh?cn:en;}private int dp(float n){return Math.round(n*getResources().getDisplayMetrics().density);}
    @Override public void onCreate(Bundle b){super.onCreate(b);prefs=getSharedPreferences("carelink",MODE_PRIVATE);zh=prefs.getBoolean("zh",true);auto=prefs.getBoolean("auto",true);
        controller=new MonitoringController(next->main.post(()->{if(isFinishing()||isDestroyed())return;state=next;render();}));showLogin();}
    @Override public void onResume(){super.onResume();if(auto)controller.resume();main.post(ticker);}
    @Override public void onPause(){super.onPause();controller.pause();main.removeCallbacks(ticker);}
    @Override public void onDestroy(){controller.close();main.removeCallbacksAndMessages(null);super.onDestroy();}
    private LinearLayout column(){LinearLayout v=new LinearLayout(this);v.setOrientation(LinearLayout.VERTICAL);return v;}
    private TextView text(String value,int size,boolean bold){TextView v=new TextView(this);v.setText(value);v.setTextSize(size);v.setTextColor(0xff14241b);if(bold)v.setTypeface(Typeface.DEFAULT,Typeface.BOLD);v.setPadding(0,dp(4),0,dp(4));return v;}
    private Button button(String label,Runnable action){Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setMinHeight(dp(48));b.setOnClickListener(v->action.run());return b;}
    private GradientDrawable background(int color,int stroke){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(14));d.setStroke(dp(1),stroke);return d;}
    private LinearLayout card(String title){LinearLayout v=column();v.setPadding(dp(16),dp(12),dp(16),dp(14));v.setBackground(background(Color.WHITE,0xffd8e2dc));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,dp(6),0,dp(8));v.setLayoutParams(p);if(title!=null)v.addView(text(title,17,true));body.addView(v);return v;}
    private void base(){root=column();root.setBackgroundColor(0xfff4f7f4);root.setPadding(dp(16),dp(8),dp(16),dp(8));root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(dp(16)+insets.getSystemWindowInsetLeft(),dp(8)+insets.getSystemWindowInsetTop(),dp(16)+insets.getSystemWindowInsetRight(),dp(8)+insets.getSystemWindowInsetBottom());return insets;});setContentView(root);root.requestApplyInsets();}
    private EditText field(String label,String initial,boolean secret){TextView name=text(label,14,true);body.addView(name);EditText e=new EditText(this);e.setSingleLine(true);e.setText(initial);e.setContentDescription(label);e.setInputType(secret?InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD:InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);e.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);body.addView(e,new LinearLayout.LayoutParams(-1,dp(52)));return e;}
    private void showLogin(){logged=false;base();scroll=new ScrollView(this);body=column();body.setPadding(dp(8),dp(24),dp(8),dp(20));scroll.addView(body);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        body.addView(text("CareLink",36,true));body.addView(text(t("安心看见每一次更新","A clear view of each update"),22,true));body.addView(text(t("心率 · 体温 · 跌倒监测","Heart rate · Temperature · Fall monitoring"),16,false));
        body.addView(text(t("教学原型：不可用于诊断、治疗或临床决策。","Educational prototype: not for diagnosis, treatment or clinical decisions."),13,false));
        urlInput=field(t("服务器地址","Server address"),prefs.getString("url","http://10.0.2.2:8000"),false);
        body.addView(text(t("真机请填电脑的局域网 IP；10.0.2.2 仅用于 Android 模拟器。","Use the computer's LAN IP on a phone; 10.0.2.2 is for the Android emulator."),12,false));
        userInput=field(t("用户 ID","User ID"),"",false);passwordInput=field(t("密码","Password"),"",true);loginError=text(state.error,14,false);loginError.setTextColor(0xffa22335);body.addView(loginError);
        loginButton=button(t("登录","Sign in"),()->{String u=userInput.getText().toString().trim(),p=passwordInput.getText().toString(),url=urlInput.getText().toString().trim();if(u.isEmpty()||p.isEmpty()){loginError.setText(t("请输入账号和密码","Enter a user ID and password"));return;}prefs.edit().putString("url",url).apply();loginButton.setEnabled(false);controller.login(url,u,p);});body.addView(loginButton);
        body.addView(button(zh?"English":"中文",()->{zh=!zh;prefs.edit().putBoolean("zh",zh).apply();showLogin();}));
    }
    private void shell(){logged=true;base();LinearLayout top=new LinearLayout(this);top.setGravity(Gravity.CENTER_VERTICAL);top.addView(text("CareLink",25,true),new LinearLayout.LayoutParams(0,-2,1));top.addView(button(t("刷新","Refresh"),()->controller.refresh()));root.addView(top);
        statusBox=column();statusBox.setPadding(dp(16),dp(8),dp(16),dp(8));statusBox.addView(text(t("当前判断","CURRENT ASSESSMENT"),12,true));statusLabel=text("",30,true);statusLabel.setTextColor(Color.BLACK);statusBox.addView(statusLabel);statusNote=text("",12,false);statusBox.addView(statusNote);root.addView(statusBox,new LinearLayout.LayoutParams(-1,-2));
        root.addView(text(state.session.simulation?t("无硬件测试 · 模拟数据 · 真实 HTTP 后端","Hardware-free test · Synthetic data · Real HTTP backend"):t("教学原型 · 不用于临床决策","Educational prototype · Not for clinical decisions"),11,false));errorText=text("",13,true);errorText.setTextColor(0xffa22335);root.addView(errorText);
        scroll=new ScrollView(this);body=column();scroll.addView(body);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));HorizontalScrollView navScroll=new HorizontalScrollView(this);navScroll.setHorizontalScrollBarEnabled(false);LinearLayout nav=new LinearLayout(this);
        String[] ids={"readings","history","charts","ai","alerts","settings"};String[] names={t("读数","Readings"),t("历史","History"),t("图表","Charts"),"AI",t("告警","Alerts"),t("设置","Settings")};
        for(int i=0;i<ids.length;i++){final String dest=ids[i];Button b=button(names[i],()->{page=dest;renderPage();scroll.scrollTo(0,0);});b.setTextSize(13);nav.addView(b);}navScroll.addView(nav);root.addView(navScroll);renderPage();}
    private void render(){if(state.session==null){if(logged)showLogin();if(loginError!=null)loginError.setText(state.error);if(loginButton!=null)loginButton.setEnabled(!state.busy);return;}
        if(!logged){if(passwordInput!=null)passwordInput.setText("");shell();}else if(!page.equals("settings")){int y=scroll.getScrollY();renderPage();scroll.post(()->scroll.scrollTo(0,y));}updateReadings();}
    private Reading reading(){return state.patient==null?null:state.patient.reading;}
    private String clock(long time){return DateTimeFormatter.ofPattern("HH:mm:ss").withZone(ZoneId.systemDefault()).format(Instant.ofEpochMilli(time));}
    private String number(Double v,boolean temp){return v==null?"—":String.format(Locale.US,temp?"%.1f":"%.0f",v);}
    private void updateReadings(){if(!logged)return;Reading r=reading();long now=System.currentTimeMillis();String level=Monitoring.level(r,now);statusLabel.setText(level.equals("unknown")?t("等待有效数据","WAITING FOR DATA"):Monitoring.label(level));
        int color=level.equals("green")?0xffedf8f0:level.equals("yellow")?0xfffff3cd:level.equals("red")?0xffffe9ec:0xffe9eeeb;statusBox.setBackground(background(color,0xff9caaa1));
        statusNote.setText(level.equals("unknown")?t("数据不足，暂不判断状态","Not enough valid data to classify"):Monitoring.incomplete(r,now)?t("最近一次判断 · 数据缺失或过期","Last assessment · Data missing or stale"):t("依据后端 AI 分类与安全规则","Backend AI classification and safety rules"));
        errorText.setText(state.error.isEmpty()?"":t("更新失败，保留上次数据：","Update failed; retained data: ")+state.error);errorText.setVisibility(state.error.isEmpty()?View.GONE:View.VISIBLE);
        if(!page.equals("readings")||heartValue==null)return;
        Double current=r==null?null:Monitoring.current(r,r.hr,now),held=current==null?Monitoring.retainedHeart(r,now):null;heartValue.setText(number(current!=null?current:held,false)+" bpm");
        heartNote.setText(current!=null?(r.source.equals("backend")?t("合成测试读数","Synthetic test reading"):t("持续采集中 · 有效脉搏更新","Continuous acquisition · Accepted beat")):held!=null?t("上次有效值 · 不参与当前分类","Last valid value · Not used for current classification"):t("等待可靠脉搏","Waiting for a reliable pulse"));
        Double temp=r==null?null:Monitoring.current(r,r.temp,now);tempValue.setText(number(temp,true)+" °C");tempNote.setText(temp==null?t("暂无有效温度","No valid temperature"):t("表面测温 · 待校准","Surface reading · Calibration pending"));
        fallValue.setText(r!=null&&r.fall?t("检测到事件 · 请核实","Event detected · Needs review"):r!=null&&r.prediction.cnnSuspected?t("CNN 疑似跌倒 · 请核实","CNN suspected fall · Needs review"):r!=null&&Monitoring.fresh(r,now)&&r.fallGood?t("未检测到跌倒","No fall detected"):t("暂不可用","Unavailable"));
    }
    private void renderPage(){body.removeAllViews();heartValue=null;body.addView(text(title(),24,true));if(!page.equals("settings"))body.addView(text(state.patient==null?t("暂无授权患者","No authorized patient"):state.patient.name+" · "+state.patient.id,14,false));
        switch(page){case "readings":readings();break;case "history":history();break;case "charts":charts();break;case "ai":predictions();break;case "alerts":alerts();break;case "settings":settings();break;}updateReadings();}
    private String title(){switch(page){case "history":return t("历史记录","History");case "charts":return t("趋势图表","Trends");case "ai":return t("分类与置信度","Classification & confidence");case "alerts":return t("告警历史","Alert history");case "settings":return t("设置","Settings");default:return t("实时读数","Live readings");}}
    private void readings(){LinearLayout h=card(t("心率","HEART RATE"));heartValue=text("— bpm",42,true);heartNote=text("",13,false);h.addView(heartValue);h.addView(heartNote);
        LinearLayout temp=card(t("体温","TEMPERATURE"));tempValue=text("— °C",42,true);tempNote=text("",13,false);temp.addView(tempValue);temp.addView(tempNote);LinearLayout f=card(t("跌倒监测","FALL MONITORING"));fallValue=text("",20,true);f.addView(fallValue);
        Reading r=reading();if(r!=null){body.addView(text(t("采集时间：","Sample time: ")+clock(r.time),13,false));for(String reason:r.reasons)body.addView(text(reason,13,false));if(r.prediction!=null)prediction(card(t("当前模型结果","Current model output")),r.prediction);}}
    private void history(){body.addView(text(t("最近 10 分钟；过期数据仅用于历史回顾。","Last 10 minutes; older values are historical only."),13,false));if(state.history.isEmpty())body.addView(text(t("暂无历史数据","No history yet"),16,false));int count=0;for(Reading r:state.history){if(count++>=100)break;LinearLayout c=card(clock(r.time));c.addView(text(number(r.hr.value,false)+" bpm   ·   "+number(r.temp.value,true)+" °C",21,true));c.addView(text(Monitoring.label(r.level)+(r.hr.held?t(" · 心率为保留值"," · Heart rate held"):""),14,false));}}
    private void charts(){body.addView(text(t("每 5 秒汇总有效采样中位数；缺失处断线，不填造数据。","Valid sample median every 5 seconds. Missing data leaves a gap."),14,false));for(boolean heart:new boolean[]{true,false}){LinearLayout c=card(heart?t("心率 · bpm","Heart rate · bpm"):t("体温 · °C","Temperature · °C"));List<Monitoring.Point> points=Monitoring.chart(state.history,heart,System.currentTimeMillis());c.addView(new TrendView(this,points,heart),new LinearLayout.LayoutParams(-1,dp(220)));}}
    private void prediction(LinearLayout c,Prediction p){if(!p.state.equals("available")){c.addView(text(t("分类暂不可用","Classification unavailable"),18,true));c.addView(text(p.meaning,13,false));return;}c.addView(text(p.label.toUpperCase(Locale.US),24,true));c.addView(text(t("置信度 / 指示值：","Confidence / indicator: ")+(p.confidence==null?"—":String.format(Locale.US,"%.1f%%",p.confidence*100)),17,true));c.addView(text(p.meaning,13,false));c.addView(text(p.model,12,false));}
    private void predictions(){body.addView(text(t("CNN 检测疑似跌倒；LR 分类生命体征，安全规则处理严重异常。","CNN flags suspected falls; LR classifies vital signs, with safety rules for severe conditions."),14,false));if(state.predictions.isEmpty())body.addView(text(t("暂无模型输出","No model outputs yet"),16,false));int count=0;for(Prediction p:state.predictions){if(count++>=30)break;prediction(card(p.at.isEmpty()?"AI":clock(Models.timestamp(p.at))),p);}}
    private void alerts(){if(state.alerts.isEmpty())body.addView(text(t("暂无告警","No alerts"),16,false));for(Alert a:state.alerts){LinearLayout c=card(Monitoring.label(a.severity)+" · "+clock(Models.timestamp(a.time)));c.addView(text(a.summary,16,true));c.addView(text(a.status+(a.active?t(" · 条件仍存在"," · Condition active"):t(" · 条件已解除"," · Condition cleared")),13,false));if(state.session.role.equals("clinician")&&a.status.equals("new"))c.addView(button(t("确认已查看","Acknowledge"),()->controller.acknowledge(a.id)));}if(!state.session.role.equals("clinician"))body.addView(text(t("告警确认由护理人员处理。","Caregivers acknowledge alerts."),13,false));}
    private void settings(){LinearLayout c=card(t("账号与角色","Account & role"));c.addView(text(state.session.userId+" · "+state.session.role,19,true));c.addView(text(prefs.getString("url",""),13,false));
        body.addView(button(zh?"Switch to English":"切换为中文",()->{zh=!zh;prefs.edit().putBoolean("zh",zh).apply();shell();}));Switch toggle=new Switch(this);toggle.setText(t("前台每 5 秒自动刷新","Refresh every 5 seconds in foreground"));toggle.setChecked(auto);toggle.setPadding(dp(8),dp(14),dp(8),dp(14));toggle.setOnCheckedChangeListener((v,on)->{auto=on;prefs.edit().putBoolean("auto",auto).apply();if(on)controller.resume();else controller.pause();});body.addView(toggle);
        body.addView(text(t("更换服务器前请退出登录。密码不保存在手机中。图表数据和告警记录保存在后端 SQLite。","Sign out to change servers. Passwords are not stored on the phone. History and alerts persist in backend SQLite."),14,false));body.addView(button(t("退出登录","Sign out"),()->controller.logout()));}
}
