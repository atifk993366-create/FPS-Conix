package com.conix.fpsai

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.*

class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var profileLabel: TextView
    private val REQ_CAPTURE = 1001
    private val REQ_NOTIF = 1002

    private fun refreshProfile() { profileLabel.text = "Active profile: ${ProfileStore.game(this)}" }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28, 32, 28, 28) }
        box.addView(TextView(this).apply { text = "CONIX FPS AI  -  Universal"; textSize = 24f })
        profileLabel = TextView(this).apply { textSize = 16f; setPadding(0, 12, 0, 0) }
        box.addView(profileLabel)
        status = TextView(this).apply { text = "Select a profile, calibrate controls, then record demonstrations."; textSize = 15f; setPadding(0, 16, 0, 16) }
        box.addView(status)

        box.addView(Button(this).apply { text = "Select FPS Strike Ops profile"; setOnClickListener {
            ProfileStore.setGame(this@MainActivity, "FPS Strike Ops"); refreshProfile(); status.text = "FPS Strike Ops profile selected." } })
        box.addView(Button(this).apply { text = "Select Cover Fire profile"; setOnClickListener {
            ProfileStore.setGame(this@MainActivity, "Cover Fire"); refreshProfile(); status.text = "Cover Fire profile selected." } })
        box.addView(Button(this).apply { text = "Open control calibration"; setOnClickListener {
            startActivity(Intent(this@MainActivity, CalibrationActivity::class.java)) } })
        box.addView(Button(this).apply { text = "Enable user-controlled gesture service"; setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            status.text = "Find Conix FPS AI and enable its accessibility service manually." } })
        box.addView(Button(this).apply { text = "Start screen recording"; setOnClickListener {
            if (ProfileStore.game(this@MainActivity) == "Unconfigured") {
                status.text = "Select a game profile first."
            } else {
                val mgr = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
                startActivityForResult(mgr.createScreenCaptureIntent(), REQ_CAPTURE)
            } } })
        box.addView(Button(this).apply { text = "STOP screen recording"; setOnClickListener {
            startService(Intent(this@MainActivity, ScreenCaptureService::class.java).setAction(ScreenCaptureService.STOP))
            status.text = "Capture stop requested." } })
        box.addView(Button(this).apply { text = "Where are my files?"; setOnClickListener {
            status.text = "Files: Android/data/com.conix.fpsai/files/demonstrations (videos .mp4 + actions.csv)" } })
        box.addView(TextView(this).apply {
            text = "Safety: use only in offline games where automation is permitted. Android requires explicit screen-capture approval and explicit Accessibility enablement. This app does not secretly observe or control other apps. A STOP button is also in the recording notification."
            textSize = 13f; setPadding(0, 18, 0, 0)
        })
        setContentView(ScrollView(this).apply { addView(box) })
        refreshProfile()

        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIF)
        }
    }

    override fun onResume() { super.onResume(); if (::profileLabel.isInitialized) refreshProfile() }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_CAPTURE) return
        if (resultCode == Activity.RESULT_OK && data != null) {
            startForegroundService(Intent(this, ScreenCaptureService::class.java).apply {
                action = ScreenCaptureService.START
                putExtra(ScreenCaptureService.CODE, resultCode)
                putExtra(ScreenCaptureService.DATA, data)
            })
            status.text = "Screen capture started. Start your offline game. Stop from the notification or this app."
        } else status.text = "Screen capture permission not granted."
    }
}
