package org.smri.ridobserver.kmp

import android.content.Context
import android.location.LocationManager
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import android.os.Build
import android.provider.Settings
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Legacy access is device-dependent. No root or hidden-API policy changes. */
object PlatformCompat {
    data class Ies(val bodies:List<ByteArray>,val route:String,val elementCount:Int,val error:String?=null)
    fun informationElements(result:ScanResult):Ies {
        val route=if(Build.VERSION.SDK_INT>=30) "public_api" else "legacy_field"
        return try {
            val entries=if(Build.VERSION.SDK_INT>=30) {
                result.informationElements.map {ie ->
                    val b=ie.bytes.duplicate();ie.id to ByteArray(b.remaining()).also {b.get(it)}
                }
            } else {
                val raw=ScanResult::class.java.getField("informationElements").get(result) as? Array<*>
                    ?: return Ies(emptyList(),route,0,"field_unavailable")
                raw.mapNotNull {ie ->if(ie==null) null else {
                    val id=ie.javaClass.getField("id").getInt(ie)
                    val bytes=ie.javaClass.getField("bytes").get(ie) as? ByteArray
                    bytes?.copyOf()?.let {id to it}
                }}
            }
            Ies(entries.filter {it.first==221}.map {it.second},route,entries.size)
        } catch(e:ReflectiveOperationException) {Ies(emptyList(),route,0,e.javaClass.simpleName)}
          catch(e:SecurityException) {Ies(emptyList(),route,0,e.javaClass.simpleName)}
    }
    fun locationEnabled(context:Context):Boolean = if(Build.VERSION.SDK_INT>=28)
        (context.getSystemService(Context.LOCATION_SERVICE) as LocationManager).isLocationEnabled
    else (context.getSystemService(Context.LOCATION_SERVICE) as LocationManager).let {
        it.isProviderEnabled(LocationManager.GPS_PROVIDER) || it.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
    }

    fun scanThrottleEnabled(wifi:WifiManager):Boolean? = if(Build.VERSION.SDK_INT>=30) wifi.isScanThrottleEnabled else null
    fun utc(epochMs:Long=System.currentTimeMillis()):String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",Locale.US).apply {
        timeZone=TimeZone.getTimeZone("UTC")
    }.format(Date(epochMs))
}
