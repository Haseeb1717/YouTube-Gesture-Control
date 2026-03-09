Active the virtual environment
.\gesture_env\Scripts\Activate

import cv2
# some installations of opencv-python don't expose __version__, which pyscreeze
# (used by pyautogui) expects when comparing versions.  Provide a fallback so
# importing pyautogui doesn't crash.
if not hasattr(cv2, "__version__"):
    cv2.__version__ = "4.0.0"

import mediapipe as mp
import pyautogui as pag
import time
from collections import deque

# MediaPipe configuration
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

# choose color for landmarks/connections (BGR format): navy would be (128,0,0),
# maroon is (0,0,128).  using maroon per user request.
landmark_color = (0, 0, 128)
connection_color = (0, 0, 128)

# allow two hands so keyboard can be used with either
hands = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7,
)

# indices for fingertips
finger_tips = [4, 8, 12, 16, 20]

# gesture variables
cooldown = 1
last_action_time = 0
x_history = deque(maxlen=6)
prev_index_y = None
prev_finger_sum = None

# virtual keyboard toggle button (not used any more)
# kept coordinates in case we want a status indicator later
button_x, button_y = 50, 400
button_w, button_h = 200, 60
keyboard_cooldown = 1
last_keyboard = 0

# keyboard state
keyboard_visible = False    # become true when two hands appear
input_text = ""
hovered_key = None
hover_start = 0
key_cooldown = 0.8  # seconds of hover to trigger key
last_cursor_toggle = 0
show_cursor = True

# colors for keyboard theme
key_bg = (30, 30, 30)         # dark grey
key_bg_alt = (50, 50, 50)     # slightly lighter for hovered
key_outline = (200, 200, 200) # light grey for border and labels
text_color = (235, 235, 235)  # off-white for key text
input_bg = (20, 20, 20)       # near-black for input display

# map for icon text on special keys
key_icons = {"BACK": "⌫", "SPACE": "␣", "ENT": "↵"}

# layout parameters (will be reused each frame)
rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
extra_row = ["SPACE", "BACK", "ENT"]

# helper routines for drawing

def draw_rounded_rect(frame, x, y, w, h, color, thickness=0, r=10):
    # draw rectangle with rounded corners by overlaying circles at the corners
    # thickness=0 means filled
    if thickness == 0:
        cv2.rectangle(frame, (x+r, y), (x+w-r, y+h), color, -1)
        cv2.rectangle(frame, (x, y+r), (x+w, y+h-r), color, -1)
        cv2.circle(frame, (x+r, y+r), r, color, -1)
        cv2.circle(frame, (x+w-r, y+r), r, color, -1)
        cv2.circle(frame, (x+r, y+h-r), r, color, -1)
        cv2.circle(frame, (x+w-r, y+h-r), r, color, -1)
    else:
        # draw outer shape then inner cutout for thickness effect
        cv2.rectangle(frame, (x+r, y), (x+w-r, y+h), color, thickness)
        cv2.rectangle(frame, (x, y+r), (x+w, y+h-r), color, thickness)
        cv2.circle(frame, (x+r, y+r), r, color, thickness)
        cv2.circle(frame, (x+w-r, y+r), r, color, thickness)
        cv2.circle(frame, (x+r, y+h-r), r, color, thickness)
        cv2.circle(frame, (x+w-r, y+h-r), r, color, thickness)


