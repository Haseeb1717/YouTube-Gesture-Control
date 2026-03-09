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

# MediaPipe cofiguration
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

# choose color for landmarks/connections (BGR format)
landmark_color = (0, 0, 128)   # maroon
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
x_history = deque(maxlen=8)
y_history = deque(maxlen=8)
# track whether each stored y-value came from a valid swipe candidate
y_candidate_history = deque(maxlen=8)
# track whether each stored x-value came from a valid swipe candidate
x_candidate_history = deque(maxlen=8)
prev_finger_sum = None
prev_fingers = None        # remember last finger configuration
volume_hold = None        # "up" or "down" when two/three-finger gesture held
prev_tip_y = None         # for tap detection
# state for play/pause tap: track when index tip has gone below the pip
tap_down = False
# tap timing parameters
tap_start = None
TAP_TIMEOUT = 0.5        # seconds allowed between down and up
TAP_DOWN_THRESH = 0.03   # how far below pip the tip must drop
TAP_UP_THRESH = 0.005    # how far above pip it must return

# virtual keyboard state (always visible)
keyboard_visible = True  # permanent
caps = False
# input_text is no longer used, field removed
hovered_key = None
hover_start = 0
key_cooldown = 0.8

# appearance
key_bg = (30, 30, 30)
key_bg_alt = (50, 50, 50)
key_outline = (200, 200, 200)
text_color = (235, 235, 235)
input_bg = (20, 20, 20)

# icons and layout
key_icons = {"BACK": "⌫", "SPACE": "␣", "ENT": "↵", "CAP": "⇪", "CLR": "🗑"}
rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
extra_row = ["SPACE", "BACK", "ENT", "CAP", "CLR"]


def draw_rounded_rect(frame, x, y, w, h, color, thickness=0, r=10):
    if thickness == 0:
        cv2.rectangle(frame, (x+r, y), (x+w-r, y+h), color, -1)
        cv2.rectangle(frame, (x, y+r), (x+w, y+h-r), color, -1)
        cv2.circle(frame, (x+r, y+r), r, color, -1)
        cv2.circle(frame, (x+w-r, y+r), r, color, -1)
        cv2.circle(frame, (x+r, y+h-r), r, color, -1)
        cv2.circle(frame, (x+w-r, y+h-r), r, color, -1)
    else:
        cv2.rectangle(frame, (x+r, y), (x+w-r, y+h), color, thickness)
        cv2.rectangle(frame, (x, y+r), (x+w, y+h-r), color, thickness)
        cv2.circle(frame, (x+r, y+r), r, color, thickness)
        cv2.circle(frame, (x+w-r, y+r), r, color, thickness)
        cv2.circle(frame, (x+r, y+h-r), r, color, thickness)
        cv2.circle(frame, (x+w-r, y+h-r), r, color, thickness)


def draw_keyboard(frame, highlight=None, caps_state=False):
    h, w, _ = frame.shape
    origin_x, origin_y = 50, 300
    key_w, key_h = 60, 60
    margin = 5
    key_rects = []

    y = origin_y
    for row in rows:
        x = origin_x
        for ch in row:
            display = ch if caps_state else ch.lower()
            bg = key_bg_alt if highlight == ch else key_bg
            draw_rounded_rect(frame, x, y, key_w, key_h, bg, thickness=0, r=10)
            # no outline to simplify appearance
            cv2.putText(frame, display, (x+15, y+40), cv2.FONT_HERSHEY_SIMPLEX, 1, text_color, 2)
            key_rects.append((ch, (x, y, key_w, key_h)))
            x += key_w + margin
        y += key_h + margin

    # extra row
    x = origin_x
    for ch in extra_row:
        if ch == "SPACE":
            w2 = key_w * 2
        else:
            w2 = key_w
        if ch == "CAP" and caps_state:
            bg = (80, 80, 150)
        else:
            bg = key_bg_alt if highlight == ch else key_bg
        draw_rounded_rect(frame, x, y, w2, key_h, bg, thickness=0, r=10)
        # no outline
        label = key_icons.get(ch, ch)
        cv2.putText(frame, label, (x+20, y+40), cv2.FONT_HERSHEY_SIMPLEX, 1, text_color, 2)
        key_rects.append((ch, (x, y, w2, key_h)))
        x += w2 + margin

    return key_rects


