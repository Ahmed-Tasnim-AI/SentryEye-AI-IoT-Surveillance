from ultralytics import YOLO
import cv2
import time

model = YOLO('yolov8n.pt')
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

cap = cv2.VideoCapture("http://YOUR_ESP32_IP:80/stream")

# Define restricted zone (x1, y1, x2, y2) - adjust these numbers based on your camera resolution
ZONE_X1, ZONE_Y1, ZONE_X2, ZONE_Y2 = 50, 30, 600, 470

INTRUSION_SECONDS = 5   # how long someone must stay in zone to trigger alert
CONFIRM_SECONDS = 2     # face concealment confirmation delay
zone_entry_time = None
no_face_start_time = None

while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame, verbose=False)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Draw the restricted zone rectangle (yellow outline)
    cv2.rectangle(frame, (ZONE_X1, ZONE_Y1), (ZONE_X2, ZONE_Y2), (0, 255, 255), 2)
    cv2.putText(frame, "RESTRICTED ZONE", (ZONE_X1, ZONE_Y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    person_in_zone = False
    face_found_this_frame = False

    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            label = model.names[cls_id]

            if label == 'person':
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                # Find center point of the person's box
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                # Check if center point is inside the restricted zone
                if ZONE_X1 < cx < ZONE_X2 and ZONE_Y1 < cy < ZONE_Y2:
                    person_in_zone = True
                    box_color = (0, 0, 255)  # red box if inside zone
                else:
                    box_color = (255, 255, 0)  # cyan box if outside zone

                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

                # Face check
                person_region = gray[y1:y2, x1:x2]
                faces = face_cascade.detectMultiScale(person_region, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
                if len(faces) > 0:
                    face_found_this_frame = True

    # Zone timer logic
    if person_in_zone:
        if zone_entry_time is None:
            zone_entry_time = time.time()
        zone_elapsed = time.time() - zone_entry_time
    else:
        zone_entry_time = None
        zone_elapsed = 0

    # Face concealment timer logic
    if face_found_this_frame:
        no_face_start_time = None
        face_status = "Face Visible"
    else:
        if no_face_start_time is None:
            no_face_start_time = time.time()
        face_elapsed = time.time() - no_face_start_time
        face_status = "Face Concealed" if face_elapsed >= CONFIRM_SECONDS else "Checking..."

    # Determine overall alert status
    if person_in_zone and zone_elapsed >= INTRUSION_SECONDS:
        if face_status == "Face Concealed":
            alert_text = "HIGH PRIORITY: INTRUDER (FACE HIDDEN)"
            alert_color = (0, 0, 255)
        else:
            alert_text = "INTRUSION DETECTED"
            alert_color = (0, 100, 255)
    elif person_in_zone:
        alert_text = f"Person in zone... ({int(zone_elapsed)}s / {INTRUSION_SECONDS}s)"
        alert_color = (0, 255, 255)
    else:
        alert_text = "Zone Clear"
        alert_color = (0, 255, 0)

    cv2.putText(frame, alert_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, alert_color, 2)
    cv2.putText(frame, face_status, (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    cv2.imshow('SentryEye - Zone Intrusion Test (Press Q to quit)', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()