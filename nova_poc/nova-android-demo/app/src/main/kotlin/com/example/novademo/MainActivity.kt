package com.example.novademo

import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import uniffi.nova_mobile.ChainState
import uniffi.nova_mobile.ObservationInput

// week20/09の「Nova UIへの配線」を最小構成で実装したデモ画面。
// nova_poc/nova-mobile（UniFFIラッパー）と nova_poc/sonobe/target/aarch64-linux-android の
// libnova_mobile.so をそのまま呼び出し、week20/08と同じ3ステップシナリオを画面上で実行する。
class MainActivity : AppCompatActivity() {

    private lateinit var logView: TextView
    private lateinit var runButton: Button
    private val log = StringBuilder()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 96, 48, 48)
        }

        val title = TextView(this).apply {
            text = "Nova(Sonobe) UAVチェーン デモ"
            textSize = 20f
            gravity = Gravity.CENTER
        }
        root.addView(title)

        runButton = Button(this).apply {
            text = "3ステップ実行（week20/08と同じシナリオ）"
            setOnClickListener { runChain() }
        }
        root.addView(runButton)

        logView = TextView(this).apply {
            textSize = 13f
            setPadding(0, 32, 0, 0)
        }
        val scroll = ScrollView(this).apply { addView(logView) }
        root.addView(scroll, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))

        setContentView(root)
    }

    private fun appendLog(line: String) {
        log.append(line).append('\n')
        runOnUiThread { logView.text = log.toString() }
    }

    private fun obsConsistent() = ObservationInput(
        droneLat = 1_256_891_390uL, droneLon = 3_196_917_000uL, droneAlt = 1_200uL,
        targetLat = 1_256_891_590uL, targetLon = 3_196_917_180uL, targetAlt = 1_000uL,
        measuredRangeCm = 341uL,
    )

    private fun obsSpoofed() = ObservationInput(
        droneLat = 1_256_891_390uL, droneLon = 3_196_917_000uL, droneAlt = 1_200uL,
        targetLat = 1_256_891_590uL, targetLon = 3_196_917_180uL, targetAlt = 1_000uL,
        measuredRangeCm = 5_000uL,
    )

    private fun runChain() {
        runButton.isEnabled = false
        log.setLength(0)
        appendLog("libnova_mobile.so 読み込み確認中…")

        Thread {
            try {
                val t0 = System.nanoTime()
                val state = ChainState(droneId = 424242uL, timeBucket = 100001uL)
                appendLog("ChainState.new(): ${elapsedMs(t0)}ms（初回preprocess込み）")

                val steps = listOf(
                    "整合な観測1" to obsConsistent(),
                    "整合な観測2" to obsConsistent(),
                    "なりすまし観測" to obsSpoofed(),
                )
                for ((label, obs) in steps) {
                    val ts = System.nanoTime()
                    state.proveStep(obs)
                    appendLog("proveStep($label): ${elapsedMs(ts)}ms  z=${state.state()}")
                }

                val tv = System.nanoTime()
                val ok = state.verify()
                appendLog("verify(): ${elapsedMs(tv)}ms  ok=$ok")
                appendLog(if (ok) "\n✅ 完了：3ステップとも成功、IVC証明の検証もOK" else "\n❌ 検証失敗")
            } catch (e: Throwable) {
                appendLog("\n❌ エラー: ${e}")
            } finally {
                runOnUiThread { runButton.isEnabled = true }
            }
        }.start()
    }

    private fun elapsedMs(startNanos: Long): Long = (System.nanoTime() - startNanos) / 1_000_000
}
