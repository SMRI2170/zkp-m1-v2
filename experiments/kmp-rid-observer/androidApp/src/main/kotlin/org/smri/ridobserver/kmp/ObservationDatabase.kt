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
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** Android persistence; no Activity reference, no network or destructive migration. */
class ObservationDatabase private constructor(private val app:Context) {
    private val directory=File(app.filesDir,"captures/database")
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
        helper=object:SQLiteOpenHelper(app,file.absolutePath,null,1,
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
            }
            override fun onUpgrade(db:SQLiteDatabase,old:Int,new:Int) {
                error("Explicit non-destructive database migration required")
            }
        }
        helper.setWriteAheadLoggingEnabled(false)
        rowCount=DatabaseUtils.queryNumEntries(helper.writableDatabase,"observations")
        privateFiles()
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
                        put("raw_json",o.toJson(nodeId,"database-process-$processScope"));put("text_line",o.toTextLine())
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
    fun recentText(limit:Int=50):String {
        require(limit in 1..200)
        return buildString {
            helper.readableDatabase.query("observations",arrayOf("text_line"),null,null,null,null,"id DESC",limit.toString()).use {c ->
                while(c.moveToNext()) {if(isNotEmpty()) append('\n');append(c.getString(0))}
            }
        }
    }
    /** Call only after the receiver has stopped; stream rows instead of loading the whole DB. */
    fun exportJsonLines(uri:Uri,onDone:(Boolean)->Unit) {
        check(pendingWrites==0) {"Database writes pending"}
        check(!exporting) {"Export already active"}
        exporting=true
        try {worker.execute {
            var ok=false
            try {
                app.contentResolver.openOutputStream(uri)?.bufferedWriter(Charsets.UTF_8)?.use {out ->
                    helper.readableDatabase.query("observations",arrayOf("raw_json"),null,null,null,null,"id ASC").use {c ->
                        while(c.moveToNext()) {out.write(c.getString(0));out.newLine()}
                    }
                } ?: error("Export destination unavailable")
                ok=true
            } catch(e:Exception) { /* report failure without exposing private row values */ }
            finally {exporting=false;main.post {onDone(ok)}}
        }} catch(e:Exception) {exporting=false;throw e}
    }
    companion object {
        @Volatile private var instance:ObservationDatabase?=null
        fun get(context:Context):ObservationDatabase = instance ?: synchronized(this) {
            instance ?: ObservationDatabase(context.applicationContext).also {instance=it}
        }
    }
}
