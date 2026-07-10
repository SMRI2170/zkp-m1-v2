package com.example.rapidsnark_app

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import android.net.wifi.aware.AttachCallback
import android.net.wifi.aware.DiscoverySessionCallback
import android.net.wifi.aware.PeerHandle
import android.net.wifi.aware.SubscribeConfig
import android.net.wifi.aware.SubscribeDiscoverySession
import android.net.wifi.aware.WifiAwareManager
import android.net.wifi.aware.WifiAwareSession
import android.os.Build
import android.os.Handler
import android.os.Looper
import io.flutter.plugin.common.EventChannel

/**
 * WiFi Beacon 経由の OpenDroneID (ASTM F3411 / opendroneid-core-c) を受信する基盤。
 *
 * DJI など市販ドローンの多くは Remote ID を WiFi ビーコンフレームのベンダ固有
 * Information Element (IE) でブロードキャストする。BLE では捕捉できないため、
 * WifiManager のスキャン結果から該当 IE を抽出して Flutter 側へ送る。
 *
 * スキャンは [WifiScanHub] に 1 本化し、以下 2 系統のストリームへ配る:
 *  - [WifiOdidStreamHandler] : OpenDroneID の message pack のみ（証明フロー用）
 *  - [WifiRawStreamHandler]  : 全ネットワーク + ベンダ IE（BLE Raw に相当する診断用）
 *
 * 制約:
 *  - 生 IE 取得 (ScanResult.getInformationElements) は API 30 (Android 11) 以上。
 *    未満の端末では何も配信しない（アプリは BLE のみで動作する）。
 *  - スキャン結果取得には位置情報権限が必要（アプリ側で取得済み）。
 */
private const val ODID_IE_VENDOR = 221                                   // element id 0xDD
private val ODID_OUI = byteArrayOf(0xFA.toByte(), 0x0B, 0xBC.toByte())   // ASTM Remote ID
private const val ODID_OUI_TYPE = 0x0D                                   // Drone Remote ID
private const val ODID_HEADER_LEN = 5                                    // OUI(3)+type(1)+counter(1)

/** ScanResult から IE を安全に取得する（API 30 未満は空）。 */
private fun infoElements(result: ScanResult): List<ScanResult.InformationElement> {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return emptyList()
    return result.informationElements ?: emptyList()
}

private fun ieContent(ie: ScanResult.InformationElement): ByteArray {
    val buf = ie.bytes
    val out = ByteArray(buf.remaining())
    buf.duplicate().get(out)
    return out
}

private fun isOdidContent(c: ByteArray): Boolean =
    c.size > ODID_HEADER_LEN &&
        c[0] == ODID_OUI[0] && c[1] == ODID_OUI[1] &&
        c[2] == ODID_OUI[2] && c[3] == ODID_OUI_TYPE.toByte()

/** OUI+type+counter の 5 バイトを除いた message pack。 */
private fun odidMessagePack(c: ByteArray): ByteArray = c.copyOfRange(ODID_HEADER_LEN, c.size)

private fun toHex(bytes: ByteArray, max: Int = bytes.size): String {
    val sb = StringBuilder()
    for (i in 0 until minOf(max, bytes.size)) sb.append(String.format("%02X", bytes[i]))
    return sb.toString()
}

/**
 * WiFi スキャンを 1 本に集約し、登録された複数リスナーへ結果を配る共有ハブ。
 * 最初のリスナー登録でスキャン開始、最後のリスナー解除で停止する。
 */
object WifiScanHub {
    private const val RESCAN_INTERVAL_MS = 12_000L

    private val mainHandler = Handler(Looper.getMainLooper())
    private val listeners = LinkedHashSet<(List<ScanResult>) -> Unit>()
    private var receiver: BroadcastReceiver? = null
    private var rescan: Runnable? = null
    private var appContext: Context? = null

    private fun wifi(ctx: Context): WifiManager? =
        ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager

    @Synchronized
    fun addListener(context: Context, listener: (List<ScanResult>) -> Unit) {
        appContext = context.applicationContext
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return
        val first = listeners.isEmpty()
        listeners.add(listener)
        if (first) start()
        // 起動直後に既存のスキャン結果を一度配信
        listener(currentResults())
    }

    @Synchronized
    fun removeListener(listener: (List<ScanResult>) -> Unit) {
        listeners.remove(listener)
        if (listeners.isEmpty()) stop()
    }

