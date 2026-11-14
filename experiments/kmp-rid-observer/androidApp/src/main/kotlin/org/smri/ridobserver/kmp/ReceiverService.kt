package org.smri.ridobserver.kmp

import android.Manifest
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.location.LocationManager
import android.net.wifi.WifiManager
import android.os.*
import org.smri.ridobserver.core.*
import java.io.File
import java.util.UUID

/** Process-local model; never retains an Activity. All access is on the main looper. */
object ReceiverState {
    val engine=ObserverEngine()
    val textLog=RecentTextLog(50)
    var scanning=false
    var status="停止中"
    var scanCount=0
    var recording: CaptureSession?=null
    var lastCapture: File?=null
    var lastSession: CaptureSession?=null
    var lastSessionCsv:File?=null
    var callbacks=0
    var scanRequests=0
    var requestsRejected=0
    var lastNewUs:Long?=null
    var revision=0
    var screen="unknown"
    var directionStatus="端末方位：停止中"
    var locationStatus="自位置：停止中"
}

/** Visible-user-started location FGS; no boot restart, sticky restart, wake lock or scan bypass. */
class ReceiverService: Service() {
    private val handler=Handler(Looper.getMainLooper())
    private lateinit var wifi:WifiManager
    private var registered=false
    private var stopping=false
    private var intervalMs=30_000L
    private var receiverNodeId="unknown"
    private lateinit var database:ObservationDatabase
    private lateinit var direction:DirectionCapture
    private lateinit var locationCapture:ReceiverLocationCapture
    private val receiver=object:BroadcastReceiver() {
        override fun onReceive(context:Context?,intent:Intent?) {
            if(intent?.action==WifiManager.SCAN_RESULTS_AVAILABLE_ACTION) {
                readResults(intent.getBooleanExtra(WifiManager.EXTRA_RESULTS_UPDATED,false))
            }
        }
    }
    private val poll=object:Runnable {
        override fun run() {
            if(!ReceiverState.scanning) return
            try {
                checkAccess()
                ReceiverState.scanRequests++
                @Suppress("DEPRECATION") val accepted=wifi.startScan()
                if(!accepted) ReceiverState.requestsRejected++
                ReceiverState.status=if(accepted) "受信中 · 更新を要求" else "受信中 · OSの更新待ち"
                heartbeat("scan_request",mapOf("accepted" to accepted))
                updateNotification()
            } catch(e:SecurityException) { finish("access_denied:"+(e.message ?: "unspecified"));return }
            catch(e:Exception) { finish("scan_or_storage_error");return }
            handler.postDelayed(this,intervalMs)
        }
    }
    override fun onCreate() {
        super.onCreate();wifi=applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
        direction=DirectionCapture(this)
    }
    override fun onBind(intent:Intent?) : IBinder? = null
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
        if(intent?.action==ACTION_STOP) { finish("notification_stop");return START_NOT_STICKY }
        if(intent?.action!=ACTION_START) { stopSelf();return START_NOT_STICKY }
        try {
            database=ObservationDatabase.get(this)
            check(database.lastError==null && database.rowCount<100_000 && !database.exporting) {"Database unavailable or full"}
            receiverNodeId=intent.getStringExtra("node_id")?.takeIf {it.matches(Regex("[a-zA-Z0-9_-]{1,40}"))} ?: "unknown"
            intervalMs=getSharedPreferences("receiver",MODE_PRIVATE).getLong("scan_interval_ms",30_000)
            checkAccess()
            val nm=getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            if(Build.VERSION.SDK_INT>=26) nm.createNotificationChannel(NotificationChannel(CHANNEL,"Remote ID受信",NotificationManager.IMPORTANCE_LOW))
            if(Build.VERSION.SDK_INT>=29) startForeground(7,notification(),ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
            else startForeground(7,notification())
            if(ReceiverState.scanning) return START_NOT_STICKY
            current=this;stopping=false
            if(Build.VERSION.SDK_INT>=33) registerReceiver(receiver,IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION),Context.RECEIVER_NOT_EXPORTED)
            else registerReceiver(receiver,IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION))
            registered=true;ReceiverState.scanning=true;ReceiverState.status="受信中"
            locationCapture=ReceiverLocationCapture(this) {fix ->
                try {database.enqueueFix(fix,receiverNodeId) {if(current===this) finish("location_database_write_failed")}}
                catch(e:Exception) {finish("location_database_write_failed");return@ReceiverLocationCapture}
                ReceiverState.locationStatus=locationCapture.currentStatus();ReceiverState.revision++
            }
            locationCapture.start();ReceiverState.locationStatus=locationCapture.currentStatus()
            direction.start()
            readResults(false);handler.post(poll)
        } catch(e:SecurityException) { finish("access_denied:"+(e.message ?: "unspecified")) }
          catch(e:Exception) { finish("start_denied_or_failed:"+e.javaClass.simpleName) }
        return START_NOT_STICKY
    }
    private fun checkAccess() {
        if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED) throw SecurityException("fine_location_permission_denied")
        if(!PlatformCompat.locationEnabled(this)) throw SecurityException("location_services_disabled")
        if(!wifi.isWifiEnabled) throw SecurityException("wifi_disabled")
        if(!ScanPolicy.allowed(intervalMs,(PlatformCompat.scanThrottleEnabled(wifi) ?: true))) throw SecurityException("fast mode requires developer scan throttling off")
    }
    private fun readResults(updated:Boolean) {
        if(!ReceiverState.scanning) return
        try {
            checkAccess()
            @Suppress("DEPRECATION") val results=wifi.scanResults
            ReceiverState.scanCount=results.size;ReceiverState.callbacks++
            val delivered=SystemClock.elapsedRealtimeNanos()/1000;val now=System.currentTimeMillis()
            for(r in results) {
                val ies=PlatformCompat.informationElements(r)
                // Counts and exception types only; never log identifiers or payloads.
                android.util.Log.d("RidObserverCompat","ie_access=${ies.route} elements=${ies.elementCount} error=${ies.error ?: "none"}")
                val bodies=ies.bodies
                val observed=r.timestamp.takeIf {it>0}
                val utc=if(observed!=null && observed<=delivered) PlatformCompat.utc(now-(delivered-observed)/1000) else null
                val input=ScanInput(r.BSSID.lowercase(),r.level,r.frequency,observed,delivered,utc,bodies)
                for(raw in ReceiverState.engine.ingest(input,getSharedPreferences("receiver",MODE_PRIVATE).getBoolean("capture_unknown_wifi",false))) {
                    val o=locationCapture.annotate(direction.annotate(raw.withSourceRules(SourceRegistry(this).load())),delivered).copy(polledAtUtc=PlatformCompat.utc(now),ieAccess=mapOf("route" to ies.route,"element_count" to ies.elementCount,"error" to ies.error))
                    ReceiverState.engine.targets.values.firstOrNull {it.latest===raw}?.latest=o
                    if(!o.stale && o.decoded!=null) ReceiverState.lastNewUs= maxOf(ReceiverState.lastNewUs ?: 0, observed ?: 0)
                    database.enqueue(o,receiverNodeId) {
                        if(current===this) finish("database_write_failed")
                    }
                    ReceiverState.textLog.append(o)
                    ReceiverState.recording?.append(o)
                }
            }
            ReceiverState.revision++
            ReceiverState.directionStatus=direction.status
            ReceiverState.locationStatus=locationCapture.currentStatus()
            heartbeat("scan_callback",mapOf("results_updated" to updated))
            updateNotification()
        } catch(e:SecurityException) { finish("access_denied:"+(e.message ?: "unspecified")) }
        catch(e:CaptureLimitException) { finish("capture_size_limit") }
        catch(e:Exception) { finish("scan_or_storage_error") }
    }
    fun startRecording(nodeId:String) {
        if(!ReceiverState.scanning || ReceiverState.recording!=null) return
        try {
            val session=CaptureSession(filesDir,nodeId)
            ReceiverState.recording=session;ReceiverState.lastCapture=session.observations
            getSharedPreferences("receiver",MODE_PRIVATE).edit().putString("last_run",session.runId).apply()
            heartbeat("recording_started");updateNotification()
        } catch(e:Exception) { finish("recording_start_failed") }
    }
    fun stopRecording(reason:String="user_record_stop") {
        val session=ReceiverState.recording ?: return
        ReceiverState.recording=null;ReceiverState.lastCapture=session.observations;ReceiverState.lastSession=session;ReceiverState.lastSessionCsv=session.summary
        try {session.close(reason)} catch(e:Exception) {ReceiverState.status="記録終了の書込み失敗 · ログを確認"}
        updateNotification()
    }
    private fun heartbeat(kind:String,extra:Map<String,Any?> = emptyMap()) {
        val info=ActivityManager.MemoryInfo();(getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(info)
        val battery=registerReceiver(null,IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val pm=getSystemService(POWER_SERVICE) as PowerManager
        val fields=mapOf<String,Any?>("node_id" to receiverNodeId,
            "android_sdk" to Build.VERSION.SDK_INT,"device_model" to Build.MODEL,"app_version" to "0.11-permission-guide",
            "location_status" to ReceiverState.locationStatus,
            "fine_location_granted" to (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED),
            "location_enabled" to PlatformCompat.locationEnabled(this),
            "unknown_wifi_capture" to getSharedPreferences("receiver",MODE_PRIVATE).getBoolean("capture_unknown_wifi",false),
            "elapsed_us" to SystemClock.elapsedRealtimeNanos()/1000,
            "scan_results" to ReceiverState.scanCount,"callbacks" to ReceiverState.callbacks,
            "scan_requests" to ReceiverState.scanRequests,"request_interval_ms" to intervalMs,"scan_throttle_enabled" to PlatformCompat.scanThrottleEnabled(wifi),"scan_throttle_state_known" to (Build.VERSION.SDK_INT>=30),"requests_rejected" to ReceiverState.requestsRejected,
            "candidate_records" to ReceiverState.engine.records,"rid_records" to (ReceiverState.engine.records-ReceiverState.engine.invalidRecords),"duplicate_results" to ReceiverState.engine.duplicateResults,
            "invalid_records" to ReceiverState.engine.invalidRecords,"last_new_observation_us" to ReceiverState.lastNewUs,
            "screen_interactive" to pm.isInteractive,"activity_visible" to (ReceiverState.screen=="visible"),
            "device_idle" to pm.isDeviceIdleMode,"pss_kib" to Debug.getPss(),
            "process_cpu_ms" to Process.getElapsedCpuTime(),"available_memory_bytes" to info.availMem,
            "battery_level" to battery?.getIntExtra(BatteryManager.EXTRA_LEVEL,-1),
            "battery_scale" to battery?.getIntExtra(BatteryManager.EXTRA_SCALE,-1),
            "battery_plugged" to battery?.getIntExtra(BatteryManager.EXTRA_PLUGGED,-1)
        )+extra
        database.enqueueEvent(kind,fields) {if(current===this) finish("diagnostic_database_write_failed")}
        ReceiverState.recording?.event(kind,fields)
    }
    private fun notification():Notification {
        val open=PendingIntent.getActivity(this,0,Intent(this,MainActivity::class.java),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop=PendingIntent.getService(this,1,Intent(this,ReceiverService::class.java).setAction(ACTION_STOP),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val builder=if(Build.VERSION.SDK_INT>=26) Notification.Builder(this,CHANNEL) else Notification.Builder(this)
        return builder.setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("Remote ID ${if(ReceiverState.recording!=null) "受信・記録中" else "受信中"}")
            .setContentText("対象 ${ReceiverState.engine.targets.size}件 · タップで表示")
            .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
            .addAction(Notification.Action.Builder(null,"停止",stop).build()).build()
    }
    private fun updateNotification() {
        if(!stopping && ReceiverState.scanning) (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(7,notification())
    }
    fun finish(reason:String) {
        if(stopping) return
        stopping=true;handler.removeCallbacksAndMessages(null)
        if(::locationCapture.isInitialized) locationCapture.stop()
        ReceiverState.locationStatus="自位置：停止中"
        direction.stop();ReceiverState.directionStatus="端末方位：停止中"
        if(::database.isInitialized && database.lastError==null) {
            try {database.enqueueEvent("receiver_stopped",mapOf("reason" to reason,"elapsed_us" to SystemClock.elapsedRealtimeNanos()/1000)) {}} catch(e:Exception) { /* DB failure already visible */ }
        }
        if(registered) {unregisterReceiver(receiver);registered=false}
        ReceiverState.scanning=false;stopRecording(reason);ReceiverState.status="停止中 · $reason"
        current=null;stopForeground(STOP_FOREGROUND_REMOVE);stopSelf()
    }
    override fun onDestroy() {finish("service_destroyed");super.onDestroy()}
    companion object {
        const val ACTION_START="org.smri.ridobserver.kmp.START"
        const val ACTION_STOP="org.smri.ridobserver.kmp.STOP"
        const val CHANNEL="rid_capture"
        var current:ReceiverService?=null;private set
    }
}

class CaptureLimitException:Exception()
/** Append-only owner-only captures. A completed session_end marks a clean close; an absent/partial end is interrupted or unknown. */
class CaptureSession(root:File,val nodeId:String,private val maxBytes:Long=20L*1024*1024) {
    val runId=UUID.randomUUID().toString()
    private val dir=File(root,"captures/$runId")
    val observations=File(dir,"observations.jsonl")
    private val events=File(dir,"events.jsonl")
    val summary=File(dir,"summary.csv")
    private val sessionEngine=ObserverEngine()
    var count=0;private set
    private var closed=false
    private val budget=CaptureBudget(maxBytes,32768)
    init {
        val captures=File(root,"captures")
        check(root.usableSpace>64L*1024*1024) {"insufficient free space"}
        check((captures.walkTopDown().filter {it.isFile}.sumOf {it.length()}) <= 108L*1024*1024) {"capture archive limit; export and manage existing captures"}
        check(dir.mkdirs());android.system.Os.chmod(dir.parentFile!!.absolutePath,448);android.system.Os.chmod(dir.absolutePath,448)
        for(f in listOf(observations,events,summary)) {check(f.createNewFile());android.system.Os.chmod(f.absolutePath,384)}
        event("session_start",mapOf("schema" to "rid_capture_events_v1","node_id" to nodeId,"run_id" to runId,
            "software_version" to BuildConfigVersion.value,"source_type" to "real_capture","physical_packet_match" to "unconfirmed"))
    }
    private fun write(file:File,text:String,reserved:Boolean=false) {
        val bytes=text.toByteArray(Charsets.UTF_8)
        if(!budget.allows(observations.length()+events.length()+summary.length(),bytes.size.toLong(),reserved)) throw CaptureLimitException()
        file.appendBytes(bytes)
    }
    fun append(o:Observation) {
        check(!closed);write(observations,o.toJson(nodeId,runId)+"\n");count++
        // Independent per-recording summary; global de-duplication happened before this call.
        sessionEngine.ingest(ScanInput(o.sourceKey,o.rssiDbm,o.frequencyMhz,o.observedUs,
            if(o.stale) null else o.observedUs,o.receivedAtUtc,listOf(o.body),o.sourceType))
    }
    fun event(kind:String,extra:Map<String,Any?>) {
        check(!closed);write(events,json(mapOf("event" to kind,"utc" to PlatformCompat.utc())+extra)+"\n")
    }
    fun csv():String=sessionEngine.summaryCsv()
    fun close(reason:String) {
        if(closed) return
        write(summary,csv(),true)
        write(events,json(mapOf("event" to "session_end","utc" to PlatformCompat.utc(),"reason" to reason,"recorded_observations" to count))+"\n",true)
        closed=true
    }
}
private object BuildConfigVersion {const val value="0.11-permission-guide"}
