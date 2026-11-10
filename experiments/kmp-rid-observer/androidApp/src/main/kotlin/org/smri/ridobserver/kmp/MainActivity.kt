package org.smri.ridobserver.kmp

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.*
import android.content.pm.PackageManager
import android.graphics.*
import android.graphics.drawable.GradientDrawable
import android.location.LocationManager
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import android.os.*
import android.provider.Settings
import android.view.*
import android.widget.*
import org.smri.ridobserver.core.*
import java.io.File
import java.time.Instant
import java.util.UUID

/** Android I/O and UI only. Decoding, de-duplication and JSON/CSV are shared KMP. */
class MainActivity : Activity() {
    private val navy=Color.rgb(16,39,73)
    private val blue=Color.rgb(29,78,216)
    private val handler=Handler(Looper.getMainLooper())
    private val engine get()=ReceiverState.engine
    private val scanning get()=ReceiverState.scanning
    private val recording get()=ReceiverState.recording
    private val lastCapture get()=ReceiverState.lastCapture
    private val lastScanCount get()=ReceiverState.scanCount
    private lateinit var status:TextView
    private lateinit var counts:TextView
    private lateinit var start:Button
    private lateinit var record:Button
    private lateinit var list:LinearLayout
    private lateinit var chart:RssiChart
    private lateinit var nodeText:TextView
    private lateinit var scanConfig:TextView
    private var selected:String?=null
    private var pendingExport:String?=null
    private var exportBytes:ByteArray?=null
    private var exportFile:File?=null
    private var notificationAsked=false
    private var renderedState:String?=null
    private val refresh=object:Runnable {
        override fun run() {
            val now=SystemClock.elapsedRealtimeNanos()/1000
            val signature=listOf(ReceiverState.revision,scanning,recording?.count,ReceiverState.status,
                engine.targets.values.count {it.latest.isStaleAt(now)},selected).joinToString("|")
            // Do not rebuild an unchanged view tree every second: it prevents UI-idle and wastes work.
            if(signature!=renderedState) {renderedState=signature;render()}
            handler.postDelayed(this,1000)
        }
    }
    private val nodeId:String get()=getPreferences(MODE_PRIVATE).getString("node_id",null) ?: run {
        val id="phone-"+UUID.randomUUID().toString().take(8)
        getPreferences(MODE_PRIVATE).edit().putString("node_id",id).apply();id
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val saved=getSharedPreferences("receiver",MODE_PRIVATE).getString("last_run",null)
        if(ReceiverState.lastCapture==null && saved!=null && saved.matches(Regex("[0-9a-f-]{36}"))) {
            val dir=File(filesDir,"captures/$saved")
            ReceiverState.lastCapture=File(dir,"observations.jsonl").takeIf {it.isFile}
            ReceiverState.lastSessionCsv=File(dir,"summary.csv").takeIf {it.isFile && it.length()>0}
        }
        val root=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setBackgroundColor(Color.rgb(245,247,251)) }
        root.setOnApplyWindowInsetsListener { view,insets ->
            val bars=insets.getInsets(WindowInsets.Type.systemBars())
            view.setPadding(dp(18),bars.top+dp(18),dp(18),bars.bottom+dp(12));insets
        }
        root.addView(label("Remote ID 受信",25,navy,true))
        status=label("停止中",14,Color.DKGRAY);root.addView(status)
        counts=label("Wi-Fi 0件  /  RID 0件",19,navy,true);root.addView(counts,params(WRAP,14))
        val actions=LinearLayout(this)
        start=button("受信開始") { if(scanning) stopScan() else requestStart() }
        record=button("記録開始") { if(recording==null) startRecording() else stopRecording() }
        record.isEnabled=false
        actions.addView(start,LinearLayout.LayoutParams(0,dp(52),1f))
        actions.addView(record,LinearLayout.LayoutParams(0,dp(52),1f))
        actions.addView(button("書き出し") { exportDialog() },LinearLayout.LayoutParams(0,dp(52),1f))
        root.addView(actions,params(WRAP,12))
        nodeText=label("ノード：$nodeId  ⚙",12,Color.DKGRAY)
        nodeText.setOnClickListener { editNode() };root.addView(nodeText,params(WRAP,10))
        scanConfig=label(scanModeLabel(),13,blue)
        scanConfig.setOnClickListener {editScanMode()};root.addView(scanConfig,params(WRAP,8))
        chart=RssiChart(this);root.addView(chart,params(dp(185),12))
        root.addView(label("RID形式を検査 · 位置は送信者の申告値",12,Color.DKGRAY),params(WRAP,8))
        val scroll=ScrollView(this)
        list=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL };scroll.addView(list)
        root.addView(scroll,LinearLayout.LayoutParams(-1,0,1f))
        setContentView(root)
    }

    private fun scanModeLabel():String {
        val ms=getSharedPreferences("receiver",MODE_PRIVATE).getLong("scan_interval_ms",30_000)
        return "スキャン要求：${ms/1000}秒${if(ms<30_000) "（開発用）" else "（標準）"} · 変更"
    }
    private fun editScanMode() {
        if(scanning) {toast("受信を停止してから変更してください");return}
        val modes=ScanPolicy.intervalsMs
        val current=getSharedPreferences("receiver",MODE_PRIVATE).getLong("scan_interval_ms",30_000)
        AlertDialog.Builder(this).setTitle("要求間隔（取得保証ではありません）")
            .setSingleChoiceItems(arrayOf("標準30秒","開発用5秒","開発用1秒"),modes.indexOf(current)) {dialog,which ->
                getSharedPreferences("receiver",MODE_PRIVATE).edit().putLong("scan_interval_ms",modes[which]).apply()
                scanConfig.text=scanModeLabel();dialog.dismiss()
            }.setNegativeButton("閉じる",null).show()
    }

    private fun requestStart() {
        android.util.Log.d("RidObserverKmp","start_button_request")
        if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION),10);return
        }
        val wifi=applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
        if(!wifi.isWifiEnabled) { toast("Wi-Fiを有効にしてください");startActivity(Intent(Settings.ACTION_WIFI_SETTINGS));return }
        val location=getSystemService(LOCATION_SERVICE) as LocationManager
        if(!location.isLocationEnabled) { toast("位置情報サービスを有効にしてください");startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS));return }
        if(scanning) return
        val interval=getSharedPreferences("receiver",MODE_PRIVATE).getLong("scan_interval_ms",30_000)
        android.util.Log.d("RidObserverKmp","start_mode interval=$interval throttle=${wifi.isScanThrottleEnabled}")
        if(!ScanPolicy.allowed(interval,wifi.isScanThrottleEnabled)) {
            AlertDialog.Builder(this).setTitle("高速測定は開発用です")
                .setMessage("Androidの開発者向けオプションでWi-FiスキャンのスロットリングをOFFにした実験専用です。アプリはOS設定を変更しません。通常は30秒を選んでください。要求間隔と実際の取得間隔は異なります。")
                .setPositiveButton("閉じる",null).show();return
        }
        if(Build.VERSION.SDK_INT>=33 && !notificationAsked && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED) {
            notificationAsked=true;requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),11);return
        }
        try {startForegroundService(Intent(this,ReceiverService::class.java).setAction(ReceiverService.ACTION_START))}
        catch(e:Exception) {ReceiverState.status="開始できません · 設定・権限を確認";android.util.Log.w("RidObserverKmp","start_failed ${e.javaClass.simpleName}");render();toast("受信サービスを開始できません")}
    }
    override fun onRequestPermissionsResult(code:Int,permissions:Array<out String>,grants:IntArray) {
        super.onRequestPermissionsResult(code,permissions,grants)
        if(code==11) {requestStart();return}
        if(code==10 && checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED) requestStart()
        else toast("Wi-Fiスキャンには位置情報の許可が必要です")
    }
    private fun stopScan() {ReceiverService.current?.finish("user_stop");render()}
    private fun startRecording() {ReceiverService.current?.startRecording(nodeId);render()}
    private fun stopRecording() {ReceiverService.current?.stopRecording();render()}
    private fun render() {
        start.text=if(scanning) "受信停止" else "受信開始"
        record.isEnabled=scanning;record.text=if(recording!=null) "記録停止" else "記録開始"
        record.setTextColor(if(recording!=null) Color.rgb(185,28,28) else blue)
        val mode=if(recording!=null) "記録 ${recording!!.count}件 · " else ""
        val notificationHidden=Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED
        status.text=mode+ReceiverState.status+(if(scanning && notificationHidden) " · 通知非表示" else "")
        counts.text="Wi-Fi ${lastScanCount}件  /  RID ${engine.targets.size}件"
        list.removeAllViews()
        for((key,t) in engine.targets) {
            val o=t.latest
            val card=LinearLayout(this).apply {
                orientation=LinearLayout.VERTICAL;setPadding(dp(14),dp(12),dp(14),dp(12))
                background=GradientDrawable().apply {setColor(Color.WHITE);cornerRadius=dp(12).toFloat();setStroke(dp(1),if(key==selected) blue else Color.LTGRAY)}
            }
            val id=o.decoded?.messages?.firstOrNull { it.uasId!=null }?.uasId ?: t.alias
            card.addView(label(id,18,navy,true))
            val validity=if(o.decoded==null) "形式エラー" else if(o.isStaleAt(SystemClock.elapsedRealtimeNanos()/1000)) "古い観測／時刻不明" else "受信"
            card.addView(label("${o.rssiDbm?.let { "$it dBm" } ?: "RSSI不明"} · ${o.frequencyMhz ?: "?"} MHz · $validity",14,Color.DKGRAY))
            card.addView(label("観測 ${t.records}件 · counter ${o.decoded?.counter ?: "?"}",12,Color.DKGRAY))
            card.setOnClickListener { selected=key;render();showDetails(t) }
            list.addView(card,params(WRAP,10))
        }
        if(selected !in engine.targets) selected=engine.targets.keys.firstOrNull()
        chart.samples=engine.targets[selected]?.samples?.toList() ?: emptyList();chart.invalidate()
        if(engine.targets.isEmpty()) list.addView(label(if(scanning) "RIDの受信待ち" else "受信開始で観測します",16,Color.GRAY),params(WRAP,24))
    }
    private fun showDetails(t:TargetState) {
        val o=t.latest;val claim=o.decoded?.messages?.firstOrNull { it.claim!=null }?.claim
        val text="状態：${if(o.isStaleAt(SystemClock.elapsedRealtimeNanos()/1000)) "古い観測／時刻不明" else "スキャン観測"}\n${o.error ?: "ODID形式を解析"}\n"+
            (claim?.let { "申告位置：${it.latitude}, ${it.longitude}\n申告高度：${it.altitudeGeoM ?: "不明"} m\n" } ?: "")+
            "スキャン値であり、同一物理パケット・機体・位置の真正性は未確認です。"
        AlertDialog.Builder(this).setTitle(t.alias).setMessage(text).setPositiveButton("閉じる",null).show()
    }
    private fun editNode() {
        if(recording!=null) {toast("記録を停止してから変更してください");return}
        val input=EditText(this).apply {setText(nodeId);isSingleLine=true}
        AlertDialog.Builder(this).setTitle("ノード名").setView(input).setNegativeButton("戻る",null).setPositiveButton("保存") {_,_ ->
            val id=input.text.toString()
            if(id.matches(Regex("[a-zA-Z0-9_-]{1,40}"))) {getPreferences(MODE_PRIVATE).edit().putString("node_id",id).apply();nodeText.text="ノード：$id  ⚙"}
            else toast("英数字・ハイフン・_で40文字以内")
        }.show()
    }

    private fun exportDialog() {
        if(recording!=null) {toast("記録を停止してから書き出してください");return}
        AlertDialog.Builder(this).setTitle("書き出し").setItems(arrayOf("受信全体CSV（現在の履歴）","記録セッションCSV","生ログJSONL（ID・位置を含む）")) {_,which ->
            if(which>0 && lastCapture==null) {toast("先に観測を記録してください");return@setItems}
            if(which==1 && ReceiverState.lastSessionCsv?.let {it.isFile && it.length()>0}!=true) {toast("セッションCSV未確定：中断された記録は生ログを確認してください");return@setItems}
            pendingExport=if(which<2) "csv" else "jsonl"
            exportBytes=when(which) {0 -> engine.summaryCsv().toByteArray(Charsets.UTF_8);1 -> ReceiverState.lastSessionCsv!!.readBytes();else -> null}
            exportFile=if(which==2) lastCapture else null
            val intent=Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE);type=if(which==0) "text/csv" else "application/octet-stream"
                putExtra(Intent.EXTRA_TITLE,"rid-observer-${System.currentTimeMillis()}.${pendingExport}")
            }
            startActivityForResult(intent,20)
        }.show()
    }
    override fun onActivityResult(code:Int,result:Int,data:Intent?) {
        super.onActivityResult(code,result,data)
        val uri=data?.data ?: return
        if(code!=20 || result!=RESULT_OK) return
        val kind=pendingExport
        try {
            contentResolver.openOutputStream(uri)?.use { output ->
                if(kind=="csv") output.write(checkNotNull(exportBytes))
                else checkNotNull(exportFile).inputStream().use { it.copyTo(output) }
            } ?: error("保存先を開けません")
            toast("書き出しました")
        } catch(e: Exception) {toast("書き出し失敗：${e.message}")}
    }
    override fun onStart() {super.onStart();ReceiverState.screen="visible";handler.post(refresh)}
    override fun onStop() {ReceiverState.screen="hidden";handler.removeCallbacks(refresh);super.onStop()}
    private fun dp(n:Int)=(n*resources.displayMetrics.density).toInt()
    private fun label(value:String,size:Int,color:Int,bold:Boolean=false)=TextView(this).apply {
        text=value;textSize=size.toFloat();setTextColor(color);if(bold)setTypeface(typeface,Typeface.BOLD)
    }
    private fun button(value:String,action:()->Unit)=Button(this).apply {text=value;isAllCaps=false;setTextColor(blue);setOnClickListener {action()} }
    private fun params(height:Int,top:Int=0)=LinearLayout.LayoutParams(-1,height).apply {topMargin=dp(top)}
    private fun toast(text:String)=Toast.makeText(this,text,Toast.LENGTH_LONG).show()
    private companion object { const val WRAP=-2 }
}

