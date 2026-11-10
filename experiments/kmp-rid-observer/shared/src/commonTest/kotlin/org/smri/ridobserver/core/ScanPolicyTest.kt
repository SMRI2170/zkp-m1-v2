package org.smri.ridobserver.core
import kotlin.test.*
class ScanPolicyTest {
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
