package org.smri.ridobserver.kmp

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import org.smri.ridobserver.core.SourceRule

/** Private operator configuration; no network sync or claims of authentication. */
class SourceRegistry(context:Context) {
    private val prefs=context.applicationContext.getSharedPreferences("source_labels",Context.MODE_PRIVATE)
    fun load():List<SourceRule> {
        val array=JSONArray(prefs.getString("rules","[]"))
        require(array.length()<=32)
        return (0 until array.length()).map {i ->val r=array.getJSONObject(i)
            SourceRule(r.getString("role"),r.getString("label"),
                r.optString("uas_id").takeIf {it.isNotEmpty()},r.optString("bssid").takeIf {it.isNotEmpty()})}
    }
    fun add(rule:SourceRule) {
        val old=load();require(old.size<32)
        require(rule !in old) {"already registered"}
        val array=JSONArray()
        for(r in old+rule) array.put(JSONObject().apply {
            put("role",r.role);put("label",r.label);r.uasId?.let {put("uas_id",it)};r.bssid?.let {put("bssid",it.lowercase())}
        })
        check(prefs.edit().putString("rules",array.toString()).commit()) {"source label save failed"}
    }
    fun remove(index:Int) {
        val old=load();require(index in old.indices)
        val array=JSONArray(prefs.getString("rules","[]"));array.remove(index)
        check(prefs.edit().putString("rules",array.toString()).commit())
    }
}
