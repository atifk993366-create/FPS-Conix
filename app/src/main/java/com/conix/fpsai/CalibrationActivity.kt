package com.conix.fpsai

import android.os.Bundle
import android.widget.*
import androidx.appcompat.app.AppCompatActivity

class CalibrationActivity : android.app.Activity() {
    private val controls = listOf("MOVE_JOYSTICK", "FIRE", "SCOPE_ADS", "RELOAD", "JUMP", "CROUCH", "LEFT", "RIGHT", "WEAPON_SWITCH", "GRENADE")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20,24,20,20) }
        root.addView(TextView(this).apply { text = "Control calibration • ${ProfileStore.game(this@CalibrationActivity)}"; textSize = 20f })
        root.addView(TextView(this).apply { text = "Enter normalized screen positions (0.0–1.0). Example: X=0.85, Y=0.80 means near bottom-right."; textSize = 13f })
        controls.forEach { key ->
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            row.addView(TextView(this).apply { text = key; width = 155 })
            val x = EditText(this).apply { hint = "X"; setText(ProfileStore.control(this@CalibrationActivity,key)?.first?.toString() ?: "0.5"); inputType = 8194 }
            val y = EditText(this).apply { hint = "Y"; setText(ProfileStore.control(this@CalibrationActivity,key)?.second?.toString() ?: "0.5"); inputType = 8194 }
            val r = EditText(this).apply { hint = "Size"; setText(ProfileStore.control(this@CalibrationActivity,key)?.third?.toString() ?: "0.06"); inputType = 8194 }
            row.addView(x, LinearLayout.LayoutParams(0,-2,1f)); row.addView(y, LinearLayout.LayoutParams(0,-2,1f)); row.addView(r, LinearLayout.LayoutParams(0,-2,1f))
            root.addView(row)
            root.addView(Button(this).apply { text = "Save $key"; setOnClickListener {
                val xv=x.text.toString().toFloatOrNull(); val yv=y.text.toString().toFloatOrNull(); val rv=r.text.toString().toFloatOrNull()
                if (xv==null || yv==null || rv==null || xv !in 0f..1f || yv !in 0f..1f || rv !in .005f..0.5f) {
                    Toast.makeText(this@CalibrationActivity,"Use X/Y 0–1 and size 0.005–0.5",Toast.LENGTH_SHORT).show()
                } else { ProfileStore.saveControl(this@CalibrationActivity,key,xv,yv,rv); Toast.makeText(this@CalibrationActivity,"Saved $key",Toast.LENGTH_SHORT).show() }
            } })
        }
        root.addView(TextView(this).apply { text = "Calibration stores each game's button positions separately. Confirm positions visually in landscape mode before any automated actions."; textSize = 13f })
        setContentView(ScrollView(this).apply { addView(root) })
    }
}
