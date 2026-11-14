package org.smri.ridobserver.kmp

import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Looper
import android.os.SystemClock
import org.smri.ridobserver.core.*

/** Runs inside the user-started location foreground service. No last-known fallback. */
class ReceiverLocationCapture(context:Context,private val onFix:(ReceiverFix)->Unit) : LocationListener {
    private val manager=context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    private val history=ReceiverPositionHistory()
    private var lastFixUs:Long?=null
    var status="自位置：停止中";private set
    fun start() {
        val providers=listOf(LocationManager.GPS_PROVIDER,LocationManager.NETWORK_PROVIDER)
        var registered=0
        for(provider in providers) {
            try {
                if(manager.isProviderEnabled(provider)) {
                    manager.requestLocationUpdates(provider,1000L,0f,this,Looper.getMainLooper());registered++
                }
            } catch(e:SecurityException) {status="自位置：権限拒否"}
              catch(e:IllegalArgumentException) { /* provider absent on this device */ }
        }
        if(registered>0) status="自位置：測位待ち"
        else if(status!="自位置：権限拒否") status="自位置：利用可能な測位なし"
    }
    override fun onLocationChanged(location:Location) {
        val now=SystemClock.elapsedRealtimeNanos()/1000
        val us=location.elapsedRealtimeNanos/1000
        val fix=ReceiverFix(us,PlatformCompat.utc(location.time),location.latitude,location.longitude,
            if(location.hasAccuracy()) location.accuracy.toDouble() else Double.NaN,
            location.provider ?: "unknown",location.isFromMockProvider,
            if(location.hasAltitude()) location.altitude else null)
        if(us>now || now-us>120_000_000 || !history.add(fix)) return
        lastFixUs=us
        status="自位置：${fix.provider} ±${fix.accuracyM.toInt()}m"+(if(fix.mock) "（模擬位置）" else "")
        onFix(fix)
    }
    override fun onProviderEnabled(provider:String) {status="自位置：測位待ち"}
    override fun onProviderDisabled(provider:String) {status="自位置：$provider 無効"}
    @Deprecated("Legacy API callback")
    override fun onStatusChanged(provider:String?,status:Int,extras:Bundle?) {}
    fun annotate(o:Observation,deliveredUs:Long)=history.annotate(o,deliveredUs)
    fun currentStatus():String {
        val fix=lastFixUs
        return if(fix!=null && SystemClock.elapsedRealtimeNanos()/1000-fix>5_000_000) "自位置：測位更新なし（5秒超）" else status
    }
    fun stop() {try {manager.removeUpdates(this)} catch(e:SecurityException) {}
        status="自位置：停止中"}
}
