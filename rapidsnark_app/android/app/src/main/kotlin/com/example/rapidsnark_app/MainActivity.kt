package com.example.rapidsnark_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        val messenger = flutterEngine.dartExecutor.binaryMessenger

        // WiFi Beacon 経由の OpenDroneID 受信（証明フロー用：message pack のみ）
        EventChannel(messenger, WifiOdidStreamHandler.CHANNEL)
            .setStreamHandler(WifiOdidStreamHandler(applicationContext))

        // WiFi 全ネットワーク + ベンダ IE（BLE Raw 相当の診断用）
        EventChannel(messenger, WifiRawStreamHandler.CHANNEL)
            .setStreamHandler(WifiRawStreamHandler(applicationContext))
    }
}
