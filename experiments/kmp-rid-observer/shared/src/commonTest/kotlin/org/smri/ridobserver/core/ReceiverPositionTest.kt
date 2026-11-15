package org.smri.ridobserver.core
import kotlin.test.*

class ReceiverPositionTest {
    private fun fix(us:Long=10_000_000,accuracy:Double=3.0,mock:Boolean=false)=ReceiverFix(us,"fixture-utc",0.0,0.0,accuracy,"gps",mock)
    @Test fun matchingUsesScanTimeInsteadOfDeliveryTime() {
        val h=ReceiverPositionHistory();h.add(fix(10_000_000));h.add(fix(25_000_000))
        assertEquals(10_000_000L,h.match(10_500_000,26_000_000,false)["fix_elapsed_us"])
        assertEquals("NO_FIX_WITHIN_2_SECONDS",h.match(20_000_000,26_000_000,false)["match_status"])
        assertEquals("STALE_WIFI_OBSERVATION",h.match(10_000_000,50_000_000,true)["match_status"])
        assertEquals("UNKNOWN_OR_FUTURE_WIFI_TIME",h.match(50_000_000,10_000_000,false)["match_status"])
    }
    @Test fun invalidFutureAndDuplicateFixesAreNotTrusted() {
        val h=ReceiverPositionHistory();assertFalse(h.add(fix().copy(latitude=91.0)))
        assertFalse(h.add(fix(accuracy=Double.NaN)));assertTrue(h.add(fix()));assertFalse(h.add(fix()))
        val future=ReceiverPositionHistory();future.add(fix(12_000_000))
        assertEquals("NO_FIX_WITHIN_2_SECONDS",future.match(10_000_000,10_500_000,false)["match_status"])
    }
    @Test fun distanceIsClaimComparisonNotGroundTruthAndMockCannotSetDistance() {
        fun observation()=Observation("02:00:00:00:00:01",SourceType.REPLAY,-50,2452,10_000_000,"fixture",false,
            DecodedRid(0,byteArrayOf(),"digest",listOf(RidMessage("location",claim=ClaimedPosition(0.0,0.00027,null,null)))),byteArrayOf(),null)
        val h=ReceiverPositionHistory();h.add(fix())
        val o=h.annotate(observation(),10_100_000);val p=o.receiverPosition!!
        assertEquals(30.02,p["claimed_horizontal_distance_m"] as Double,.05)
        assertEquals("UNCERTAIN_AT_30M",p["distance_30m_reference"])
        assertEquals(false,p["distance_is_ground_truth"])
        val mock=ReceiverPositionHistory();mock.add(fix(mock=true))
        assertNull(mock.annotate(observation(),10_100_000).receiverPosition!!["claimed_horizontal_distance_m"])
    }
    @Test fun unknownVendorAndMissingIeAreRetainedOnlyWithExplicitOptIn() {
        val input=ScanInput("02:00:00:00:00:01",-50,2452,10,20,"fixture",listOf(fromHex("0102030405")))
        assertTrue(ObserverEngine().ingest(input).isEmpty())
        val o=ObserverEngine().ingest(input,true).single()
        assertNull(o.decoded);assertEquals("UNCLASSIFIED_VENDOR_IE",o.error)
        assertTrue(o.toJson("fixture","run").contains("0102030405"))
        assertEquals("VENDOR_IE_UNAVAILABLE",ObserverEngine().ingest(input.copy(vendorIes=emptyList()),true).single().error)
    }
    @Test fun csvQuotesFieldsAndDoesNotExecuteFormulas() {
        assertEquals("\"a,\"\"b\"\"\n\"",csvCell("a,\"b\"\n"))
        assertEquals("\"'=1+1\"",csvCell("=1+1"));assertEquals("\"-60\"",csvCell(-60));assertEquals("\"\"",csvCell(null))
    }
}
