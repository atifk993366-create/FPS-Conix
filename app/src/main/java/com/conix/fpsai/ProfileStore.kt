package com.conix.fpsai

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Stores any number of user-created game profiles, each with its own list of controls. */
object ProfileStore {
    val DEFAULT_CONTROLS = listOf("MOVE_JOYSTICK", "FIRE", "SCOPE_ADS", "RELOAD", "JUMP", "CROUCH", "LEFT", "RIGHT", "WEAPON_SWITCH", "GRENADE")
    private val DEFAULT_GAMES = listOf("FPS Strike Ops", "Cover Fire")

    fun prefs(c: Context) = c.getSharedPreferences("conix_profiles", Context.MODE_PRIVATE)

    fun cleanGame(raw: String): String = raw.replace(Regex("[^A-Za-z0-9 _-]"), "").trim().take(30)
    fun cleanControl(raw: String): String =
        raw.trim().replace(" ", "_").replace(Regex("[^A-Za-z0-9_]"), "").uppercase().take(24)
    fun safe(name: String): String = name.replace(" ", "_")

    // ---- games ----
    fun games(c: Context): List<String> {
        val s = prefs(c).getString("games", null) ?: return DEFAULT_GAMES
        return s.split("\n").filter { it.isNotBlank() }
    }

    private fun saveGames(c: Context, list: List<String>) {
        prefs(c).edit().putString("games", list.joinToString("\n")).apply()
    }

    /** Returns the stored name of the game, or null if the name is empty after cleaning. */
    fun addGame(c: Context, raw: String): String? {
        val n = cleanGame(raw)
        if (n.isEmpty()) return null
        val list = games(c)
        val existing = list.firstOrNull { it.equals(n, ignoreCase = true) }
        if (existing != null) return existing
        saveGames(c, list + n)
        return n
    }

    fun deleteGame(c: Context, name: String) {
        val ed = prefs(c).edit()
        for (k in controlNames(c, name)) {
            ed.remove("${name}_${k}_x").remove("${name}_${k}_y").remove("${name}_${k}_r")
        }
        ed.remove("ctl_names_$name")
        ed.putString("games", games(c).filter { it != name }.joinToString("\n"))
        if (game(c) == name) ed.putString("active_game", games(c).firstOrNull { it != name } ?: "Unconfigured")
        ed.apply()
    }

    fun setGame(c: Context, name: String) { prefs(c).edit().putString("active_game", name).apply() }
    fun game(c: Context): String = prefs(c).getString("active_game", "Unconfigured") ?: "Unconfigured"

    // ---- controls (per game, editable) ----
    fun controlNames(c: Context, game: String = game(c)): List<String> {
        val s = prefs(c).getString("ctl_names_$game", null) ?: return DEFAULT_CONTROLS
        return s.split("\n").filter { it.isNotBlank() }
    }

    private fun saveControlNames(c: Context, game: String, list: List<String>) {
        prefs(c).edit().putString("ctl_names_$game", list.joinToString("\n")).apply()
    }

    fun addControl(c: Context, raw: String): String? {
        val n = cleanControl(raw)
        if (n.isEmpty()) return null
        val g = game(c)
        val list = controlNames(c, g)
        if (list.contains(n)) return n
        saveControlNames(c, g, list + n)
        return n
    }

    fun removeControl(c: Context, key: String) {
        val g = game(c)
        saveControlNames(c, g, controlNames(c, g).filter { it != key })
        prefs(c).edit().remove("${g}_${key}_x").remove("${g}_${key}_y").remove("${g}_${key}_r").apply()
        exportProfile(c)
    }

    fun saveControl(c: Context, key: String, x: Float, y: Float, radius: Float) {
        val g = game(c)
        prefs(c).edit().putFloat("${g}_${key}_x", x).putFloat("${g}_${key}_y", y)
            .putFloat("${g}_${key}_r", radius).apply()
        exportProfile(c)
    }

    fun control(c: Context, key: String): Triple<Float, Float, Float>? {
        val p = prefs(c)
        val prefix = "${game(c)}_${key}_"
        if (!p.contains(prefix + "x")) return null
        return Triple(p.getFloat(prefix + "x", .5f), p.getFloat(prefix + "y", .5f), p.getFloat(prefix + "r", .06f))
    }

    /**
     * Writes the active game's calibrated controls to a JSON file in the demonstrations folder.
     * sessionId == null -> profile_<Game>.json (latest); otherwise <Game>_<session>.profile.json
     * (saved next to the video so the ML pipeline can pair them).
     * "r" is the control radius as a fraction of the frame WIDTH. x,y are fractions of width/height.
     */
    fun exportProfile(c: Context, sessionId: String? = null, w: Int = 0, h: Int = 0): File {
        val g = game(c)
        val arr = JSONArray()
        for (k in controlNames(c, g)) {
            val v = control(c, k) ?: continue
            arr.put(JSONObject().put("name", k).put("x", v.first.toDouble()).put("y", v.second.toDouble()).put("r", v.third.toDouble()))
        }
        val root = JSONObject()
            .put("game", g)
            .put("session_id", sessionId ?: "")
            .put("profile_version", EventLogger.PROFILE_VERSION)
            .put("screen_width", w)
            .put("screen_height", h)
            .put("controls", arr)
        val dir = File(c.getExternalFilesDir(null), "demonstrations").apply { mkdirs() }
        val name = if (sessionId == null) "profile_${safe(g)}.json" else "${safe(g)}_$sessionId.profile.json"
        val f = File(dir, name)
        f.writeText(root.toString(2))
        return f
    }
}
