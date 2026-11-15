package org.smri.ridobserver.core

/** Request interval only: never a guarantee of new data at this rate. */
object ScanPolicy {
    val intervalsMs=listOf(30_000L,5_000L,1_000L)
    fun allowed(intervalMs:Long,throttleEnabled:Boolean):Boolean =
        intervalMs in intervalsMs && (intervalMs>=30_000 || !throttleEnabled)
}
