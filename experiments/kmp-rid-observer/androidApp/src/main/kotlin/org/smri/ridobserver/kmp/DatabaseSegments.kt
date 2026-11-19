package org.smri.ridobserver.kmp

import android.database.DatabaseErrorHandler
import android.database.DatabaseUtils
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteDatabaseCorruptException
import android.database.sqlite.SQLiteOpenHelper
import android.system.Os
import android.os.SystemClock
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.FileInputStream
import java.util.UUID

internal data class DatabaseStorageLimits(
    val rotateBytes:Long=48L*1024*1024,
    val hardBytes:Long=64L*1024*1024,
    val rows:Long=80_000,
    val archiveBytes:Long=1024L*1024*1024,
    val freeBytes:Long=512L*1024*1024,
    val maxSegments:Int=64
)
internal class StorageCapacityException(val reason:String):Exception(reason)

/** Call under the owner's storage lock. Legacy bytes are never opened writable or migrated. */
internal class DatabaseSegments(
    private val directory:File,
    private val limits:DatabaseStorageLimits,
    private val bootScope:String,
    private val factory:(File)->SQLiteOpenHelper
) {
    private val segmentDirectory=File(directory,"segments")
    private val legacy=File(directory,"observations.sqlite")
    private val pattern=Regex("segment-([0-9]{6})-[a-f0-9-]+\\.sqlite")
    private val archived=linkedMapOf<String,SQLiteDatabase>()
    private var helper:SQLiteOpenHelper?=null
    private var active:File?=null
    private var activeRows=0L
    private var lastStatusMs=-5000L
    @Volatile var state="READY";private set
    @Volatile var summary="既存データを保持";private set
    var rotations=0;private set
    init {
        require(limits.rotateBytes>0 && limits.hardBytes>limits.rotateBytes && limits.rows>0)
        require(limits.archiveBytes>0 && limits.freeBytes>=0 && limits.maxSegments>0)
        check(directory.mkdirs() || directory.isDirectory)
        check(segmentDirectory.mkdirs() || segmentDirectory.isDirectory)
        for(d in listOf(directory.parentFile!!,directory,segmentDirectory)) {
            check((Os.lstat(d.absolutePath).st_mode and 61440)!=40960) {"Storage symlink rejected"}
            Os.chmod(d.absolutePath,448)
        }
    }
    private fun segmentFiles():List<File> = segmentDirectory.listFiles().orEmpty()
        .filter {pattern.matches(it.name)}.sortedBy {it.name}.onEach {
            check(it.canonicalFile.parentFile==segmentDirectory.canonicalFile && (Os.lstat(it.absolutePath).st_mode and 61440)!=40960)
        }
    private fun paths():List<File> = (if(legacy.exists()) listOf(legacy) else emptyList())+segmentFiles()
    private fun reader(file:File):SQLiteDatabase {
        if(file==active) return checkNotNull(helper).readableDatabase
        check((Os.lstat(file.absolutePath).st_mode and 61440)!=40960) {"Database symlink rejected"}
        return archived.getOrPut(file.absolutePath) {
            SQLiteDatabase.openDatabase(file.absolutePath,null,SQLiteDatabase.OPEN_READONLY,
                DatabaseErrorHandler {throw SQLiteDatabaseCorruptException("Archived database retained")})
                .also {it.execSQL("PRAGMA cache_size=-512")}
        }
    }
    private var recoveryChecked=false
    /** Preserve exact interrupted-segment bytes before SQLite rolls back. Legacy stays immutable. */
    private fun recoverInterruptedSegments() {
        for(file in segmentFiles()) {
            val journal=File(file.absolutePath+"-journal")
            if(!journal.exists()) continue
            check((Os.lstat(journal.absolutePath).st_mode and 61440)!=40960) {"Journal symlink rejected"}
            if(journal.length()<=512) continue
            val header=ByteArray(8)
            val read=FileInputStream(journal).use {it.read(header)}
            val magic=byteArrayOf(0xd9.toByte(),0xd5.toByte(),0x05,0xf9.toByte(),0x20,0xa1.toByte(),0x63,0xd7.toByte())
            if(read!=8 || !header.contentEquals(magic)) continue
            val bytes=file.length()+journal.length()+256*1024
            if(directory.usableSpace<limits.freeBytes+bytes) throw StorageCapacityException("DEVICE_SPACE_LOW")
            if(usedBytes()+bytes>limits.archiveBytes) throw StorageCapacityException("ARCHIVE_LIMIT_REACHED")
            val root=File(directory,"recovery")
            check(root.mkdirs() || root.isDirectory)
            check((Os.lstat(root.absolutePath).st_mode and 61440)!=40960)
            Os.chmod(root.absolutePath,448)
            val backup=File(root,UUID.randomUUID().toString());check(backup.mkdir());Os.chmod(backup.absolutePath,448)
            fun digest(f:File):ByteArray {
                val md=java.security.MessageDigest.getInstance("SHA-256")
                FileInputStream(f).use {input -> val buffer=ByteArray(65536);while(true) {val n=input.read(buffer);if(n<0) break;md.update(buffer,0,n)}}
                return md.digest()
            }
            for(source in listOf(file,journal)) {
                val target=File(backup,source.name);check(target.createNewFile());Os.chmod(target.absolutePath,384)
                FileOutputStream(target).use {out -> FileInputStream(source).use {it.copyTo(out)};out.fd.sync()}
                check(digest(source).contentEquals(digest(target))) {"Incomplete recovery evidence"}
            }
            // SQLite recovery only: no migration, record deletion or corruption fallback.
            SQLiteDatabase.openDatabase(file.absolutePath,null,SQLiteDatabase.OPEN_READWRITE,
                DatabaseErrorHandler {throw SQLiteDatabaseCorruptException("Interrupted database retained")}).use {db ->
                db.rawQuery("PRAGMA integrity_check",null).use {c ->check(c.moveToFirst() && c.getString(0)=="ok") {"Recovery integrity failed"}}
            }
            state="RECOVERED_INTERRUPTED_TRANSACTION"
        }
    }
    fun readers():List<SQLiteDatabase> {
        if(!recoveryChecked) {recoverInterruptedSegments();recoveryChecked=true}
        return paths().map {reader(it)}
    }
    fun hasTable(db:SQLiteDatabase,table:String):Boolean = db.rawQuery(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",arrayOf(table)).use {it.moveToFirst()}
    fun count(db:SQLiteDatabase,table:String):Long = if(hasTable(db,table)) DatabaseUtils.queryNumEntries(db,table) else 0
    fun observationCount():Long=readers().sumOf {count(it,"observations")}
    fun observationExists(key:String):Boolean = readers().any {db ->
        hasTable(db,"observations") && db.rawQuery("SELECT 1 FROM observations WHERE dedupe_key=? LIMIT 1",arrayOf(key)).use {it.moveToFirst()}
    }
    private fun usedBytes():Long=directory.walkTopDown().onEnter {
        check((Os.lstat(it.absolutePath).st_mode and 61440)!=40960) {"Storage symlink rejected"};true
    }.filter {it.isFile}.sumOf {it.length()}
    private fun guard(incoming:Long,newSegment:Boolean=false) {
        if(incoming>limits.hardBytes/4) throw StorageCapacityException("RECORD_TOO_LARGE")
        if(directory.usableSpace<limits.freeBytes+incoming) throw StorageCapacityException("DEVICE_SPACE_LOW")
        val reserve=if(newSegment) limits.hardBytes else incoming+256*1024
        if(usedBytes()+reserve>limits.archiveBytes) throw StorageCapacityException("ARCHIVE_LIMIT_REACHED")
        if(newSegment && segmentFiles().size>=limits.maxSegments) throw StorageCapacityException("SEGMENT_LIMIT_REACHED")
    }
    private fun activate(file:File) {
        archived.remove(file.absolutePath)?.close()
        val next=factory(file)
        try {
            val db=next.writableDatabase
            active=file;helper=next
            activeRows=listOf("observations","receiver_fixes","receiver_events").sumOf {count(db,it)}
            privateFiles()
        } catch(e:Exception) {next.close();throw e}
    }
    fun writableFor(estimatedBytes:Long):SQLiteDatabase {
        guard(estimatedBytes)
        if(helper==null) {
            val last=segmentFiles().lastOrNull()
            if(last!=null) activate(last)
        }
        val db=helper?.writableDatabase
        val allocated=db?.rawQuery("PRAGMA page_count",null)?.use {it.moveToFirst();it.getLong(0)}?.let {pages ->
            pages*db.rawQuery("PRAGMA page_size",null).use {it.moveToFirst();it.getLong(0)}
        } ?: 0
        if(db==null || allocated+estimatedBytes>=limits.rotateBytes || activeRows>=limits.rows) {
            guard(estimatedBytes,true)
            val sequence=(segmentFiles().mapNotNull {pattern.matchEntire(it.name)?.groupValues?.get(1)?.toIntOrNull()}.maxOrNull() ?: 0)+1
            check(sequence<1_000_000)
            val next=File(segmentDirectory,"segment-%06d-%s.sqlite".format(sequence,UUID.randomUUID()))
            if(helper!=null) {helper!!.close();helper=null;active=null;rotations++}
            activate(next);state="ROTATED"
        }
        return checkNotNull(helper).writableDatabase
    }
    fun inserted() {
        activeRows++;state="RECORDING"
        active?.let {file ->
            for(f in listOf(file,File(file.absolutePath+"-journal"))) if(f.exists()) Os.chmod(f.absolutePath,384)
        }
        if(SystemClock.elapsedRealtime()-lastStatusMs>=5000) persistStatus()
    }
    fun persistStatus() {
        val used=usedBytes();summary="保存 ${used/(1024*1024)} / ${limits.archiveBytes/(1024*1024)} MiB · 自動切替 ${rotations}回"
        val status=JSONObject().put("schema","rid_storage_segments_v1").put("state",state)
            .put("used_bytes",used).put("archive_limit_bytes",limits.archiveBytes)
            .put("free_bytes",directory.usableSpace).put("reserve_free_bytes",limits.freeBytes)
            .put("active_segment",active?.name).put("active_rows",activeRows).put("rotation_count_process",rotations)
            .put("updated_at_utc",PlatformCompat.utc()).put("legacy_writable",false)
            .put("updated_elapsed_us",SystemClock.elapsedRealtimeNanos()/1000).put("boot_scope",bootScope)
            .put("wall_clock_independently_synced",false)
        val temp=File(directory,"storage-status.tmp")
        if(!temp.exists()) check(temp.createNewFile())
        check((Os.lstat(temp.absolutePath).st_mode and 61440)!=40960)
        Os.chmod(temp.absolutePath,384)
        FileOutputStream(temp).use {it.write(status.toString().toByteArray(Charsets.UTF_8));it.fd.sync()}
        check(temp.renameTo(File(directory,"storage-status.json"))) {"Status rename failed"}
        lastStatusMs=SystemClock.elapsedRealtime()
    }
    fun stopped(reason:String):Boolean {
        state="STOPPED_$reason"
        return try {persistStatus();true} catch(e:Exception) {false}
    }
    fun privateFiles() {
        for(d in listOf(directory,segmentDirectory)) for(f in d.listFiles().orEmpty()) if(f.isFile) {
            check((Os.lstat(f.absolutePath).st_mode and 61440)!=40960);Os.chmod(f.absolutePath,384)
        }
    }
    fun close() {helper?.close();helper=null;active=null;archived.values.forEach {it.close()};archived.clear()}
}
