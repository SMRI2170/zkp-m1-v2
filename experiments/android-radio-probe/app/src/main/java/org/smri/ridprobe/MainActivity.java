package org.smri.ridprobe;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.*;
import android.bluetooth.le.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.hardware.*;
import android.location.LocationManager;
import android.net.wifi.WifiManager;
import android.os.*;
import android.ranging.RangingManager;
import android.ranging.RangingCapabilities;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.*;

/** Independent foreground-only RF/heading probe. No Internet permission, no transmitter. */
public final class MainActivity extends Activity implements SensorEventListener {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ArrayList<RadioMath.Heading> headings=new ArrayList<>();
    private final LinkedHashMap<String,Target> targets=new LinkedHashMap<>();
    private final HashMap<String,Long> wifiStamps=new HashMap<>();
    private final JSONArray errors=new JSONArray();private JSONObject rangingCaps=new JSONObject();
    private final String salt=UUID.randomUUID().toString();
    private File sessionDir;private BufferedWriter log;private SensorManager sensors;private WifiManager wifi;
    private BluetoothLeScanner ble;private RangingManager ranging;
    private RangingManager.RangingCapabilitiesCallback rangingCallback;
    private boolean running=false,registered=false;private long startedNanos,lastSampleHeading;
    private long activeNanos=0;private Runnable timedStop;
    private double heading=Double.NaN;private int sensorAccuracy=0;
    private long blePackets=0,wifiReads=0,wifiRows=0,wifiUnique=0,wifiFreshBroadcasts=0,wifiVendor=0,wifiIE=0,wifiRid=0,bleRid=0;
    private long scanRequests=0,scanAccepted=0,poseRejected=0,stored=0,droppedTargets=0;
    private TextView status,headingView,resultView;private Spinner selector;private ArrayAdapter<String> targetAdapter;
    private final ArrayList<String> targetKeys=new ArrayList<>();private String selected=null;
    private EditText knownBearing;private int scanIntervalMs=35_000;
    private static final ParcelUuid ODID=new ParcelUuid(UUID.fromString("0000fffa-0000-1000-8000-00805f9b34fb"));
    private static final class Target {
        final String key,label,kind;final ArrayList<RadioMath.Sample> samples=new ArrayList<>();
        long lastStamp=0;int rssi;boolean rid;int frequency;
        Target(String k,String l,String type){key=k;label=l;kind=type;}
    }
    private JSONObject json(Object... pairs) {
        JSONObject o=new JSONObject();try{for(int i=0;i<pairs.length;i+=2){Object v=pairs[i+1];
            if(v instanceof Double && !Double.isFinite((double)v))v=JSONObject.NULL;
            o.put(String.valueOf(pairs[i]),v==null?JSONObject.NULL:v);}}
        catch(JSONException e){throw new IllegalStateException(e);}return o;
    }
    private String alias(String key) {
        try{byte[] hash=MessageDigest.getInstance("SHA-256").digest((salt+key).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return String.format(Locale.ROOT,"%02x%02x%02x",hash[0]&255,hash[1]&255,hash[2]&255);}
        catch(Exception e){throw new IllegalStateException(e);}
    }
    private void event(String type,JSONObject data) {
        try{data.put("type",type);data.put("recorded_elapsed_nanos",SystemClock.elapsedRealtimeNanos());
            log.write(data.toString());log.newLine();stored++;}
        catch(Exception e){errors.put(json("stage","write_event","error",e.getClass().getSimpleName()));}
    }
    private void failure(String stage,Exception e) {errors.put(json("stage",stage,"error",e.getClass().getSimpleName()));}
    private boolean granted(String name){return checkSelfPermission(name)==PackageManager.PERMISSION_GRANTED;}
    private boolean feature(String name){return getPackageManager().hasSystemFeature(name);}
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        sessionDir=new File(getFilesDir(),"sessions/run-"+System.currentTimeMillis());sessionDir.mkdirs();
        try{log=new BufferedWriter(new OutputStreamWriter(new FileOutputStream(new File(sessionDir,"observations.jsonl")),java.nio.charset.StandardCharsets.UTF_8));}
        catch(IOException e){throw new IllegalStateException(e);}
        sensors=(SensorManager)getSystemService(SENSOR_SERVICE);wifi=(WifiManager)getApplicationContext().getSystemService(WIFI_SERVICE);
        LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(24,24,24,24);
        body.setOnApplyWindowInsetsListener((v,insets)->{android.graphics.Insets safe=insets.getInsets(WindowInsets.Type.systemBars());v.setPadding(24,24+safe.top,24,24+safe.bottom);return insets;});
        ScrollView scroll=new ScrollView(this);scroll.addView(body);setContentView(scroll);
        text(body,"RID方向検証",24);text(body,"RSSI＋端末姿勢の実験。位相AoA・機体認証ではありません。",14);
        LinearLayout buttons=row(body);button(buttons,"権限",()->requestRadioPermissions());button(buttons,"受信開始",this::start);button(buttons,"停止",()->stop("user"));
        LinearLayout second=row(body);button(second,"Wi-Fiスキャン",this::scanWifi);button(second,"機能確認",this::capabilities);
        status=text(body,"準備中",14);headingView=text(body,"方位待機中",16);
        text(body,"対象（識別子は画面では一時ハッシュ）",15);
        selector=new Spinner(this);targetAdapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new ArrayList<>()){
            private View label(View view,int position){if(position<targetKeys.size()){Target t=targets.get(targetKeys.get(position));if(t!=null)((TextView)view).setText(t.kind+" "+t.label+" "+t.rssi+"dBm / "+t.samples.size()+"点"+(t.rid?" RID候補":""));}return view;}
            @Override public View getView(int position,View old,ViewGroup parent){return label(super.getView(position,old,parent),position);}
            @Override public View getDropDownView(int position,View old,ViewGroup parent){return label(super.getDropDownView(position,old,parent),position);}
        };selector.setAdapter(targetAdapter);body.addView(selector);
        selector.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> p){}
            public void onItemSelected(AdapterView<?> p,View v,int i,long id){if(i<targetKeys.size())selected=targetKeys.get(i);showEstimate();}
        });
        text(body,"水平に持ち、同じ場所でゆっくり1周。まずBLEで試してください。Wi-Fiは制限により24点集めるのに約12〜15分かかる場合があります。",15);
        LinearLayout third=row(body);button(third,"方向推定",this::showEstimate);button(third,"対象データをリセット",()->{Target t=targets.get(selected);if(t!=null)t.samples.clear();showEstimate();});
        resultView=text(body,"24点・6方位区画・270°以上の回転が必要です。",16);
        knownBearing=new EditText(this);knownBearing.setHint("既知の送信方向（磁北基準 0〜359°）");knownBearing.setInputType(android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);body.addView(knownBearing);
        LinearLayout fourth=row(body);button(fourth,"方向補正を校正",this::calibrate);button(fourth,"別データで誤差を記録",this::validateBearing);
        text(body,"校正前は「RSSIが最大となる端末方位」です。送信元の方角とは限りません。校正後も任意の電力変更・移動・反射には保証がありません。",14);
        event("session",json("model",Build.MODEL,"android",Build.VERSION.RELEASE,"sdk",Build.VERSION.SDK_INT,"scope","local research only; no authenticated aircraft"));
        capabilities();render();
        if(getIntent().getBooleanExtra("auto_start",false))handler.postDelayed(()->start(getIntent().getIntExtra("duration_s",0)),500);
    }
    private TextView text(LinearLayout parent,String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setPadding(0,8,0,8);parent.addView(t);return t;}
    private LinearLayout row(LinearLayout parent){LinearLayout row=new LinearLayout(this);parent.addView(row);return row;}
    private void button(LinearLayout parent,String label,Runnable action){Button b=new Button(this);b.setText(label);b.setTextSize(13);parent.addView(b,new LinearLayout.LayoutParams(0,ViewGroup.LayoutParams.WRAP_CONTENT,1));b.setOnClickListener(v->action.run());}
    private void requestRadioPermissions(){
        ArrayList<String> names=new ArrayList<>(Arrays.asList(Manifest.permission.ACCESS_COARSE_LOCATION,Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.BLUETOOTH_SCAN,Manifest.permission.BLUETOOTH_CONNECT));
        if(Build.VERSION.SDK_INT>=33)names.add("android.permission.NEARBY_WIFI_DEVICES");
        if(Build.VERSION.SDK_INT>=36)names.add("android.permission.RANGING");
        requestPermissions(names.toArray(new String[0]),7);
    }
    @Override public void onRequestPermissionsResult(int c,String[] p,int[] g){super.onRequestPermissionsResult(c,p,g);capabilities();render();}
    private void capabilities(){
        JSONObject caps=json("uwb_feature",feature("android.hardware.uwb"),"wifi_rtt_feature",feature("android.hardware.wifi.rtt"),
            "wifi_aware_feature",feature("android.hardware.wifi.aware"),"ble_feature",feature("android.hardware.bluetooth_le"),
            "rotation_vector",sensors.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)!=null,
            "ble_public_cte_iq_path","not exposed by this app's ordinary BLE ScanResult API",
            "wifi_public_per_antenna_csi_path","not exposed by WifiManager scan results",
            "phase_aoa_session","not started; no compatible peer or raw-IQ path");
        try{BluetoothAdapter adapter=getSystemService(BluetoothManager.class).getAdapter();if(adapter!=null){caps.put("bluetooth_enabled",adapter.isEnabled());caps.put("coded_phy_flag",adapter.isLeCodedPhySupported());caps.put("extended_advertising_flag",adapter.isLeExtendedAdvertisingSupported());}}
        catch(Exception e){failure("bluetooth_capabilities",e);}
        try{if(rangingCaps.has("ranging_api"))caps.put("ranging_api",rangingCaps.get("ranging_api"));}catch(JSONException e){failure("copy_caps",e);}
        event("capabilities",caps);rangingCaps=caps;
        if(Build.VERSION.SDK_INT>=36 && granted("android.permission.RANGING")){
            try{
                ranging=getSystemService(RangingManager.class);
                if(ranging!=null && rangingCallback==null){rangingCallback=c->{
                    JSONObject availability=new JSONObject();
                    for(int tech:new int[]{RangingManager.UWB,RangingManager.BLE_CS,RangingManager.WIFI_NAN_RTT,RangingManager.BLE_RSSI}){
                        String label=tech==RangingManager.UWB?"uwb":tech==RangingManager.BLE_CS?"ble_channel_sounding":tech==RangingManager.WIFI_NAN_RTT?"wifi_nan_rtt":"ble_rssi";
                        int value=c.getTechnologyAvailability().getOrDefault(tech,RangingCapabilities.NOT_SUPPORTED);
                        String name=value==RangingCapabilities.ENABLED?"ENABLED":value==RangingCapabilities.NOT_SUPPORTED?"NOT_SUPPORTED":value==RangingCapabilities.DISABLED_USER?"DISABLED_USER":value==RangingCapabilities.DISABLED_REGULATORY?"DISABLED_REGULATORY":"OTHER_DISABLED";
                        try{availability.put(label,name);}catch(JSONException e){failure("availability",e);}
                    }
                    JSONObject report=json("availability",availability,
                        "uwb_capabilities_present",c.getUwbCapabilities()!=null,"cs_capabilities_present",c.getCsCapabilities()!=null);
                    if(c.getUwbCapabilities()!=null)try{report.put("uwb_azimuth",c.getUwbCapabilities().isAzimuthalAngleSupported());report.put("uwb_elevation",c.getUwbCapabilities().isElevationAngleSupported());}catch(Exception e){failure("uwb_caps",e);}
                    try{rangingCaps.put("ranging_api",report);}catch(JSONException e){failure("ranging_json",e);}
                    event("ranging_capabilities",report);render();
                };ranging.registerCapabilitiesCallback(getMainExecutor(),rangingCallback);}
            }catch(Exception e){failure("ranging_capabilities",e);}
        }
        render();
    }
    private final BroadcastReceiver wifiReceiver=new BroadcastReceiver(){@Override public void onReceive(Context c,Intent i){
        if(!running)return;boolean fresh=i.getBooleanExtra(WifiManager.EXTRA_RESULTS_UPDATED,false);
        if(fresh)wifiFreshBroadcasts++;readWifi(fresh);render();
    }};
    private final Runnable scanLoop=new Runnable(){public void run(){if(running){scanWifi();handler.postDelayed(this,scanIntervalMs);}}};
    private final Runnable uiLoop=new Runnable(){public void run(){if(running){render();handler.postDelayed(this,2000);}}};
    private void start(){start(0);}
    private void start(int duration){
        if(running)return;
        if(!granted(Manifest.permission.ACCESS_FINE_LOCATION)||!granted(Manifest.permission.BLUETOOTH_SCAN)){requestRadioPermissions();return;}
        capabilities();running=true;startedNanos=SystemClock.elapsedRealtimeNanos();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        Sensor sensor=sensors.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR);
        if(sensor!=null)sensors.registerListener(this,sensor,SensorManager.SENSOR_DELAY_GAME);
        if(!registered){registerReceiver(wifiReceiver,new IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION),Context.RECEIVER_EXPORTED);registered=true;}
        try{BluetoothAdapter adapter=getSystemService(BluetoothManager.class).getAdapter();
            if(adapter!=null && adapter.isEnabled()){ble=adapter.getBluetoothLeScanner();
                ScanSettings.Builder settings=new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY);
                if(adapter.isLeExtendedAdvertisingSupported())settings.setLegacy(false).setPhy(ScanSettings.PHY_LE_ALL_SUPPORTED);
                ble.startScan(null,settings.build(),bleCallback);}}
        catch(Exception e){failure("ble_start",e);}
        event("start",json("location_enabled",getSystemService(LocationManager.class).isLocationEnabled(),"wifi_enabled",wifi.isWifiEnabled()));
        readWifi(false);handler.post(scanLoop);handler.post(uiLoop);
        if(duration>0){timedStop=()->stop("timer");handler.postDelayed(timedStop,duration*1000L);}
    }
    private void stop(String reason){
        if(timedStop!=null){handler.removeCallbacks(timedStop);timedStop=null;}
        if(running){running=false;handler.removeCallbacks(scanLoop);handler.removeCallbacks(uiLoop);sensors.unregisterListener(this);
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            if(ble!=null)try{ble.stopScan(bleCallback);}catch(Exception e){failure("ble_stop",e);}
            if(registered){unregisterReceiver(wifiReceiver);registered=false;}
            long elapsed=SystemClock.elapsedRealtimeNanos()-startedNanos;activeNanos+=elapsed;
            event("stop",json("duration_s",elapsed/1e9,"reason",reason));}
        render();try{log.flush();}catch(IOException e){failure("flush",e);}
    }
    private void scanWifi(){
        if(!running)return;try{scanRequests++;boolean accepted=wifi.startScan();if(accepted)scanAccepted++;
            event("wifi_scan_request",json("accepted",accepted,"note","false can mean throttling or scan failure; cached results are not new samples"));}
        catch(Exception e){failure("wifi_scan",e);}render();
    }
    private static String hex(byte[] data){StringBuilder b=new StringBuilder();for(byte v:data)b.append(String.format(Locale.ROOT,"%02x",v&255));return b.toString();}
    private void readWifi(boolean updated){
        try{wifiReads++;for(android.net.wifi.ScanResult sr:wifi.getScanResults()){
            wifiRows++;String key="wifi:"+sr.BSSID+":"+sr.frequency;
            JSONArray ies=new JSONArray();int rid=0;
            if(sr.getInformationElements()!=null)for(android.net.wifi.ScanResult.InformationElement ie:sr.getInformationElements()){
                ByteBuffer buffer=ie.getBytes().duplicate();byte[] body=new byte[buffer.remaining()];buffer.get(body);
                wifiIE++;if(ie.getId()==221)wifiVendor++;rid+=RadioMath.wifiRidCount(ie.getId(),body);
                ies.put(json("id",ie.getId(),"id_ext",ie.getIdExt(),"body_hex",hex(body)));
            }
            long stamp=sr.timestamp*1000L;boolean unique=stamp>wifiStamps.getOrDefault(key,0L);
            if(unique){wifiUnique++;wifiStamps.put(key,stamp);}
            if(rid>0 && unique)wifiRid++;
            String sampleStatus="cached_or_scan_not_updated";
            if(unique && updated)sampleStatus=sample(key,"Wi-Fi",stamp,sr.level,rid>0,sr.frequency);
            event("wifi_observation",json("key",key,"rssi_dbm",sr.level,"frequency_mhz",sr.frequency,"observed_elapsed_nanos",stamp,
                "read_age_s",(SystemClock.elapsedRealtimeNanos()-stamp)/1e9,"fresh_broadcast",updated,"unique_timestamp",unique,
                "sample_status",sampleStatus,"rid_syntax_messages",rid,"ies",ies));
        }}catch(Exception e){failure("wifi_read",e);}
    }
    private final ScanCallback bleCallback=new ScanCallback(){
        @Override public void onScanFailed(int code){event("ble_scan_failed",json("code",code));errors.put(json("stage","ble_scan_failed","code",code));render();}
        @Override public void onScanResult(int type,android.bluetooth.le.ScanResult sr){if(!running)return;
            blePackets++;try{
                String key="ble:"+sr.getDevice().getAddress()+":"+sr.getPrimaryPhy()+":"+sr.getSecondaryPhy();int rid=0;String raw="";
                ScanRecord record=sr.getScanRecord();
                if(record!=null){byte[] data=record.getServiceData(ODID);raw=hex(record.getBytes());
                    if(data!=null && data.length>2 && (data[0]&255)==0x0d)rid=RadioMath.messageCount(Arrays.copyOfRange(data,2,data.length));}
                if(rid>0)bleRid++;
                String accepted=sample(key,"BLE",sr.getTimestampNanos(),sr.getRssi(),rid>0,0);
                event("ble_observation",json("key",key,"rssi_dbm",sr.getRssi(),"observed_elapsed_nanos",sr.getTimestampNanos(),
                    "primary_phy",sr.getPrimaryPhy(),"secondary_phy",sr.getSecondaryPhy(),"rid_syntax_messages",rid,"sample_status",accepted,"advertisement_hex",raw));
            }catch(Exception e){failure("ble_result",e);}
        }
    };
    private String sample(String key,String kind,long stamp,int rssi,boolean rid,int frequency){
        Target target=targets.get(key);
        if(target==null){if(targets.size()>=300){droppedTargets++;return "target_limit";}
            target=new Target(key,alias(key),kind);targets.put(key,target);targetKeys.add(key);
            targetAdapter.add(kind+" "+target.label+" "+rssi+"dBm"+(rid?" RID候補":""));if(selected==null)selected=key;}
        target.rssi=rssi;target.rid|=rid;target.frequency=frequency;
        if(stamp<=target.lastStamp || stamp-target.lastStamp<250_000_000L)return "duplicate_or_dense";
        target.lastStamp=stamp;
        RadioMath.Heading h=RadioMath.nearest(headings,stamp,250_000_000L);
        if(h==null){poseRejected++;return "missing_unreliable_or_nonhorizontal_heading";}
        if(target.samples.size()>=1200)target.samples.remove(0);
        target.samples.add(new RadioMath.Sample(stamp,h.degrees(),rssi));return "used_for_rotation_fit";
    }
    @Override public void onSensorChanged(SensorEvent e){
        if(!running || e.timestamp-lastSampleHeading<50_000_000L)return;lastSampleHeading=e.timestamp;
        float[] matrix=new float[9],ori=new float[3];SensorManager.getRotationMatrixFromVector(matrix,e.values);SensorManager.getOrientation(matrix,ori);
        sensorAccuracy=e.accuracy;
        heading=RadioMath.wrap(Math.toDegrees(ori[0]));boolean level=Math.abs(Math.toDegrees(ori[1]))<25 && Math.abs(Math.toDegrees(ori[2]))<25;
        boolean usable=level && sensorAccuracy>SensorManager.SENSOR_STATUS_UNRELIABLE;
        headings.add(new RadioMath.Heading(e.timestamp,heading,usable));
        while(headings.size()>7200)headings.remove(0);
        event("heading",json("observed_elapsed_nanos",e.timestamp,"magnetic_heading_deg",heading,"pitch_deg",Math.toDegrees(ori[1]),"roll_deg",Math.toDegrees(ori[2]),"accuracy",sensorAccuracy,"usable",usable));
    }
    @Override public void onAccuracyChanged(Sensor s,int accuracy){sensorAccuracy=accuracy;}
    private JSONObject estimateJson(Target target){
        RadioMath.Result r=RadioMath.fit(target.samples);
        String pref="offset:"+target.key;boolean calibrated=getPreferences(MODE_PRIVATE).contains(pref);
        double offset=getPreferences(MODE_PRIVATE).getFloat(pref,0);
        return json("status",r.status(),"n",r.count(),"bins",r.bins(),"coverage_deg",r.coverageDeg(),
            "peak_phone_heading_magnetic_deg",r.peakHeadingDeg(),"amplitude_db",r.amplitudeDb(),"directional_r2",r.directionalR2(),
            "residual_sd_db",r.residualSdDb(),"calibrated",calibrated,
            "bearing_magnetic_deg",calibrated && r.status().equals("EXPERIMENTAL_PEAK")?RadioMath.wrap(r.peakHeadingDeg()+offset):null,
            "accuracy_claim","none; held-out physical ground truth required");
    }
    private void showEstimate(){
        if(resultView==null)return;Target target=targets.get(selected);
        if(target==null){resultView.setText("対象の新しい受信データを待っています。");return;}
        RadioMath.Result r=RadioMath.fit(target.samples);
        String message=target.kind+" "+target.label+" / "+(target.rid?"RID形式候補":"一般電波・RID未検出")+"\n";
        message+=String.format(Locale.JAPAN,"使用%d点、%d/8区画、回転範囲%.0f°\n",r.count(),r.bins(),r.coverageDeg());
        if(!r.status().equals("EXPERIMENTAL_PEAK"))message+="推定不可："+(r.status().equals("INSUFFICIENT_ROTATION")?"回転範囲または受信数が不足":r.status().equals("WEAK_DIRECTIONAL_SIGNAL")?"方向による電波の違いが不明瞭":"データが偏り計算できません");
        else{
            message+=String.format(Locale.JAPAN,"RSSI最大の端末方位 %.0f°（磁北）\n振幅 %.1fdB / 方向成分R² %.2f\n",r.peakHeadingDeg(),r.amplitudeDb(),r.directionalR2());
            String pref="offset:"+target.key;
            if(getPreferences(MODE_PRIVATE).contains(pref))message+=String.format(Locale.JAPAN,"校正後の方向推定 %.0f°（精度未確認）",RadioMath.wrap(r.peakHeadingDeg()+getPreferences(MODE_PRIVATE).getFloat(pref,0)));
            else message+="送信元の方向は未校正。実際の誤差はまだ測れていません。";
        }
        resultView.setText(message);
    }
    private double known(){double b=Double.parseDouble(knownBearing.getText().toString());if(!Double.isFinite(b)||b<0||b>=360)throw new IllegalArgumentException();return b;}
    private void calibrate(){
        try{Target t=targets.get(selected);if(t==null)throw new IllegalStateException();RadioMath.Result r=RadioMath.fit(t.samples);
            if(!r.status().equals("EXPERIMENTAL_PEAK"))throw new IllegalStateException();double truth=known();
            getPreferences(MODE_PRIVATE).edit().putFloat("offset:"+t.key,(float)RadioMath.error(truth,r.peakHeadingDeg())).apply();
            event("calibration",json("key",t.key,"known_magnetic_bearing_deg",truth,"fit",estimateJson(t)));
            t.samples.clear();Toast.makeText(this,"補正を保存。別の1周で評価してください。",Toast.LENGTH_LONG).show();showEstimate();
        }catch(Exception e){Toast.makeText(this,"有効な推定と既知方向0〜359°が必要です。",Toast.LENGTH_LONG).show();}
    }
    private void validateBearing(){
        try{Target t=targets.get(selected);if(t==null || !getPreferences(MODE_PRIVATE).contains("offset:"+t.key))throw new IllegalStateException();
            RadioMath.Result r=RadioMath.fit(t.samples);if(!r.status().equals("EXPERIMENTAL_PEAK"))throw new IllegalStateException();
            double truth=known(),estimated=RadioMath.wrap(r.peakHeadingDeg()+getPreferences(MODE_PRIVATE).getFloat("offset:"+t.key,0));
            double error=Math.abs(RadioMath.error(estimated,truth));
            event("heldout_validation",json("key",t.key,"truth_magnetic_deg",truth,"estimated_deg",estimated,"absolute_error_deg",error,"fit",estimateJson(t)));
            Toast.makeText(this,String.format(Locale.JAPAN,"今回の誤差 %.1f°。反復評価が必要です。",error),Toast.LENGTH_LONG).show();
        }catch(Exception e){Toast.makeText(this,"先に校正し、別の回転データと正解方向を用意してください。",Toast.LENGTH_LONG).show();}
    }
    private void render(){
        if(status==null)return;
        int fitted=0,usableSamples=0;JSONArray targetSummary=new JSONArray();
        for(Target t:targets.values()){RadioMath.Result r=RadioMath.fit(t.samples);if(r.status().equals("EXPERIMENTAL_PEAK"))fitted++;usableSamples+=r.count();
            targetSummary.put(json("alias",t.label,"kind",t.kind,"rid_syntax",t.rid,"frequency_mhz",t.frequency,"estimate",estimateJson(t)));}
        JSONObject summary=json("schema","rid-radio-probe-v1","model",Build.MODEL,"android",Build.VERSION.RELEASE,"sdk",Build.VERSION.SDK_INT,
            "running",running,"active_duration_s",(activeNanos+(running?SystemClock.elapsedRealtimeNanos()-startedNanos:0))/1e9,
            "capabilities",rangingCaps,"wifi_scan_requests",scanRequests,"wifi_scan_accepted",scanAccepted,
            "wifi_read_callbacks",wifiReads,"wifi_rows_including_cache",wifiRows,"wifi_unique_scan_timestamps",wifiUnique,
            "wifi_fresh_broadcasts",wifiFreshBroadcasts,"wifi_information_elements",wifiIE,"wifi_vendor_elements",wifiVendor,
            "wifi_rid_observations",wifiRid,"ble_packets",blePackets,"ble_rid_observations",bleRid,"heading_count",headings.size(),
            "pose_rejected",poseRejected,"rotation_samples",usableSamples,"fitted_targets",fitted,"targets",targetSummary,
            "errors",errors,"stored_events",stored,"target_limit_rejections",droppedTargets,
            "scope","RF reception diagnostics; neither location authenticity nor verified AoA accuracy");
        try{File tmp=new File(sessionDir,"summary.json.tmp");try(FileWriter w=new FileWriter(tmp)){w.write(summary.toString(2));}
            File output=new File(sessionDir,"summary.json");if(!tmp.renameTo(output))throw new IOException("summary rename failed");
            try(FileWriter w=new FileWriter(new File(getFilesDir(),"latest-session.txt"))){w.write(sessionDir.getName());}log.flush();}
        catch(Exception e){failure("summary",e);}
        status.setText((running?"受信中":"停止中")+"\nWi-Fi: 新規時刻 "+wifiUnique+" / IE "+wifiIE+" / Vendor IE "+wifiVendor+" / RID候補 "+wifiRid+
            "\nBLE: "+blePackets+" / RID候補 "+bleRid+"\nUWB: "+feature("android.hardware.uwb")+" / エラー "+errors.length());
        headingView.setText(Double.isFinite(heading)?String.format(Locale.JAPAN,"端末方位 %.0f°（磁北）／姿勢センサ精度状態 %d",heading,sensorAccuracy):"方位センサ待機中");
        targetAdapter.notifyDataSetChanged();showEstimate();
    }
    @Override protected void onPause(){stop("activity_paused");super.onPause();}
    @Override protected void onDestroy(){
        stop("destroyed");if(Build.VERSION.SDK_INT>=36 && ranging!=null && rangingCallback!=null)try{ranging.unregisterCapabilitiesCallback(rangingCallback);}catch(Exception e){failure("ranging_unregister",e);}
        try{log.close();}catch(IOException e){failure("close",e);}super.onDestroy();
    }
}
