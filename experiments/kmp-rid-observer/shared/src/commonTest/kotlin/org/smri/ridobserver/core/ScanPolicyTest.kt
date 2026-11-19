package org.smri.ridobserver.core
import kotlin.test.*
class ScanPolicyTest {
    @Test fun legacyFastPathIsOnlyForPre26AndRemainsBestEffort() {
        for(sdk in listOf(24,25)) assertTrue(ScanPolicy.allowedOnPlatform(1_000,sdk,null))
        for(sdk in 26..29) assertFalse(ScanPolicy.allowedOnPlatform(1_000,sdk,null))
        assertFalse(ScanPolicy.allowedOnPlatform(1_000,31,null))
        assertFalse(ScanPolicy.allowedOnPlatform(1_000,31,true))
        assertTrue(ScanPolicy.allowedOnPlatform(1_000,31,false))
        assertFalse(ScanPolicy.allowedOnPlatform(500,24,null))
    }
    @Test fun fastestSelectionDoesNotTreatUnknownModernStateAsOff() {
        assertEquals(1_000,ScanPolicy.fastestOnPlatform(24,null))
        assertEquals(30_000,ScanPolicy.fastestOnPlatform(28,null))
        assertEquals(30_000,ScanPolicy.fastestOnPlatform(31,null))
        assertEquals(30_000,ScanPolicy.fastestOnPlatform(31,true))
        assertEquals(1_000,ScanPolicy.fastestOnPlatform(31,false))
    }
    @Test fun rejectionBackoffIsBoundedAndRecoversOnlyAfterAcceptance() {
        val delay=ScanRetryDelay()
        assertEquals(listOf(2_000L,4_000L,8_000L,16_000L,30_000L,30_000L),List(6){delay.next(1_000,false)})
        assertEquals(1_000,delay.next(1_000,true))
        assertEquals(2_000,delay.next(1_000,false))
        assertEquals(30_000,ScanRetryDelay().next(30_000,false))
    }
    @Test fun normalModeDoesNotRequireChangingOsPolicy() {
        assertTrue(ScanPolicy.allowed(30_000,true));assertTrue(ScanPolicy.allowed(30_000,false))
    }
    @Test fun fastRequestsFailClosedWhileThrottlingIsOn() {
        for(interval in listOf(1_000L,5_000L)) {
            assertFalse(ScanPolicy.allowed(interval,true));assertTrue(ScanPolicy.allowed(interval,false))
        }
    }
    @Test fun InvalidOrBusyLoopIntervalsReject() {
        for(interval in listOf(0L,-1L,500L,Long.MAX_VALUE))assertFalse(ScanPolicy.allowed(interval,false))
    }
}
