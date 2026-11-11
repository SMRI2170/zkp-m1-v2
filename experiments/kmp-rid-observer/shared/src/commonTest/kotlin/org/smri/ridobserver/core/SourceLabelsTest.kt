package org.smri.ridobserver.core

import kotlin.test.*

class SourceLabelsTest {
    @Test fun explicitIdsAndAddressesDistinguishSameClaimedId() {
        val rules=listOf(SourceRule("drone","Drone fixture","SAME","02:00:00:00:00:01"),SourceRule("onboard_pi","Pi fixture","SAME","02:00:00:00:00:02"))
        assertEquals("drone",classifySource("02:00:00:00:00:01",listOf("SAME"),rules).role)
        assertEquals("onboard_pi",classifySource("02:00:00:00:00:02",listOf("SAME"),rules).role)
        assertEquals(false,classifySource("02:00:00:00:00:02",listOf("SAME"),rules).fields()["identity_verified"])
    }
    @Test fun conflictIsNotSilentlyAssigned() {
        val rules=listOf(SourceRule("drone","Drone fixture","SAME"),SourceRule("onboard_pi","Pi fixture","SAME"))
        assertEquals("conflicting_local_rules",classifySource("fixture",listOf("SAME"),rules).basis)
    }
    @Test fun markerDoesNotAuthenticateAndOtherIdsStayUnknown() {
        assertEquals("unverified_test_marker",classifySource("fixture",listOf("PI-RID-LAB")).basis)
        assertEquals("unknown",classifySource("fixture",listOf("OTHER")).role)
    }
    @Test fun malformedObservationPreservesRawHexAddressAndRssiInText() {
        val body=fromHex("fa0bbc0d07")
        val o=ObserverEngine().ingest(ScanInput("02:00:00:00:00:50",-45,2452,1000000,2000000,"fixture",listOf(body))).single()
            .withSourceRules(listOf(SourceRule("onboard_pi","Pi fixture",bssid="02:00:00:00:00:50")))
        assertNull(o.decoded);assertTrue(o.toTextLine().contains("raw_vendor_ie_hex=fa0bbc0d07"))
        assertTrue(o.toTextLine().contains("02:00:00:00:00:50"));assertTrue(o.toTextLine().contains("Pi fixture"))
        assertTrue(o.toJson("fixture","run").contains("\"identity_verified\":false"))
    }
    @Test fun sameIdOnDifferentAddressesIsNotDeduplicatedTogether() {
        val basic=ByteArray(25).apply {this[0]=2;this[1]=0x40;"SAME".encodeToByteArray().copyInto(this,2)}
        val raw=fromHex("fa0bbc0d07")+basic
        val e=ObserverEngine()
        for(mac in listOf("02:00:00:00:00:50","02:00:00:00:00:51"))
            assertEquals("SAME",e.ingest(ScanInput(mac,-45,2452,1000000,2000000,"fixture",listOf(raw))).single().decoded!!.messages.single().uasId)
        assertEquals(2,e.targets.size)
    }
}