    private fun start() {
        val ctx = appContext ?: return
        receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context?, i: Intent?) = emitAll()
        }
        ctx.registerReceiver(receiver, IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION))
        val r = object : Runnable {
            override fun run() {
                try {
                    @Suppress("DEPRECATION")
                    wifi(ctx)?.startScan()
                } catch (_: Exception) {
                }
                mainHandler.postDelayed(this, RESCAN_INTERVAL_MS)
            }
        }
        rescan = r
        mainHandler.post(r)
    }

    private fun stop() {
        rescan?.let { mainHandler.removeCallbacks(it) }
        rescan = null
        receiver?.let {
            try {
                appContext?.unregisterReceiver(it)
            } catch (_: IllegalArgumentException) {
            }
        }
        receiver = null
    }

    private fun currentResults(): List<ScanResult> {
        val ctx = appContext ?: return emptyList()
        return try {
            @Suppress("DEPRECATION")
            wifi(ctx)?.scanResults ?: emptyList()
        } catch (_: SecurityException) {
            emptyList()
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun emitAll() {
        val snapshot = currentResults()
        val targets = synchronized(this) { listeners.toList() }
        targets.forEach { it(snapshot) }
    }
}

/**
 * OpenDroneID の message pack を Flutter へ流す（証明フロー用）。
 *
 * DJI 等を確実に拾うため 2 つの WiFi トランスポートを購読する:
 *  - WiFi Beacon  : ベンダ固有 IE (API 30+)
 *  - WiFi NAN     : Wi-Fi Aware の Remote ID サービス (API 26+, 対応端末のみ)
 */
class WifiOdidStreamHandler(private val context: Context) : EventChannel.StreamHandler {
    companion object {
        const val CHANNEL = "uav/wifi_odid"
    }

    private var listener: ((List<ScanResult>) -> Unit)? = null
    private var nan: WifiNanSubscriber? = null

    override fun onListen(arguments: Any?, sink: EventChannel.EventSink?) {
        if (sink == null) return

        // ① WiFi Beacon（ベンダ固有 IE）— API 30+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val l: (List<ScanResult>) -> Unit = { results ->
                for (r in results) {
                    val pack = extractPack(r) ?: continue
                    sink.success(
                        hashMapOf<String, Any?>(
                            "transport" to "Beacon",
                            "bssid" to r.BSSID,
                            "ssid" to r.SSID,
                            "rssi" to r.level,
                            "payload" to pack,
                        )
                    )
                }
            }
            listener = l
            WifiScanHub.addListener(context, l)
        }

        // ② WiFi NAN（Wi-Fi Aware）— API 26+ / 対応端末のみ
        val n = WifiNanSubscriber(context)
        n.onPack = { ssi ->
            sink.success(
                hashMapOf<String, Any?>(
                    "transport" to "NAN",
                    "bssid" to "",
                    "ssid" to "",
                    "rssi" to 0,
                    "payload" to ssi,
                )
            )
        }
        n.start()
        nan = n
    }

    override fun onCancel(arguments: Any?) {
        listener?.let { WifiScanHub.removeListener(it) }
        listener = null
        nan?.stop()
        nan = null
    }

    private fun extractPack(result: ScanResult): ByteArray? {
        for (ie in infoElements(result)) {
            if (ie.id != ODID_IE_VENDOR) continue
            val c = ieContent(ie)
            if (isOdidContent(c)) return odidMessagePack(c)
        }
        return null
    }
}

/**
 * WiFi NAN (Wi-Fi Aware) の OpenDroneID Remote ID サービスを購読する。
 *
 * 一部の DJI 機や標準 Remote ID 機は Beacon ではなく NAN で送信するため、
 * サービス名 "org.opendroneid.remoteid" を subscribe し、受信した
 * Service Specific Info（= ODID メッセージ／message pack）をコールバックする。
 *
 * 対応端末（FEATURE_WIFI_AWARE）以外では何もしない。実機が無いと検証できない
 * 経路のため、SSI のフレーミングは Dart 側 extractFromWifiBeacon で吸収する。
 */
class WifiNanSubscriber(private val context: Context) {
    var onPack: ((ByteArray) -> Unit)? = null

    private val handler = Handler(Looper.getMainLooper())
    private var session: WifiAwareSession? = null
    private var discovery: SubscribeDiscoverySession? = null
    private var stateReceiver: BroadcastReceiver? = null

