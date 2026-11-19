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
import java.security.MessageDigest
import android.database.sqlite.SQLiteFullException

/** Device-only fixture DB; never opens or deletes the operator's real database. */
@Suppress("DEPRECATION")
class FieldTestInstrumentation : Instrumentation() {
    override fun onCreate(arguments:Bundle?) {super.onCreate(arguments);start()}
    override fun onStart() {
        val result=Bundle()
        try {
            testMigrationLocationPersistenceAndCsv();testRotationAndDedup();testCapacityStop();testAdditionalCaptureBoundary();testInterruptedSegmentRecovery()
            result.putString("stream","OK (5 tests): full legacy retained, rotation/dedup/export/restart, capacity stop, additional log boundary, privacy")
            finish(Activity.RESULT_OK,result)
        }
        catch(e:Throwable) {result.putString("stream","FAIL: "+e.javaClass.simpleName+": "+e.message);finish(Activity.RESULT_CANCELED,result)}
    }
    private fun assertEquals(a:Any?,b:Any?) {check(a==b) {"assertEquals expected=$a actual=$b"}}
    private fun assertTrue(b:Boolean) {check(b)}
    private fun assertNull(a:Any?) {check(a==null)}
    private fun hash(file:File):String {
        val h=MessageDigest.getInstance("SHA-256")
        file.inputStream().use {input -> val buffer=ByteArray(16384);while(true) {val n=input.read(buffer);if(n<0) break;h.update(buffer,0,n)}}
        return h.digest().joinToString("") {"%02x".format(it)}
    }
    private fun waitFor(db:ObservationDatabase) {
        val deadline=SystemClock.elapsedRealtime()+15000
        while(db.pendingWrites>0 && SystemClock.elapsedRealtime()<deadline) SystemClock.sleep(20)
        assertEquals(0,db.pendingWrites)
    }
    fun testInterruptedSegmentRecovery() {
        val seedName="test-seed-"+UUID.randomUUID().toString()
        val seed=ObservationDatabase.forTest(targetContext,seedName)
        seed.enqueueEvent("committed",emptyMap()) {error("seed write failed")};waitFor(seed);seed.closeTest()
        val seedFile=File(targetContext.filesDir,"captures/$seedName/segments").listFiles()!!.single {it.name.endsWith(".sqlite")}
        val name="test-recovery-"+UUID.randomUUID().toString()
        val dest=File(targetContext.filesDir,"captures/$name/segments");check(dest.mkdirs())
        val copied=File(dest,seedFile.name);val copiedJournal=File(copied.absolutePath+"-journal")
        SQLiteDatabase.openDatabase(seedFile.absolutePath,null,SQLiteDatabase.OPEN_READWRITE).use {sql ->
            sql.rawQuery("PRAGMA journal_mode=PERSIST",null).use {it.moveToFirst()}
            sql.execSQL("PRAGMA cache_size=1");sql.beginTransaction()
            try {
                repeat(5) {sql.execSQL("INSERT INTO receiver_events(raw_json) VALUES(?)",arrayOf("x".repeat(200000)))}
                seedFile.copyTo(copied);File(seedFile.absolutePath+"-journal").copyTo(copiedJournal)
            } finally {sql.endTransaction()}
        }
        assertTrue(copiedJournal.length()>512)
        val beforeDb=hash(copied);val beforeJournal=hash(copiedJournal)
        val db=ObservationDatabase.forTest(targetContext,name)
        assertEquals(0L,db.rowCount)
        val backups=File(targetContext.filesDir,"captures/$name/recovery").listFiles()!!
        assertEquals(1,backups.size)
        assertEquals(beforeDb,hash(File(backups[0],copied.name)))
        assertEquals(beforeJournal,hash(File(backups[0],copiedJournal.name)))
        SQLiteDatabase.openDatabase(copied.absolutePath,null,SQLiteDatabase.OPEN_READONLY).use {sql ->
            sql.rawQuery("SELECT COUNT(*) FROM receiver_events",null).use {c ->c.moveToFirst();assertEquals(1,c.getInt(0))}
        }
        db.closeTest()
        val again=ObservationDatabase.forTest(targetContext,name);again.closeTest()
        assertEquals(1,File(targetContext.filesDir,"captures/$name/recovery").listFiles()!!.size)
    }
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
            // An actual SQLiteFull on synthetic padding, never the operator's DB.
            db.setMaximumSize(64L*1024*1024)
            db.execSQL("CREATE TABLE padding(payload BLOB)")
            var full=false
            for(i in 0..70) {
                try {db.execSQL("INSERT INTO padding VALUES(zeroblob(1048576))")}
                catch(e:SQLiteFullException) {full=true;break}
            }
            assertTrue(full)
        }
        val originalHash=hash(file)
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
        assertEquals(originalHash,hash(file))
        SQLiteDatabase.openDatabase(file.absolutePath,null,SQLiteDatabase.OPEN_READONLY).use {assertEquals(1,it.version)}
    }
    fun testRotationAndDedup() {
        val name="test-"+UUID.randomUUID().toString()
        val limits=DatabaseStorageLimits(rotateBytes=512*1024,hardBytes=2*1024*1024,rows=3,archiveBytes=32*1024*1024,freeBytes=0)
        var db=ObservationDatabase.forTest(targetContext,name,limits)
        val engine=ObserverEngine()
        val observations=(1..10).map {i ->
            engine.ingest(ScanInput("02:00:00:00:00:01",-55,2452,10_000_000L+i*1_000_000,
                10_100_000L+i*1_000_000,"fixture-$i",listOf(fromHex("0102030405")),SourceType.REPLAY),true).single()
        }
        for(o in observations) db.enqueue(o,"fixture") {error("rotation fixture failed")}
        db.enqueueFix(ReceiverFix(20_000_000,"fixture-time",0.0,0.0,3.0,"fixture",true),"fixture") {error("fix fixture failed")}
        db.enqueueEvent("fixture",emptyMap()) {error("event fixture failed")}
        waitFor(db);assertNull(db.lastError);assertEquals(10L,db.rowCount)
        val dir=File(targetContext.filesDir,"captures/$name/segments")
        assertTrue(dir.listFiles().orEmpty().count {it.name.endsWith(".sqlite")}>=3)
        db.enqueue(observations.first(),"fixture") {error("dedup fixture failed")}
        waitFor(db);assertEquals(10L,db.rowCount)
        val out=StringWriter();db.writeExport(out,"dbjsonl");assertEquals(10,out.toString().trim().lines().size)
        db.closeTest();db=ObservationDatabase.forTest(targetContext,name,limits)
        assertEquals(10L,db.rowCount)
        db.enqueue(observations.first(),"fixture") {error("restart dedup fixture failed")}
        waitFor(db);assertNull(db.lastError);assertEquals(10L,db.rowCount);db.closeTest()
        for(file in dir.listFiles().orEmpty().filter {it.name.endsWith(".sqlite")}) {
            assertEquals(0,android.system.Os.stat(file.absolutePath).st_mode and 63)
            SQLiteDatabase.openDatabase(file.absolutePath,null,SQLiteDatabase.OPEN_READONLY).use {sql ->
                sql.rawQuery("PRAGMA integrity_check",null).use {it.moveToFirst();assertEquals("ok",it.getString(0))}
            }
        }
    }
    fun testCapacityStop() {
        val name="test-"+UUID.randomUUID().toString()
        val db=ObservationDatabase.forTest(targetContext,name,DatabaseStorageLimits(archiveBytes=1,freeBytes=0))
        val o=ObserverEngine().ingest(ScanInput("02:00:00:00:00:01",-55,2452,10_000_000,10_100_000,
            "fixture",listOf(fromHex("0102030405")),SourceType.REPLAY),true).single()
        db.enqueue(o,"fixture") {}
        waitFor(db);assertEquals("ARCHIVE_LIMIT_REACHED",db.lastError)
        val status=File(targetContext.filesDir,"captures/$name/storage-status.json")
        assertEquals("STOPPED_ARCHIVE_LIMIT_REACHED",org.json.JSONObject(status.readText()).getString("state"))
        assertEquals(0L,db.rowCount)
        val out=StringWriter();db.writeExport(out,"dbjsonl");assertEquals("",out.toString())
        db.closeTest()
    }
    fun testAdditionalCaptureBoundary() {
        val root=File(targetContext.filesDir,"test-extra-"+UUID.randomUUID());check(root.mkdirs())
        val session=CaptureSession(root,"fixture",65536)
        val o=ObserverEngine().ingest(ScanInput("02:00:00:00:00:01",-55,2452,10_000_000,10_100_000,
            "fixture",listOf(fromHex("0102030405")),SourceType.REPLAY),true).single()
        var limited=false
        for(i in 0..200) try {session.append(o)} catch(e:CaptureLimitException) {limited=true;break}
        assertTrue(limited);assertTrue(session.count>0)
        session.close("segment_rotated")
        val events=File(session.observations.parentFile,"events.jsonl").readLines()
        assertEquals("segment_rotated",org.json.JSONObject(events.last()).getString("reason"))
        val next=CaptureSession(root,"fixture",65536);next.append(o);next.close("fixture_stop")
        assertTrue(next.observations!=session.observations);assertTrue(session.observations.exists())
    }
}
