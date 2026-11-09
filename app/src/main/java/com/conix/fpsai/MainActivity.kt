package com.conix.fpsai

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.*
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts

class MainActivity : ComponentActivity() {
    private lateinit var status: TextView
    private val captureLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        if (r.resultCode == Activity.RESULT_OK && r.data != null) {
            startForegroundService(Intent(this, ScreenCaptureService::class.java).apply {
                action = ScreenCaptureService.START
                putExtra(ScreenCaptureService.CODE, r.resultCode)
                putExtra(ScreenCaptureService.DATA, r.data)
            })
            status.text = "Screen capture started. Start your offline game."
        } else status.text = "Screen capture permission not granted."
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28,32,28,28) }
        box.addView(TextView(this).apply { text = "CONIX FPS AI  •  Universal"; textSize = 24f })
        status = TextView(this).apply { text = "Create a profile, calibrate controls, then record demonstrations."; textSize = 15f; setPadding(0,16,0,16) }
        box.addView(status)
        box.addView(Button(this).apply { text = "Create / select FPS Strike Ops profile"; setOnClickListener { ProfileStore.setGame(this@MainActivity, "FPS Strike Ops"); status.text = "FPS Strike Ops profile selected." } })
        box.addView(Button(this).apply { text = "Create / select Cover Fire profile"; setOnClickListener { ProfileStore.setGame(this@MainActivity, "Cover Fire"); status.text = "Cover Fire profile selected." } })
        box.addView(Button(this).apply { text = "Open control calibration"; setOnClickListener { startActivity(Intent(this@MainActivity, CalibrationActivity::class.java)) } })
        box.addView(Button(this).apply { text = "Enable user-controlled gesture service"; setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            status.text = "Find Conix FPS AI and enable its accessibility service manually."
        } })
        box.addView(Button(this).apply { text = "Start screen recording"; setOnClickListener {
            val mgr = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            captureLauncher.launch(mgr.createScreenCaptureIntent())
        } })
        box.addView(Button(this).apply { text = "Stop screen recording"; setOnClickListener {
            startService(Intent(this@MainActivity, ScreenCaptureService::class.java).setAction(ScreenCaptureService.STOP))
            status.text = "Capture stop requested."
        } })
        box.addView(Button(this).apply { text = "Open demonstrations folder"; setOnClickListener {
            status.text = "Files are in app-specific Android/data/com.conix.fpsai/files/demonstrations"
        } })
        box.addView(TextView(this).apply {
            text = "Safety: use only in offline games where automation is permitted. Android requires explicit screen-capture approval and explicit Accessibility enablement. This starter does not secretly observe or control other apps."
            textSize = 13f; setPadding(0,18,0,0)
        })
        setContentView(ScrollView(this).apply { addView(box) })
    }
}
