package org.smri.ridobserver.core

/** Operator annotations only. Neither claimed IDs nor BSSIDs authenticate hardware. */
data class SourceAnnotation(val role:String="unknown",val label:String="未登録",val basis:String="none") {
    fun fields():Map<String,Any?> = mapOf("role" to role,"label" to label,"basis" to basis,"identity_verified" to false)
}
data class SourceRule(val role:String,val label:String,val uasId:String?=null,val bssid:String?=null) {
    init {
        require(role in listOf("drone","onboard_pi","unknown"))
        require(label.length in 1..40 && label.none {it.code<32})
        require(!uasId.isNullOrBlank() || !bssid.isNullOrBlank())
        require(uasId==null || (uasId.length in 1..20 && uasId.all {it.code in 32..126}))
        require(bssid==null || Regex("(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}").matches(bssid))
    }
}
fun classifySource(sourceKey:String,ids:List<String>,rules:List<SourceRule> = emptyList()):SourceAnnotation {
    require(rules.size<=32)
    val matched=rules.filter {(it.bssid==null || it.bssid.equals(sourceKey,true)) && (it.uasId==null || it.uasId in ids)}
    if(matched.isNotEmpty()) {
        fun score(r:SourceRule)=(if(r.uasId!=null) 1 else 0)+(if(r.bssid!=null) 1 else 0)
        val best=matched.filter {score(it)==matched.maxOf {r ->score(r)}}
        if(best.map {it.role to it.label}.distinct().size>1) return SourceAnnotation(label="登録競合",basis="conflicting_local_rules")
        val r=best.first()
        return SourceAnnotation(r.role,r.label,if(r.uasId!=null && r.bssid!=null) "configured_id_and_bssid" else
            if(r.uasId!=null) "configured_claimed_id" else "configured_bssid")
    }
    return if(ids.any {it.startsWith("PI-RID-")}) SourceAnnotation("onboard_pi","Piマーカー（申告）","unverified_test_marker") else SourceAnnotation()
}
fun Observation.withSourceRules(rules:List<SourceRule>):Observation = copy(
    annotation=classifySource(sourceKey,decoded?.messages?.mapNotNull {it.uasId} ?: emptyList(),rules))
