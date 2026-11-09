package com.conix.fpsai

import android.content.Context
import android.os.SystemClock
import java.io.File

object EventLogger {
    fun log(c: Context, event: String, x: Float? = null, y: Float? = null) {
        val dir = File(c.getExternalFilesDir(null), "demonstrations").apply { mkdirs() }
        val file = File(dir, "actions.csv")
        if (!file.exists()) file.writeText("elapsed_ns,game,event,x_norm,y_norm\n")
        file.appendText("${SystemClock.elapsedRealtimeNanos()},${ProfileStore.game(c)},$event,${x ?: ""},${y ?: ""}\n")
    }
}
