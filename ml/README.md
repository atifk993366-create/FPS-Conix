# ML pipeline (training workstation / cloud)
The Android app stores MP4 demonstrations and timestamped action CSV files in its app-specific demonstrations folder.
Copy these files to `ml/data/<profile>/`. The current app logs manual action labels and provides a gesture dispatch foundation; it does not yet collect every raw finger movement from arbitrary third-party apps. For supervised training, each frame must be paired with an action label recorded at the same time. Do not train from unlabelled video alone and assume it knows the touch controls.
