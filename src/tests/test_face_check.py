from ultralytics import YOLO
import cv2
import time

model = YOLO('yolov8n.pt')
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

cap = cv2.VideoCapture(0)

no_face_start_time = None
CONFIRM_SECONDS = 2  # how long face must be missing before flagging

while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame, verbose=False)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    face_found_this_frame = False

    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            label = model.names[cls_id]

            if label == 'person':
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                person_region = gray[y1:y2, x1:x2]
                faces = face_cascade.detectMultiScale(person_region, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))

                if len(faces) > 0:
                    face_found_this_frame = True

                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 1)

    if face_found_this_frame:
        no_face_start_time = None
        status = "Person Identified"
        color = (0, 255, 0)
    else:
        if no_face_start_time is None:
            no_face_start_time = time.time()

        elapsed = time.time() - no_face_start_time
        if elapsed >= CONFIRM_SECONDS:
            status = "FACE CONCEALED"
            color = (0, 0, 255)
        else:
            status = "Checking..."
            color = (0, 255, 255)

    cv2.putText(frame, status, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    cv2.imshow('SentryEye - Face Check (Press Q to quit)', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()