# open camera
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: cannot open camera")
    exit(1)

# main loop
while True:
    try:
        ret, frame = cap.read()
        if not ret:
            print("Warning: failed to grab frame, retrying...")
            time.sleep(0.1)
            continue

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(frame_rgb)

        gesture_name = ""
        fingers = []
        now = time.time()

        if not results.multi_hand_landmarks:
            x_history.clear()
            y_history.clear()
            y_candidate_history.clear()
            x_candidate_history.clear()
            volume_hold = None
            prev_finger_sum = None
            prev_tip_y = None
            tap_down = False
            tap_start = None
            prev_fingers = None

        if results.multi_hand_landmarks:
            index_positions = []
            idx_list = []
            idy_list = []   # normalized y positions of index tip for vertical swipe
            palm_y_list = []
            palm_x_list = []
            for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                mp_draw.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_draw.DrawingSpec(color=landmark_color, thickness=5, circle_radius=2),
                    mp_draw.DrawingSpec(color=connection_color, thickness=2),
                )
                lm = hand_landmarks.landmark
                ix = int(lm[8].x * frame.shape[1])
                iy = int(lm[8].y * frame.shape[0])
                index_positions.append((ix, iy))
                cv2.circle(frame, (ix, iy), 8, (0, 255, 0), -1)

                # accumulate positions for swipe detection regardless of hand index
                # use index tip for fine vertical movement, palm/wrist for whole-hand swipe
                idx_list.append(lm[8].x)
                idy_list.append(lm[8].y)
                palm_x_list.append(lm[9].x)
                palm_y_list.append(lm[9].y)

                if hand_idx == 0:
                    for i in range(5):
                        tip = lm[finger_tips[i]].y
                        pip = lm[finger_tips[i]-2].y
                        fingers.append(1 if tip < pip else 0)

                    # two/three finger volume hold – only trigger when exactly
                    # two or three fingers are extended (index+middle or +ring).
                    # this prevents an open-hand swipe from also changing volume.
                    finger_count = sum(fingers)
                    up_gesture = finger_count == 2 and fingers[1] == 1 and fingers[2] == 1
                    down_gesture = finger_count == 3 and fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 1
                    # prioritize three-finger decrease when both hold true
                    if down_gesture:
                        if volume_hold != "down":
                            if volume_hold == "up":
                                pag.keyUp("volumeup")
                            pag.keyDown("volumedown")
                            volume_hold = "down"
                            gesture_name = "Volume Down"
                    elif up_gesture:
                        if volume_hold != "up":
                            # release opposite key if held
                            if volume_hold == "down":
                                pag.keyUp("volumedown")
                            pag.keyDown("volumeup")
                            volume_hold = "up"
                            gesture_name = "Volume Up"
                    else:
                        if volume_hold == "up":
                            pag.keyUp("volumeup")
                        elif volume_hold == "down":
                            pag.keyUp("volumedown")
                        volume_hold = None

                    # simple one-finger toggle: when configuration becomes exactly
                    # index-only (other fingers folded) fire play/pause immediately.
                    # this tends to be more reliable than vertical pokes.
                    if fingers == [0,1,0,0,0] and prev_fingers != fingers and now - last_action_time > cooldown:
                        pag.press("space")
                        gesture_name = "Play / Pause"
                        last_action_time = now
                    prev_fingers = list(fingers) if fingers else None

                    # tap for play/pause – smoother state machine with timing
                    index_tip = lm[8].y
                    index_pip = lm[6].y
                    if prev_tip_y is not None:
                        # detect a quick downward poke below the pip
                        if not tap_down and index_tip > index_pip + TAP_DOWN_THRESH and prev_tip_y <= index_tip:
                            tap_down = True
                            tap_start = now
                        # once we think a tap is underway, look for a fast return
                        if tap_down:
                            if (index_tip < index_pip - TAP_UP_THRESH and
                                now - tap_start < TAP_TIMEOUT and
                                now - last_action_time > cooldown):
                                pag.press("space")
                                gesture_name = "Play / Pause"
                                last_action_time = now
                                tap_down = False
                                tap_start = None
                            # abort if takes too long or hand moves away
                            elif now - tap_start > TAP_TIMEOUT:
                                tap_down = False
                                tap_start = None
                    else:
                        tap_down = False
                    prev_tip_y = index_tip

                    # thumbs up
                    if fingers == [1,0,0,0,0] and now - last_action_time > cooldown:
                        pag.press("l")
                        gesture_name = "Like Video"
                        last_action_time = now

                    # fist skip/Fullscreen
                    if fingers == [0,0,0,0,0] and now - last_action_time > cooldown:
                        if prev_finger_sum is not None and now - last_action_time > cooldown and prev_finger_sum - sum(fingers) >= 4:
                            pag.press("f")
                            gesture_name = "Fullscreen"
                            last_action_time = now
                        else:
                            pag.press("l")
                            gesture_name = "Skip Ad"
                            last_action_time = now
                        prev_finger_sum = sum(fingers)

            # decide whether current frame qualifies as a swipe candidate
            # vertical: single index finger or open hand
            # horizontal: only open hand (whole-hand swipes for prev/next)
            vertical_candidate = False
            horizontal_candidate = False
            if fingers:
                finger_count = sum(fingers)
                if finger_count >= 4:
                    vertical_candidate = True
                    horizontal_candidate = True
                elif finger_count == 1 and fingers[1] == 1:
                    vertical_candidate = True

            # collect motion data only while the candidate is maintained
            if vertical_candidate:
                # for vertical movement prefer index-tip but fall back to palm
                if idy_list:
                    avg_idy = sum(idy_list)/len(idy_list)
                    y_history.append(avg_idy)
                    y_candidate_history.append(True)
                elif palm_y_list:
                    avg_py = sum(palm_y_list)/len(palm_y_list)
                    y_history.append(avg_py)
                    y_candidate_history.append(True)
            else:
                y_history.clear()
                y_candidate_history.clear()

            if horizontal_candidate:
                # horizontal swipes use palm/wrist centre
                if palm_x_list:
                    avg_px = sum(palm_x_list)/len(palm_x_list)
                    x_history.append(avg_px)
                    x_candidate_history.append(True)
            else:
                x_history.clear()
                x_candidate_history.clear()

            swipe_threshold = 0.12  # normalized distance threshold for clearer swipes
            # horizontal swipes (next/previous video) using open-hand centre
            if len(x_history) >= x_history.maxlen and all(x_candidate_history) and now - last_action_time > cooldown:
                movement = x_history[-1] - x_history[0]
                # require little vertical drift to avoid diagonals
                vert_ok = True
                if len(y_history) >= y_history.maxlen:
                    vert_move = abs(y_history[-1] - y_history[0])
                    vert_ok = vert_move < swipe_threshold/2
                # ensure motion is consistently to one side (monotonic)
                deltas = [x_history[i+1] - x_history[i] for i in range(len(x_history)-1)]
                monotonic_right = all(d > 0 for d in deltas)
                monotonic_left = all(d < 0 for d in deltas)
                if movement > swipe_threshold and vert_ok and monotonic_right:
                    pag.hotkey("shift", "n")
                    gesture_name = "Next Video"
                    last_action_time = now
                    x_history.clear()
                    x_candidate_history.clear()
                elif movement < -swipe_threshold and vert_ok and monotonic_left:
                    pag.hotkey("shift", "p")
                    gesture_name = "Previous Video"
                    last_action_time = now
                    x_history.clear()
                    x_candidate_history.clear()
            # vertical swipes for fullscreen toggle (open hand or single index)
            if len(y_history) >= y_history.maxlen and all(y_candidate_history) and now - last_action_time > cooldown:
                movement = y_history[0] - y_history[-1]  # positive means upward motion
                horiz_ok = True
                if len(x_history) >= x_history.maxlen:
                    horiz_move = abs(x_history[-1] - x_history[0])
                    horiz_ok = horiz_move < swipe_threshold/2
                # check monotonic vertical movement as well
                y_deltas = [y_history[i+1] - y_history[i] for i in range(len(y_history)-1)]
                monotonic_up = all(d < 0 for d in y_deltas)
                monotonic_down = all(d > 0 for d in y_deltas)
                if movement > swipe_threshold and horiz_ok and monotonic_up:
                    pag.press("f")
                    gesture_name = "Fullscreen"
                    last_action_time = now
                    y_history.clear()
                    y_candidate_history.clear()
                    x_history.clear()
                    x_candidate_history.clear()
                elif movement < -swipe_threshold and horiz_ok and monotonic_down:
                    pag.press("esc")
                    gesture_name = "Exit Fullscreen"
                    last_action_time = now
                    y_history.clear()
                    y_candidate_history.clear()
                    x_history.clear()
                    x_candidate_history.clear()

            # keyboard interaction (always visible)
            if keyboard_visible:
                key_rects = draw_keyboard(frame, highlight=hovered_key, caps_state=caps)
                hit_key = None
                for ix, iy in index_positions:
                    for lbl, (kx, ky, kw, kh) in key_rects:
                        if kx < ix < kx+kw and ky < iy < ky+kh:
                            hit_key = lbl
                            break
                    if hit_key:
                        break
                if hit_key is not None:
                    if hovered_key != hit_key:
                        hovered_key = hit_key
                        hover_start = now
                    elif now - hover_start > key_cooldown:
                        if hit_key == "BACK":
                            pag.press("backspace")
                        elif hit_key == "SPACE":
                            pag.typewrite(" ")
                        elif hit_key == "ENT":
                            pag.press("enter")
                        elif hit_key == "CAP":
                            caps = not caps
                        elif hit_key == "CLR":
                            pag.hotkey('ctrl','a')
                            pag.press('backspace')
                        elif hit_key == "CLOSE":
                            # close key removed; ignore
                            pass
                        else:
                            char = hit_key.upper() if caps else hit_key.lower()
                            pag.typewrite(char)
                        hover_start = now
                else:
                    hovered_key = None
                    hover_start = now

        # info overlay
        cv2.putText(frame, f"Fingers: {fingers}", (10,40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        if gesture_name:
            cv2.putText(frame, f"Gesture: {gesture_name}", (10,80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        info_lines = [
            "Supported Gestures:",
            "Swipe right/left – Next/Prev video (open hand swipe)",
            "Swipe up – Fullscreen (one finger or open hand)",
            "Swipe down – Exit fullscreen",
            "Victory sign (2 fingers) – Hold to raise volume",
            "Three fingers – Hold to lower volume",
            "Index down-tap – Play/Pause",
            "Thumbs up – Like video",
            "Fist – Skip ad",
            "Clear key – erase all text",
            "Virtual keyboard always visible (CAP key toggles case)"
        ]
        y0 = 110
        for line in info_lines:
            cv2.putText(frame, line, (10,y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
            y0 += 25

        cv2.imshow("YouTube Gesture Controller", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    except Exception as e:
        print("Error in main loop:", e)
        import traceback; traceback.print_exc()
        continue

# clean up
cap.release()
cv2.destroyAllWindows()