package org.smri.ridobserver.core

/** Consent does not itself authorize starting a recording. Preserve the user's intent. */
class PermissionFlow {
    private var startRequested=false
    fun begin(startAfterPermission:Boolean) {startRequested=startAfterPermission}
    fun cancel() {startRequested=false}
    fun complete(fineLocationGranted:Boolean):Boolean {
        val start=startRequested && fineLocationGranted
        startRequested=false
        return start
    }
}

object PermissionPolicy {
    enum class Action { READY, REQUEST, SETTINGS }
    fun location(fineGranted:Boolean,askedBefore:Boolean,canShowRationale:Boolean):Action = when {
        fineGranted -> Action.READY
        askedBefore && !canShowRationale -> Action.SETTINGS
        else -> Action.REQUEST
    }
}
