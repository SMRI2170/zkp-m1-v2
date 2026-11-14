package org.smri.ridobserver.kmp

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.*
import android.content.pm.PackageManager
import android.graphics.*
import android.location.LocationManager
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import android.os.*
import android.provider.Settings
import android.text.InputType
import android.view.*
import android.widget.*
import org.smri.ridobserver.core.*
import java.io.File
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
    private lateinit var dataText:TextView
    private lateinit var nodeText:TextView
    private lateinit var scanConfig:TextView
    private var database:ObservationDatabase?=null
    private var databaseOpenFailed=false
    private var pendingExport:String?=null
    private var exportBytes:ByteArray?=null
    private var exportFile:File?=null
    private val permissionFlow=PermissionFlow()
    private lateinit var permissionStatus:TextView
    private var renderedState:String?=null
    private val refresh=object:Runnable {
        override fun run() {
            val signature=listOf(ReceiverState.revision,scanning,recording?.count,ReceiverState.status,
                ReceiverState.scanCount,ReceiverState.locationStatus,database?.rowCount,database?.pendingWrites,database?.lastError,database?.exporting).joinToString("|")
            // Do not rebuild an unchanged view tree every second: it prevents UI-idle and wastes work.
            if(signature!=renderedState) {renderedState=signature;render()}
            handler.postDelayed(this,5000)
        }
    }
    private val nodeId:String get()=getPreferences(MODE_PRIVATE).getString("node_id",null) ?: run {
        val id="phone-"+UUID.randomUUID().toString().take(8)
        getPreferences(MODE_PRIVATE).edit().putString("node_id",id).apply();id
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        try {database=ObservationDatabase.get(this)} catch(e:Exception) {databaseOpenFailed=true}
        val saved=getSharedPreferences("receiver",MODE_PRIVATE).getString("last_run",null)
        if(ReceiverState.lastCapture==null && saved!=null && saved.matches(Regex("[0-9a-f-]{36}"))) {
            val dir=File(filesDir,"captures/$saved")
            ReceiverState.lastCapture=File(dir,"observations.jsonl").takeIf {it.isFile}
            ReceiverState.lastSessionCsv=File(dir,"summary.csv").takeIf {it.isFile && it.length()>0}
        }
        val root=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setBackgroundColor(Color.rgb(245,247,251));setPadding(dp(18),dp(18),dp(18),dp(12)) }
        root.setOnApplyWindowInsetsListener { view,insets ->
            val top:Int;val bottom:Int
            if(Build.VERSION.SDK_INT>=30) {val bars=insets.getInsets(WindowInsets.Type.systemBars());top=bars.top;bottom=bars.bottom}
            else {top=insets.systemWindowInsetTop;bottom=insets.systemWindowInsetBottom}
            view.setPadding(dp(18),top+dp(18),dp(18),bottom+dp(12));insets
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
        permissionStatus=label("権限を確認",13,blue)
        permissionStatus.setOnClickListener {showPermissionGuide(false)}
        root.addView(permissionStatus,params(WRAP,6))
        nodeText=label("ノード：$nodeId  ⚙",12,Color.DKGRAY)
        nodeText.setOnClickListener { editNode() };root.addView(nodeText,params(WRAP,10))
        scanConfig=label(scanModeLabel(),13,blue)
        scanConfig.setOnClickListener {editScanMode()};root.addView(scanConfig,params(WRAP,8))
        val candidate=label("未解析のWi-Fi保存："+(if(getSharedPreferences("receiver",MODE_PRIVATE).getBoolean("capture_unknown_wifi",false)) "ON" else "OFF"),13,blue)
        candidate.setOnClickListener {
            if(scanning) {toast("受信を停止してから変更してください");return@setOnClickListener}
            val prefs=getSharedPreferences("receiver",MODE_PRIVATE)
            AlertDialog.Builder(this).setTitle("調査用の候補保存")
                .setMessage("ONでは周囲のWi-FiのBSSID・RSSI・取得できるVendor IEも保存します。解析できなくても残りますが、Remote IDやDJIとは断定しません。SSIDは保存しません。")
                .setPositiveButton("ON") {_,_ ->prefs.edit().putBoolean("capture_unknown_wifi",true).apply();candidate.text="未解析のWi-Fi保存：ON"}
                .setNegativeButton("OFF") {_,_ ->prefs.edit().putBoolean("capture_unknown_wifi",false).apply();candidate.text="未解析のWi-Fi保存：OFF"}.show()
        };root.addView(candidate,params(WRAP,4))
        val dataActions=LinearLayout(this)
        dataActions.addView(button("データ表示・更新") {showSnapshot()},LinearLayout.LayoutParams(0,dp(52),1f))
        dataActions.addView(button("送信元登録") {editSources()},LinearLayout.LayoutParams(0,dp(52),1f))
        root.addView(dataActions,params(WRAP,12))
        root.addView(button("方位・RSSI推定を確認") {showDirection()},params(WRAP,6))
        root.addView(label("受信開始でDB保存 · 記録開始は追加ログ",12,Color.DKGRAY),params(WRAP,8))
        root.addView(label("RID形式を検査 · 位置は送信者の申告値",12,Color.DKGRAY),params(WRAP,8))
        val scroll=ScrollView(this)
        dataText=label("受信後に「データ表示・更新」を押してください",13,navy).apply {
            typeface=Typeface.MONOSPACE;setTextIsSelectable(true)
        };scroll.addView(dataText)
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

    private fun fineGranted()=checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED
    private fun permissionSummary():String {
        val loc=if(fineGranted()) "位置：正確を許可" else if(checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED) "位置：概算のみ" else "位置：未許可"
        val notification=if(Build.VERSION.SDK_INT<33) "通知：追加許可不要" else if(checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED) "通知：許可" else "通知：未許可"
        return "$loc · $notification"
    }
    private fun renderPermissions() {if(::permissionStatus.isInitialized) permissionStatus.text="権限を確認 · "+permissionSummary()}
    private fun openAppSettings() {
        permissionFlow.cancel()
        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,android.net.Uri.parse("package:$packageName")))
    }
    private fun showPermissionGuide(startAfter:Boolean) {
        permissionFlow.begin(startAfter)
        val explanation="Wi-Fi受信と自位置の保存には、正確な位置情報の許可が必要です。データは端末内に保存します。"+
            (if(Build.VERSION.SDK_INT>=33) "\n通知は受信中の表示と停止操作に使います。通知の許可は任意です。" else "\nこのAndroidでは通知の追加許可は不要です。")+
            (if(startAfter) "\n許可後、受信を開始します。" else "\n許可だけでは受信は開始しません。")
        AlertDialog.Builder(this).setTitle("受信に必要な権限")
            .setMessage(permissionSummary()+"\n\n"+explanation)
            .setPositiveButton("権限を確認") {_,_ ->requestRequiredPermission()}
            .setNegativeButton("あとで") {_,_ ->permissionFlow.cancel()}
            .setNeutralButton("アプリ設定") {_,_ ->openAppSettings()}
            .setOnCancelListener {permissionFlow.cancel()}.show()
    }
    private fun requestRequiredPermission() {
        val prefs=getSharedPreferences("receiver",MODE_PRIVATE)
        when(PermissionPolicy.location(fineGranted(),prefs.getBoolean("location_permission_requested",false),
            shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_FINE_LOCATION))) {
            PermissionPolicy.Action.SETTINGS ->openAppSettings()
            PermissionPolicy.Action.REQUEST -> {
                prefs.edit().putBoolean("location_permission_requested",true).apply()
                requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION),10)
            }
            PermissionPolicy.Action.READY ->requestNotificationOrComplete()
        }
    }
    private fun requestNotificationOrComplete() {
        val prefs=getSharedPreferences("receiver",MODE_PRIVATE)
        if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED &&
            !prefs.getBoolean("notification_permission_requested",false)) {
            prefs.edit().putBoolean("notification_permission_requested",true).apply()
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),11);return
        }
        completePermissions()
    }
    private fun completePermissions() {
        renderPermissions()
        if(permissionFlow.complete(fineGranted())) startReceiverReady()
    }
    private fun requestStart() {
        val prefs=getSharedPreferences("receiver",MODE_PRIVATE)
        val notificationPending=Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED &&
            !prefs.getBoolean("notification_permission_requested",false)
        if(!fineGranted() || notificationPending) showPermissionGuide(true) else startReceiverReady()
    }
    private fun startReceiverReady() {
        if(database==null || database?.exporting==true) {toast("DBを開けません。既存データを保持して停止しています");return}
        if(!fineGranted()) {renderPermissions();return}
        android.util.Log.d("RidObserverKmp","start_button_request")
        val wifi=applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
        if(!wifi.isWifiEnabled) { toast("Wi-Fiを有効にしてください");startActivity(Intent(Settings.ACTION_WIFI_SETTINGS));return }
        val location=getSystemService(LOCATION_SERVICE) as LocationManager
        if(!PlatformCompat.locationEnabled(this)) { toast("位置情報サービスを有効にしてください");startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS));return }
        if(scanning) return
        val interval=getSharedPreferences("receiver",MODE_PRIVATE).getLong("scan_interval_ms",30_000)
        android.util.Log.d("RidObserverKmp","start_mode interval=$interval throttle=${PlatformCompat.scanThrottleEnabled(wifi)}")
        if(!ScanPolicy.allowed(interval,PlatformCompat.scanThrottleEnabled(wifi) ?: true)) {
            AlertDialog.Builder(this).setTitle("高速測定は開発用です")
                .setMessage(if(Build.VERSION.SDK_INT<30) "このOSでは制限状態を確認できません。標準30秒で受信してください。" else "Androidの開発者向けオプションでWi-FiスキャンのスロットリングをOFFにした実験専用です。アプリはOS設定を変更しません。通常は30秒を選んでください。要求間隔と実際の取得間隔は異なります。")
                .setPositiveButton("閉じる",null).show();return
        }
        try {
            val intent=Intent(this,ReceiverService::class.java).setAction(ReceiverService.ACTION_START).putExtra("node_id",nodeId)
            if(Build.VERSION.SDK_INT>=26) startForegroundService(intent) else startService(intent)
        }
        catch(e:Exception) {ReceiverState.status="開始できません · 設定・権限を確認";android.util.Log.w("RidObserverKmp","start_failed ${e.javaClass.simpleName}");render();toast("受信サービスを開始できません")}
    }
    override fun onRequestPermissionsResult(code:Int,permissions:Array<out String>,grants:IntArray) {
        super.onRequestPermissionsResult(code,permissions,grants)
        if(code==11) {completePermissions();return}
        if(code!=10) return
        renderPermissions()
        if(fineGranted()) requestNotificationOrComplete()
        else {
            permissionFlow.cancel()
            AlertDialog.Builder(this).setTitle("正確な位置情報が未許可です")
                .setMessage("受信・自位置記録は開始していません。概算のみの許可では、この受信機能は利用できません。画面の「権限を確認」から再設定できます。")
                .setPositiveButton("閉じる",null).show()
        }
    }
    override fun onPostResume() {
        super.onPostResume();renderPermissions()
        val prefs=getSharedPreferences("receiver",MODE_PRIVATE)
        if(!prefs.getBoolean("permission_intro_v11",false)) {
            prefs.edit().putBoolean("permission_intro_v11",true).apply()
            if(!scanning && (!fineGranted() || (Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)))
                showPermissionGuide(false)
        }
    }

    private fun stopScan() {ReceiverService.current?.finish("user_stop");render()}
    private fun startRecording() {ReceiverService.current?.startRecording(nodeId);render()}
    private fun stopRecording() {ReceiverService.current?.stopRecording();render()}
    private fun render() {
        start.isEnabled=database!=null && database?.exporting!=true
        start.text=if(scanning) "受信停止" else "受信開始"
        record.isEnabled=scanning;record.text=if(recording!=null) "記録停止" else "記録開始"
        record.setTextColor(if(recording!=null) Color.rgb(185,28,28) else blue)
        val mode=if(recording!=null) "記録 ${recording!!.count}件 · " else ""
        val notificationHidden=Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED
        status.text=mode+ReceiverState.status+(if(scanning && notificationHidden) " · 通知非表示" else "")
        counts.text="DB ${database?.rowCount ?: 0}件 · 保存待ち ${database?.pendingWrites ?: 0}件\nWi-Fi ${lastScanCount}件 / 対象 ${engine.targets.size}件\n${ReceiverState.locationStatus}"
        if(databaseOpenFailed || database?.lastError!=null) status.text="DB保存エラー · 失敗${database?.failedWrites ?: 0}件 · 確認してください"
        if(database?.exporting==true) status.text="DBを書き出しています"
    }
    private fun snapshotText():String = try {database?.recentText()?.ifEmpty {"DBに観測はまだありません"} ?: "DBを開けません"} catch(e:Exception) {"DBの読出しに失敗しました"}
    private fun showDirection() {
        val text=buildString {
            append(ReceiverState.directionStatus+"\n\n")
            append("端末を水平に持ち、同じ場所でゆっくり回転。24点・270°以上が必要です。30秒間隔なら約12分以上が目安です。\n\n")
            append("表示する角度はRSSIが最大になる端末上端の向き（磁北基準）です。電波の到来角・ドローンの方向を測定した値ではありません。精度は未検証です。\n\n")
            for(t in engine.targets.values) {
                val fields=t.latest.direction
                val fit=fields?.get("peak_estimate") as? Map<*,*>
                append("${t.alias} : ${fit?.get("samples") ?: 0}点 / ${fit?.get("occupied_bins") ?: 0}方位区画\n")
                val peak=fit?.get("peak_phone_heading_deg") as? Double
                append(if(peak!=null) "RSSI最大の端末方位：${peak.toInt()}°（実験値）\n" else "方位推定：保留（回転・点数・信号差を確認）\n")
                append("方位対応：${fields?.get("missing_reason") ?: if(fields==null) "旧記録／未測定" else "対応あり"}\n\n")
            }
        }
        dataText.text=text
    }

    private fun showSnapshot() {
        dataText.text="DBの最新50件まで（観測時点の値）\n\n"+snapshotText()
    }
    private fun editNode() {
        if(scanning) {toast("受信を停止してから変更してください");return}
        val input=EditText(this).apply {setText(nodeId);isSingleLine=true}
        AlertDialog.Builder(this).setTitle("ノード名").setView(input).setNegativeButton("戻る",null).setPositiveButton("保存") {_,_ ->
            val id=input.text.toString()
            if(id.matches(Regex("[a-zA-Z0-9_-]{1,40}"))) {getPreferences(MODE_PRIVATE).edit().putString("node_id",id).apply();nodeText.text="ノード：$id  ⚙"}
            else toast("英数字・ハイフン・_で40文字以内")
        }.show()
    }

    private fun editSources() {
        if(scanning || database?.pendingWrites!=0) {toast("受信停止・保存完了後に登録してください");return}
        val registry=SourceRegistry(this)
        val rules=try {registry.load()} catch(e:Exception) {toast("登録を読めません。既存設定を保持しています");return}
        AlertDialog.Builder(this).setTitle("送信元の登録（認証ではありません）")
            .setItems((rules.map {it.label}+listOf("＋ 追加")).toTypedArray()) {_,index ->
                if(index<rules.size) {
                    AlertDialog.Builder(this).setTitle(rules[index].label).setMessage("この登録を削除しますか？ 過去の観測は保持します。")
                        .setPositiveButton("削除") {_,_ ->try {registry.remove(index)} catch(e:Exception) {toast("削除できません")}}
                        .setNegativeButton("戻る",null).show()
                } else {
                    val form=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(dp(18),0,dp(18),0)}
                    val role=Spinner(this).apply {adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,listOf("ドローン（登録）","搭載Pi（登録）","不明"))}
                    val name=EditText(this).apply {hint="表示名";isSingleLine=true}
                    val id=EditText(this).apply {hint="申告RID（半角・任意）";inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS;isSingleLine=true}
                    val mac=EditText(this).apply {hint="BSSID（半角・任意）";inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS;isSingleLine=true}
                    listOf(role,name,id,mac).forEach {form.addView(it)}
                    AlertDialog.Builder(this).setTitle("IDまたはBSSIDで照合").setView(form)
                        .setPositiveButton("保存") {_,_ ->try {
                            val kind=listOf("drone","onboard_pi","unknown")[role.selectedItemPosition]
                            registry.add(SourceRule(kind,name.text.toString().ifBlank {role.selectedItem.toString()},
                                id.text.toString().trim().takeIf {it.isNotEmpty()},mac.text.toString().trim().takeIf {it.isNotEmpty()}))
                            toast("登録しました。次の受信から記録します")
                        } catch(e:Exception) {toast("登録できません。入力・上限・重複を確認してください")}}
                        .setNegativeButton("戻る",null).show()
                }
            }.setNegativeButton("閉じる",null).show()
    }
    private fun exportDialog() {
        AlertDialog.Builder(this).setTitle("書き出し").setItems(arrayOf("受信全体CSV（現在の履歴）","記録セッションCSV","生ログJSONL（ID・位置を含む）","最新50件テキスト（ID・位置を含む）","DB全件JSONL（ID・位置を含む）","DB明細CSV（自位置・距離付き）","自位置履歴CSV","診断CSV（権限・要求成否）")) {_,which ->
            if(which>=4 && (scanning || database?.pendingWrites!=0)) {toast("DB全件の書き出しは受信停止・保存完了後に行ってください");return@setItems}
            if(which>=4 && database==null) {toast("DBを開けません");return@setItems}
            if(which in 1..2 && recording!=null) {toast("生ログ・セッションCSVの書き出しは記録停止後に行ってください");return@setItems}
            if(which in 1..2 && lastCapture==null) {toast("先に観測を記録してください");return@setItems}
            if(which==1 && ReceiverState.lastSessionCsv?.let {it.isFile && it.length()>0}!=true) {toast("セッションCSV未確定：中断された記録は生ログを確認してください");return@setItems}
            pendingExport=when(which) {0,1 -> "csv";2 -> "jsonl";4 -> "dbjsonl";5 -> "dbcsv";6 -> "fixcsv";7 -> "diagnosticcsv";else -> "txt"}
            exportBytes=when(which) {0 -> engine.summaryCsv().toByteArray(Charsets.UTF_8);1 -> ReceiverState.lastSessionCsv!!.readBytes();3 -> snapshotText().toByteArray(Charsets.UTF_8);else -> null}
            exportFile=if(which==2) lastCapture else null
            val intent=Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE);type=when(which) {0,1,5,6,7 -> "text/csv";2,4 -> "application/x-ndjson";else -> "text/plain"}
                putExtra(Intent.EXTRA_TITLE,"rid-observer-${System.currentTimeMillis()}.${if(which==4) "jsonl" else if(which>=5) "csv" else pendingExport}")
            }
            startActivityForResult(intent,20)
        }.show()
    }
    override fun onActivityResult(code:Int,result:Int,data:Intent?) {
        super.onActivityResult(code,result,data)
        val uri=data?.data ?: return
        if(code!=20 || result!=RESULT_OK) return
        val kind=pendingExport
        if(kind in listOf("dbjsonl","dbcsv","fixcsv","diagnosticcsv")) {
            if(scanning) {toast("受信停止後にDBを書き出してください");return}
            try {database?.exportData(uri,kind!!) {ok ->if(!isDestroyed) {render();toast(if(ok) "DBを書き出しました" else "DB書き出し失敗")}}}
            catch(e:Exception) {toast("DB書き出しを開始できません")}
            return
        }
        try {
            contentResolver.openOutputStream(uri)?.use { output ->
                if(kind=="csv" || kind=="txt") output.write(checkNotNull(exportBytes))
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
