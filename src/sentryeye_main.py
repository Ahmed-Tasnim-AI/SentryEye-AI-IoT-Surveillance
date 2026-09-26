from ultralytics import YOLO
import cv2
import time
import smtplib
import sqlite3
import requests
import numpy as np
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
import config

model = YOLO('yolov8n.pt')
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# ESP32-CAM stream URL - UPDATE THIS IP IF IT CHANGES
STREAM_URL = 'http://YOUR_ESP32_IP:81/stream'

ZONE_X1, ZONE_Y1, ZONE_X2, ZONE_Y2 = 40, 20, 280, 220
INTRUSION_SECONDS = 5
CONFIRM_SECONDS = 2
ALERT_COOLDOWN = 30

zone_entry_time = None
no_face_start_time = None
last_alert_time = 0
alert_sent_this_intrusion = False


def init_db():
    conn = sqlite3.connect('sentryeye_log.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS detections
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  status TEXT,
                  face_status TEXT,
                  snapshot_path TEXT)''')
    conn.commit()
    conn.close()


def log_detection(status, face_status, frame):
    timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
    snapshot_filename = f"snapshots/{timestamp}.jpg"
    cv2.imwrite(snapshot_filename, frame)

    conn = sqlite3.connect('sentryeye_log.db')
    c = conn.cursor()
    c.execute("INSERT INTO detections (timestamp, status, face_status, snapshot_path) VALUES (?, ?, ?, ?)",
              (time.strftime('%Y-%m-%d %H:%M:%S'), status, face_status, snapshot_filename))
    conn.commit()
    conn.close()


def send_email_alert(frame, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = config.EMAIL_ADDRESS
        msg['To'] = config.ALERT_TO_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        _, img_encoded = cv2.imencode('.jpg', frame)
        image = MIMEImage(img_encoded.tobytes(), name='snapshot.jpg')
        msg.attach(image)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config.EMAIL_ADDRESS, config.EMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("Alert email sent!")
    except Exception as e:
        print("Email failed:", e)


init_db()

quit_flag = False

while not quit_flag:
    try:
        print("Connecting to ESP32-CAM stream...")
        stream = requests.get(STREAM_URL, stream=True, timeout=10)
        bytes_buffer = bytes()
        print("Connected. Starting detection loop...")

        for chunk in stream.iter_content(chunk_size=1024):
            bytes_buffer += chunk
            a = bytes_buffer.find(b'\xff\xd8')
            b = bytes_buffer.find(b'\xff\xd9')

            if a != -1 and b != -1:
                jpg = bytes_buffer[a:b+2]
                bytes_buffer = bytes_buffer[b+2:]
                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

                if frame is None:
                    continue
                

                results = model(frame, verbose=False)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                cv2.rectangle(frame, (ZONE_X1, ZONE_Y1), (ZONE_X2, ZONE_Y2), (0, 255, 255), 2)
                cv2.putText(frame, "ZONE", (ZONE_X1 + 5, ZONE_Y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

                person_in_zone = False
                face_found_this_frame = False

                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        label = model.names[cls_id]
                        if label == 'person':
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                            if ZONE_X1 < cx < ZONE_X2 and ZONE_Y1 < cy < ZONE_Y2:
                                person_in_zone = True
                                box_color = (0, 0, 255)
                            else:
                                box_color = (255, 255, 0)

                            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

                            person_region = gray[y1:y2, x1:x2]
                            faces = face_cascade.detectMultiScale(person_region, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
                            if len(faces) > 0:
                                face_found_this_frame = True

                if person_in_zone:
                    if zone_entry_time is None:
                        zone_entry_time = time.time()
                    zone_elapsed = time.time() - zone_entry_time
                else:
                    zone_entry_time = None
                    zone_elapsed = 0
                    alert_sent_this_intrusion = False

                if face_found_this_frame:
                    no_face_start_time = None
                    face_status = "Face Visible"
                else:
                    if no_face_start_time is None:
                        no_face_start_time = time.time()
                    face_elapsed = time.time() - no_face_start_time
                    face_status = "Face Concealed" if face_elapsed >= CONFIRM_SECONDS else "Checking..."

                if person_in_zone and zone_elapsed >= INTRUSION_SECONDS:
                    if face_status == "Face Concealed":
                        alert_text = "HIGH PRIORITY: INTRUDER (FACE HIDDEN)"
                        alert_color = (0, 0, 255)
                    else:
                        alert_text = "INTRUSION DETECTED"
                        alert_color = (0, 100, 255)

                    if not alert_sent_this_intrusion and (time.time() - last_alert_time) > ALERT_COOLDOWN:
                        send_email_alert(frame, "SentryEye Alert: " + alert_text,
                                          f"Intrusion detected at {time.strftime('%Y-%m-%d %H:%M:%S')}\nFace status: {face_status}")
                        log_detection(alert_text, face_status, frame)
                        last_alert_time = time.time()
                        alert_sent_this_intrusion = True
                elif person_in_zone:
                    alert_text = f"Person in zone... ({int(zone_elapsed)}s / {INTRUSION_SECONDS}s)"
                    alert_color = (0, 255, 255)
                else:
                    alert_text = "Zone Clear"
                    alert_color = (0, 255, 0)

                cv2.putText(frame, alert_text, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, alert_color, 1)
                cv2.putText(frame, face_status, (5, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

                cv2.imshow('SentryEye - Live', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    quit_flag = True
                    break
    except KeyboardInterrupt:
        print("Stopped by user.")
        break

    except Exception as e:
        print("Connection lost, reconnecting in 2 seconds...", e)
        time.sleep(2)
        continue

cv2.destroyAllWindows()