def draw_keyboard(frame, highlight=None):
    h, w, _ = frame.shape
    origin_x = 50
    origin_y = 300
    key_w = 60
    key_h = 60
    margin = 5
    key_rects = []  # list of (label, (x,y,w,h))

    y = origin_y
    for row in rows:
        x = origin_x
        for ch in row:
            bg = key_bg_alt if highlight == ch else key_bg
            draw_rounded_rect(frame, x, y, key_w, key_h, bg, thickness=0, r=10)
            draw_rounded_rect(frame, x, y, key_w, key_h, key_outline, thickness=1, r=10)
            cv2.putText(frame, ch, (x + 15, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 1,
                        text_color, 2)
            key_rects.append((ch, (x, y, key_w, key_h)))
            x += key_w + margin
        y += key_h + margin

    # extras row
    x = origin_x
    for ch in extra_row:
        w2 = key_w * 2
        bg = key_bg_alt if highlight == ch else key_bg
        draw_rounded_rect(frame, x, y, w2, key_h, bg, thickness=0, r=10)
        draw_rounded_rect(frame, x, y, w2, key_h, key_outline, thickness=1, r=10)
        label = key_icons.get(ch, ch)  # ensure label is drawable; unicode may not render
        if ch == "BACK":
            label = "<-" if len(label) > 1 else label
        elif ch == "SPACE":
            label = "SP"
        elif ch == "ENT":
            label = "EN"
        cv2.putText(frame, label, (x + 20, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    text_color, 2)
        key_rects.append((ch, (x, y, w2, key_h)))
        x += w2 + margin

    return key_rects


# open camera
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: cannot open camera")
    exit(1)

# main processing loop
while True:
    try:
        ret, frame = cap.read()
        if not ret:
            # transient read failure – log and try again rather than exiting
            print("Warning: failed to grab frame, retrying...")
            time.sleep(0.1)
            continue

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(frame_rgb)

        gesture_name = ""
        fingers = []
        now = time.time()

        if results.multi_hand_landmarks:
            # store all index finger positions for keyboard interaction
            index_positions = []  # list of (x_px, y_px)

            # process each detected hand
            for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                # draw with customized colors
                mp_draw.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_draw.DrawingSpec(color=landmark_color, thickness=5, circle_radius=2),
                    mp_draw.DrawingSpec(color=connection_color, thickness=2),
                )
                lm = hand_landmarks.landmark

                # record index tip position in pixels
                ix = int(lm[8].x * frame.shape[1])
                iy = int(lm[8].y * frame.shape[0])
                index_positions.append((ix, iy))
                cv2.circle(frame, (ix, iy), 8, (0, 255, 0), -1)

                # only use first hand for video control gestures
                if hand_idx == 0:
                    # finger status
                    for i in range(5):
                        tip = lm[finger_tips[i]].y
                        pip = lm[finger_tips[i] - 2].y
                        fingers.append(1 if tip < pip else 0)

                    # swipe detection
                    palm_x = lm[9].x
                    x_history.append(palm_x)
                    if len(x_history) == 6 and now - last_action_time > cooldown:
                        movement = x_history[-1] - x_history[0]
                        if movement > 0.25:
                            pag.hotkey("shift", "n")
                            gesture_name = "Next Video"
                            last_action_time = now
                            x_history.clear()
                        elif movement < -0.25:
                            pag.hotkey("shift", "p")
                            gesture_name = "Previous Video"
                            last_action_time = now
                            x_history.clear()

                    # volume control via index finger
                    index_y = lm[8].y
                    if prev_index_y is not None and now - last_action_time > cooldown:
                        diff = prev_index_y - index_y
                        if diff > 0.05:
                            pag.press("volumeup")
                            gesture_name = "Volume Up"
                            last_action_time = now
                        elif diff < -0.05:
                            pag.press("volumedown")
                            gesture_name = "Volume Down"
                            last_action_time = now
                    prev_index_y = index_y

                    # play/pause tap
                    index_tip = lm[8].y
                    index_pip = lm[6].y
                    if index_tip > index_pip + 0.05 and now - last_action_time > cooldown:
                        pag.press("space")
                        gesture_name = "Play / Pause"
                        last_action_time = now

                    # thumbs up like
                    if fingers == [1, 0, 0, 0, 0] and now - last_action_time > cooldown:
                        pag.press("l")
                        gesture_name = "Like Video"
                        last_action_time = now

                    # fist gesture (skip ad/fullscreen)
                    if fingers == [0, 0, 0, 0, 0] and now - last_action_time > cooldown:
                        if prev_finger_sum is not None and now - last_action_time > cooldown and prev_finger_sum - sum(fingers) >= 4:
                            pag.press("f")
                            gesture_name = "Fullscreen"
                            last_action_time = now
                        else:
                            pag.press("l")
                            gesture_name = "Skip Ad"
                            last_action_time = now
                        prev_finger_sum = sum(fingers)

            # keyboard should be visible only while two hands are detected
            keyboard_visible = len(index_positions) >= 2
            # if keyboard disappears, clear its state so typing doesn't linger
            if not keyboard_visible:
                input_text = ""
                hovered_key = None
                hover_start = 0

            if keyboard_visible:
                key_rects = draw_keyboard(frame, highlight=hovered_key)
                hit_key = None
                # check each finger position
                for ix, iy in index_positions:
                    for lbl, (kx, ky, kw, kh) in key_rects:
                        if kx < ix < kx + kw and ky < iy < ky + kh:
                            hit_key = lbl
                            break
                    if hit_key:
                        break
                if hit_key is not None:
                    if hovered_key != hit_key:
                        hovered_key = hit_key
                        hover_start = now
                    elif now - hover_start > key_cooldown:
                        # trigger key action
                        if hit_key == "BACK":
                            pag.press("backspace")
                            input_text = input_text[:-1]
                        elif hit_key == "SPACE":
                            pag.typewrite(" ")
                            input_text += " "
                        elif hit_key == "ENT":
                            pag.press("enter")
                            input_text = ""
                        else:
                            pag.typewrite(hit_key.lower())
                            input_text += hit_key
                        hover_start = now
                else:
                    hovered_key = None
                    hover_start = now

                # draw input bar with blinking cursor
                cv2.rectangle(frame, (40, 30), (frame.shape[1]-40, 70), input_bg, -1)
                cursor = "|" if int(now*2) % 2 == 0 else ""
                cv2.putText(frame, f"Input: {input_text}{cursor}", (50, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, text_color, 2)

        # display info
        cv2.putText(frame, f"Fingers: {fingers}", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        if gesture_name:
            cv2.putText(frame, f"Gesture: {gesture_name}", (10, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # overlay a static list of supported gestures
        info_lines = [
            "Supported Gestures:",
            "Swipe right/left – Next/Prev video",
            "Swipe up/down – Fullscreen toggle",
            "Victory sign (2 fingers) – Volume up",
            "Three fingers – Volume down",
            "Index tap – Play/Pause",
            "Thumbs up – Like video",
            "Fist – Skip ad",
            "Two hands – Show virtual keyboard (use CAP/CLOSE)"
        ]
        y0 = 110
        for line in info_lines:
            cv2.putText(frame, line, (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (200, 200, 200), 1)
            y0 += 25
        cv2.imshow("YouTube Gesture Controller", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    except Exception as e:
        print("Error in main loop:", e)
        import traceback; traceback.print_exc()
        continue

# clean up
cap.release()
cv2.destroyAllWindows()