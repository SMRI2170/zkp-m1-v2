package org.smri.ridobserver.replay

import org.smri.ridobserver.core.*
import java.nio.file.*
import java.nio.file.attribute.PosixFilePermissions
import java.io.File
import kotlin.system.exitProcess

/** JVM/Mac/Linux replay, always labelled replay. Does not operate a radio. */
fun main(args:Array<String>) {
    try {
        require(args.size in listOf(4,6) && args.size%2==0) { "--input input.tsv --output captures/new.jsonl [--repo-root path]" }
        val options=args.toList().chunked(2).associate {it[0] to it[1]}
        val input=File(requireNotNull(options["--input"]))
        val output=Path.of(requireNotNull(options["--output"])).toAbsolutePath().normalize()
        val root=Path.of(options["--repo-root"] ?: System.getProperty("rid.repoRoot") ?: error("repo-root required")).toAbsolutePath().normalize()
        require(output.startsWith(root.resolve("captures")) || output.startsWith(root.resolve("uav/captures"))) {"output must be in ignored captures/"}
        var parent=root
        for(component in root.relativize(output.parent)) {
            parent=parent.resolve(component)
            require(!Files.isSymbolicLink(parent)) {"symlink capture directory"}
            if(!Files.exists(parent)) Files.createDirectory(parent,PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")))
            require(Files.getOwner(parent).name==System.getProperty("user.name")) {"capture owner mismatch"}
            require(Files.getPosixFilePermissions(parent).none {it.name.startsWith("GROUP_") || it.name.startsWith("OTHERS_")}) {"capture directory must be owner-only"}
        }
        require(input.length()<=20*1024*1024) {"input too large"}
        val engine=ObserverEngine()
        var rows=0
        Files.newByteChannel(output,setOf(StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE),
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------"))).use { channel ->
            val writer=java.nio.channels.Channels.newWriter(channel,Charsets.UTF_8.newEncoder(),-1)
            input.useLines { lines ->
                lines.filter {it.isNotBlank() && !it.startsWith("#") && !it.startsWith("observed_us\t")}.forEach { line ->
                    require(++rows<=100000) {"too many rows"}
                    val c=line.split('\t');require(c.size==6) {"TSV needs 6 columns"}
                    val observed=c[0].takeIf {it.isNotEmpty()}?.toLong()
                    val delivered=c[1].takeIf {it.isNotEmpty()}?.toLong()
                    val rssi=c[2].takeIf {it.isNotEmpty()}?.toInt()
                    val frequency=c[3].takeIf {it.isNotEmpty()}?.toInt()
                    for(o in engine.ingest(ScanInput(c[5],rssi,frequency,observed,delivered,null,listOf(fromHex(c[4])),SourceType.REPLAY))) {
                        val data=o.toJson("jvm-replay","replay-run")+"\n"
                        require(channel.position()+data.toByteArray(Charsets.UTF_8).size<=20*1024*1024) {"output limit"}
                        writer.write(data);writer.flush()
                    }
                }
            }
        }
        println(json(mapOf("source_type" to "replay","input_rows" to rows,"records" to engine.records,
            "duplicates" to engine.duplicateResults,"invalid" to engine.invalidRecords,"new_rf_runs" to 0)))
    } catch(e: Exception) {
        System.err.println("Replay failed: ${e::class.simpleName}. Check arguments, permissions and TSV format.")
        exitProcess(2)
    }
}
