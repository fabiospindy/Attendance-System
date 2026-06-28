from flask import Flask, render_template, request, redirect, session, url_for, jsonify, Response
from flask_wtf.csrf import CSRFProtect, generate_csrf
from functools import wraps
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import csv, io, os, cv2, numpy as np, sqlite3, base64, json, re, uuid

app = Flask(__name__)

debug_mode = os.environ.get('FLASK_DEBUG', '1') == '1'
production_mode = os.environ.get('FLASK_ENV', '').lower() == 'production' or os.environ.get('PRODUCTION', '0') == '1'
secret_key = os.environ.get('SECRET_KEY')
if production_mode and not secret_key:
    raise RuntimeError('SECRET_KEY environment variable must be set in production')
app.secret_key = secret_key or 'ams_dev_secret_2024'
app.config['DEBUG'] = debug_mode
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = production_mode
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_REFRESH_EACH_REQUEST'] = True
app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken', 'X-CSRF-Token']
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['WTF_CSRF_SSL_STRICT'] = False
csrf = CSRFProtect(app)

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR  = os.path.join(BASE_DIR, 'dataset')
TRAINER_DIR  = os.path.join(BASE_DIR, 'trainer')
DB_PATH      = os.path.join(BASE_DIR, 'database', 'attendance.db')
CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'

