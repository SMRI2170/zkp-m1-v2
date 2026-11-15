package org.smri.ridobserver.core

/** Reserve a small amount of the session budget for the final stop reason. No arithmetic overflow. */
class CaptureBudget(val maxBytes:Long=20L*1024*1024,val endReserve:Long=8192) {
    init {require(maxBytes>0 && endReserve>=0 && endReserve<maxBytes)}
    fun allows(existing:Long,incoming:Long,ending:Boolean=false):Boolean {
        if(existing<0 || incoming<0) return false
        val limit=maxBytes-(if(ending) 0 else endReserve)
        return existing<=limit && incoming<=limit-existing
    }
}
