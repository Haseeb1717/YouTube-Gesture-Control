# YouTube Gesture Controller

**YouTube Gesture Controller** is a lightweight Python tool that leverages
**MediaPipe**’s hand‑tracking model and OpenCV to control YouTube in a browser
using simple hand gestures.  It is intended primarily for Windows machines
with a standard webcam.  Gestures such as swipes, taps and poses are mapped to
corresponding YouTube keyboard shortcuts via `pyautogui`, enabling hands‑free
playback and navigation.

---

## 🧰 Requirements

- **Python 3.9** (the code has been tested on 3.9.x; other 3.x versions may work
  but are not guaranteed).  A `venv` is included in the repo for convenient
  isolation.
- **MediaPipe 0.10.14** (the version currently installed in `gesture_env`).
- A webcam accessible by OpenCV.
- Windows 10/11 – the script sends native Win32 key events and relies on the
  standard virtual‑key codes; behaviour on other platforms is untested.

### Python packages
Create and activate the provided virtual environment, then install the
dependencies:

```text
opencv-python>=4.7
mediapipe==0.10.14
pyautogui>=0.9
numpy
```

> 💡 On some systems, `pyautogui` may trigger a security prompt when sending
> keystrokes; ensure the script is allowed to control the desktop.

---
> script has permission to control the system (some antivirus or privacy
> settings may block it).

---

## 🚀 Running the Application

Once dependencies are installed, run:

```powershell
python main.py
```

A window titled **"YouTube Gesture Controller"** will appear showing the camera
feed with landmarks drawn on detected hands.  Keep a YouTube video open and
make gestures in front of the camera; corresponding keyboard shortcuts will be
sent to the active window.

Press `q` in the camera window to quit at any time.

---

## 🎯 Supported Gestures

| Gesture                      | Description                           | YouTube Action        |
|-----------------------------|---------------------------------------|-----------------------|
| Open-hand swipe right/left  | Whole-hand horizontal movement        | Next / Previous video |
| Open-hand swipe up/down     | Whole-hand vertical movement          | Fullscreen / Exit     |
| Single-index finger raised  | Toggle play / pause                   | Spacebar              |
| Tap (index finger drop)     | Quick poke below pip then lift        | Spacebar (fallback)   |
| Two fingers (index+middle)  | Hold to raise volume                  | Volume Up (hold)      |
| Three fingers (index+middle+ring) | Hold to lower volume         | Volume Down (hold)    |
| Thumbs-up                   | Static thumbs-up pose                 | Like video (`l`)      |
| Fist                        | Skip ad (first time) / fullscreen     | `l` / `f`             |

> ✨ The library distinguishes between **whole-hand** and **finger-based**
> gestures so that an open-hand swipe doesn’t accidentally trigger a volume
> change or play/pause command.

Additional feature: a virtual keyboard pixel-perfectly tracks two index
fingers when two hands are present.  Hover over a key for ~0.8 s to type it.

---

## 🛠 Implementation Notes

- Uses MediaPipe's `Hands` solution with `max_num_hands=2` and moderate
  confidence thresholds.
- Gesture logic is stateful: motion histories ensure swipes are **monotonic**
  and exceed a normalized threshold before activating, reducing false
  positives.
- Cool-down timers prevent repeated triggers from jitter.
- Play/pause is recognized as either a finger-only configuration or a tap
  motion, whichever is detected first.

The primary source file is `main.py`; feel free to modify the thresholds or add
new gestures.

---

## ✅ Tips for Best Results

1. Ensure your hand is completely within the camera frame and fairly well-lit.
2. Avoid rapid camera movement or background clutter that could confuse
   landmark detection.
3. Keep a little distance (30‑50 cm) between your hand and the webcam.
4. If swipes are unreliable, adjust `swipe_threshold` or history length near
   the top of `main.py`.

---

## 📄 License

This project is provided **as-is** for personal and educational use.  No
licenses are asserted for third-party packages; please review those projects
for their terms.

---

## 🎬 Acknowledgments

- [MediaPipe](https://developers.google.com/mediapipe) for high-quality hand
  landmark detection.
- `pyautogui` for convenient cross-platform keyboard control.

Enjoy controlling YouTube with just your hands! 👋

---


