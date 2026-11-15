package org.smri.ridobserver.kmp

import android.content.ContentValues
import android.content.Context
import android.database.DatabaseErrorHandler
import android.database.DatabaseUtils
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteDatabaseCorruptException
import android.database.sqlite.SQLiteOpenHelper
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import org.smri.ridobserver.core.*
import java.io.File
import java.util.UUID
import java.io.Writer
import org.json.JSONObject
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** Android persistence; no Activity reference, no network or destructive migration. */
class ObservationDatabase private constructor(private val app:Context,storageName:String="database") {
    private val directory=File(app.filesDir,"captures/$storageName")
    private val file=File(directory,"observations.sqlite")
    private val processScope=UUID.randomUUID().toString()
    private val bootScope=try {
        Settings.Global.getInt(app.contentResolver,Settings.Global.BOOT_COUNT).toString()
    } catch(e:Exception) { "unknown-boot-$processScope" }
    private val worker=ThreadPoolExecutor(1,1,0L,TimeUnit.MILLISECONDS,ArrayBlockingQueue(256))
    private val pending=AtomicInteger()
    private val main=Handler(Looper.getMainLooper())
    private val helper:SQLiteOpenHelper
    @Volatile var rowCount=0L;private set
    @Volatile var lastError:String?=null;private set
    private val failed=AtomicInteger()
    val failedWrites:Int get()=failed.get()
    @Volatile var exporting=false;private set
    val pendingWrites:Int get()=pending.get()
    init {
        check(directory.mkdirs() || directory.isDirectory)
        android.system.Os.chmod(directory.parentFile!!.absolutePath,448)
        android.system.Os.chmod(directory.absolutePath,448)
        helper=object:SQLiteOpenHelper(app,file.absolutePath,null,2,
            DatabaseErrorHandler {throw SQLiteDatabaseCorruptException("Database retained for recovery")}) {
            override fun onConfigure(db:SQLiteDatabase) {
                // Keep the journal so its 0600 permissions can be set before any field observations.
                db.rawQuery("PRAGMA journal_mode=PERSIST",null).use {it.moveToFirst()}
                db.setMaximumSize(64L*1024*1024)
            }
            override fun onCreate(db:SQLiteDatabase) {
                db.execSQL("""CREATE TABLE observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    node_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    observed_us INTEGER,
                    received_at_utc TEXT,
                    rssi_dbm INTEGER,
                    frequency_mhz INTEGER,
                    uas_id TEXT,
                    latitude_claimed REAL,
                    longitude_claimed REAL,
                    altitude_geo_claimed REAL,
                    cache_stale INTEGER NOT NULL,
                    parse_status TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    text_line TEXT NOT NULL)""")
                addPositionSchema(db)
            }
            override fun onUpgrade(db:SQLiteDatabase,old:Int,new:Int) {
                check(old==1 && new==2) {"Unsupported migration; database retained"}
                addPositionSchema(db)
            }
        }
        helper.setWriteAheadLoggingEnabled(false)
        rowCount=DatabaseUtils.queryNumEntries(helper.writableDatabase,"observations")
        privateFiles()
    }
    private fun addPositionSchema(db:SQLiteDatabase) {
        for((name,type) in listOf("receiver_latitude" to "REAL","receiver_longitude" to "REAL",
            "receiver_accuracy_m" to "REAL","receiver_fix_us" to "INTEGER","receiver_scan_delta_us" to "INTEGER",
            "location_match_status" to "TEXT","claimed_horizontal_distance_m" to "REAL"))
            db.execSQL("ALTER TABLE observations ADD COLUMN $name $type")
        db.execSQL("CREATE TABLE receiver_events (id INTEGER PRIMARY KEY AUTOINCREMENT,raw_json TEXT NOT NULL)")
        db.execSQL("""CREATE TABLE receiver_fixes (id INTEGER PRIMARY KEY AUTOINCREMENT,
            fix_key TEXT NOT NULL UNIQUE,node_id TEXT NOT NULL,raw_json TEXT NOT NULL)""")
    }
    private fun privateFiles() {
        for(f in directory.listFiles().orEmpty()) if(f.isFile) android.system.Os.chmod(f.absolutePath,384)
    }
    fun enqueue(o:Observation,nodeId:String,onFailure:()->Unit) {
        check(lastError==null) {"Database requires recovery"}
        pending.incrementAndGet()
        try {
            worker.execute {
                try {
                    check(rowCount<100_000) {"Database row limit reached"}
                    val claim=o.decoded?.messages?.firstOrNull {it.claim!=null}?.claim
                    val values=ContentValues().apply {
                        put("dedupe_key",o.storageKey(bootScope,processScope));put("node_id",nodeId)
                        put("source_type",o.sourceType.wire);put("observed_us",o.observedUs)
                        put("received_at_utc",o.receivedAtUtc);put("rssi_dbm",o.rssiDbm);put("frequency_mhz",o.frequencyMhz)
                        put("uas_id",o.decoded?.messages?.firstOrNull {it.uasId!=null}?.uasId)
                        put("latitude_claimed",claim?.latitude);put("longitude_claimed",claim?.longitude)
                        put("altitude_geo_claimed",claim?.altitudeGeoM);put("cache_stale",if(o.stale) 1 else 0)
                        put("parse_status",if(o.decoded==null) "invalid" else "decoded")
                        val position=o.receiverPosition
                        put("receiver_latitude",position?.get("latitude") as? Double)
                        put("receiver_longitude",position?.get("longitude") as? Double)
                        put("receiver_accuracy_m",position?.get("accuracy_m") as? Double)
                        put("receiver_fix_us",position?.get("fix_elapsed_us") as? Long)
                        put("receiver_scan_delta_us",position?.get("scan_delta_us") as? Long)
                        put("location_match_status",position?.get("match_status") as? String)
                        put("claimed_horizontal_distance_m",position?.get("claimed_horizontal_distance_m") as? Double)
                        put("raw_json",JSONObject(o.toJson(nodeId,"database-process-$processScope")).put("boot_scope",bootScope).toString());put("text_line",o.toTextLine())
                    }
                    val id=helper.writableDatabase.insertWithOnConflict("observations",null,values,SQLiteDatabase.CONFLICT_IGNORE)
                    if(id!=-1L) rowCount++
                    privateFiles()
                } catch(e:Exception) {
                    failed.incrementAndGet();lastError=e.javaClass.simpleName;main.post(onFailure)
                } finally {pending.decrementAndGet()}
            }
        } catch(e:Exception) {
            pending.decrementAndGet();failed.incrementAndGet();lastError=e.javaClass.simpleName;throw e
        }
    }
    fun enqueueFix(fix:ReceiverFix,nodeId:String,onFailure:()->Unit) {
        check(lastError==null)
        pending.incrementAndGet()
        try {worker.execute {
            try {
                check(DatabaseUtils.queryNumEntries(helper.writableDatabase,"receiver_fixes")<100_000) {"Fix row limit reached"}
                val values=ContentValues().apply {
                    put("fix_key","$bootScope|${fix.us}|${fix.provider}");put("node_id",nodeId)
                    put("raw_json",json(fix.fields()+mapOf("node_id" to nodeId,"source_type" to "phone_location",
                        "boot_scope" to bootScope,"physical_position_verified" to false)))
                }
                helper.writableDatabase.insertWithOnConflict("receiver_fixes",null,values,SQLiteDatabase.CONFLICT_IGNORE);privateFiles()
            } catch(e:Exception) {failed.incrementAndGet();lastError=e.javaClass.simpleName;main.post(onFailure)}
            finally {pending.decrementAndGet()}
        }} catch(e:Exception) {pending.decrementAndGet();throw e}
    }
    fun enqueueEvent(kind:String,fields:Map<String,Any?>,onFailure:()->Unit) {
        check(lastError==null);pending.incrementAndGet()
        try {worker.execute {
            try {
                check(DatabaseUtils.queryNumEntries(helper.writableDatabase,"receiver_events")<100_000) {"Event limit reached"}
                val values=ContentValues();values.put("raw_json",json(mapOf("event" to kind,"utc" to PlatformCompat.utc(),"boot_scope" to bootScope)+fields))
                helper.writableDatabase.insertOrThrow("receiver_events",null,values);privateFiles()
            } catch(e:Exception) {failed.incrementAndGet();lastError=e.javaClass.simpleName;main.post(onFailure)}
            finally {pending.decrementAndGet()}
        }} catch(e:Exception) {pending.decrementAndGet();throw e}
    }
    /** A stopped receiver gives a stable streaming export, including legacy rows with empty new fields. */
    internal fun writeExport(out:Writer,kind:String) {
        require(kind in listOf("dbjsonl","dbcsv","fixcsv","diagnosticcsv"))
        val fields=if(kind=="diagnosticcsv") listOf("utc","boot_scope","event","elapsed_us","scan_requests","requests_rejected","request_interval_ms","scan_throttle_enabled","location_status","reason","raw_json") else if(kind=="fixcsv") listOf("node_id","boot_scope","fix_utc","fix_elapsed_us","latitude","longitude","accuracy_m","provider","mock","altitude_ellipsoid_m") else
            listOf("node_id","boot_scope","source_type","received_at_utc","polled_at_utc","monotonic_time_us","delivered_elapsed_us","bssid","rssi_dbm","frequency_mhz","rid_parse_status","rid_parse_reason","cache_stale","raw_vendor_ie_hex","ie_access","source_annotation","rid_messages","claimed_latitude","claimed_longitude","claimed_altitude_geo_m","rid_seconds_within_hour","receiver_position","receiver_latitude","receiver_longitude","receiver_accuracy_m","receiver_fix_utc","receiver_fix_us","receiver_scan_delta_us","location_match_status","claimed_horizontal_distance_m","distance_30m_reference","raw_json")
        if(kind!="dbjsonl") out.write(fields.joinToString(",") {csvCell(it)}+"\n")
        helper.readableDatabase.query(if(kind=="diagnosticcsv") "receiver_events" else if(kind=="fixcsv") "receiver_fixes" else "observations",arrayOf("raw_json"),null,null,null,null,"id ASC").use {c ->
            while(c.moveToNext()) {
                val raw=c.getString(0)
                if(kind=="dbjsonl") {out.write(raw);out.write("\n");continue}
                val o=JSONObject(raw)
                val messages=o.optJSONArray("rid_messages")
                val claim=(0 until (messages?.length() ?: 0)).mapNotNull {messages?.optJSONObject(it)?.optJSONObject("claimed_position")}.firstOrNull()
                out.write(fields.joinToString(",") {field ->
                    val keys=mapOf("receiver_latitude" to "latitude","receiver_longitude" to "longitude",
                        "receiver_accuracy_m" to "accuracy_m","receiver_fix_utc" to "fix_utc","receiver_fix_us" to "fix_elapsed_us",
                        "receiver_scan_delta_us" to "scan_delta_us","location_match_status" to "match_status",
                        "claimed_horizontal_distance_m" to "claimed_horizontal_distance_m","distance_30m_reference" to "distance_30m_reference")
                    val claimKeys=mapOf("claimed_latitude" to "latitude","claimed_longitude" to "longitude","claimed_altitude_geo_m" to "altitude_geo_m","rid_seconds_within_hour" to "seconds_within_hour")
                    csvCell(if(field=="raw_json") raw else (if(field in claimKeys) claim?.opt(claimKeys.getValue(field)) else if(field in keys) o.optJSONObject("receiver_position")?.opt(keys.getValue(field)) else o.opt(field)).takeUnless {it==JSONObject.NULL})
                }+"\n")
            }
        }
    }
    internal fun closeTest() {worker.shutdown();worker.awaitTermination(5,TimeUnit.SECONDS);helper.close()}
    fun recentText(limit:Int=50):String {
        require(limit in 1..200)
        return buildString {
            helper.readableDatabase.query("observations",arrayOf("text_line"),null,null,null,null,"id DESC",limit.toString()).use {c ->
                while(c.moveToNext()) {if(isNotEmpty()) append('\n');append(c.getString(0))}
            }
        }
    }
    /** Call only after the receiver has stopped; stream rows instead of loading the whole DB. */
    fun exportJsonLines(uri:Uri,onDone:(Boolean)->Unit) = exportData(uri,"dbjsonl",onDone)
    fun exportData(uri:Uri,kind:String,onDone:(Boolean)->Unit) {
        check(pendingWrites==0) {"Database writes pending"}
        check(!exporting) {"Export already active"}
        exporting=true
        try {worker.execute {
            var ok=false
            try {
                app.contentResolver.openOutputStream(uri)?.bufferedWriter(Charsets.UTF_8)?.use {out ->
                    writeExport(out,kind)
                } ?: error("Export destination unavailable")
                ok=true
            } catch(e:Exception) { /* report failure without exposing private row values */ }
            finally {exporting=false;main.post {onDone(ok)}}
        }} catch(e:Exception) {exporting=false;throw e}
    }
    companion object {
        internal fun forTest(context:Context,name:String):ObservationDatabase {
            require(name.matches(Regex("test-[a-zA-Z0-9-]+")))
            return ObservationDatabase(context.applicationContext,name)
        }
        @Volatile private var instance:ObservationDatabase?=null
        fun get(context:Context):ObservationDatabase = instance ?: synchronized(this) {
            instance ?: ObservationDatabase(context.applicationContext).also {instance=it}
        }
    }
}
