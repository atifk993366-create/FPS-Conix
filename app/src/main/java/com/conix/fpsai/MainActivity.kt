package com.conix.fpsai

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.*

class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var profileLabel: TextView
    private lateinit var spinner: Spinner
    private var spinnerReady = false
    private val REQ_CAPTURE = 1001
    private val REQ_NOTIF = 1002

    private fun refreshProfile() { profileLabel.text = "Active game profile: ${ProfileStore.game(this)}" }

    private fun refreshGames() {
        val list = ProfileStore.games(this)
        spinnerReady = false
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, list)
        val idx = list.indexOf(ProfileStore.game(this))
        if (idx >= 0) {
            spinner.setSelection(idx)
        } else if (list.isNotEmpty()) {
            ProfileStore.setGame(this, list[0])
            spinner.setSelection(0)
        }
        spinnerReady = true
        refreshProfile()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28, 32, 28, 28) }
        box.addView(TextView(this).apply { text = "CONIX FPS AI  -  Universal"; textSize = 24f })
        profileLabel = TextView(this).apply { textSize = 16f; setPadding(0, 12, 0, 0) }
        box.addView(profileLabel)
        status = TextView(this).apply { text = "1) Pick or add a game  2) Calibrate  3) Record."; textSize = 15f; setPadding(0, 16, 0, 16) }
        box.addView(status)

        box.addView(TextView(this).apply { text = "Game profile:"; textSize = 14f })
        spinner = Spinner(this)
        box.addView(spinner)
        spinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (!spinnerReady) return
                val name = parent?.getItemAtPosition(position) as? String ?: return
                ProfileStore.setGame(this@MainActivity, name)
                refreshProfile()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        val newGame = EditText(this).apply { hint = "New game name (any offline FPS)" }
        box.addView(newGame)
        box.addView(Button(this).apply { text = "Add game profile"; setOnClickListener {
            val n = ProfileStore.addGame(this@MainActivity, newGame.text.toString())
            if (n == null) {
                status.text = "Type a game name first (letters and numbers)."
            } else {
                ProfileStore.setGame(this@MainActivity, n)
                newGame.setText("")
                refreshGames()
                status.text = "Profile '$n' added and selected. Now open calibration."
            }
        } })
        box.addView(Button(this).apply { text = "Delete selected game profile"; setOnClickListener {
            val g = ProfileStore.game(this@MainActivity)
            AlertDialog.Builder(this@MainActivity)
                .setTitle("Delete '$g'?")
                .setMessage("Its calibration is removed. Recorded files are kept.")
                .setPositiveButton("Delete") { _, _ ->
                    ProfileStore.deleteGame(this@MainActivity, g)
                    refreshGames()
                    status.text = "Deleted '$g'."
                }
                .setNegativeButton("Cancel", null)
                .show()
        } })

        box.addView(Button(this).apply { text = "Open control calibration"; setOnClickListener {
            startActivity(Intent(this@MainActivity, CalibrationActivity::class.java)) } })
        box.addView(Button(this).apply { text = "Enable user-controlled gesture service"; setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            status.text = "Find Conix FPS AI and enable its accessibility service manually." } })
        box.addView(Button(this).apply { text = "Open Developer options (turn ON Show taps)"; setOnClickListener {
            try {
                startActivity(Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS))
                status.text = "Turn ON 'Show taps' (Input section). Taps then appear in the recording and become training labels."
            } catch (e: Exception) {
                startActivity(Intent(Settings.ACTION_DEVICE_INFO_SETTINGS))
                status.text = "Tap 'Build number' 7 times to unlock Developer options, then come back."
            }
        } })
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
            status.text = "Android/data/com.conix.fpsai/files/demonstrations: for each recording you get Game_session.mp4 + Game_session.profile.json (copy BOTH to Google Drive for training) and actions.csv." } })
        box.addView(TextView(this).apply {
            text = "Safety: use only in offline games where automation is permitted. Android requires explicit screen-capture approval and explicit Accessibility enablement. This app does not secretly observe or control other apps. A STOP button is also in the recording notification."
            textSize = 13f; setPadding(0, 18, 0, 0)
        })
        setContentView(ScrollView(this).apply { addView(box) })
        refreshGames()

        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIF)
        }
    }

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
            status.text = "Recording started. Open your offline game now. Stop from the notification or this app."
        } else status.text = "Screen capture permission not granted."
    }
}
