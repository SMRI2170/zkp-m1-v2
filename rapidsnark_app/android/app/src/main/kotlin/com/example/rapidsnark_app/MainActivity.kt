package com.example.rapidsnark_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

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

        // 端末アテステーション（Android Key Attestation）: device_pubkey の裏書き
        MethodChannel(messenger, "com.example.rapidsnark_app/attestation")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "attest" -> {
                        try {
                            val nonce = (call.argument<String>("nonce") ?: "").toByteArray()
                            result.success(DeviceAttestation.attest(nonce))
                        } catch (e: Exception) {
                            result.error("ATTEST_FAILED", e.message, null)
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }
}
