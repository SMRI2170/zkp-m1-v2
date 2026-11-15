package org.smri.ridobserver.core
import kotlin.test.*

private fun body(counter: Int=204): ByteArray {
    val basic=ByteArray(25);basic[0]=2;basic[1]=0x12
    "KMP-TEST".encodeToByteArray().copyInto(basic,2)
    val loc=ByteArray(25);loc[0]=0x12;loc[15]=0xff.toByte();loc[16]=0xff.toByte();loc[21]=0xff.toByte();loc[22]=0xff.toByte()
    return fromHex("fa0bbc0d")+byteArrayOf(counter.toByte(),0xf2.toByte(),25,2)+basic+loc
}
private fun input(b: ByteArray=body(), observed: Long?=1_000_000, rssi: Int? = -50, source: SourceType=SourceType.REAL_CAPTURE) =
    ScanInput("02:00:00:00:00:01",rssi,2452,observed,2_000_000,"fixture-time",listOf(b),source)

class CoreTest {
    @Test fun displayedObservationAgesWithoutAnotherScan() {
        val o=ObserverEngine().ingest(input()).single()
        assertFalse(o.isStaleAt(2_000_000))
        assertTrue(o.isStaleAt(32_000_000))
        assertTrue(o.isStaleAt(999_999))
    }
    @Test fun hashVector() { assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",sha256("abc".encodeToByteArray())) }
    @Test fun packAndMissingFields() {
        val d=Odid.decode(body());assertEquals(204,d.counter);assertEquals("KMP-TEST",d.messages[0].uasId)
        assertNull(d.messages[1].claim?.altitudeGeoM);assertNull(d.messages[1].claim?.secondsWithinHour)
        assertEquals(sha256(body()),d.digest)
    }
    @Test fun malformedPacksReject() {
        assertFailsWith<IllegalArgumentException> { Odid.decode(body().copyOf(20)) }
        val wrong=body();wrong[7]=0xf1.toByte()
        assertFailsWith<IllegalArgumentException> { Odid.decode(wrong) }
    }
    @Test fun unknownRssiAndTimestampStayUnknown() {
        val o=ObserverEngine().ingest(input(observed=null,rssi=0)).single()
        assertNull(o.rssiDbm);assertTrue(o.stale)
        val data=o.toJson("fixture","run")
        assertTrue(data.contains("\"rssi_dbm\":null"));assertTrue(data.contains("\"frame_digest\":null"))
    }
    @Test fun cachedReplayNotAnotherObservation() {
        val engine=ObserverEngine();assertEquals(1,engine.ingest(input()).size);assertTrue(engine.ingest(input()).isEmpty())
        assertEquals(1,engine.duplicateResults);assertEquals(1,engine.records)
    }
    @Test fun changedCounterIsNotDropped() {
        val engine=ObserverEngine();engine.ingest(input());assertEquals(1,engine.ingest(input(body(205))).size)
    }
    @Test fun replayAndLiveAreDistinct() {
        val e=ObserverEngine();val o=e.ingest(input(source=SourceType.REPLAY)).single()
        assertTrue(o.toJson("fixture","run").contains("\"source_type\":\"replay\""))
        assertEquals(1,e.ingest(input()).size)
        assertEquals(2,e.targets.size)
        assertFalse(e.summaryCsv().contains("02:00"));assertFalse(e.summaryCsv().contains("KMP-TEST"))
    }
    @Test fun malformedIesRecordedAsInvalidNotNormal() {
        val e=ObserverEngine();val o=e.ingest(input(fromHex("fa0bbc0d07"))).single()
        assertNull(o.decoded);assertEquals(1,e.invalidRecords);assertTrue(e.targets.values.single().samples.isEmpty())
    }
    @Test fun boundedHistoryAndState() {
        val e=ObserverEngine(maxSeen=64)
        repeat(150) { e.ingest(input(observed=1000000L+it)) }
        assertEquals(120,e.targets.values.single().samples.size)
    }
    @Test fun jsonEscapesUserLabels() { assertEquals("\"a\\\"b\\nc\"",json("a\"b\nc")) }
    @Test fun outOfOrderTimesDoNotReverseChart() {
        val e=ObserverEngine();e.ingest(input(observed=1_500_000));e.ingest(input(observed=1_000_000))
        assertEquals(listOf(1_000_000L,1_500_000L),e.targets.values.single().samples.map {it.first})
    }
    @Test fun readableJsonContainsDecodedClaimsWithUnknownValuesPreserved() {
        val data=ObserverEngine().ingest(input()).single().toJson("fixture","run")
        assertTrue(data.contains("\"rid_messages\":["))
        assertTrue(data.contains("\"uas_id\":\"KMP-TEST\""))
        assertTrue(data.contains("\"altitude_geo_m\":null"))
    }
    @Test fun textLineEscapesNewlinesAndKeepsUnknownRssi() {
        val o=ObserverEngine().ingest(input(rssi=null).copy(receivedAtUtc="clock\nunknown")).single()
        val text=o.toTextLine()
        assertFalse(text.contains('\n'));assertTrue(text.contains("rssi_dbm=null"))
        assertTrue(text.contains("clock\\nunknown"));assertTrue(text.contains("KMP-TEST"))
    }
    @Test fun textPreviewRetainsOnlyRecentLines() {
        val log=RecentTextLog(3);val e=ObserverEngine()
        repeat(5) {i ->log.append(e.ingest(input(observed=1_000_000L+i)).single())}
        assertEquals(3,log.size);val text=log.snapshot()
        assertFalse(text.contains("observed_us=1000000 "))
        assertTrue(text.contains("observed_us=1000004 "));assertEquals(3,text.lines().size)
    }
    @Test fun malformedPayloadDoesNotInventDecodedText() {
        val o=ObserverEngine().ingest(input(fromHex("fa0bbc0d07"))).single()
        assertTrue(o.toTextLine().contains("parse_status=invalid"))
        assertTrue(o.toTextLine().contains("messages=null"))
    }
    @Test fun databaseDeduplicationSurvivesProcessButNotDeviceBoot() {
        val o=ObserverEngine().ingest(input()).single()
        assertEquals(o.storageKey("boot1","process1"),o.storageKey("boot1","process2"))
        assertNotEquals(o.storageKey("boot1","process1"),o.storageKey("boot2","process1"))
        val newer=ObserverEngine().ingest(input(observed=1_000_001)).single()
        assertNotEquals(o.storageKey("boot1","p"),newer.storageKey("boot1","p"))
    }
    @Test fun databaseDoesNotMergeUnknownTimesAcrossProcessRestarts() {
        val o=ObserverEngine().ingest(input(observed=null)).single()
        assertNotEquals(o.storageKey("boot1","p1"),o.storageKey("boot1","p2"))
    }
}
