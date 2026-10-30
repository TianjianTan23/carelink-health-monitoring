package com.carelink.coursework;
import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
public class MainActivity extends BridgeActivity {
    @Override public void onCreate(Bundle savedInstanceState){registerPlugin(CareLinkApiPlugin.class);super.onCreate(savedInstanceState);}
}