    /// WiFi Aware の subscribe に必要な権限があるか。無ければ start をスキップして
    /// SecurityException によるクラッシュを防ぐ（許可後に再度 start される想定）。
    private fun hasNearbyPermission(): Boolean {
        val perm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.NEARBY_WIFI_DEVICES
        } else {
            Manifest.permission.ACCESS_FINE_LOCATION
        }
        return context.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED
    }

    fun start() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        if (!context.packageManager.hasSystemFeature(PackageManager.FEATURE_WIFI_AWARE)) return
        if (!hasNearbyPermission()) return
        val mgr = context.applicationContext
            .getSystemService(Context.WIFI_AWARE_SERVICE) as? WifiAwareManager ?: return

        if (mgr.isAvailable) {
            attach(mgr)
        } else {
            // Wi-Fi Aware が利用可能になるのを待ってから attach する。
            stateReceiver = object : BroadcastReceiver() {
                override fun onReceive(c: Context?, i: Intent?) {
                    if (mgr.isAvailable && session == null) attach(mgr)
                }
            }
            context.registerReceiver(
                stateReceiver,
                IntentFilter(WifiAwareManager.ACTION_WIFI_AWARE_STATE_CHANGED),
            )
        }
    }

    private fun attach(mgr: WifiAwareManager) {
        try {
            mgr.attach(object : AttachCallback() {
                override fun onAttached(awareSession: WifiAwareSession) {
                    session = awareSession
                    val config = SubscribeConfig.Builder()
                        .setServiceName("org.opendroneid.remoteid")
                        .build()
                    // 権限が取り消された場合などに subscribe が SecurityException を投げても
                    // アプリを落とさない（コールバックスレッドで throw されるため try で包む）。
                    try {
                        awareSession.subscribe(config, object : DiscoverySessionCallback() {
                            override fun onSubscribeStarted(s: SubscribeDiscoverySession) {
                                discovery = s
                            }

                            override fun onServiceDiscovered(
                                peerHandle: PeerHandle,
                                serviceSpecificInfo: ByteArray?,
                                matchFilter: MutableList<ByteArray>?,
                            ) {
                                val ssi = serviceSpecificInfo ?: return
                                if (ssi.isNotEmpty()) onPack?.invoke(ssi)
                            }
                        }, handler)
                    } catch (_: SecurityException) {
                        // 近傍デバイス権限が無い → WiFi Aware 受信は無効（クラッシュさせない）
                    }
                }
            }, handler)
        } catch (_: Exception) {
        }
    }

    fun stop() {
        try {
            discovery?.close()
        } catch (_: Exception) {
        }
        try {
            session?.close()
        } catch (_: Exception) {
        }
        discovery = null
        session = null
        stateReceiver?.let {
            try {
                context.unregisterReceiver(it)
            } catch (_: IllegalArgumentException) {
            }
        }
        stateReceiver = null
    }
}

/** 全 WiFi ネットワーク + ベンダ IE を Flutter へ流す（BLE Raw 相当の診断用）。 */
class WifiRawStreamHandler(private val context: Context) : EventChannel.StreamHandler {
    companion object {
        const val CHANNEL = "uav/wifi_raw"
    }

    private var listener: ((List<ScanResult>) -> Unit)? = null

    override fun onListen(arguments: Any?, sink: EventChannel.EventSink?) {
        if (sink == null) return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            // 非対応端末: 空配列を 1 度送り、UI 側で「Android 11+ が必要」と案内する。
            sink.success(ArrayList<Any?>())
            return
        }
        val l: (List<ScanResult>) -> Unit = { results ->
            val list = ArrayList<HashMap<String, Any?>>(results.size)
            for (r in results) list.add(networkMap(r))
            sink.success(list)
        }
        listener = l
        WifiScanHub.addListener(context, l)
    }

    override fun onCancel(arguments: Any?) {
        listener?.let { WifiScanHub.removeListener(it) }
        listener = null
    }

    private fun networkMap(result: ScanResult): HashMap<String, Any?> {
        val vendorIes = ArrayList<HashMap<String, Any?>>()
        var odid: ByteArray? = null
        for (ie in infoElements(result)) {
            if (ie.id != ODID_IE_VENDOR) continue
            val c = ieContent(ie)
            val isOdid = isOdidContent(c)
            if (isOdid) odid = odidMessagePack(c)
            vendorIes.add(
                hashMapOf(
                    "oui" to toHex(c, 3),
                    "bytes" to c,
                    "isOdid" to isOdid,
                )
            )
        }
        return hashMapOf(
            "bssid" to result.BSSID,
            "ssid" to result.SSID,
            "rssi" to result.level,
            "frequency" to result.frequency,
            "capabilities" to result.capabilities,
            "vendorIes" to vendorIes,
            "odid" to odid,
        )
    }
}
