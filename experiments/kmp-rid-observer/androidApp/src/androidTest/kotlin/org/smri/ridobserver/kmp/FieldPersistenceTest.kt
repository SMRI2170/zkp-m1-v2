package org.smri.ridobserver.kmp

import android.database.sqlite.SQLiteDatabase
import android.os.SystemClock
import android.app.Instrumentation
import android.app.Activity
import android.os.Bundle
import org.smri.ridobserver.core.*
import java.io.File
import java.io.StringWriter
import java.util.UUID

/** Device-only fixture DB; never opens or deletes the operator's real database. */
@Suppress("DEPRECATION")
class FieldTestInstrumentation : Instrumentation() {
    override fun onCreate(arguments:Bundle?) {super.onCreate(arguments);start()}
    override fun onStart() {
        val result=Bundle()
        try {testMigrationLocationPersistenceAndCsv();result.putString("stream","OK (1 test): migration, CSV, persistence, privacy");finish(Activity.RESULT_OK,result)}
        catch(e:Throwable) {result.putString("stream","FAIL: "+e.javaClass.simpleName+": "+e.message);finish(Activity.RESULT_CANCELED,result)}
    }
    private fun assertEquals(a:Any?,b:Any?) {check(a==b) {"assertEquals expected=$a actual=$b"}}
    private fun assertTrue(b:Boolean) {check(b)}
    private fun assertNull(a:Any?) {check(a==null)}
    fun testMigrationLocationPersistenceAndCsv() {
        val name="test-"+UUID.randomUUID().toString()
        val dir=File(targetContext.filesDir,"captures/$name");check(dir.mkdirs())
        val file=File(dir,"observations.sqlite")
        val oldRaw="""{"node_id":"old-fixture","rssi_dbm":-60}"""
        SQLiteDatabase.openOrCreateDatabase(file,null).use {db ->
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
            db.execSQL("INSERT INTO observations(dedupe_key,node_id,source_type,cache_stale,parse_status,raw_json,text_line) VALUES('fixture-old','fixture','replay',1,'invalid',?,'fixture-old-text')",arrayOf(oldRaw))
            db.version=1
        }
        var db=ObservationDatabase.forTest(targetContext,name)
        assertEquals(1L,db.rowCount)
        val base=ObserverEngine().ingest(ScanInput("02:00:00:00:00:01",-55,2452,10_000_000,10_100_000,"fixture-time",listOf(fromHex("0102030405")),SourceType.REPLAY),true).single()
        val h=ReceiverPositionHistory();val fix=ReceiverFix(10_000_000,"fixture-time",0.0,0.0,3.0,"fixture",true);h.add(fix)
        db.enqueue(h.annotate(base,10_100_000),"fixture") {error("fixture write failed")}
        db.enqueueFix(fix,"fixture") {error("fixture fix failed")}
        val deadline=SystemClock.elapsedRealtime()+5000
        while(db.pendingWrites>0 && SystemClock.elapsedRealtime()<deadline) SystemClock.sleep(20)
        assertEquals(0,db.pendingWrites);assertNull(db.lastError);assertEquals(2L,db.rowCount)
        val csv=StringWriter();db.writeExport(csv,"dbcsv")
        assertTrue(csv.toString().contains("boot_scope"));assertTrue(csv.toString().contains("receiver_scan_delta_us"));assertTrue(csv.toString().contains("0102030405"))
        val jsonLines=StringWriter();db.writeExport(jsonLines,"dbjsonl")
        assertTrue(org.json.JSONObject(jsonLines.toString().trim().lines().last()).has("boot_scope"))
        val fixes=StringWriter();db.writeExport(fixes,"fixcsv")
        assertTrue(fixes.toString().contains("fixture-time"));assertTrue(fixes.toString().contains("true"))
        db.closeTest()
        db=ObservationDatabase.forTest(targetContext,name);assertEquals(2L,db.rowCount);db.closeTest()
        SQLiteDatabase.openDatabase(file.absolutePath,null,SQLiteDatabase.OPEN_READONLY).use {sql ->
            sql.rawQuery("SELECT raw_json,text_line FROM observations WHERE dedupe_key='fixture-old'",null).use {c ->
                assertTrue(c.moveToFirst());assertEquals(oldRaw,c.getString(0));assertEquals("fixture-old-text",c.getString(1))
            }
            sql.rawQuery("PRAGMA integrity_check",null).use {c ->c.moveToFirst();assertEquals("ok",c.getString(0))}
        }
        assertEquals(0,android.system.Os.stat(file.absolutePath).st_mode and 63)
    }
}
