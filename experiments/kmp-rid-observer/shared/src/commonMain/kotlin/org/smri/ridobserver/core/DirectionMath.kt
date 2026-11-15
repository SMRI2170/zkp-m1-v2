package org.smri.ridobserver.core

import kotlin.math.*

/** RSSI maximum PHONE orientation. Never a measured transmitter bearing or AoA. */
object DirectionMath {
    data class Heading(val us:Long,val degrees:Double,val tiltDeg:Double,val accuracy:Int)
    data class Sample(val us:Long,val headingDeg:Double,val rssiDbm:Double)
    fun wrap(deg:Double)=((deg%360)+360)%360
    fun nearest(history:List<Heading>,stamp:Long?):Heading? {
        if(stamp==null || stamp<=0) return null
        return history.minByOrNull {abs(it.us-stamp)}?.takeIf {
            abs(it.us-stamp)<=250_000 && it.accuracy>=2 && it.tiltDeg<=25 &&
                it.degrees.isFinite() && it.tiltDeg.isFinite()
        }
    }
    private fun solve(matrix:Array<DoubleArray>,rhs:DoubleArray):DoubleArray? {
        val n=rhs.size
        val a=Array(n) {i -> DoubleArray(n+1) {j -> if(j==n) rhs[i] else matrix[i][j]}}
        for(col in 0 until n) {
            val p=(col until n).maxBy {abs(a[it][col])}
            if(abs(a[p][col])<1e-8) return null
            val tmp=a[col];a[col]=a[p];a[p]=tmp
            val divisor=a[col][col];for(j in col..n) a[col][j]/=divisor
            for(i in 0 until n) if(i!=col) {val f=a[i][col];for(j in col..n) a[i][j]-=f*a[col][j]}
        }
        return DoubleArray(n) {a[it][n]}
    }
    fun fit(samples:List<Sample>):Map<String,Any?> {
        val s=samples.filter {it.us>0 && it.headingDeg.isFinite() && it.rssiDbm.isFinite()}
        val bins=IntArray(8);s.forEach {bins[(wrap(it.headingDeg)/45).toInt()]++}
        val angles=s.map {wrap(it.headingDeg)}.sorted()
        val gap=if(angles.size<2) 360.0 else maxOf(angles.first()+360-angles.last(),angles.zipWithNext {a,b->b-a}.maxOrNull() ?: 0.0)
        val base=mapOf<String,Any?>("method" to "experimental_rssi_phone_rotation_v1","samples" to s.size,
            "occupied_bins" to bins.count {it>0},"coverage_deg" to 360-gap,
            "transmitter_bearing_deg" to null,"aoa_measured" to false,"accuracy_validated" to false)
        if(s.size<24 || bins.count {it>0}<6 || gap>90) return base+mapOf("status" to "INSUFFICIENT_ROTATION")
        val t0=s.first().us;val mean=s.map {(it.us-t0)/60_000_000.0}.average()
        fun x(p:Sample):DoubleArray {val theta=wrap(p.headingDeg)*PI/180;return doubleArrayOf(1.0,cos(theta),sin(theta),(p.us-t0)/60_000_000.0-mean)}
        fun regression(dim:Int):DoubleArray? {
            val a=Array(dim) {DoubleArray(dim)};val b=DoubleArray(dim)
            for(p in s) {val full=x(p);val v=if(dim==2) doubleArrayOf(1.0,full[3]) else full
                val w=1.0/bins[(wrap(p.headingDeg)/45).toInt()]
                for(i in 0 until dim) {b[i]+=w*v[i]*p.rssiDbm;for(j in 0 until dim) a[i][j]+=w*v[i]*v[j]}}
            return solve(a,b)
        }
        val beta=regression(4) ?: return base+mapOf("status" to "DEGENERATE_FIT")
        val nullBeta=regression(2) ?: return base+mapOf("status" to "DEGENERATE_FIT")
        var sse=0.0;var sse0=0.0
        for(p in s) {val v=x(p);val w=1.0/bins[(wrap(p.headingDeg)/45).toInt()]
            sse+=w*(p.rssiDbm-v.indices.sumOf {v[it]*beta[it]}).pow(2)
            sse0+=w*(p.rssiDbm-nullBeta[0]-nullBeta[1]*v[3]).pow(2)}
        val amplitude=hypot(beta[1],beta[2]);val r2=if(sse0>1e-8) 1-sse/sse0 else 0.0
        val usable=amplitude>=2 && r2>=0.35
        return base+mapOf("status" to if(usable) "EXPERIMENTAL_PHONE_PEAK" else "WEAK_DIRECTIONAL_SIGNAL",
            "peak_phone_heading_deg" to if(usable) wrap(atan2(beta[2],beta[1])*180/PI) else null,
            "amplitude_db" to amplitude,"directional_r2" to r2)
    }
}
