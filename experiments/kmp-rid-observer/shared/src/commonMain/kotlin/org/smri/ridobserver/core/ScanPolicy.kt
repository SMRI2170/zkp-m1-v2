package org.smri.ridobserver.core

/** Request interval only: never a guarantee of new data at this rate. */
object ScanPolicy {
    val intervalsMs=listOf(30_000L,5_000L,1_000L)
    fun allowed(intervalMs:Long,throttleEnabled:Boolean):Boolean =
        intervalMs in intervalsMs && (intervalMs>=30_000 || !throttleEnabled)

    // Android's standard scan frequency restrictions begin at API26. Vendor limits
    // can still reject requests on API24/25; these are best-effort, never verified OFF.
    fun allowedOnPlatform(intervalMs:Long,sdk:Int,throttleEnabled:Boolean?):Boolean {
        if(intervalMs !in intervalsMs || sdk<24) return false
        return when {
            sdk<=25 -> true
            sdk<30 -> intervalMs>=30_000
            else -> allowed(intervalMs,throttleEnabled ?: true)
        }
    }
    fun fastestOnPlatform(sdk:Int,throttleEnabled:Boolean?):Long =
        if(allowedOnPlatform(1_000,sdk,throttleEnabled)) 1_000 else 30_000
    fun route(sdk:Int)=when {
        sdk in 24..25 -> "pre26_best_effort_vendor_limits_unverified"
        sdk>=30 -> "public_throttle_api"
        else -> "unknown_throttle_fail_closed"
    }
}

/** Rejected scans are not successful captures; reduce pressure until acceptance. */
class ScanRetryDelay {
    private var failures=0
    fun next(requestedMs:Long,accepted:Boolean):Long {
        require(requestedMs in ScanPolicy.intervalsMs)
        failures=if(accepted) 0 else (failures+1).coerceAtMost(5)
        return (requestedMs*(1L shl failures)).coerceAtMost(30_000)
    }
}