for d in [DATASET_DIR, TRAINER_DIR, os.path.dirname(DB_PATH)]:
    os.makedirs(d, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def hash_pw(pw):
    return generate_password_hash(pw)

def verify_pw(stored_hash, pw):
    return check_password_hash(stored_hash, pw)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS lecturers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                email      TEXT UNIQUE NOT NULL,
                password   TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS students (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL,
                department  TEXT,
                password    TEXT NOT NULL,
                samples     INTEGER DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                token        TEXT UNIQUE NOT NULL,
                lecturer_id  INTEGER NOT NULL,
                course       TEXT NOT NULL,
                date         DATE NOT NULL,
                active       INTEGER DEFAULT 1,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(lecturer_id) REFERENCES lecturers(id)
            );
            CREATE TABLE IF NOT EXISTS attendance (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  TEXT NOT NULL,
                session_id  INTEGER NOT NULL,
                date        DATE NOT NULL,
                time        TIME NOT NULL,
                confidence  REAL,
                UNIQUE(student_id, session_id)
            );
        ''')

init_db()

@app.context_processor
def inject_csrf_token():
    from flask import session as flask_session
    return {
        'csrf_token': generate_csrf,
        'session': flask_session
    }


@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "object-src 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
    return response


# ── Auth decorators ───────────────────────────────────────────────────────────
def lecturer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('lecturer_id'):
            return redirect(url_for('lecturer_login'))
        return f(*args, **kwargs)
    return decorated

def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('student_id'):
            return redirect(url_for('student_login'))
        return f(*args, **kwargs)
    return decorated


# ── Landing page ──────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

@app.route('/portals')
def portals():
    return render_template('portals.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/help-support')
def help_support():
    return render_template('help_support.html')


# ══════════════════════════════════════════════════════════════════════════════
# LECTURER ROUTES
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/lecturer/signup', methods=['GET', 'POST'])
def lecturer_signup():
    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        pw2   = request.form.get('confirm_password', '')
        if not name or not email or not pw:
            return render_template('lecturer_signup.html', error='All fields are required.')
        if pw != pw2:
            return render_template('lecturer_signup.html', error='Passwords do not match.')
        if len(pw) < 6:
            return render_template('lecturer_signup.html', error='Password must be at least 6 characters.')
        try:
            with get_db() as conn:
                conn.execute('INSERT INTO lecturers (name, email, password) VALUES (?,?,?)',
                             (name, email, hash_pw(pw)))
            return redirect(url_for('lecturer_login', success='Account created. Please sign in.'))
        except sqlite3.IntegrityError:
            return render_template('lecturer_signup.html', error='Email already registered.')
    return render_template('lecturer_signup.html')

@app.route('/lecturer/login', methods=['GET', 'POST'])
def lecturer_login():
    success = request.args.get('success')
    if request.method == 'POST':
        try:
            attempts = session.get('l_attempts', 0)
            if attempts >= 3:
                return render_template('lecturer_login.html', error='Account locked. Please restart.')
            email = request.form.get('email', '').strip().lower()
            pw    = request.form.get('password', '')
            with get_db() as conn:
                lecturer = conn.execute('SELECT * FROM lecturers WHERE email=?', (email,)).fetchone()
            if lecturer and verify_pw(lecturer['password'], pw):
                session['lecturer_id']   = lecturer['id']
                session['lecturer_name'] = lecturer['name']
                session['l_attempts']    = 0
                session.permanent        = True
                return redirect(url_for('lecturer_dashboard'))
            session['l_attempts'] = attempts + 1
            remaining = 3 - session['l_attempts']
            error = ('Account locked.' if session['l_attempts'] >= 3
                     else f'Invalid credentials. {remaining} attempt(s) remaining.')
            return render_template('lecturer_login.html', error=error)
        except Exception as e:
            import traceback
            print(f"ERROR in lecturer_login: {e}")
            traceback.print_exc()
            return render_template('lecturer_login.html', error=f'Server error: {str(e)}')
    return render_template('lecturer_login.html', success=success)

@app.route('/lecturer/logout')
def lecturer_logout():
    session.pop('lecturer_id', None)
    session.pop('lecturer_name', None)
    return redirect(url_for('index'))

@app.route('/lecturer/dashboard')
@lecturer_required
def lecturer_dashboard():
    print('[DEBUG] lecturer_dashboard session=', dict(session))
    with get_db() as conn:
        total_students  = conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]
        total_sessions  = conn.execute(
            'SELECT COUNT(*) FROM sessions WHERE lecturer_id=?',
            (session['lecturer_id'],)).fetchone()[0]
        active_session  = conn.execute(
            'SELECT * FROM sessions WHERE lecturer_id=? AND active=1 ORDER BY created_at DESC LIMIT 1',
            (session['lecturer_id'],)).fetchone()
        recent          = conn.execute('''
            SELECT a.student_id, s.name, se.course, a.date, a.time, a.confidence
            FROM attendance a
            JOIN students s  ON a.student_id = s.student_id
            JOIN sessions se ON a.session_id  = se.id
            WHERE se.lecturer_id = ?
            ORDER BY a.date DESC, a.time DESC LIMIT 10
        ''', (session['lecturer_id'],)).fetchall()
    return render_template('lecturer_dashboard.html',
                           total_students=total_students,
                           total_sessions=total_sessions,
                           active_session=active_session,
                           recent=recent)

@app.route('/lecturer/register')
@lecturer_required
def lecturer_register():
    with get_db() as conn:
        students = conn.execute('SELECT * FROM students ORDER BY created_at DESC').fetchall()
    return render_template('lecturer_register.html', students=students)

@app.route('/lecturer/sessions')
@lecturer_required
def lecturer_sessions():
    with get_db() as conn:
        sessions_list = conn.execute('''
            SELECT se.*, COUNT(a.id) as attendance_count
            FROM sessions se
            LEFT JOIN attendance a ON se.id = a.session_id
            WHERE se.lecturer_id = ?
            GROUP BY se.id
            ORDER BY se.created_at DESC
        ''', (session['lecturer_id'],)).fetchall()
    return render_template('lecturer_sessions.html', sessions=sessions_list)

@app.route('/lecturer/attendance-summary')
@lecturer_required
def lecturer_attendance_summary():
    with get_db() as conn:
        rows = conn.execute('''
            SELECT a.student_id, s.name, se.course,
                   COUNT(DISTINCT a.session_id) AS attended_sessions,
                   (SELECT COUNT(*) FROM sessions WHERE lecturer_id = ? AND course = se.course) AS total_sessions
            FROM attendance a
            JOIN students s ON a.student_id = s.student_id
            JOIN sessions se ON a.session_id = se.id
            WHERE se.lecturer_id = ?
            GROUP BY a.student_id, s.name, se.course
            ORDER BY se.course, s.name
        ''', (session['lecturer_id'], session['lecturer_id'])).fetchall()
    summary = []
    for row in rows:
        total_sessions = row['total_sessions'] or 0
        percent = round((row['attended_sessions'] / total_sessions) * 100, 1) if total_sessions else 0.0
        summary.append({
            'student_id': row['student_id'],
            'name': row['name'],
            'course': row['course'],
            'attended_sessions': row['attended_sessions'],
            'total_sessions': total_sessions,
            'attendance_percent': percent
        })
    return render_template('lecturer_attendance_summary.html', summary=summary)

@app.route('/lecturer/attendance-summary/download')
@lecturer_required
def download_attendance_summary():
    with get_db() as conn:
        rows = conn.execute('''
            SELECT a.student_id, s.name, se.course,
                   COUNT(DISTINCT a.session_id) AS attended_sessions,
                   (SELECT COUNT(*) FROM sessions WHERE lecturer_id = ? AND course = se.course) AS total_sessions
            FROM attendance a
            JOIN students s ON a.student_id = s.student_id
            JOIN sessions se ON a.session_id = se.id
            WHERE se.lecturer_id = ?
            GROUP BY a.student_id, s.name, se.course
            ORDER BY se.course, s.name
        ''', (session['lecturer_id'], session['lecturer_id'])).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student ID', 'Name', 'Course', 'Attended Sessions', 'Total Sessions', 'Attendance Percent'])
    for row in rows:
        total_sessions = row['total_sessions'] or 0
        percent = round((row['attended_sessions'] / total_sessions) * 100, 1) if total_sessions else 0.0
        writer.writerow([row['student_id'], row['name'], row['course'], row['attended_sessions'], total_sessions, percent])
    csv_data = output.getvalue()
    filename = 'attendance_summary.csv'
    return Response(csv_data, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

@app.route('/lecturer/session/<int:session_id>/attendance/download')
@lecturer_required
def download_session_attendance(session_id):
    with get_db() as conn:
        session_row = conn.execute(
            'SELECT id, course FROM sessions WHERE id=? AND lecturer_id=?',
            (session_id, session['lecturer_id'])).fetchone()
        if not session_row:
            return render_template('error.html', message='Session not found or not accessible.')
        rows = conn.execute('''
            SELECT a.student_id, s.name, a.date, a.time, a.confidence
            FROM attendance a
            JOIN students s ON a.student_id = s.student_id
            WHERE a.session_id = ?
            ORDER BY a.date DESC, a.time DESC
        ''', (session_id,)).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student ID', 'Name', 'Date', 'Time', 'Confidence'])
    for row in rows:
        writer.writerow([row['student_id'], row['name'], row['date'], row['time'], row['confidence']])
    filename = f'session_{session_row["id"]}_attendance.csv'
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})

@app.route('/api/lecturer/session/create', methods=['POST'])
@lecturer_required
def create_session():
    data   = request.get_json()
    course = data.get('course', '').strip()
    if not course:
        return jsonify({'success': False, 'message': 'Course name is required.'})
    token = None
    attempts = 0
    while attempts < 5:
        candidate = str(uuid.uuid4())[:8].upper()
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO sessions (token, lecturer_id, course, date) VALUES (?,?,?,DATE('now'))",
                             (candidate, session['lecturer_id'], course))
            token = candidate
            break
        except sqlite3.IntegrityError:
            attempts += 1
    if not token:
        return jsonify({'success': False, 'message': 'Could not create a new session. Please try again.'})
    link = url_for('join_session', token=token, _external=True)
    return jsonify({'success': True, 'token': token, 'link': link,
                    'message': f'Session created for {course}.'})

@app.route('/api/lecturer/session/end', methods=['POST'])
@lecturer_required
def end_session():
    data = request.get_json()
    sid  = data.get('session_id')
    with get_db() as conn:
        conn.execute('UPDATE sessions SET active=0 WHERE id=? AND lecturer_id=?',
                     (sid, session['lecturer_id']))
    return jsonify({'success': True, 'message': 'Session ended.'})

@app.route('/api/lecturer/student', methods=['POST'])
@lecturer_required
def lecturer_add_student():
    data       = request.get_json()
    student_id = data.get('student_id', '').strip()
    name       = data.get('name', '').strip()
    department = data.get('department', '').strip()
    password   = data.get('password', '').strip()
    if not student_id or not name or not password:
        return jsonify({'success': False, 'message': 'Student ID, name, and initial password are required.'})
    if len(password) < 4:
        return jsonify({'success': False, 'message': 'Initial password must be at least 4 characters.'})
    try:
        with get_db() as conn:
            conn.execute('INSERT INTO students (student_id, name, department, password) VALUES (?,?,?,?)',
                         (student_id, name, department, hash_pw(password)))
        return jsonify({'success': True, 'message': f'Student {name} added. Initial password set.'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Student ID already registered.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# Face capture + training (lecturer side)
@app.route('/api/lecturer/capture', methods=['POST'])
@lecturer_required
def lecturer_capture():
    data       = request.get_json()
    student_id = data.get('student_id', '').strip()
    image_data = data.get('image', '')
    return _capture_face(student_id, image_data)

@app.route('/api/lecturer/train', methods=['POST'])
@lecturer_required
def lecturer_train():
    return _train_model()

# Recognize during live session
@app.route('/api/lecturer/recognize', methods=['POST'])
@lecturer_required
def lecturer_recognize():
    data       = request.get_json()
    session_id = data.get('session_id')
    image_data = data.get('image', '')
    return _recognize(image_data, session_id)


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        name       = request.form.get('name', '').strip()
        department = request.form.get('department', '').strip()
        pw         = request.form.get('password', '')
        pw2        = request.form.get('confirm_password', '')
        if not student_id or not name or not pw:
            return render_template('student_register.html', error='All fields are required.')
        if pw != pw2:
            return render_template('student_register.html', error='Passwords do not match.')
        try:
            with get_db() as conn:
                conn.execute('INSERT INTO students (student_id, name, department, password) VALUES (?,?,?,?)',
                             (student_id, name, department, hash_pw(pw)))
            session['student_id']   = student_id
            session['student_name'] = name
            session.permanent       = True
            return redirect(url_for('student_enroll'))
        except sqlite3.IntegrityError:
            return render_template('student_register.html', error='Student ID already registered.')
    return render_template('student_register.html')

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    next_url = request.values.get('next', '')
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        pw         = request.form.get('password', '')
        with get_db() as conn:
            student = conn.execute('SELECT * FROM students WHERE student_id=?', (student_id,)).fetchone()
        if student and verify_pw(student['password'], pw):
            session['student_id']   = student['student_id']
            session['student_name'] = student['name']
            session.permanent       = True
            safe_next = next_url if next_url.startswith('/') else ''
            return redirect(safe_next or url_for('student_dashboard'))
        return render_template('student_login.html', error='Invalid Student ID or password.', next=next_url)
    return render_template('student_login.html', next=next_url)

@app.route('/student/logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    return redirect(url_for('index'))

@app.route('/student/change-password', methods=['GET', 'POST'])
@student_required
def student_change_password():
    if request.method == 'POST':
        old_pw  = request.form.get('old_password', '')
        new_pw  = request.form.get('new_password', '')
        new_pw2 = request.form.get('confirm_password', '')
        if not old_pw or not new_pw or not new_pw2:
            return render_template('student_change_password.html', error='All fields are required.')
        if new_pw != new_pw2:
            return render_template('student_change_password.html', error='New passwords do not match.')
        if len(new_pw) < 6:
            return render_template('student_change_password.html', error='New password must be at least 6 characters.')
        with get_db() as conn:
            student = conn.execute('SELECT * FROM students WHERE student_id=?', (session['student_id'],)).fetchone()
        if not student or not verify_pw(student['password'], old_pw):
            return render_template('student_change_password.html', error='Current password is incorrect.')
        with get_db() as conn:
            conn.execute('UPDATE students SET password=? WHERE student_id=?',
                         (hash_pw(new_pw), session['student_id']))
        return render_template('student_change_password.html', success='Password changed successfully!')
    return render_template('student_change_password.html')

@app.route('/student/enroll')
@student_required
def student_enroll():
    with get_db() as conn:
        student = conn.execute('SELECT samples FROM students WHERE student_id=?', (session['student_id'],)).fetchone()
        samples = student['samples'] if student else 0
    return render_template('student_enroll.html', samples_captured=samples)

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    with get_db() as conn:
        records = conn.execute('''
            SELECT a.date, a.time, a.confidence, se.course
            FROM attendance a
            JOIN sessions se ON a.session_id = se.id
            WHERE a.student_id = ?
            ORDER BY a.date DESC, a.time DESC
        ''', (session['student_id'],)).fetchall()
        total   = len(records)
        student = conn.execute('SELECT * FROM students WHERE student_id=?',
                               (session['student_id'],)).fetchone()
    return render_template('student_dashboard.html', records=records,
                           total=total, student=student)

@app.route('/student/join/<token>')
def join_session(token):
    with get_db() as conn:
        sess = conn.execute(
            'SELECT se.*, l.name as lecturer_name FROM sessions se '
            'JOIN lecturers l ON se.lecturer_id = l.id '
            'WHERE se.token=? AND se.active=1', (token,)).fetchone()
    if not sess:
        return render_template('error.html', message='Session not found or has ended.')
    return render_template('student_join.html', sess=sess)

@app.route('/api/student/clear-samples', methods=['POST'])
@student_required
def student_clear_samples():
    import shutil
    student_id = session['student_id']
    student_dir = os.path.join(DATASET_DIR, student_id)
    if os.path.exists(student_dir):
        shutil.rmtree(student_dir)
    os.makedirs(student_dir, exist_ok=True)
    with get_db() as conn:
        conn.execute('UPDATE students SET samples=0 WHERE student_id=?', (student_id,))
    return jsonify({'success': True, 'message': 'Face samples cleared. You can re-enroll now.'})


@app.route('/api/student/capture', methods=['POST'])
@student_required
def student_capture():
    data       = request.get_json()
    image_data = data.get('image', '')
    return _capture_face(session['student_id'], image_data)

@app.route('/api/student/recognize', methods=['POST'])
def student_recognize():
    data       = request.get_json()
    session_id = data.get('session_id')
    image_data = data.get('image', '')
    result     = _recognize(image_data, session_id, target_student=None)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# SHARED ML FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════
def _capture_face(student_id, image_data):
    if not student_id or not image_data:
        return jsonify({'success': False, 'message': 'Missing student ID or image.'})
    try:
        img_bytes = base64.b64decode(re.sub(r'^data:image/\w+;base64,', '', image_data))
        np_arr    = np.frombuffer(img_bytes, np.uint8)
        frame     = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({'success': False, 'message': 'Could not decode image.'})
        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray    = cv2.equalizeHist(gray)
        cascade = cv2.CascadeClassifier(CASCADE_PATH)
        faces   = cascade.detectMultiScale(gray, scaleFactor=1.03, minNeighbors=1, minSize=(20, 20))
        if len(faces) == 0:
            faces = cascade.detectMultiScale(gray, scaleFactor=1.01, minNeighbors=1, minSize=(15, 15))
        if len(faces) == 0:
            return jsonify({'success': False, 'message': 'No face detected. Adjust lighting or position.'})
        if len(faces) > 1:
            faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)[:1]
        student_dir = os.path.join(DATASET_DIR, student_id)
        os.makedirs(student_dir, exist_ok=True)
        count = len([f for f in os.listdir(student_dir) if f.endswith('.jpg')])
        if count >= 30:
            return jsonify({'success': True, 'count': count, 'message': 'Already have 30 samples.'})
        x, y, w, h = faces[0]

        last_face_key = f'last_face_{student_id}'
        motion_key = f'motion_score_{student_id}'
        last_face = session.get(last_face_key)
        motion_score = session.get(motion_key, 0)
        if last_face:
            movement = abs(x - last_face[0]) + abs(y - last_face[1])
            if movement > 16:
                motion_score = min(99, motion_score + 1)
                session[motion_key] = motion_score
        session[last_face_key] = [int(x), int(y), int(w), int(h)]

        if count >= 10 and motion_score < 1:
            return jsonify({
                'success': False,
                'message': 'Move your head slightly between samples to confirm live presence.'
            })

        face_roi   = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
        cv2.imwrite(os.path.join(student_dir, f'{count+1}.jpg'), face_roi)
        with get_db() as conn:
            conn.execute('UPDATE students SET samples=? WHERE student_id=?', (count+1, student_id))

        if count + 1 >= 30:
            session.pop(last_face_key, None)
            session.pop(motion_key, None)

        return jsonify({'success': True, 'count': count+1, 'message': f'Sample {count+1} captured.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def _train_model():
    try:
        recognizer  = cv2.face.LBPHFaceRecognizer_create()
        face_images, labels, label_map = [], [], {}
        with get_db() as conn:
            students = conn.execute('SELECT student_id FROM students').fetchall()
        for i, row in enumerate(students):
            sid         = row['student_id']
            label_map[i] = sid
            student_dir  = os.path.join(DATASET_DIR, sid)
            if not os.path.exists(student_dir):
                continue
            for img_file in os.listdir(student_dir):
                if img_file.endswith('.jpg'):
                    img = cv2.imread(os.path.join(student_dir, img_file), cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        face_images.append(img)
                        labels.append(i)
        if len(face_images) < 2:
            return jsonify({'success': False, 'message': 'Need at least 2 face samples to train.'})
        recognizer.train(face_images, np.array(labels))
        recognizer.save(os.path.join(TRAINER_DIR, 'trainer.yml'))
        with open(os.path.join(TRAINER_DIR, 'label_map.json'), 'w') as f:
            json.dump(label_map, f)
        return jsonify({'success': True,
                        'message': f'Model trained on {len(face_images)} samples from {len(students)} student(s).'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def _recognize(image_data, session_id, target_student=None):
    if not session_id:
        return jsonify({'success': False, 'message': 'Session ID is required.'})
    with get_db() as conn:
        if target_student:
            valid_session = conn.execute('SELECT id FROM sessions WHERE id=? AND active=1', (session_id,)).fetchone()
        else:
            valid_session = conn.execute('SELECT id FROM sessions WHERE id=? AND lecturer_id=? AND active=1',
                                         (session_id, session['lecturer_id'])).fetchone()
    if not valid_session:
        return jsonify({'success': False, 'message': 'Invalid or inactive session.'})

    model_path = os.path.join(TRAINER_DIR, 'trainer.yml')
    label_path = os.path.join(TRAINER_DIR, 'label_map.json')
    if not os.path.exists(model_path):
        return jsonify({'success': False, 'message': 'Model not trained yet. Please train first.'})
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(model_path)
        with open(label_path) as f:
            label_map = json.load(f)
        img_bytes = base64.b64decode(re.sub(r'^data:image/\w+;base64,', '', image_data))
        np_arr    = np.frombuffer(img_bytes, np.uint8)
        frame     = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({'success': False, 'message': 'Could not decode image.'})
        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray    = cv2.equalizeHist(gray)
        cascade = cv2.CascadeClassifier(CASCADE_PATH)
        faces   = cascade.detectMultiScale(gray, scaleFactor=1.03, minNeighbors=1, minSize=(20, 20))
        if len(faces) == 0:
            faces = cascade.detectMultiScale(gray, scaleFactor=1.01, minNeighbors=1, minSize=(15, 15))
        results = []
        for (x, y, w, h) in faces:
            face_roi          = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            label, confidence = recognizer.predict(face_roi)
            confidence_pct    = round(max(0, 100 - confidence), 1)
            if confidence < 45:
                student_id = label_map.get(str(label))
                if student_id:
                    if target_student and student_id != target_student:
                        results.append({'name': 'Not you', 'confidence': confidence_pct,
                                        'status': 'mismatch', 'box': [int(x), int(y), int(w), int(h)]})
                        continue
                    with get_db() as conn:
                        student = conn.execute(
                            'SELECT name FROM students WHERE student_id=?', (student_id,)).fetchone()
                        if student:
                            cursor = conn.execute(
                                "INSERT OR IGNORE INTO attendance (student_id,session_id,date,time,confidence) "
                                "VALUES (?,?,DATE('now'),TIME('now'),?)",
                                (student_id, session_id, confidence_pct))
                            status = 'marked' if cursor.rowcount else 'already_marked'
                            results.append({'student_id': student_id, 'name': student['name'],
                                            'confidence': confidence_pct, 'status': status,
                                            'box': [int(x), int(y), int(w), int(h)]})
            else:
                results.append({'name': 'Face not recognized', 'confidence': confidence_pct, 'status': 'unknown', 'box': [int(x), int(y), int(w), int(h)]})
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.errorhandler(500)
def internal_server_error(e):
    import traceback
    tb = traceback.format_exc()
    print(tb)
    if production_mode:
        return render_template('error.html', message='An internal server error occurred. Please contact support.'), 500
    return f"<pre>{tb}</pre>", 500


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
















