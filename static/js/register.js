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
  if (!lastMotionFrame) {
    lastMotionFrame = new Uint8ClampedArray(current);
    return false;
  }
  let diff = 0;
  for (let i = 0; i < current.length; i += 8) {
    diff += Math.abs(current[i] - lastMotionFrame[i]);
    if (diff > 2400) break;
  }
  lastMotionFrame.set(current);
  if (diff > 2400) {
    motionScore = Math.min(99, motionScore + 1);
    return true;
  }
  return false;
}

// Check browser capabilities first
function hasCameraSupport() {
  if (typeof navigator === 'undefined') {
    console.error('Navigator not available');
    return false;
  }
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    return true;
  }
  const hasLegacy = !!(navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia);
  return hasLegacy;
}

// Wait for DOM to be ready
function initDOMElements() {
  video = video || document.getElementById('video');
  canvas = canvas || document.getElementById('canvas');
  camOverlay = camOverlay || document.getElementById('cam-overlay');
  if (!video || !canvas || !camOverlay) {
    console.error('DOM elements not found. Check HTML structure.');
    return false;
  }
  return true;
}

function getMedia(constraints) {
  if (!navigator) {
    return Promise.reject(new Error('navigator unavailable'));
  }
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    return navigator.mediaDevices.getUserMedia(constraints);
  }
  const legacy = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia;
  if (legacy) {
    return new Promise((resolve, reject) => legacy.call(navigator, constraints, resolve, reject));
  }
  return Promise.reject(new Error('no_getUserMedia'));
}

function cameraErrorMessage(error) {
  if (!error) return 'Camera access failed. Check browser permissions.';
  const errStr = (error.message || error.name || error.toString()).toLowerCase();
  if (errStr.includes('no_getusermedia') || errStr.includes('camera api not supported') || errStr.includes('getusermedia')) {
    return 'Your browser does not support camera access. Try Chrome, Edge, Firefox, or Safari.';
  }
  if (errStr.includes('notfound')) return 'No camera found. Connect a webcam and refresh.';
  if (errStr.includes('security') || errStr.includes('cross-origin')) return 'Must use HTTPS or http://localhost:5000 for camera access.';
  if (errStr.includes('notreadable') || errStr.includes('permission')) return 'Camera is in use or access denied. Click Allow in browser.';
  if (errStr.includes('navigator')) return 'Browser not ready. Refresh the page and try again.';
  return error.message || 'Camera unavailable';
}

async function startCamera() {
  if (!initDOMElements()) {
    showMsg('cap-msg', 'Page not fully loaded. Please wait and try again.', 'err');
    return;
  }
  
  try {
    showMsg('cap-msg','Requesting camera access...','');
    console.log('Starting camera...');
    
    let stream_attempt = null;
    
    // Try with ideal constraints first
    try {
      stream_attempt = await getMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false
      });
    } catch(e1) {
      console.warn('Ideal constraints failed, trying basic:', e1.message);
      // Fallback to basic constraint
      stream_attempt = await getMedia({ video: true, audio: false });
    }
    
    if (!stream_attempt || !stream_attempt.getTracks) {
      throw new Error('No valid stream received');
    }
    
    const tracks = stream_attempt.getVideoTracks();
    if (tracks.length === 0) {
      throw new Error('No video track in stream');
    }
    
    stream = stream_attempt;
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    
    // Try to play
    const playPromise = video.play();
    if (playPromise !== undefined) {
      await playPromise.catch(e => {
        console.warn('Play failed (may be OK):', e.message);
      });
    }
    
    video.style.display = 'block';
    camOverlay.style.display = 'none';
    showMsg('cap-msg','✓ Camera started. Click Auto-capture button to begin.','ok');
    console.log('Camera started successfully');
    
  } catch(e) {
    console.error('Camera error details:', {
      name: e.name,
      message: e.message,
      toString: e.toString()
    });
    
    const msg = e && e.name === 'NotAllowedError'
      ? 'Permission denied. Please allow camera access in browser.'
      : cameraErrorMessage(e);
    
    showMsg('cap-msg','Camera error: '+msg,'err');
  }
}

function stopCamera() {
  if (capInterval) { clearInterval(capInterval); capInterval = null; }
  if (stream) { 
    stream.getTracks().forEach(t => {
      t.stop();
    }); 
    stream = null; 
  }
  if (video) {
    video.style.display = 'none';
  }
  if (camOverlay) {
    camOverlay.style.display = 'flex';
  }
  const btn = document.getElementById('capture-btn');
  if (btn) {
    btn.disabled = false;
    btn.textContent = 'Auto-capture (30 samples)';
  }
}

async function registerStudent() {
  const student_id  = document.getElementById('student_id').value.trim();
  const name        = document.getElementById('name').value.trim();
  const department  = document.getElementById('department').value.trim();
  if (!student_id || !name) { showMsg('reg-msg','Student ID and name required.','err'); return; }
  const res  = await fetch('/api/lecturer/student', {
    method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken': getCsrfToken()},
    body: JSON.stringify({student_id, name, department})
  });
  const data = await res.json();
  showMsg('reg-msg', data.message, data.success ? 'ok' : 'err');
  if (data.success) setTimeout(() => location.reload(), 1200);
}

function startAutoCapture() {
  const student_id = document.getElementById('student_id').value.trim();
  if (!student_id) { showMsg('cap-msg','Enter Student ID first.','err'); return; }
  if (!stream)     { showMsg('cap-msg','Start the camera first.','err'); return; }
  capCount = 0;
  const btn = document.getElementById('capture-btn');
  btn.disabled = true; btn.textContent = 'Capturing…';
  showMsg('cap-msg','Keep your face visible. Slight movement helps.','');

  capInterval = setInterval(async () => {
    if (capCount >= TARGET) {
      clearInterval(capInterval); capInterval = null;
      btn.disabled = false; btn.textContent = 'Auto-capture (30 samples)';
      showMsg('cap-msg',`Done! ${TARGET} samples captured. Train the model now.`,'ok');
      return;
    }
    const moved = detectMotion();
    if (moved) {
      showMsg('cap-msg','Motion detected. Capturing sample…','');
    }
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const res  = await fetch('/api/lecturer/capture', {
      method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken': getCsrfToken()},
      body: JSON.stringify({student_id, image: canvas.toDataURL('image/jpeg', 0.85), motion_score: motionScore})
    });
    const data = await res.json();
    if (data.success) {
      capCount = data.count;
      document.getElementById('prog-fill').style.width = Math.min(100, Math.round(capCount/TARGET*100)) + '%';
      document.getElementById('count-display').textContent = capCount + ' / ' + TARGET;
    } else {
      clearInterval(capInterval); capInterval = null;
      btn.disabled = false; btn.textContent = 'Auto-capture (30 samples)';
      showMsg('cap-msg', data.message, 'err');
    }
  }, 400);
}

async function trainModel() {
  const btn = document.getElementById('train-btn');
  btn.disabled = true; btn.textContent = 'Training…';
  showMsg('train-msg','Training LBPH model…','');
  const res  = await fetch('/api/lecturer/train', {method:'POST', headers:{'X-CSRFToken': getCsrfToken()}});
  const data = await res.json();
  showMsg('train-msg', data.message, data.success ? 'ok' : 'err');
  btn.disabled = false; btn.textContent = 'Train LBPH model';
}

function showMsg(id, txt, type) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = txt; 
    el.className = 'msg ' + type;
  }
}