private class RssiChart(context:Context):View(context) {
    var samples:List<Pair<Long,Int>> = emptyList()
    private val p=Paint(Paint.ANTI_ALIAS_FLAG)
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas)
        val d=resources.displayMetrics.density
        val left=42*d;val right=width-12*d;val top=34*d;val bottom=height-27*d
        p.color=Color.DKGRAY;p.textSize=12*d;canvas.drawText("RSSI（スキャン値）",8*d,18*d,p)
        if(samples.isEmpty()) {p.color=Color.GRAY;canvas.drawText("新しいRSSIの受信待ち",left,top+40*d,p);return}
        val low=(samples.minOf {it.second}-3).toFloat();val high=(samples.maxOf {it.second}+3).toFloat()
        val start=samples.first().first;val span=(samples.last().first-start).coerceAtLeast(1)
        p.strokeWidth=d;p.color=Color.LTGRAY;canvas.drawLine(left,top,left,bottom,p);canvas.drawLine(left,bottom,right,bottom,p)
        p.color=Color.DKGRAY;canvas.drawText(high.toInt().toString(),0f,top+4*d,p);canvas.drawText(low.toInt().toString(),0f,bottom,p)
        canvas.drawText("0 s",left,bottom+19*d,p);canvas.drawText("${span/1_000_000} s",right-42*d,bottom+19*d,p)
        val path=Path()
        for((index,sample) in samples.withIndex()) {
            val x=left+(right-left)*(sample.first-start).toFloat()/span
            val y=bottom-(bottom-top)*(sample.second-low)/(high-low)
            if(index==0) path.moveTo(x,y) else path.lineTo(x,y)
            p.color=Color.rgb(29,78,216);p.style=Paint.Style.FILL;canvas.drawCircle(x,y,3*d,p)
        }
        p.style=Paint.Style.STROKE;p.strokeWidth=2*d;canvas.drawPath(path,p);p.style=Paint.Style.FILL
    }
}
