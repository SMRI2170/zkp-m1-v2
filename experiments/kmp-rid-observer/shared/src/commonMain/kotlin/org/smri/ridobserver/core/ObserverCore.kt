package org.smri.ridobserver.core

/** Pure shared parsing/state/serialization. No Android or java imports here. */
expect fun sha256(bytes: ByteArray): String

fun ByteArray.hex(): String = joinToString("") { (it.toInt() and 255).toString(16).padStart(2, '0') }
fun fromHex(text: String): ByteArray {
    require(text.length % 2 == 0 && text.all { it in "0123456789abcdefABCDEF" }) { "invalid hex" }
    return ByteArray(text.length / 2) { text.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
}
private fun ByteArray.u(i: Int) = this[i].toInt() and 255
private fun ByteArray.u16(i: Int) = u(i) or (u(i + 1) shl 8)
private fun ByteArray.i32(i: Int) = u(i) or (u(i+1) shl 8) or (u(i+2) shl 16) or (u(i+3) shl 24)

data class ClaimedPosition(val latitude: Double, val longitude: Double, val altitudeGeoM: Double?, val secondsWithinHour: Double?)
data class RidMessage(val type: String, val uasId: String? = null, val claim: ClaimedPosition? = null)
data class DecodedRid(val counter: Int, val payload: ByteArray, val digest: String, val messages: List<RidMessage>)

object Odid {
    fun isVendor(body: ByteArray): Boolean = body.size >= 4 &&
        body.u(0)==0xfa && body.u(1)==0x0b && body.u(2)==0xbc && body.u(3)==0x0d

    fun decode(body: ByteArray): DecodedRid {
        require(isVendor(body) && body.size in 6..255) { "invalid ODID Vendor IE" }
        val payload = body.copyOfRange(5, body.size)
        val messages = if (payload.size == 25 && payload.u(0) shr 4 != 15) {
            listOf(decodeMessage(payload))
        } else {
            require(payload.size >= 3 && payload.u(0)==0xf2 && payload.u(1)==25 && payload.u(2) in 1..9) { "invalid Message Pack header" }
            require(payload.size == 3 + 25 * payload.u(2)) { "Message Pack length mismatch" }
            List(payload.u(2)) { decodeMessage(payload.copyOfRange(3 + it*25, 28 + it*25)) }
        }
        return DecodedRid(body.u(4), payload, sha256(body), messages)
    }

    private fun decodeMessage(raw: ByteArray): RidMessage {
        require(raw.size==25 && raw.u(0) and 15==2) { "unsupported message protocol version" }
        return when(raw.u(0) shr 4) {
            0 -> {
                val id = raw.copyOfRange(2,22).takeWhile { it.toInt()!=0 }
                require(id.all { (it.toInt() and 255) in 32..126 }) { "Basic ID is not ASCII" }
                RidMessage("basic_id", id.map { (it.toInt() and 255).toChar() }.joinToString("").trim().ifEmpty { null })
            }
            1 -> {
                val lat = raw.i32(5) / 10_000_000.0
                val lon = raw.i32(9) / 10_000_000.0
                val altitude = raw.u16(15)
                val time = raw.u16(21)
                require(lat in -90.0..90.0 && lon in -180.0..180.0) { "invalid claimed coordinates" }
                require(time==65535 || time < 36000) { "invalid timestamp within hour" }
                RidMessage("location", claim=ClaimedPosition(lat,lon,if(altitude==0 || altitude==65535) null else altitude*0.5-1000,
                    if(time==65535) null else time/10.0))
            }
            2 -> RidMessage("authentication") // framing only; no DRIP verification.
            3 -> RidMessage("self_id")
            4 -> RidMessage("system")
            5 -> RidMessage("operator_id")
            else -> throw IllegalArgumentException("unsupported message type")
        }
    }
}

enum class SourceType(val wire: String) { REAL_CAPTURE("real_capture"), REPLAY("replay") }
data class ScanInput(val sourceKey: String, val rssiDbm: Int?, val frequencyMhz: Int?,
                     val observedUs: Long?, val deliveredUs: Long?, val receivedAtUtc: String?,
                     val vendorIes: List<ByteArray>, val sourceType: SourceType = SourceType.REAL_CAPTURE)

data class Observation(val sourceKey: String, val sourceType: SourceType, val rssiDbm: Int?,
                       val frequencyMhz: Int?, val observedUs: Long?, val receivedAtUtc: String?,
                       val stale: Boolean, val decoded: DecodedRid?, val body: ByteArray, val error: String?,
                       val annotation:SourceAnnotation=SourceAnnotation(),
                       val direction:Map<String,Any?>?=null,
                       val receiverPosition:Map<String,Any?>?=null,
                       val deliveredUs:Long?=null,val polledAtUtc:String?=null,
                       val ieAccess:Map<String,Any?>?=null) {
    fun isStaleAt(nowUs:Long):Boolean = stale || observedUs==null || observedUs<=0 || nowUs<observedUs || nowUs-observedUs>30_000_000
    private fun messageFields() = decoded?.messages?.map { m -> mapOf(
        "type" to m.type, "uas_id" to m.uasId,
        "claimed_position" to m.claim?.let { mapOf("latitude" to it.latitude,
            "longitude" to it.longitude,"altitude_geo_m" to it.altitudeGeoM,
            "seconds_within_hour" to it.secondsWithinHour) }) }
    /** A single escaped text line; freshness is the state when the observation was captured. */
    fun toTextLine():String = "received_at_utc=${json(receivedAtUtc)} observed_us=$observedUs " +
        "rssi_dbm=$rssiDbm frequency_mhz=$frequencyMhz source_type=${sourceType.wire} " +
        "bssid=${json(sourceKey)} source=${json(annotation.fields())} " +
        "parse_status=${if(decoded==null) "invalid" else "decoded"} counter=${decoded?.counter} " +
        "cache_stale_at_capture=$stale messages=${json(messageFields())} raw_vendor_ie_hex=${body.hex()} " +
        "direction=${json(direction)} receiver_position=${json(receiverPosition)}"
    /** Monotonic observation times must not collide across device boots. Unknown times use process scope. */
    fun storageKey(bootScope:String,unknownTimeScope:String):String = sha256(json(listOf(
        bootScope,if(observedUs==null || observedUs<=0) unknownTimeScope else null,
        sourceType.wire,sourceKey.lowercase(),frequencyMhz,observedUs,digest)).encodeToByteArray())
    val digest: String get() = decoded?.digest ?: sha256(body)
    fun toJson(nodeId: String, runId: String): String = json(mapOf(
        "schema_version" to "wifi_observation_v1", "node_id" to nodeId, "capture_run_id" to runId,
        "source_type" to sourceType.wire,
        "observation_kind" to if(sourceType==SourceType.REPLAY) "replayed_scan_result" else "android_scan_result",
        "rx_phy" to "wifi_beacon", "vendor_format" to if(Odid.isVendor(body)) "opendroneid_candidate" else "unclassified_wifi_candidate", "received_at_utc" to receivedAtUtc, "monotonic_time_us" to observedUs,
        "clock_sync_method" to "unknown", "time_uncertainty_ms" to null,
        "rssi_dbm" to rssiDbm, "rssi_missing_reason" to if(rssiDbm==null) "RSSI_ABSENT_OR_INVALID" else null,
        "frequency_mhz" to frequencyMhz, "bssid" to sourceKey, "frame_digest" to null,
        "sequence_control" to null, "beacon_tsf_us" to null,
        "vendor_content_digest" to digest, "odid_counter" to decoded?.counter,
        "odid_payload_hex" to if(body.size>=5) body.copyOfRange(5,body.size).hex() else null,
        "rid_messages" to messageFields(), "raw_vendor_ie_hex" to body.hex(),
        "source_annotation" to annotation.fields(),
        "direction" to direction,
        "rid_parse_status" to if(decoded==null) "invalid" else "decoded", "rid_parse_reason" to error,
        "cache_stale" to stale, "physical_packet_match" to "unconfirmed",
        "ie_access" to ieAccess,"delivered_elapsed_us" to deliveredUs,"polled_at_utc" to polledAtUtc,
        "receiver_position" to receiverPosition, "absolute_power_calibrated" to false,
        "drip_verified" to false))
}

data class TargetState(val alias: String, var latest: Observation, var records: Int = 1,
                       val samples: MutableList<Pair<Long,Int>> = mutableListOf())

class ObserverEngine(private val maxAgeUs: Long = 30_000_000, private val maxSeen: Int = 4096) {
    private val seen = mutableSetOf<String>()
    val targets: MutableMap<String,TargetState> = linkedMapOf()
    var duplicateResults: Int = 0; private set
    var invalidRecords: Int = 0; private set
    var records: Int = 0; private set
    fun ingest(input: ScanInput,includeUnknownWifi:Boolean=false): List<Observation> {
        val out = mutableListOf<Observation>()
        for(body in input.vendorIes.ifEmpty {if(includeUnknownWifi) listOf(byteArrayOf()) else emptyList()}) {
            if(!Odid.isVendor(body) && !includeUnknownWifi) continue
            val digest = sha256(body)
            val key = "${input.sourceType.wire}|${input.sourceKey.lowercase()}|${input.frequencyMhz}|${input.observedUs}|$digest"
            if(!seen.add(key)) { duplicateResults++; continue }
            if(seen.size>maxSeen) seen.remove(seen.first())
            val age = if(input.observedUs!=null && input.observedUs>0 && input.deliveredUs!=null && input.deliveredUs>=input.observedUs)
                input.deliveredUs-input.observedUs else null
            val decoded = runCatching { Odid.decode(body) }
            val observation = Observation(input.sourceKey.lowercase(),input.sourceType,
                input.rssiDbm?.takeIf { it in -127..-1 },input.frequencyMhz?.takeIf { it>0 },input.observedUs,
                input.receivedAtUtc,age==null || age>maxAgeUs,decoded.getOrNull(),body.copyOf(),
                if(!Odid.isVendor(body)) (if(body.isEmpty()) "VENDOR_IE_UNAVAILABLE" else "UNCLASSIFIED_VENDOR_IE") else decoded.exceptionOrNull()?.message,deliveredUs=input.deliveredUs)
            records++
            if(observation.decoded==null) invalidRecords++
            val targetKey = "${input.sourceType}|${observation.sourceKey}|${input.frequencyMhz}"
            var target = targets[targetKey]
            if(target==null) {
                if(targets.size>=128) targets.remove(targets.keys.first())
                target=TargetState("T${records}",observation)
                targets[targetKey]=target
            } else { target.latest=observation;target.records++ }
            if(observation.rssiDbm!=null && input.observedUs!=null && !observation.stale && observation.decoded!=null) {
                target.samples.add(input.observedUs to observation.rssiDbm)
                target.samples.sortBy { it.first }
                if(target.samples.size>120) target.samples.removeAt(0)
            }
            out.add(observation)
        }
        return out
    }

    /** Summary export excludes BSSID, claimed coordinates, serial IDs and raw payloads. */
    fun summaryCsv(): String = buildString {
        append("target_alias,source_type,scan_observations,rssi_dbm,frequency_mhz,parse_status,cache_stale\n")
        for(t in targets.values) {
            val o=t.latest
            append(listOf(t.alias,o.sourceType.wire,t.records,o.rssiDbm ?: "",o.frequencyMhz ?: "",
                if(o.decoded==null) "invalid" else "decoded",o.stale).joinToString(","))
            append('\n')
        }
    }
}

/** Small dependency-free common JSON writer; no platform serializer in the core. */
fun json(value: Any?): String = when(value) {
    null -> "null"
    is String -> buildString {
        append('"')
        for(c in value) when(c) {
            '"' -> append("\\\""); '\\' -> append("\\\\"); '\n' -> append("\\n"); '\r' -> append("\\r"); '\t' -> append("\\t")
            else -> if(c.code<32) append("\\u"+c.code.toString(16).padStart(4,'0')) else append(c)
        }
        append('"')
    }
    is Boolean, is Int, is Long -> value.toString()
    is Double -> if(value.isFinite()) value.toString() else "null"
    is Map<*,*> -> value.entries.joinToString(",","{","}") { json(it.key.toString())+":"+json(it.value) }
    is List<*> -> value.joinToString(",","[","]") { json(it) }
    else -> error("unsupported JSON value")
}

/** Small in-memory text preview, independent of full on-disk JSONL capture. */
class RecentTextLog(private val maxLines:Int=50) {
    init {require(maxLines in 1..200)}
    private val lines=ArrayDeque<String>()
    fun append(observation:Observation) {
        lines.addLast(observation.toTextLine())
        if(lines.size>maxLines) lines.removeFirst()
    }
    fun snapshot():String=lines.joinToString("\n")
    val size:Int get()=lines.size
}
