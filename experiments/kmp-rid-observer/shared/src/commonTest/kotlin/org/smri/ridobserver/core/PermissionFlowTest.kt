package org.smri.ridobserver.core
import kotlin.test.*

class PermissionFlowTest {
    @Test fun locationConsentPrecedesDisabledRadiosAndNotification() {
        assertEquals(PermissionPolicy.SetupStep.LOCATION_PERMISSION,PermissionPolicy.setupStep(false,false,false,true))
    }
    @Test fun grantedLocationStillNeedsEnabledLocationService() {
        assertEquals(PermissionPolicy.SetupStep.LOCATION_SETTINGS,PermissionPolicy.setupStep(true,false,true,false))
    }
    @Test fun wifiOffIsNotTreatedAsMissingRuntimeConsent() {
        assertEquals(PermissionPolicy.SetupStep.WIFI_SETTINGS,PermissionPolicy.setupStep(true,true,false,true))
    }
    @Test fun notificationIsOptionalAfterRequiredSetup() {
        assertEquals(PermissionPolicy.SetupStep.NOTIFICATION,PermissionPolicy.setupStep(true,true,true,true))
        assertEquals(PermissionPolicy.SetupStep.READY,PermissionPolicy.setupStep(true,true,true,false))
        val flow=PermissionFlow();flow.begin(false);assertFalse(flow.complete(true))
    }
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
