let stream = null, capInterval = null, capCount = 0;
const TARGET = 30;
let video, canvas, camOverlay;
let motionCanvas = null, lastMotionFrame = null, motionScore = 0;

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : '';
}

function initMotionCanvas() {
  if (!motionCanvas) {
    motionCanvas = document.createElement('canvas');
    motionCanvas.width = 160;
    motionCanvas.height = 120;
  }
  return motionCanvas.getContext('2d');
}

function detectMotion() {
  if (!video || video.readyState < 2) return false;
  const ctx = initMotionCanvas();
  ctx.drawImage(video, 0, 0, motionCanvas.width, motionCanvas.height);
  const current = ctx.getImageData(0, 0, motionCanvas.width, motionCanvas.height).data;
  if (!lastMotionFrame) { lastMotionFrame = new Uint8ClampedArray(current); return false; }
  let diff = 0;
  for (let i = 0; i < current.length; i += 8) {
    diff += Math.abs(current[i] - lastMotionFrame[i]);
    if (diff > 2400) break;
  }
  lastMotionFrame.set(current);
  if (diff > 2400) { motionScore = Math.min(99, motionScore + 1); return true; }
  return false;
}

function initDOMElements() {
  video = video || document.getElementById('video');
  canvas = canvas || document.getElementById('canvas');
  camOverlay = camOverlay || document.getElementById('cam-overlay');
  if (!video || !canvas || !camOverlay) { console.error('DOM elements not found.'); return false; }
  return true;
}

function getMedia(constraints) {
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    return navigator.mediaDevices.getUserMedia(constraints);
  }
  const legacy = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia;
  if (legacy) return new Promise((resolve, reject) => legacy.call(navigator, constraints, resolve, reject));
  return Promise.reject(new Error('no_getUserMedia'));
}

function cameraErrorMessage(error) {
  if (!error) return 'Camera access failed. Check browser permissions.';
  const errStr = (error.message || error.name || error.toString()).toLowerCase();
  if (errStr.includes('no_getusermedia') || errStr.includes('getusermedia')) return 'Your browser does not support camera access.';
  if (errStr.includes('notfound')) return 'No camera found. Connect a webcam and refresh.';
  if (errStr.includes('security') || errStr.includes('cross-origin')) return 'Must use HTTPS or http://localhost:5000 for camera access.';
  if (errStr.includes('notallowed') || errStr.includes('permission')) return 'Camera access denied. Click Allow in your browser.';
  return error.message || 'Camera unavailable';
}

async function startCamera() {
  if (!initDOMElements()) { showMsg('cap-msg', 'Page not fully loaded. Please wait and try again.', 'err'); return; }
  try {
    showMsg('cap-msg', 'Requesting camera access...', '');
    let stream_attempt = null;
    try {
      stream_attempt = await getMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: false });
    } catch(e1) {
      stream_attempt = await getMedia({ video: true, audio: false });
    }
    if (!stream_attempt || !stream_attempt.getTracks) throw new Error('No valid stream received');
    const tracks = stream_attempt.getVideoTracks();
    if (tracks.length === 0) throw new Error('No video track in stream');
    stream = stream_attempt;
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    const playPromise = video.play();
    if (playPromise !== undefined) await playPromise.catch(e => console.warn('Play failed:', e.message));
    video.setAttribute('style', 'display:block !important; width:100%; height:100%; object-fit:cover;');
    camOverlay.style.display = 'none';
    showMsg('cap-msg', 'Camera started. Click Start face enrollment to begin.', 'ok');
  } catch(e) {
    const msg = e && e.name === 'NotAllowedError' ? 'Permission denied. Please allow camera access in browser.' : cameraErrorMessage(e);
    showMsg('cap-msg', 'Camera error: ' + msg, 'err');
  }
}

function stopCamera() {
  if (capInterval) { clearInterval(capInterval); capInterval = null; }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  if (video) video.setAttribute('style', 'display:none');
  if (camOverlay) camOverlay.style.display = 'flex';
  const btn = document.getElementById('capture-btn');
  if (btn) { btn.disabled = false; btn.textContent = 'Start face enrollment'; }
}

function startAutoCapture() {
  if (!stream) { showMsg('cap-msg', 'Start the camera first.', 'err'); return; }
  capCount = 0;
  const btn = document.getElementById('capture-btn');
  btn.disabled = true; btn.textContent = 'Capturing...';
  showMsg('cap-msg', 'Keep your face visible and vary your angle slightly.', '');
  capInterval = setInterval(async () => {
    if (capCount >= TARGET) {
      clearInterval(capInterval); capInterval = null;
      btn.disabled = false; btn.textContent = 'Start face enrollment';
      showMsg('cap-msg', 'Enrollment complete! You can now join attendance sessions.', 'ok');
      setTimeout(() => window.location.href = '/student/dashboard', 2000);
      return;
    }
    detectMotion();
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const res = await fetch('/api/student/capture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
      body: JSON.stringify({ image: canvas.toDataURL('image/jpeg', 0.85), motion_score: motionScore })
    });
    const data = await res.json();
    if (data.success) {
      capCount = data.count;
      document.getElementById('prog-fill').style.width = Math.min(100, Math.round(capCount / TARGET * 100)) + '%';
      document.getElementById('count-display').textContent = capCount + ' / ' + TARGET;
    } else {
      clearInterval(capInterval); capInterval = null;
      btn.disabled = false; btn.textContent = 'Start face enrollment';
      showMsg('cap-msg', data.message, 'err');
    }
  }, 400);
}

function showMsg(id, txt, type) {
  const el = document.getElementById(id);
  if (el) { el.textContent = txt; el.className = 'msg ' + type; }
}
