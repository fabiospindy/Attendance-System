# AttendanceIQ — Facial Recognition Attendance System

## Tech stack
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Backend**: Flask (Python)
- **Face detection**: OpenCV + Haar Cascade
- **Face recognition**: LBPH (Local Binary Pattern Histogram)
- **Database**: SQLite

## Setup

### 1. Clone / copy the project
```bash
cd attendance-system
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
python app.py
```

Open `http://localhost:5000` in your browser.

## Usage flow

1. **Lecturer sign-up** at `/lecturer/signup` and then log in at `/lecturer/login`.
2. **Add or enroll students** from the lecturer portal:
   - Use `/lecturer/register` to add a student record.
   - Use the face capture tools to collect samples for each student.
   - Click **Train LBPH model** after capture is complete.
3. **Create a session** from the lecturer dashboard.
   - Share the generated join link with students.
4. **Student attendance**:
   - Students log in at `/student/login` or register at `/student/register`.
   - They join a live session through the shared link and mark attendance with face recognition.

## Project structure
```
attendance/
├── app.py
├── requirements.txt
├── README.md
├── database/
│   └── attendance.db
├── dataset/
├── trainer/
│   ├── label_map.json
│   └── trainer.yml
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── register.js
│       └── student_enroll.js
└── templates/
    ├── auth_base.html
    ├── base.html
    ├── error.html
    ├── help_support.html
    ├── how_it_works.html
    ├── index.html
    ├── lecturer_base.html
    ├── lecturer_dashboard.html
    ├── lecturer_login.html
    ├── lecturer_register.html
    ├── lecturer_sessions.html
    ├── lecturer_signup.html
    ├── portals.html
    ├── privacy.html
    ├── student_dashboard.html
    ├── student_enroll.html
    ├── student_join.html
    ├── student_login.html
    └── student_register.html
```

## Key API endpoints
| Method | Route                        | Description                              |
|--------|------------------------------|------------------------------------------|
| POST   | `/lecturer/signup`           | Create a new lecturer account            |
| POST   | `/lecturer/login`            | Lecturer authentication                  |
| POST   | `/student/register`          | Student account creation                 |
| POST   | `/student/login`             | Student authentication                   |
| POST   | `/api/lecturer/student`      | Add student from lecturer dashboard      |
| POST   | `/api/lecturer/capture`      | Capture student face sample              |
| POST   | `/api/lecturer/train`        | Train LBPH recognition model             |
| POST   | `/api/lecturer/recognize`    | Recognize faces during a lecturer session|
| POST   | `/api/lecturer/session/create` | Create a new attendance session        |
| POST   | `/api/lecturer/session/end`  | End an active session                    |
| POST   | `/api/student/capture`       | Capture student face sample              |
| POST   | `/api/student/recognize`     | Recognize student in live session        |

## Notes
- Requires **opencv-contrib-python** (not `opencv-python`) for LBPH.
- Aim for **50 face samples** per student for good accuracy.
- LBPH confidence threshold is set to **60** — lower means stricter matching.
- For production: hash passwords with `werkzeug.security`, use a fixed `SECRET_KEY`.
