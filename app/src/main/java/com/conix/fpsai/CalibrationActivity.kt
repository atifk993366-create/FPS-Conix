package com.conix.fpsai

import android.app.Activity
import android.os.Bundle
import android.widget.*

class CalibrationActivity : Activity() {
    private val controls = listOf("MOVE_JOYSTICK", "FIRE", "SCOPE_ADS", "RELOAD", "JUMP", "CROUCH", "LEFT", "RIGHT", "WEAPON_SWITCH", "GRENADE")

    private fun field(hint: String, value: String) = EditText(this).apply {
        this.hint = hint
        setText(value)
        inputType = 8194 // number | decimal
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 24, 20, 20) }
        root.addView(TextView(this).apply { text = "Control calibration - ${ProfileStore.game(this@CalibrationActivity)}"; textSize = 20f })
        root.addView(TextView(this).apply {
            text = "Enter normalized screen positions (0.0 to 1.0). Example: X=0.85, Y=0.80 means near bottom-right. Size = button radius (0.005 to 0.5). Test tap needs the accessibility service enabled."
            textSize = 13f
        })
        controls.forEach { key ->
            val saved = ProfileStore.control(this, key)
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            row.addView(TextView(this).apply { text = key }, LinearLayout.LayoutParams(0, -2, 1.4f))
            val x = field("X", (saved?.first ?: 0.5f).toString())
            val y = field("Y", (saved?.second ?: 0.5f).toString())
            val r = field("Size", (saved?.third ?: 0.06f).toString())
            row.addView(x, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(y, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(r, LinearLayout.LayoutParams(0, -2, 1f))
            root.addView(row)

            fun parse(): Triple<Float, Float, Float>? {
                val xv = x.text.toString().toFloatOrNull()
                val yv = y.text.toString().toFloatOrNull()
                val rv = r.text.toString().toFloatOrNull()
                if (xv == null || yv == null || rv == null || xv !in 0f..1f || yv !in 0f..1f || rv !in 0.005f..0.5f) {
                    Toast.makeText(this, "Use X/Y 0-1 and size 0.005-0.5", Toast.LENGTH_SHORT).show()
                    return null
                }
                return Triple(xv, yv, rv)
            }

            val btns = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            btns.addView(Button(this).apply { text = "Save"; setOnClickListener {
                parse()?.let { ProfileStore.saveControl(this@CalibrationActivity, key, it.first, it.second, it.third)
                    Toast.makeText(this@CalibrationActivity, "Saved $key", Toast.LENGTH_SHORT).show() }
            } }, LinearLayout.LayoutParams(0, -2, 1f))
            btns.addView(Button(this).apply { text = "Test tap"; setOnClickListener {
                val p = parse() ?: return@setOnClickListener
                val svc = GameAccessibilityService.instance
                if (svc == null) {
                    Toast.makeText(this@CalibrationActivity, "Enable Conix in Accessibility settings first", Toast.LENGTH_LONG).show()
                } else {
                    svc.tapNormalized(p.first, p.second)
                    EventLogger.log(this@CalibrationActivity, "CALIBRATION_TEST_$key", p.first, p.second, "calibration")
                }
            } }, LinearLayout.LayoutParams(0, -2, 1f))
            root.addView(btns)
        }
        root.addView(TextView(this).apply {
            text = "Each game's button positions are stored separately. Select the game profile on the home screen first, then confirm positions in landscape before any automated action."
            textSize = 13f
        })
        setContentView(ScrollView(this).apply { addView(root) })
    }
}
