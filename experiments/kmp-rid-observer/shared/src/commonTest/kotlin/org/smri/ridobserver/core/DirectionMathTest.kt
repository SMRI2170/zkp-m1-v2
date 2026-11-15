package org.smri.ridobserver.core

import kotlin.test.*
import kotlin.math.*

class DirectionMathTest {
    private fun sweep(power:(Double,Int)->Double)=List(72) {i ->
        val theta=i*5.0
        DirectionMath.Sample(1_000_000L+i*30_000_000L,theta,power(theta,i))
    }
    @Test fun matchesScanTimeNotCallbackTime() {
        val h=DirectionMath.Heading(1_000_000,90.0,0.0,3)
        assertEquals(h,DirectionMath.nearest(listOf(h),1_100_000))
        assertNull(DirectionMath.nearest(listOf(h),31_000_000))
        assertNull(DirectionMath.nearest(listOf(h.copy(accuracy=0)),1_000_000))
        assertNull(DirectionMath.nearest(listOf(h.copy(tiltDeg=26.0)),1_000_000))
        assertNull(DirectionMath.nearest(listOf(h),null))
    }
    @Test fun recoversSyntheticPhonePeakWithLinearDrift() {
        val fit=DirectionMath.fit(sweep {a,i -> -60+5*cos((a-75)*PI/180)+i*.05})
        assertEquals("EXPERIMENTAL_PHONE_PEAK",fit["status"])
        assertEquals(75.0,fit["peak_phone_heading_deg"] as Double,1e-5)
        assertNull(fit["transmitter_bearing_deg"])
        assertEquals(false,fit["accuracy_validated"])
    }
    @Test fun flatSignalAndLimitedRotationWithholdAngle() {
        val flat=DirectionMath.fit(sweep {_,i -> -60+i*.1})
        assertEquals("WEAK_DIRECTIONAL_SIGNAL",flat["status"])
        assertNull(flat["peak_phone_heading_deg"])
        assertEquals("INSUFFICIENT_ROTATION",DirectionMath.fit(sweep {_,_-> -60.0}.take(10))["status"])
    }
    @Test fun directionCorrelatedPowerCanSpoofGoodFit() {
        // Identical input can arise from power manipulation alone. The fit must never claim AoA.
        val fit=DirectionMath.fit(sweep {a,_-> -60+6*cos((a-220)*PI/180)})
        assertEquals("EXPERIMENTAL_PHONE_PEAK",fit["status"])
        assertEquals(false,fit["aoa_measured"])
        assertNull(fit["transmitter_bearing_deg"])
    }
    @Test fun savedRawTextAndJsonKeepDirectionAndMissingReason() {
        val o=Observation("02:00:00:00:00:01",SourceType.REAL_CAPTURE,-50,2452,1000,"TEST_TIME",false,
            null,byteArrayOf(1,2),"invalid",direction=mapOf("missing_reason" to "SENSOR_UNAVAILABLE"))
        assertTrue(o.toTextLine().contains("raw_vendor_ie_hex=0102"))
        assertTrue(o.toTextLine().contains("SENSOR_UNAVAILABLE"))
        assertTrue(o.toJson("test","test").contains("\"direction\":{"))
        assertFalse(o.toTextLine().contains('\n'))
    }
}
