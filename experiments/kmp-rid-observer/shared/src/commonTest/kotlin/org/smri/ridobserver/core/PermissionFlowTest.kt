package org.smri.ridobserver.core
import kotlin.test.*

class PermissionFlowTest {
    @Test fun onboardingConsentNeverStartsCapture() {
        val f=PermissionFlow();f.begin(false)
        assertFalse(f.complete(true));assertFalse(f.complete(true))
    }
    @Test fun deniedStartCannotBeResumedByUnrelatedLaterCallback() {
        val f=PermissionFlow();f.begin(true);assertFalse(f.complete(false))
        assertFalse(f.complete(true))
        f.begin(true);f.cancel();assertFalse(f.complete(true))
    }
    @Test fun optionalNotificationOutcomeDoesNotReplaceLocationConsent() {
        val f=PermissionFlow();f.begin(true)
        assertTrue(f.complete(true));assertFalse(f.complete(true))
    }
    @Test fun firstRequestRetryAndPermanentDenialHaveDifferentRoutes() {
        assertEquals(PermissionPolicy.Action.REQUEST,PermissionPolicy.location(false,false,false))
        assertEquals(PermissionPolicy.Action.REQUEST,PermissionPolicy.location(false,true,true))
        assertEquals(PermissionPolicy.Action.SETTINGS,PermissionPolicy.location(false,true,false))
        assertEquals(PermissionPolicy.Action.READY,PermissionPolicy.location(true,true,false))
    }
}
