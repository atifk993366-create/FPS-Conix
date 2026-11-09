package com.conix.fpsai

import android.content.Context

object ProfileStore {
    fun prefs(c: Context) = c.getSharedPreferences("conix_profiles", Context.MODE_PRIVATE)
    fun setGame(c: Context, name: String) { prefs(c).edit().putString("active_game", name).apply() }
    fun game(c: Context) = prefs(c).getString("active_game", "Unconfigured") ?: "Unconfigured"
    fun saveControl(c: Context, key: String, x: Float, y: Float, radius: Float) {
        prefs(c).edit().putFloat("${game(c)}_${key}_x", x).putFloat("${game(c)}_${key}_y", y)
            .putFloat("${game(c)}_${key}_r", radius).apply()
    }
    fun control(c: Context, key: String): Triple<Float,Float,Float>? {
        val p = prefs(c); val prefix = "${game(c)}_${key}_"
        if (!p.contains(prefix + "x")) return null
        return Triple(p.getFloat(prefix+"x", .5f), p.getFloat(prefix+"y", .5f), p.getFloat(prefix+"r", .06f))
    }
}
