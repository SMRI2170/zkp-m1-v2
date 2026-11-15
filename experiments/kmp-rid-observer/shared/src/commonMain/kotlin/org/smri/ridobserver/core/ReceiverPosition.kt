package org.smri.ridobserver.core

import kotlin.math.*

/** Phone location is independent of the transmitter's unverified position claim. */
data class ReceiverFix(val us:Long,val utc:String,val latitude:Double,val longitude:Double,
                       val accuracyM:Double,val provider:String,val mock:Boolean,
                       val altitudeEllipsoidM:Double?=null) {
    fun valid()=us>0 && latitude.isFinite() && latitude in -90.0..90.0 &&
        longitude.isFinite() && longitude in -180.0..180.0 && accuracyM.isFinite() && accuracyM>=0
    fun fields():Map<String,Any?> = mapOf("fix_elapsed_us" to us,"fix_utc" to utc,
        "latitude" to latitude,"longitude" to longitude,"accuracy_m" to accuracyM,
        "provider" to provider,"mock" to mock,"altitude_ellipsoid_m" to altitudeEllipsoidM)
}

class ReceiverPositionHistory {
    private val fixes=mutableListOf<ReceiverFix>()
    fun add(fix:ReceiverFix):Boolean {
        if(!fix.valid()) return false
        if(fixes.any {it.us==fix.us && it.provider==fix.provider}) return false
        fixes.add(fix);fixes.sortBy {it.us}
        while(fixes.size>240) fixes.removeAt(0)
        return true
    }
    fun match(observedUs:Long?,deliveredUs:Long?,stale:Boolean):Map<String,Any?> {
        val reason=when {
            stale -> "STALE_WIFI_OBSERVATION"
            observedUs==null || deliveredUs==null || observedUs<=0 || observedUs>deliveredUs -> "UNKNOWN_OR_FUTURE_WIFI_TIME"
            else -> null
        }
        if(reason!=null) return mapOf("match_status" to reason)
        val fix=fixes.filter {it.us<=deliveredUs!!}.minWithOrNull(
            compareBy<ReceiverFix> {abs(it.us-observedUs!!)}.thenBy {it.accuracyM})
        if(fix==null || abs(fix.us-observedUs!!)>2_000_000)
            return mapOf("match_status" to "NO_FIX_WITHIN_2_SECONDS")
        return fix.fields()+mapOf("match_status" to "MATCHED","scan_delta_us" to fix.us-observedUs,
            "association_basis" to "same_device_elapsed_realtime","max_delta_us" to 2_000_000,
            "physical_position_verified" to false)
    }
    fun annotate(o:Observation,deliveredUs:Long):Observation {
        val matched=match(o.observedUs,deliveredUs,o.stale)
        val claim=o.decoded?.messages?.firstOrNull {it.claim!=null}?.claim
        val lat=matched["latitude"] as? Double;val lon=matched["longitude"] as? Double
        val accuracy=matched["accuracy_m"] as? Double
        val distance=if(lat!=null && lon!=null && claim!=null && matched["mock"]==false)
            horizontalDistanceM(lat,lon,claim.latitude,claim.longitude) else null
        val reference=when {
            distance==null || accuracy==null -> "UNAVAILABLE"
            distance+accuracy<30 -> "BELOW_30M_PHONE_ACCURACY_ONLY"
            distance-accuracy>30 -> "ABOVE_30M_PHONE_ACCURACY_ONLY"
            else -> "UNCERTAIN_AT_30M"
        }
        return o.copy(receiverPosition=matched+mapOf("claimed_horizontal_distance_m" to distance,
            "distance_30m_reference" to reference,"claim_accuracy_known" to false,
            "distance_is_ground_truth" to false))
    }
}

fun horizontalDistanceM(lat1:Double,lon1:Double,lat2:Double,lon2:Double):Double {
    val p1=lat1*PI/180;val p2=lat2*PI/180
    val a=sin((p2-p1)/2).pow(2)+cos(p1)*cos(p2)*sin((lon2-lon1)*PI/360).pow(2)
    return 6371008.8*2*asin(sqrt(a.coerceIn(0.0,1.0)))
}

/** Quote CSV and prevent untrusted text being interpreted as spreadsheet formulas. */
fun csvCell(value:Any?):String {
    val s=if(value==null) "" else if(value is String && value.firstOrNull() in listOf('=','+','-','@','\t','\r')) "'"+value else value.toString()
    return "\""+s.replace("\"","\"\"")+"\""
}
