package org.smri.ridobserver.kmp

import android.content.Context
import android.hardware.*
import org.smri.ridobserver.core.*
import kotlin.math.*

/** Runs only during the visible-user-started receiver service. No wake lock or background restart. */
class DirectionCapture(context:Context):SensorEventListener {
    private val manager=context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val history=mutableListOf<DirectionMath.Heading>()
    private val targets=linkedMapOf<String,MutableList<DirectionMath.Sample>>()
    private val matrix=FloatArray(9)
    private val angles=FloatArray(3)
    private var accuracy=SensorManager.SENSOR_STATUS_UNRELIABLE
    private var active=false
    var status="端末方位：停止中";private set
    fun start() {
        history.clear();targets.clear();accuracy=SensorManager.SENSOR_STATUS_UNRELIABLE
        val sensor=manager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        active=sensor!=null && manager.registerListener(this,sensor,100_000)
        status=if(active) "端末方位：測定準備中" else "端末方位：センサー利用不可"
    }
    fun stop() {manager.unregisterListener(this);active=false;history.clear()}
    override fun onAccuracyChanged(sensor:Sensor?,value:Int) {accuracy=value}
    override fun onSensorChanged(event:SensorEvent) {
        SensorManager.getRotationMatrixFromVector(matrix,event.values)
        SensorManager.getOrientation(matrix,angles)
        // Device natural +Y axis (top edge), relative to magnetic north; not display remapped.
        val h=DirectionMath.Heading(event.timestamp/1000,DirectionMath.wrap(angles[0]*180/PI),
            acos(matrix[8].toDouble().coerceIn(-1.0,1.0))*180/PI,accuracy)
        history.add(h);if(history.size>1200) history.removeAt(0)
        status=if(h.accuracy<2) "端末方位：精度不足" else if(h.tiltDeg>25) "端末方位：水平にしてください" else "端末方位：記録可能（電波の方向とは別）"
    }
    fun annotate(o:Observation):Observation {
        val h=DirectionMath.nearest(history,o.observedUs)
        val reason=if(!active) "SENSOR_UNAVAILABLE" else if(o.observedUs==null) "SCAN_TIMESTAMP_MISSING" else if(h==null) "NO_USABLE_HEADING_WITHIN_250MS" else null
        val key="${o.sourceType.wire}|${o.sourceKey}|${o.frequencyMhz}|${o.decoded?.messages?.mapNotNull {it.uasId}?.joinToString() ?: ""}"
        if(!targets.containsKey(key) && targets.size>=32) targets.remove(targets.keys.first())
        val samples=targets.getOrPut(key) {mutableListOf()}
        val rssi=o.rssiDbm
        if(h!=null && !o.stale && o.decoded!=null && o.sourceType==SourceType.REAL_CAPTURE && rssi!=null) {
            val us=o.observedUs!!
            // A cached scan/second IE from the same timestamp is not an independent RF sample.
            if(samples.isEmpty() || us-samples.last().us>=250_000) {
                samples.add(DirectionMath.Sample(us,h.degrees,rssi.toDouble()))
                if(samples.size>1200) samples.removeAt(0)
            }
        }
        val fit=DirectionMath.fit(samples)
        val fields=mapOf<String,Any?>("phone_heading_magnetic_deg" to h?.degrees,"heading_sensor_us" to h?.us,
            "heading_scan_delta_us" to h?.let {it.us-o.observedUs!!},"phone_tilt_deg" to h?.tiltDeg,
            "heading_accuracy" to h?.accuracy,"missing_reason" to reason,
            "reference_axis" to "device_natural_positive_y_magnetic_north","peak_estimate" to fit)
        return o.copy(direction=fields)
    }
}
