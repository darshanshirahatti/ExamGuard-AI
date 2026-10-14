const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const S = {
    token: localStorage.getItem('eg_token') || '',
    user: null,
    page: 'dashboard',
    analysisSession: null,
    exam: null,
    session: null,
    qi: 0,
    answers: {},
    stream: null,
    micStream: null,
    screenStream: null,
    timer: null,
    left: 0,
    cameraStarting: false,
    permissionGateOpen: false,
    examFocus: false,
    fullscreenWarningShown: false
};
// One persistent, hidden video element lives outside #exam, so question redraws never replace it.
const cameraVideo = document.createElement('video');
cameraVideo.id = 'examguardHiddenCamera';
cameraVideo.autoplay = true;
cameraVideo.playsInline = true;
cameraVideo.muted = true;
cameraVideo.setAttribute('aria-hidden', 'true');
cameraVideo.tabIndex = -1;
Object.assign(cameraVideo.style, {
    position: 'fixed',
    width: '2px',
    height: '2px',
    left: '-10px',
    top: '-10px',
    opacity: '0',
    pointerEvents: 'none',
    zIndex: '-1'
});
document.addEventListener('DOMContentLoaded', () => {
    if (!cameraVideo.isConnected) {
        document.body.appendChild(cameraVideo);
    }
});
if (document.body && !cameraVideo.isConnected) {
    document.body.appendChild(cameraVideo);
}
const api = async (path, opt = {}) => {
    let h = { 'Content-Type': 'application/json', ...(opt.headers || {}) };
    if (S.token) {
        h.Authorization = 'Bearer ' + S.token;
    }
    let r = await fetch(path, { ...opt, headers: h });
    if (!r.ok) {
        let d = {};
        try {
            d = await r.json();
        } catch { }
        throw Error(d.detail || 'Request failed');
    }
    return (r.headers.get('content-type') || '').includes('json') ? r.json() : r;
};

function toast(m, error = false) {
    let t = $('#toast');
    t.textContent = m;
    t.classList.remove('hidden', 'error');
    if (error) {
        t.classList.add('error');
    }
    setTimeout(() => t.classList.add('hidden'), 3500);
}

function esc(s = '') {
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[c]));
}

function initials(s = 'User') {
    return s.split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
}

function date(s) {
    return s ? new Date(s).toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }) : '—';
}

function pill(s) {
    let c = {
        pending: 'amber',
        reviewed: 'green',
        dismissed: '',
        submitted: 'green',
        in_progress: 'blue',
        low: '',
        medium: 'amber',
        high: 'red'
    }[s] || '';
    return `<span class="pill ${c}">${esc(s.replaceAll('_', ' '))}</span>`;
}

async function login(email, password) {
    try {
        let d = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
        S.token = d.token;
        S.user = d.user;
        localStorage.setItem('eg_token', S.token);
        showApp();
        await go('dashboard');
    } catch (e) {
        toast(e.message, true);
    }
}

function openProfileSettings() {
    if (S.user?.role !== 'student') {
        toast('Student profile settings are available only to students.', true);
        return;
    }
    const existing = document.getElementById('profileSettingsModal');
    if (existing) {
        existing.remove();
    }
    const modal = document.createElement('div');
    modal.id = 'profileSettingsModal';
    modal.className = 'profile-modal-overlay';
    modal.innerHTML = `
        <section class="profile-modal" role="dialog"
                 aria-modal="true" aria-labelledby="profileModalTitle">
            <div class="profile-modal-header">
                <div>
                    <h2 id="profileModalTitle">Profile Settings</h2>
                    <p>Manage your student account information.</p>
                </div>
                <button type="button" id="closeProfileModal"
                        class="profile-close" aria-label="Close">×</button>
            </div>

            <form id="profileSettingsForm">
                <label>
                    Full name
                    <input id="profileEditName" required
                           minlength="2" maxlength="100"
                           autocomplete="name">
                </label>

                <label>
                    Email address
                    <input id="profileEditEmail" type="email"
                           required maxlength="254"
                           autocomplete="email">
                </label>

                <label>
                    Current password
                    <input id="profileCurrentPassword" type="password"
                           required autocomplete="current-password">
                </label>

                <div class="profile-modal-actions">
                    <button type="button" id="cancelProfileModal"
                            class="btn outline">Cancel</button>
                    <button type="submit" id="saveProfileModal"
                            class="btn primary">Save changes</button>
                </div>
            </form>
        </section>
    `;
    document.body.appendChild(modal);
    const close = () => modal.remove();
    modal.querySelector('#profileEditName').value = S.user.name || '';
    modal.querySelector('#profileEditEmail').value = S.user.email || '';
    modal.querySelector('#closeProfileModal').onclick = close;
    modal.querySelector('#cancelProfileModal').onclick = close;
    modal.addEventListener('click', event => {
        if (event.target === modal) {
            close();
        }
    });
    modal.querySelector('#profileSettingsForm').onsubmit = async (event) => {
        event.preventDefault();
        const saveButton = modal.querySelector('#saveProfileModal');
        const name = modal.querySelector('#profileEditName').value.trim();
        const email = modal.querySelector('#profileEditEmail').value.trim();
        const currentPassword = modal.querySelector('#profileCurrentPassword').value;
        if (name.length < 2) {
            toast('Name must contain at least 2 characters.', true);
            return;
        }
        saveButton.disabled = true;
        saveButton.textContent = 'Saving...';
        try {
            const result = await api('/api/profile', {
                method: 'PUT',
                body: JSON.stringify({
                    name,
                    email,
                    current_password: currentPassword
                })
            });
            // Support either response format.
            const updatedUser = result.user || result;
            S.user.name = updatedUser.name || name;
            S.user.email = updatedUser.email || email;
            document.getElementById('username').textContent = S.user.name;
            document.getElementById('avatar').textContent =
                initials(S.user.name);
            close();
            toast(result.message || 'Profile updated successfully.');
        } catch (error) {
            toast(error.message || 'Could not update profile.', true);
            saveButton.disabled = false;
            saveButton.textContent = 'Save changes';
        }
    };
}
document.getElementById('profileButton')?.addEventListener('click', openProfileSettings);
$('#loginForm').addEventListener('submit', e => {
    e.preventDefault();
    login($('#email').value, $('#password').value);
});

function authMode(mode) {
    $('#loginForm').classList.toggle('hidden', mode !== 'login');
    $('#registerForm').classList.toggle('hidden', mode !== 'register');
    $('#showLogin').classList.toggle('active', mode === 'login');
    $('#showRegister').classList.toggle('active', mode === 'register');
    $('#authFeedback').classList.add('hidden');
}
$('#showLogin').onclick = () => authMode('login');
$('#showRegister').onclick = () => authMode('register');
$('#registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = $('#regName').value.trim(), email = $('#regEmail').value.trim(), password = $('#regPassword').value, confirm = $('#regConfirm').value;
    if (password !== confirm) {
        toast('Passwords do not match.', true);
        return;
    }
    if (password.length < 8) {
        toast('Use at least 8 characters for the password.', true);
        return;
    }
    try {
        const d = await api('/api/auth/register', { method: 'POST', body: JSON.stringify({ name, email, password }) });
        $('#authFeedback').textContent = d.message + ' Sign in to continue.';
        $('#authFeedback').classList.remove('hidden', 'error');
        $('#loginForm').reset();
        $('#email').value = email;
        authMode('login');
        toast(d.message);
    } catch (err) {
        toast(err.message, true);
    }
});
$('#forgotBtn').onclick = async () => {
    const email = ($('#email').value || $('#regEmail')?.value || '').trim();
    const typed = prompt('Enter the email address for your account:', email);
    if (!typed) {
        return;
    }
    try {
        const d = await api('/api/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email: typed }) });
        let token = d.demo_reset_token;
        if (token) {
            const chosen = prompt('Local demo reset token (no email provider is configured). Copy this token to continue:', token);
            if (!chosen) {
                return;
            }
            const pass = prompt('Enter a new password (minimum 8 characters):');
            if (!pass) {
                return;
            }
            const confirm = prompt('Confirm your new password:');
            if (pass !== confirm) {
                toast('Passwords do not match.', true);
                return;
            }
            await api('/api/auth/reset-password', { method: 'POST', body: JSON.stringify({ token: chosen, password: pass }) });
            toast('Password reset. You can now sign in.');
        } else {
            toast(d.message);
        }
    } catch (err) {
        toast(err.message, true);
    }
};
$$('[data-demo]').forEach(b => b.onclick = () => {
    let a = b.dataset.demo === 'admin';
    $('#email').value = a ? 'admin@examguard.local' : 'student@examguard.local';
    $('#password').value = a ? 'AdminDemo123!' : 'StudentDemo123!';
    login($('#email').value, $('#password').value);
});

function signout() {
    endExamFocus();
    stopAllAssessmentMedia();
    clearInterval(S.timer);
    S.token = '';
    localStorage.removeItem('eg_token');
    $('#appView').classList.add('hidden');
    $('#loginView').classList.remove('hidden');
}
$('#logout').onclick = signout;
$$('[data-page]').forEach(b => b.onclick = () => go(b.dataset.page));

async function go(page) {
    if (S.page === 'exam' && page !== 'exam' && S.stream) {
        stopAllAssessmentMedia();
    }
    if (['students', 'manageExams', 'settings', 'review', 'reports'].includes(page) && S.user?.role !== 'admin') {
        toast('Administrator access required.', true);
        return;
    }
    S.page = page;
    $$('.nav[data-page]').forEach(b => b.classList.toggle('active', b.dataset.page === page));
    $$('.page').forEach(x => x.classList.add('hidden'));
    $('#' + page).classList.remove('hidden');
    const names = {
        dashboard: 'Overview',
        exam: 'Take an exam',
        sessions: 'Session history',
        review: 'Review events',
        reports: 'Reports & analytics',
        students: 'Student management',
        manageExams: 'Exam & question setting',
        settings: 'Admin profile & settings'
    };
    $('#title').textContent = names[page] || 'Overview';
    $('#crumb').textContent = $('#title').textContent;
    try {
        if (page === 'dashboard') {
            await dashboard();
            if (S.user?.role === 'student') {
                await studentProfilePanel();
            }
        }
        if (page === 'exam') {
            await examList();
        }
        if (page === 'sessions') {
            await sessions();
        }
        if (page === 'review') {
            await review();
        }
        if (page === 'reports') {
            await reports();
        }
        if (page === 'students') {
            await studentManagement();
        }
        if (page === 'manageExams') {
            await examManagement();
        }
        if (page === 'settings') {
            await adminSettings();
        }
    } catch (e) {
        $('#' + page).innerHTML = `<div class="panel">Could not load this page: ${esc(e.message)} <button class="btn outline" onclick="go('${page}')">Retry</button></div>`;
    }
}

async function getSessions() {
    return S.user.role === 'admin' ? api('/api/admin/sessions') : api('/api/sessions/mine');
}

async function getEvents() {
    return S.user.role === 'admin' ? api('/api/admin/events') : [];
}

function table(rows, admin) {
    if (!rows.length) {
        return '<p class="muted">No sessions found.</p>';
    }
    return `<div class="table-wrap">
<table>
<thead>
<tr>${admin ? '<th>Student</th>' : ''}<th>Exam</th>
<th>Started</th>
<th>Events</th>
<th>Status</th>${admin ? '<th>Review</th>' : ''}</tr></thead>
<tbody>${rows.map(s => `<tr>${admin ? `<td>${esc(s.student_name)}</td>` : ''}<td>${esc(s.exam_title)} <small>#${s.id}</small></td>
<td>${date(s.started_at)}</td>
<td>${s.event_count || 0}</td>
<td>${pill(s.status)}</td>${admin ? `<td>
<button class="btn outline" onclick="analyzeSession(${s.id})">Score analysis</button></td>` : ''}</tr>`).join('')}</tbody></table></div>`;
}

function eventList(events) {
    return events.length ? events.map(e => `<div class="event"><span class="dot"></span>
<div>
<h4>${esc(e.category.replaceAll('_', ' '))} ${pill(e.severity)}</h4>
<p>${esc(e.description)}</p></div></div>`).join('') : '<p class="muted">No events recorded.</p>';
}

async function dashboard() {
    let [ss, ex, ev] = await Promise.all([getSessions(), api('/api/exams'), getEvents()]);
    $('#pendingCount').textContent = ev.filter(e => e.status === 'pending').length;
    let nums = S.user.role === 'admin' ? [['Total sessions', ss.length], ['In progress', ss.filter(s => s.status === 'in_progress').length], ['Review cues', ev.length], ['Pending review', ev.filter(e => e.status === 'pending').length]] : [['Available exams', ex.length], ['Completed', ss.filter(s => s.status === 'submitted').length], ['In progress', ss.filter(s => s.status === 'in_progress').length], ['Review cues', ev.length]];
    $('#dashboard').innerHTML = `<div class="welcome">
<div>
<h3>${S.user.role === 'admin' ? 'Administrator overview' : 'Welcome back, ' + esc(S.user.name.split(' ')[0]) + ' 👋'}</h3>
<p>${S.user.role === 'admin' ? 'Review session activity and monitoring cues.' : 'Your practice workspace is ready when you are.'}</p></div><span class="pill green">● System operational</span></div>
<div class="stats">${nums.map(n => `<div class="stat"><span class="label">${n[0]}</span><strong>${n[1]}</strong><small>Educational demo data</small></div>`).join('')}</div>
<div class="two-col">
<div class="panel">
<div class="panel-head">
<div>
<h3>${S.user.role === 'admin' ? 'Recent sessions' : 'Recommended practice exam'}</h3>
<p>Session activity and exam access</p></div>
<button class="link" onclick="go('${S.user.role === 'admin' ? 'sessions' : 'exam'}')">View all →</button></div>${S.user.role === 'admin' ? table(ss.slice(0, 5), true) : ex.map(e => `<div class="exam-card">
<div class="exam-icon">▤</div>
<div><span class="pill blue">Practice exam</span>
<h4>${esc(e.title)}</h4>
<p>${esc(e.description)}</p>
<div class="meta">◷ ${e.duration_minutes} minutes · 5 questions</div></div>
<button class="btn primary" onclick="startExam(${e.id})">Start →</button></div>`).join('')}</div>
<div class="panel">
<div class="panel-head">
<div>
<h3>Recent review cues</h3>
<p>Human review only — not proof of cheating</p></div></div>${eventList(ev.slice(0, 5))}</div></div>
<div class="panel">
<div class="panel-head">
<div>
<h3>Recent sessions</h3>
<p>Session history</p></div>
<button class="link" onclick="go('sessions')">View history →</button></div>${table(ss.slice(0, 7), S.user.role === 'admin')}</div>`;
}

async function examList() {
    let ex = await api('/api/exams');
    $('#exam').innerHTML = `<div class="intro">
<div>
<h3>Available exams</h3>
<p>Review instructions before starting. Camera access is optional.</p></div></div>
<div class="privacy-note"><b>Privacy:</b> webcam preview stays in this browser and is not recorded or uploaded. Demo monitoring events are simulated; they are not AI predictions.</div>${ex.map(e => `<div class="exam-card" style="margin-bottom:13px">
<div class="exam-icon">▤</div>
<div><span class="pill blue">Practice assessment</span>
<h4>${esc(e.title)}</h4>
<p>${esc(e.description)}</p>
<div class="meta">◷ ${e.duration_minutes} minutes · 5 questions</div></div>
<button class="btn primary" onclick="startExam(${e.id})">Start exam →</button></div>`).join('')}`;
}

function startExam(id) {
    openAssessmentGate(id);
}

function openAssessmentGate(id) {
    if (S.permissionGateOpen || S.session) {
        return;
    }
    S.permissionGateOpen = true;
    const gate = document.createElement('div');
    gate.id = 'assessmentPermissionGate';
    gate.className = 'permission-overlay';
    gate.innerHTML = `<section class="permission-card" role="dialog" aria-modal="true" aria-labelledby="permissionTitle">
<div class="eyebrow">EXAMGUARD AI · PRE-ASSESSMENT</div>
<h2 id="permissionTitle">Before you begin</h2>
<p class="muted">Read the instructions and grant the required permissions before the timer starts.</p>
<div class="permission-list">
<article><b>1. Camera access</b><span>Used for face-presence and movement checks when supported. The camera preview stays hidden during the exam.</span><em id="permCamera">Not granted</em></article>
<article><b>2. Microphone access</b><span>Measures sound activity locally. It does not identify speakers or transcribe speech.</span><em id="permMic">Not granted</em></article>
<article><b>3. Screen sharing</b><span>Select the screen or window requested. The app can detect when sharing stops, but cannot reliably read other browser tabs or inspect every background website.</span><em id="permScreen">Not granted</em></article></div>
<div class="permission-privacy"><b>Assessment instructions</b>
<ul>
<li>Stay on the assessment tab and follow the invigilator's rules.</li>
<li>Keep your face visible and the room reasonably quiet.</li>
<li>Do not stop screen sharing during the assessment unless instructed.</li>
<li>Warnings can be inaccurate and are review cues, not proof of misconduct.</li></ul>
<p>Raw camera, microphone and screen content are not recorded or uploaded by this demo. Browser permission indicators remain controlled by your browser.</p></div>
<label class="permission-consent">
<input id="permissionConsent" type="checkbox"><span>I have read and understood the instructions and consent to the requested camera, microphone and screen-sharing checks.</span></label>
<p id="permissionStatus" class="permission-status" aria-live="polite">Permissions have not been requested.</p>
<div class="permission-actions">
<button class="btn outline" id="permissionCancel">Cancel</button>
<button class="btn primary" id="permissionGrant" disabled>Grant permissions</button>
<button class="btn primary" id="permissionStart" disabled>Start assessment</button></div></section>`;
    document.body.appendChild(gate);
    const consent = $('#permissionConsent'), grant = $('#permissionGrant'), start = $('#permissionStart'), status = $('#permissionStatus');
    let ready = false;
    consent.onchange = () => {
        grant.disabled = !consent.checked;
        start.disabled = !(consent.checked && ready);
    };
    $('#permissionCancel').onclick = () => {
        releaseAssessmentMedia();
        gate.remove();
        S.permissionGateOpen = false;
    };
    grant.onclick = async () => {
        if (!consent.checked) {
            return;
        }
        grant.disabled = true;
        status.textContent = 'Requesting screen-sharing access…';
        try {
            if (!navigator.mediaDevices?.getDisplayMedia || !navigator.mediaDevices?.getUserMedia) {
                throw Error('Use a supported desktop browser over HTTPS or localhost.');
            }
            // Each capture call is initiated by the user's explicit click.
            S.screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
            $('#permScreen').textContent = 'Granted';
            $('#permScreen').classList.add('granted');
            S.screenStream.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
                if (S.session) {
                    toast('Screen sharing stopped. Resume sharing if required.', true);
                }
            }));
            status.textContent = 'Requesting camera and microphone access…';
            const media = await navigator.mediaDevices.getUserMedia({ video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    frameRate: { ideal: 15, max: 20 },
                    facingMode: 'user'
                }, audio: true });
            S.stream = new MediaStream(media.getVideoTracks());
            S.micStream = new MediaStream(media.getAudioTracks());
            cameraVideo.srcObject = S.stream;
            await cameraVideo.play().catch(() => { });
            $('#permCamera').textContent = 'Granted';
            $('#permCamera').classList.add('granted');
            $('#permMic').textContent = 'Granted';
            $('#permMic').classList.add('granted');
            ready = true;
            status.textContent = 'All requested permissions are ready. The exam timer starts only after you select Start assessment.';
            status.classList.add('success');
            start.disabled = !consent.checked;
        } catch (e) {
            releaseAssessmentMedia();
            ready = false;
            status.textContent = 'Permission setup failed: ' + (e.message || 'Access denied') + '. Please try again and allow the requested access.';
            grant.disabled = !consent.checked;
            start.disabled = true;
        }
    };
    start.onclick = async () => {
        if (!ready || !consent.checked) {
            return;
        }
        // Fullscreen must be requested directly from the user's click. Browsers may still reject it.
        requestExamFullscreen();
        gate.remove();
        S.permissionGateOpen = false;
        await launchExam(id);
    };
}

function releaseAssessmentMedia() {
    [S.stream, S.micStream, S.screenStream].forEach(stream => stream?.getTracks().forEach(track => track.stop()));
    S.stream = null;
    S.micStream = null;
    S.screenStream = null;
    cameraVideo.pause();
    cameraVideo.srcObject = null;
}

async function launchExam(id) {
    try {
        let d = await api('/api/sessions', { method: 'POST', body: JSON.stringify({ exam_id: id }) });
        S.session = d;
        S.exam = d.exam;
        S.qi = 0;
        S.answers = {};
        S.left = S.exam.duration_minutes * 60;
        S.examFocus = true;
        S.fullscreenWarningShown = false;
        document.body.classList.add('exam-focus-mode');
        await go('exam');
        drawQuestion();
        S.timer = setInterval(() => {
            S.left--;
            let t = $('#timer');
            if (t) {
                t.textContent = fmt(S.left);
            }
            if (S.left <= 0) {
                clearInterval(S.timer);
                submitExam(true);
            }
        }, 1000);
    } catch (e) {
        S.examFocus = false;
        document.body.classList.remove('exam-focus-mode');
        releaseAssessmentMedia();
        toast(e.message, true);
    }
}

function requestExamFullscreen() {
    try {
        const el = document.documentElement;
        if (!document.fullscreenElement && el.requestFullscreen) {
            const p = el.requestFullscreen();
            if (p && p.catch) {
                p.catch(() => toast('Fullscreen was not enabled. The focused exam layout will still be used.', true));
            }
        }
    } catch {
        toast('Fullscreen is unavailable in this browser. The focused exam layout will still be used.', true);
    }
}
document.addEventListener('fullscreenchange', () => {
    if (S.session && S.examFocus && !document.fullscreenElement) {
        toast('Fullscreen exited. Please return to fullscreen and continue the assessment.', true);
        recordFullscreenExit();
    }
});

async function recordFullscreenExit() {
    if (!S.session || S.fullscreenWarningShown) {
        return;
    }
    S.fullscreenWarningShown = true;
    try {
        await api(`/api/sessions/${S.session.id}/events`, { method: 'POST', body: JSON.stringify({
                category: 'fullscreen_exit',
                severity: 'medium',
                description: 'The assessment page exited browser fullscreen. This is a review cue only and is not proof of misconduct.',
                source: 'browser'
            }) });
    } catch { }
}

function endExamFocus() {
    S.examFocus = false;
    document.body.classList.remove('exam-focus-mode');
    if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(() => { });
    }
}

function fmt(s) {
    return String(Math.floor(Math.max(0, s) / 60)).padStart(2, '0') + ':' + String(Math.max(0, s) % 60).padStart(2, '0');
}

function drawQuestion() {
    let q = S.exam.questions[S.qi];
    $('#exam').innerHTML = `<div class="focus-exam-top">
<div class="focus-brand"><span class="focus-logo">EG</span>
<div><b>ExamGuard AI</b><small>${esc(S.exam.title)}</small></div></div>
<div class="focus-status"><span class="focus-live-dot"></span> Monitoring active</div>
<div class="focus-timer">TIME REMAINING<strong id="timer">${fmt(S.left)}</strong></div></div>
<div class="focus-question-wrap">
<div class="focus-question-card">
<div class="focus-progress"><span>QUESTION ${S.qi + 1} OF ${S.exam.questions.length}</span><span>${Math.round(((S.qi + 1) / S.exam.questions.length) * 100)}% complete</span></div>
<div class="focus-progress-track"><span style="width:${((S.qi + 1) / S.exam.questions.length) * 100}%"></span></div>
<h1>${esc(q.prompt)}</h1>
<p class="focus-help">Choose one answer, then continue to the next question.</p>
<div class="focus-options">${q.options.map((o, i) => `<label class="option ${S.answers[q.id] === o ? 'selected' : ''}">
<input type="radio" name="ans" ${S.answers[q.id] === o ? 'checked' : ''} value="${esc(o)}"> <span class="option-letter">${String.fromCharCode(65 + i)}</span><span>${esc(o)}</span></label>`).join('')}</div>
<div class="question-actions">
<button class="btn outline" onclick="moveQ(-1)" ${S.qi === 0 ? 'disabled' : ''}>← Previous</button>
<div class="focus-nav-count">Question ${S.qi + 1} of ${S.exam.questions.length}</div>${S.qi === S.exam.questions.length - 1 ? '<button class="btn primary" onclick="submitExam(false)">Submit exam ✓</button>' : '<button class="btn primary" onclick="moveQ(1)">Next question →</button>'}</div>
<div class="qnav">${S.exam.questions.map((x, i) => `<button aria-label="Go to question ${i + 1}" class="${i === S.qi ? 'active' : ''} ${S.answers[x.id] ? 'answered' : ''}" onclick="jumpQ(${i})">${i + 1}</button>`).join('')}</div></div>
<p class="focus-footer-note"><span class="focus-live-dot"></span> Camera, microphone and screen sharing remain active in the background. Do not close this assessment window.</p></div>`;
    $$('input[name="ans"]').forEach(x => x.onchange = e => {
        S.answers[q.id] = e.target.value;
        drawQuestion();
    });
}

function moveQ(d) {
    S.qi = Math.max(0, Math.min(S.exam.questions.length - 1, S.qi + d));
    drawQuestion();
}

function jumpQ(i) {
    S.qi = i;
    drawQuestion();
}

async function startCamera() {
    // Camera was requested in the pre-assessment gate. Never request it again here.
    if (S.stream && S.stream.getVideoTracks().some(t => t.readyState === 'live')) {
        updateCameraControls();
        return;
    }
    toast('Grant camera permission in the pre-assessment screen before starting the exam.', true);
}

function updateCameraControls() {
    const status = $('#camStatus'), start = $('#startCam'), stop = $('#stopCam'), live = !!(S.stream && S.stream.getVideoTracks().some(t => t.readyState === 'live'));
    if (status) {
        status.textContent = live ? 'Active' : 'Off';
        status.className = 'pill' + (live ? ' green' : '');
    }
    if (start) {
        start.disabled = live || S.cameraStarting;
        start.textContent = live ? 'Camera active' : 'Enable camera';
    }
    if (stop) {
        stop.disabled = !live;
    }
}

function stopCamera() {
    if (S.stream) {
        S.stream.getTracks().forEach(t => t.stop());
        S.stream = null;
    }
    cameraVideo.pause();
    cameraVideo.srcObject = null;
    updateCameraControls();
}

function stopAllAssessmentMedia() {
    releaseAssessmentMedia();
    updateCameraControls();
}

async function simulateCue() {
    let a = [['demo_head_movement', 'Simulated looking-away cue. Demo button generated this event; webcam pixels were not analyzed.'], ['demo_face_visibility', 'Simulated face-visibility check. Not a real detector result.'], ['demo_camera_check', 'Simulated camera health check. No video was sent to the server.']][Math.floor(Math.random() * 3)];
    try {
        await api(`/api/sessions/${S.session.id}/events`, { method: 'POST', body: JSON.stringify({
                category: a[0],
                severity: 'low',
                description: a[1],
                source: 'demo'
            }) });
        await renderLiveEvents();
        toast('Simulated review cue recorded.');
    } catch (e) {
        toast(e.message, true);
    }
}

async function renderLiveEvents() {
    if (!$('#liveEvents') || !S.session) {
        return;
    }
    try {
        let ev = await api('/api/admin/events').catch(() => []);
        $('#liveEvents').innerHTML = eventList(ev.filter(e => e.session_id === S.session.id));
    } catch {
        $('#liveEvents').textContent = 'No events';
    }
}

async function submitExam(auto) {
    if (!S.session) {
        return;
    }
    if (!auto && !confirm('Submit your exam now?')) {
        return;
    }
    clearInterval(S.timer);
    endExamFocus();
    stopAllAssessmentMedia();
    let answers = S.exam.questions.map(q => ({ question_id: q.id, answer: S.answers[q.id] || '' })), id = S.session.id;
    try {
        await api(`/api/sessions/${id}/submit`, { method: 'POST', body: JSON.stringify({ answers }) });
        S.session = null;
        S.exam = null;
        S.examFocus = false;
        $('#exam').innerHTML = `<div class="panel" style="text-align:center;padding:40px"><span class="pill green">Submission complete</span>
<h3 style="font-size:25px;margin:15px">Exam submitted successfully</h3>
<p class="muted">Your answers are saved. Monitoring cues are not proof of misconduct.</p>
<button class="btn primary" onclick="go('dashboard')">Back to dashboard →</button> <button class="btn outline" onclick="go('sessions')">Session history</button></div>`;
        toast(auto ? 'Time ended. Exam submitted.' : 'Exam submitted.');
    } catch (e) {
        toast(e.message, true);
    }
}

async function sessions() {
    let ss = await getSessions();
    $('#sessions').innerHTML = `<div class="intro">
<div>
<h3>Session history</h3>
<p>View status and recent exam activity.</p></div></div>
<div class="panel">
<div class="filters">
<input id="searchSession" placeholder="Search exam or student">
<select id="statusFilter">
<option value="">All statuses</option>
<option>submitted</option>
<option>in_progress</option></select></div>
<div id="sessionTable">${table(ss, S.user.role === 'admin')}</div></div>`;
    function filter() {
        let q = $('#searchSession').value.toLowerCase(), st = $('#statusFilter').value;
        $('#sessionTable').innerHTML = table(ss.filter(s => (!st || s.status === st) && (`${s.student_name || S.user.name} ${s.exam_title}`).toLowerCase().includes(q)), S.user.role === 'admin');
    }
    $('#searchSession').oninput = filter;
    $('#statusFilter').onchange = filter;
}

async function review() {
    let ev = await api('/api/admin/events');
    $('#pendingCount').textContent = ev.filter(e => e.status === 'pending').length;
    $('#review').innerHTML = `<div class="intro">
<div>
<h3>Monitoring event review</h3>
<p>Review cues in context. They are not proof of cheating and must not trigger automatic penalties.</p></div></div>
<div class="filters">
<input id="eventSearch" placeholder="Search student or event">
<select id="eventFilter">
<option value="">All statuses</option>
<option>pending</option>
<option>reviewed</option>
<option>dismissed</option></select></div>
<div id="reviewList"></div>`;
    function draw() {
        let q = $('#eventSearch').value.toLowerCase(), st = $('#eventFilter').value;
        let list = ev.filter(e => (!st || e.status === st) && (`${e.student_name} ${e.category} ${e.description}`).toLowerCase().includes(q));
        $('#reviewList').innerHTML = list.length ? list.map(e => `<article class="review-card">
<h4>${esc(e.category.replaceAll('_', ' '))} ${pill(e.severity)}</h4>
<p>${esc(e.description)}</p>
<p class="muted">Student: ${esc(e.student_name)} · Session #${e.session_id} · ${date(e.created_at)} · ${esc(e.source)}</p>
<textarea id="note${e.id}" placeholder="Reviewer note">${esc(e.note || '')}</textarea>
<div class="review-actions"><span>${pill(e.status)}</span>
<div>
<button class="btn outline" onclick="saveReview(${e.id},'dismissed')">Dismiss</button> <button class="btn primary" onclick="saveReview(${e.id},'reviewed')">Mark reviewed</button></div></div></article>`).join('') : '<div class="panel">No events match your filters.</div>';
    }
    $('#eventSearch').oninput = draw;
    $('#eventFilter').onchange = draw;
    draw();
}

async function saveReview(id, status) {
    try {
        await api(`/api/admin/events/${id}`, { method: 'PATCH', body: JSON.stringify({ status, note: $('#note' + id).value }) });
        toast('Review status updated.');
        await review();
    } catch (e) {
        toast(e.message, true);
    }
}

async function reports() {
    let [ss, ev, a, overall] = await Promise.all([api('/api/admin/sessions'), api('/api/admin/events'), api('/api/admin/analytics'), api('/api/admin/score-analysis')]);
    $('#reports').innerHTML = `<div class="intro">
<div>
<h3>Analytics & reports</h3>
<p>Overall score analysis, assessment outcomes, question insights, and monitoring workflow metrics.</p></div>
<button class="btn secondary" id="refreshScoreAnalysis">Refresh analysis</button></div>
<div class="stats">
<div class="stat"><span class="label">Students</span><strong>${a.students}</strong><small>${a.active_students} active</small></div>
<div class="stat"><span class="label">Exams</span><strong>${a.exams}</strong><small>Configured assessments</small></div>
<div class="stat"><span class="label">Sessions</span><strong>${a.sessions}</strong><small>${a.completion_rate}% submitted</small></div>
<div class="stat"><span class="label">Overall average</span><strong>${overall.overall_average_score === null ? 'N/A' : overall.overall_average_score + '%'}</strong><small>${overall.submitted_scored_sessions} scored submissions</small></div></div>
<div class="panel">
<div class="panel-head">
<div>
<h3>Score distribution</h3>
<p>Submitted sessions with configured answer keys</p></div></div>
<div class="stats">${Object.entries(overall.distribution).map(([label, count]) => `<div class="stat"><span class="label">${label}% range</span><strong>${count}</strong><small>submissions</small></div>`).join('')}</div></div>
<div class="panel">
<div class="panel-head">
<div>
<h3>Performance by exam</h3>
<p>Average, highest, and lowest calculated score</p></div></div>
<div class="table-wrap">
<table>
<thead>
<tr>
<th>Exam</th>
<th>Scored submissions</th>
<th>Average</th>
<th>Highest</th>
<th>Lowest</th></tr></thead>
<tbody>${overall.by_exam.map(x => `<tr>
<td>${esc(x.exam_title)}</td>
<td>${x.submitted_scored_sessions}</td>
<td>${x.average_score === null ? 'N/A' : x.average_score + '%'}</td>
<td>${x.highest_score === null ? 'N/A' : x.highest_score + '%'}</td>
<td>${x.lowest_score === null ? 'N/A' : x.lowest_score + '%'}</td></tr>`).join('')}</tbody></table></div></div>
<div class="panel">
<div class="panel-head">
<div>
<h3>Question insights</h3>
<p>Questions with lower correct rates may need review; attempt counts matter.</p></div></div>
<div class="table-wrap">
<table>
<thead>
<tr>
<th>Question</th>
<th>Attempts</th>
<th>Correct</th>
<th>Correct rate</th></tr></thead>
<tbody>${overall.question_insights.map(q => `<tr>
<td style="white-space:normal;min-width:220px">${esc(q.prompt)}</td>
<td>${q.attempts}</td>
<td>${q.correct}</td>
<td>${q.correct_rate === null ? 'No attempts' : q.correct_rate + '%'}</td></tr>`).join('') || '<tr><td colspan="4">No question data available yet.</td></tr>'}</tbody></table></div>
<p class="auth-hint">${esc(overall.disclaimer)}</p></div>
<div class="panel batch-review-panel">
<div class="panel-head">
<div>
<h3>AI Agent · Batch Assessment Score Review</h3>
<p>Review every submitted, scoreable exam in one run. In-progress tests are excluded.</p></div><span class="pill blue">Batch review</span></div>
<div class="button-row">
<button class="btn primary" id="runBatchReview">▶ Review all submitted scores</button>
<button class="btn outline" id="downloadScoreReviewCsv">↓ Download reviewed scores CSV</button>
<button class="btn outline" id="downloadScoreReviewPdf">↓ Download reviewed scores PDF</button></div>
<p class="auth-hint">The agent calculates scores from configured answer keys and generates transparent rule-based feedback. It is not a trained predictive model. Downloads contain submitted exams with a calculable score only.</p>
<div id="batchReviewResults">
<p class="muted">Click “Review all submitted scores” to analyze all eligible submissions together.</p></div></div>
<div class="report-banner">
<div>
<h3>Exam activity report</h3>
<p>Download monitoring event history for academic review.</p></div>
<div class="button-row">
<button class="btn" id="csvBtn">↓ Download CSV</button>
<button class="btn" id="pdfBtn">↓ Download PDF</button></div></div>
<div class="panel">
<div class="panel-head">
<div>
<h3>Online assessment review</h3>
<p>Open a session to inspect answer-key score and recommendations.</p></div></div>${table(ss, true)}<p class="auth-hint">Calculated scores and descriptive analytics are not future-score predictions. Monitoring cues require human review.</p></div>`;
    $('#runBatchReview').onclick = runBatchScoreReview;
    $('#downloadScoreReviewCsv').onclick = () => downloadReport('/api/reports/score-review.csv', 'examguard-submitted-score-review.csv');
    $('#downloadScoreReviewPdf').onclick = () => downloadReport('/api/reports/score-review.pdf', 'examguard-submitted-score-review.pdf');
    $('#csvBtn').onclick = () => downloadReport('/api/reports/events.csv', 'examguard-events.csv');
    $('#pdfBtn').onclick = () => downloadReport('/api/reports/events.pdf', 'examguard-events.pdf');
    $('#refreshScoreAnalysis').onclick = () => reports();
}

async function runBatchScoreReview() {
    const button = $('#runBatchReview'), host = $('#batchReviewResults');
    if (!button || !host) {
        return;
    }
    button.disabled = true;
    button.textContent = 'Reviewing submitted scores…';
    host.innerHTML = '<p class="muted">The review agent is calculating scores and preparing feedback for all submitted exams…</p>';
    try {
        const r = await api('/api/admin/score-analysis/batch-review');
        host.innerHTML = `<div class="stats">
<div class="stat"><span class="label">Reviewed scoreable submissions</span><strong>${r.reviewed_count}</strong><small>Submitted exams only</small></div>
<div class="stat"><span class="label">Average score</span><strong>${r.average_score === null ? 'N/A' : r.average_score + '%'}</strong><small>Across reviewed submissions</small></div>
<div class="stat"><span class="label">No answer key</span><strong>${r.skipped_without_answer_key}</strong><small>Excluded from score exports</small></div>
<div class="stat"><span class="label">In-progress tests</span><strong>0</strong><small>Excluded by design</small></div></div>
<p class="auth-hint">${esc(r.disclaimer)}</p>${r.students.length ? `<div class="table-wrap">
<table>
<thead>
<tr>
<th>Student</th>
<th>Exam</th>
<th>Submitted</th>
<th>Score</th>
<th>Correct</th>
<th>Review outcome</th>
<th>Agent guidance</th></tr></thead>
<tbody>${r.students.map(x => `<tr>
<td><b>${esc(x.student_name)}</b><br><small>${esc(x.student_email)}</small></td>
<td>${esc(x.exam_title)}</td>
<td>${date(x.submitted_at)}</td>
<td><b>${x.score_percent}%</b></td>
<td>${x.correct_answers}/${x.graded_questions}</td>
<td>${esc(x.score_outlook)}</td>
<td>
<details><summary>View feedback</summary><b>Strengths</b>
<ul>${x.strengths.map(v => `<li>${esc(v)}</li>`).join('')}</ul><b>Recommendations</b>
<ul>${x.recommendations.map(v => `<li>${esc(v)}</li>`).join('')}</ul></details></td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">No submitted exams with configured answer keys were available to score.</p>'}`;
        toast(`Batch review complete: ${r.reviewed_count} submitted exam(s) reviewed.`);
    } catch (e) {
        host.innerHTML = `<p class="auth-feedback error">Could not run batch review: ${esc(e.message)}</p>`;
        toast(e.message, true);
    } finally {
        button.disabled = false;
        button.textContent = '▶ Review all submitted scores';
    }
}

async function downloadReport(path, name) {
    try {
        let r = await fetch(path, { headers: { Authorization: 'Bearer ' + S.token } });
        if (!r.ok) {
            throw Error('Download failed');
        }
        const blob = await r.blob(), url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
        toast(name + ' downloaded.');
    } catch (e) {
        toast(e.message, true);
    }
}

async function analyzeSession(id) {
    try {
        const a = await api(`/api/admin/sessions/${id}/analysis`);
        const lines = [`Student: ${a.student_name} (${a.student_email})`, `Exam: ${a.exam_title}`, `Status: ${a.status}`, `Score: ${a.score_percent === null ? 'Not available (no answer key)' : a.score_percent + '%'}`, `Score outlook: ${a.score_outlook}`, `Correct: ${a.correct}/${a.scored_question_count} scored questions`, `Answered: ${a.answered}/${a.question_count}`, `Monitoring review cues: ${a.review_cue_count}`, `High severity cues: ${a.high_severity_cues}`, ``, `Recommendations:`, ...a.recommendations.map(x => '• ' + x), ``, `Model: ${a.model}`, a.disclaimer].join('\n');
        const host = $('#analysisResult') || document.createElement('div');
        host.id = 'analysisResult';
        host.className = 'panel analysis-panel';
        host.innerHTML = `<div class="panel-head">
<div>
<h3>Assessment review · Session #${a.session_id}</h3>
<p>${esc(a.disclaimer)}</p></div>
<button class="btn outline" onclick="$('#analysisResult').remove()">Close</button></div>
<div class="stats">
<div class="stat"><span class="label">Calculated score</span><strong>${a.score_percent === null ? 'N/A' : a.score_percent + '%'}</strong></div>
<div class="stat"><span class="label">Correct answers</span><strong>${a.correct}/${a.scored_question_count}</strong></div>
<div class="stat"><span class="label">Score outlook</span><strong style="font-size:15px">${esc(a.score_outlook)}</strong></div>
<div class="stat"><span class="label">Review cues</span><strong>${a.review_cue_count}</strong></div></div>
<h4>Guidance</h4>
<ul>${a.recommendations.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
<p class="auth-hint">Transparent rule-based baseline; not a trained AI prediction. Monitoring cues must be interpreted by a human and never automatically determine misconduct.</p>
<button class="btn outline" id="copyAnalysis">Copy analysis</button>`;
        if (!host.isConnected) {
            $('#sessions').prepend(host);
        }
        $('#copyAnalysis').onclick = () => navigator.clipboard?.writeText(lines).then(() => toast('Analysis copied.')).catch(() => toast('Clipboard unavailable.', true));
        host.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {
        toast(e.message, true);
    }
}

async function studentManagement() {
    const students = await api('/api/admin/students');
    $('#students').innerHTML = `<div class="intro">
<div>
<h3>Student management</h3>
<p>Review student accounts and control access. Public registration only creates student accounts.</p></div><span class="pill blue">${students.length} students</span></div>
<div class="panel">
<div class="filters">
<input id="studentSearch" placeholder="Search name or email">
<select id="studentStatus">
<option value="">All accounts</option>
<option value="1">Active</option>
<option value="0">Inactive</option></select></div>
<div id="studentRows"></div></div>`;
    function draw() {
        const q = $('#studentSearch').value.toLowerCase(), st = $('#studentStatus').value;
        const rows = students.filter(s => (!st || String(s.is_active) === st) && (`${s.name} ${s.email}`).toLowerCase().includes(q));
        $('#studentRows').innerHTML = rows.length ? `<div class="table-wrap">
<table>
<thead>
<tr>
<th>Name</th>
<th>Email</th>
<th>Joined</th>
<th>Status</th>
<th>Action</th></tr></thead>
<tbody>${rows.map(s => `<tr>
<td>${esc(s.name)}</td>
<td>${esc(s.email)}</td>
<td>${date(s.created_at)}</td>
<td>${s.is_active ? pill('active') : pill('inactive')}</td>
<td>
<button class="btn ${s.is_active ? 'outline' : 'primary'}" onclick="toggleStudent(${s.id},${!s.is_active})">${s.is_active ? 'Deactivate' : 'Activate'}</button></td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">No students match the filter.</p>';
    }
    $('#studentSearch').oninput = draw;
    $('#studentStatus').onchange = draw;
    draw();
}

async function toggleStudent(id, active) {
    try {
        await api(`/api/admin/students/${id}/status`, { method: 'PATCH', body: JSON.stringify({ is_active: active }) });
        toast(active ? 'Student activated.' : 'Student deactivated; active tokens revoked.');
        await studentManagement();
    } catch (e) {
        toast(e.message, true);
    }
}

async function examManagement() {
    const exams = await api('/api/exams');
    $('#manageExams').innerHTML = `<div class="intro">
<div>
<h3>Exam & question setting</h3>
<p>Create assessments and maintain answer keys used for score calculation.</p></div></div>
<div class="panel">
<h3>Create exam</h3>
<form id="newExamForm" class="form-grid">
<label>Exam title
<input id="newExamTitle" required minlength="3" maxlength="160"></label>
<label>Duration (minutes)
<input id="newExamDuration" type="number" min="1" max="360" value="30" required></label>
<label class="wide">Description
<textarea id="newExamDescription" rows="2"></textarea></label>
<button class="btn primary">Create exam</button></form></div>
<div class="panel">
<div class="panel-head">
<div>
<h3>Question bank</h3>
<p>Select an exam to add, edit, or remove MCQs.</p></div>
<select id="questionExam">${exams.map(e => `<option value="${e.id}">${esc(e.title)}</option>`).join('')}</select></div>
<div id="questionManager"></div></div>
<div class="panel">
<h3>Existing exams</h3>${exams.map(e => `
  <div class="exam-card">
    <div class="exam-icon">▤</div>

    <div>
      <h4>${esc(e.title)}</h4>
      <p>${esc(e.description)}</p>
      <div class="meta">
        ${e.duration_minutes} minutes
      </div>
    </div>

    <div class="button-row">
      <button class="btn primary"
        onclick="shareExam(${e.id})">
        Share Assessment
      </button>

      <button class="btn outline"
        onclick="editExam(
          ${e.id},
          decodeURIComponent('${encodeURIComponent(e.title)}'),
          decodeURIComponent('${encodeURIComponent(e.description)}'),
          ${e.duration_minutes}
        )">
        Edit details
      </button>

      <button class="btn outline"
        onclick="deleteExam(${e.id})">
        Delete
      </button>
    </div>
  </div>
`).join('')}</div>`;
    $('#newExamForm').onsubmit = async (e) => {
        e.preventDefault();
        try {
            await api('/api/admin/exams', { method: 'POST', body: JSON.stringify({ title: $('#newExamTitle').value, description: $('#newExamDescription').value, duration_minutes: Number($('#newExamDuration').value) }) });
            toast('Exam created. Add questions below.');
            await examManagement();
        } catch (err) {
            toast(err.message, true);
        }
    };
    $('#questionExam').onchange = loadQuestionManager;
    await loadQuestionManager();
}

async function editExam(id, title, description, duration) {
    const nt = prompt('Exam title:', title);
    if (nt === null) {
        return;
    }
    const nd = prompt('Description:', description);
    if (nd === null) {
        return;
    }
    const du = Number(prompt('Duration in minutes:', duration));
    if (!Number.isInteger(du) || du < 1 || du > 360) {
        toast('Duration must be 1–360 minutes.', true);
        return;
    }
    try {
        await api(`/api/admin/exams/${id}`, { method: 'PUT', body: JSON.stringify({ title: nt, description: nd, duration_minutes: du }) });
        toast('Exam updated.');
        await examManagement();
    } catch (e) {
        toast(e.message, true);
    }
}

async function deleteExam(id) {
    if (!confirm('Delete this exam? Exams with existing session history cannot be deleted.')) {
        return;
    }
    try {
        await api(`/api/admin/exams/${id}`, { method: 'DELETE' });
        toast('Exam deleted.');
        await examManagement();
    } catch (e) {
        toast(e.message, true);
    }
}

async function shareExam(id) {
    try {
        const data = await api(`/api/admin/exams/${id}/share-link`);
        const url = data.share_url;
        const message = data.message + "\n\n" + url;
        const whatsapp = "https://wa.me/?text=" +
            encodeURIComponent(message);
        const telegram = "https://t.me/share/url?url=" +
            encodeURIComponent(url) +
            "&text=" +
            encodeURIComponent(data.message);
        const gmail = "https://mail.google.com/mail/?view=cm&fs=1" +
            "&su=" +
            encodeURIComponent("Assessment invitation: " + data.title) +
            "&body=" +
            encodeURIComponent(message);
        document.getElementById("assessmentShareModal")?.remove();
        const modal = document.createElement("div");
        modal.id = "assessmentShareModal";
        Object.assign(modal.style, {
            position: "fixed",
            inset: "0",
            zIndex: "10000",
            background: "rgba(15,23,42,.65)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px"
        });
        modal.innerHTML = `
      <section style="
        width:100%;
        max-width:560px;
        background:white;
        color:#172033;
        padding:26px;
        border-radius:16px;
        box-shadow:0 20px 60px rgba(0,0,0,.2)"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shareAssessmentTitle">

        <div style="
          display:flex;
          justify-content:space-between;
          gap:12px;
          align-items:center">

          <div>
            <h2 id="shareAssessmentTitle"
                style="margin:0 0 6px">
              Share Assessment
            </h2>
            <p style="margin:0;color:#64748b">
              ${esc(data.title)}
            </p>
          </div>

          <button type="button" id="closeAssessmentShare"
            class="btn outline">Close</button>
        </div>

        <label style="display:block;margin-top:22px">
          Assessment link
          <input id="assessmentShareUrl"
            readonly
            value="${esc(url)}"
            style="
              display:block;
              width:100%;
              box-sizing:border-box;
              margin-top:8px;
              padding:12px;
              border:1px solid #cbd5e1;
              border-radius:8px">
        </label>

        <div class="button-row" style="margin-top:14px">
          <button type="button"
            class="btn primary"
            id="copyAssessmentLink">
            Copy link
          </button>

          <a class="btn outline"
            href="${esc(whatsapp)}"
            target="_blank" rel="noopener noreferrer">
            WhatsApp
          </a>

          <a class="btn outline"
            href="${esc(gmail)}"
            target="_blank" rel="noopener noreferrer">
            Gmail
          </a>

          <a class="btn outline"
            href="${esc(telegram)}"
            target="_blank" rel="noopener noreferrer">
            Telegram
          </a>
        </div>

        <p style="color:#64748b;font-size:13px;margin-top:16px">
          Students must sign in before starting the assessment.
          Review the invitation before sending it.
        </p>
      </section>
    `;
        document.body.appendChild(modal);
        document.getElementById("closeAssessmentShare").onclick =
            () => modal.remove();
        modal.addEventListener("click", event => {
            if (event.target === modal) {
                modal.remove();
            }
        });
        document.getElementById("copyAssessmentLink").onclick =
            async () => {
                try {
                    await navigator.clipboard.writeText(url);
                    toast("Assessment link copied.");
                } catch {
                    const input = document.getElementById("assessmentShareUrl");
                    input.focus();
                    input.select();
                    const copied = document.execCommand("copy");
                    toast(copied ? "Assessment link copied." :
                        "Select and copy the assessment link.", !copied);
                }
            };
    } catch (error) {
        toast(error.message, true);
    }
}

async function loadQuestionManager() {
    const examId = Number($('#questionExam')?.value);
    if (!examId) {
        return;
    }
    const qs = await api(`/api/admin/exams/${examId}/questions`);
    $('#questionManager').innerHTML = `<div class="analysis-panel panel">
<div class="panel-head">
<div>
<h3>Question Authoring Agent</h3>
<p>Generate editable MCQ drafts by topic. Review them before adding to the live question bank.</p></div><span class="pill blue">AI-assisted draft</span></div>
<form id="agentQuestionForm" class="form-grid">
<label>Topic or syllabus unit
<input id="agentTopic" required minlength="2" maxlength="160" placeholder="e.g. Supervised Learning, SQL, Cybersecurity"></label>
<label>Difficulty
<select id="agentDifficulty">
<option value="easy">Easy</option>
<option value="medium" selected>Medium</option>
<option value="hard">Hard</option></select></label>
<label>Number of drafts
<select id="agentCount">
<option>3</option>
<option selected>5</option>
<option>8</option>
<option>10</option></select></label>
<button class="btn secondary">Generate drafts</button></form>
<div id="agentDrafts"></div>
<p class="auth-hint">Drafts are generated by the configured backend agent. Verify the question, options, and answer key before saving.</p></div>
<form id="questionForm" class="form-grid">
<input id="editingQuestionId" type="hidden">
<label class="wide">Question prompt
<textarea id="questionPrompt" required minlength="5" rows="2"></textarea></label>
<label>Option A
<input id="optionA" required></label>
<label>Option B
<input id="optionB" required></label>
<label>Option C
<input id="optionC"></label>
<label>Option D
<input id="optionD"></label>
<label>Correct answer
<select id="correctAnswer" required></select></label>
<label>Position
<input id="questionPosition" type="number" min="1" value="1" required></label>
<div class="button-row wide">
<button class="btn primary">Save question</button>
<button type="button" class="btn outline" id="clearQuestion">Clear</button></div></form>
<div class="question-bank-list">${qs.map(q => `<article class="question-bank-item">
<div><b>${q.position}. ${esc(q.prompt)}</b>
<p>${q.options.map((o, i) => `${String.fromCharCode(65 + i)}. ${esc(o)}`).join(' · ')}</p><small>Correct answer: ${esc(q.correct_answer || 'Not configured')}</small></div>
<div class="button-row">
<button class="btn outline" onclick="fillQuestion(${q.id})">Edit</button>
<button class="btn outline" onclick="removeQuestion(${q.id})">Delete</button></div></article>`).join('') || '<p class="muted">No questions yet. Add the first question above.</p>'}</div>`;
    const updateCorrect = () => {
        const opts = ['#optionA', '#optionB', '#optionC', '#optionD'].map(x => $(x).value.trim()).filter(Boolean), sel = $('#correctAnswer'), old = sel.value;
        sel.innerHTML = opts.map(o => `<option>${esc(o)}</option>`).join('');
        if (opts.includes(old)) {
            sel.value = old;
        }
    };
    ['#optionA', '#optionB', '#optionC', '#optionD'].forEach(x => $(x).oninput = updateCorrect);
    $('#questionForm').onsubmit = async (e) => {
        e.preventDefault();
        const id = $('#editingQuestionId').value, options = ['#optionA', '#optionB', '#optionC', '#optionD'].map(x => $(x).value.trim()).filter(Boolean);
        try {
            const payload = {
                prompt: $('#questionPrompt').value,
                options,
                correct_answer: $('#correctAnswer').value,
                position: Number($('#questionPosition').value)
            };
            await api(id ? `/api/admin/questions/${id}` : `/api/admin/exams/${examId}/questions`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
            toast('Question saved.');
            await loadQuestionManager();
        } catch (err) {
            toast(err.message, true);
        }
    };
    $('#agentQuestionForm').onsubmit = async (e) => {
        e.preventDefault();
        const box = $('#agentDrafts');
        box.innerHTML = '<p class="muted">Preparing editable drafts…</p>';
        try {
            const result = await api('/api/admin/agents/question-drafts', { method: 'POST', body: JSON.stringify({ topic: $('#agentTopic').value, difficulty: $('#agentDifficulty').value, count: Number($('#agentCount').value) }) });
            box.innerHTML = `<div class="question-bank-list">
<p class="auth-hint">${esc(result.disclaimer)}</p>${result.drafts.map((d, i) => `<article class="question-bank-item">
<div><b>${i + 1}. ${esc(d.prompt)}</b>
<p>${d.options.map((o, j) => `${String.fromCharCode(65 + j)}. ${esc(o)}`).join(' · ')}</p><small>Suggested answer: ${esc(d.correct_answer)} · ${esc(d.difficulty)}</small>
<p class="auth-hint">${esc(d.rationale)}</p></div>
<button type="button" class="btn outline" data-agent-draft="${i}">Edit in question form</button></article>`).join('')}</div>`;
            box.querySelectorAll('[data-agent-draft]').forEach(btn => btn.onclick = () => {
                const d = result.drafts[Number(btn.dataset.agentDraft)];
                $('#editingQuestionId').value = '';
                $('#questionPrompt').value = d.prompt;
                ['#optionA', '#optionB', '#optionC', '#optionD'].forEach((sel, i) => $(sel).value = d.options[i] || '');
                $('#questionPosition').value = String(qs.length + 1);
                ['#optionA', '#optionB', '#optionC', '#optionD'].forEach(sel => $(sel).dispatchEvent(new Event('input')));
                $('#correctAnswer').value = d.correct_answer;
                $('#questionForm').scrollIntoView({ behavior: 'smooth', block: 'center' });
                toast('Draft copied to the editable form. Review and save it.');
            });
        } catch (err) {
            box.innerHTML = `<p class="auth-feedback error">${esc(err.message)}</p>`;
        }
    };
    $('#clearQuestion').onclick = () => loadQuestionManager();
}

async function fillQuestion(id) {
    const examId = Number($('#questionExam').value), q = (await api(`/api/admin/exams/${examId}/questions`)).find(x => x.id === id);
    if (!q) {
        return;
    }
    $('#editingQuestionId').value = q.id;
    $('#questionPrompt').value = q.prompt;
    ['#optionA', '#optionB', '#optionC', '#optionD'].forEach((x, i) => $(x).value = q.options[i] || '');
    $('#questionPosition').value = q.position;
    ['#optionA', '#optionB', '#optionC', '#optionD'].forEach(x => $(x).dispatchEvent(new Event('input')));
    $('#correctAnswer').value = q.correct_answer;
    $('#questionForm').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

async function removeQuestion(id) {
    if (!confirm('Delete this question? Existing session history remains, but scoring for this question will no longer be available.')) {
        return;
    }
    try {
        await api(`/api/admin/questions/${id}`, { method: 'DELETE' });
        toast('Question deleted.');
        await loadQuestionManager();
    } catch (e) {
        toast(e.message, true);
    }
}

async function adminSettings() {
    const p = await api('/api/admin/profile');
    $('#settings').innerHTML = `<div class="intro">
<div>
<h3>Administrator account settings</h3>
<p>Change your admin login email/ID and password securely.</p></div><span class="pill blue">Admin only</span></div>
<div class="panel account-settings-panel">
<div class="panel-head">
<div>
<h3>Account credentials</h3>
<p>Verify your current password before saving any changes.</p></div></div>
<form id="adminProfileForm" class="form-grid">
<label>Display name
<input id="adminName" value="${esc(p.name)}" required minlength="2" maxlength="100" autocomplete="name"></label>
<label>Admin email / login ID
<input id="adminEmail" type="email" value="${esc(p.email)}" required maxlength="254" autocomplete="username"></label>
<label class="wide">Current password
<input id="adminCurrentPassword" type="password" required autocomplete="current-password" placeholder="Enter current password"></label>
<div class="settings-divider wide"><b>Change password</b><small>Leave both new password fields blank if you only want to change your email or display name.</small></div>
<label>New password
<input id="adminNewPassword" type="password" minlength="8" maxlength="128" autocomplete="new-password" placeholder="At least 8 characters"></label>
<label>Confirm new password
<input id="adminConfirmPassword" type="password" minlength="8" maxlength="128" autocomplete="new-password" placeholder="Re-enter new password"></label>
<div class="button-row wide">
<button id="saveAdminProfile" class="btn primary" type="submit">Save changes</button>
<button class="btn outline" type="button" id="cancelAdminProfile">Reset form</button></div></form>
<div class="privacy-note"><b>Security note:</b> Changing the login email or password signs out active sessions for this administrator. Sign in again using the updated credentials. Public registration remains student-only.</div></div>`;
    $('#cancelAdminProfile').onclick = () => adminSettings();
    $('#adminProfileForm').onsubmit = async (e) => {
        e.preventDefault();
        const current = $('#adminCurrentPassword').value, newPassword = $('#adminNewPassword').value, confirmPassword = $('#adminConfirmPassword').value;
        if (newPassword !== confirmPassword) {
            toast('New password and confirmation do not match.', true);
            return;
        }
        if (newPassword && newPassword.length < 8) {
            toast('New password must contain at least 8 characters.', true);
            return;
        }
        const save = $('#saveAdminProfile');
        save.disabled = true;
        save.textContent = 'Saving…';
        try {
            const result = await api('/api/admin/profile', { method: 'PUT', body: JSON.stringify({
                    name: $('#adminName').value.trim(),
                    email: $('#adminEmail').value.trim(),
                    current_password: current,
                    new_password: newPassword || null
                }) });
            if (result.reauth_required) {
                S.user = result.user;
                signout();
                toast(result.message);
                return;
            }
            S.user.name = result.user.name;
            S.user.email = result.user.email;
            $('#username').textContent = S.user.name;
            $('#avatar').textContent = initials(S.user.name);
            toast(result.message);
            await adminSettings();
        } catch (err) {
            toast(err.message, true);
        } finally {
            if ($('#saveAdminProfile')) {
                save.disabled = false;
                save.textContent = 'Save changes';
            }
        }
    };
}

async function boot() {
    if (!S.token) {
        return;
    }
    try {
        S.user = await api('/api/me');
        showApp();
        await go('dashboard');
    } catch {
        localStorage.removeItem('eg_token');
        S.token = '';
    }
}
boot();

function showApp() {
    $('#loginView').classList.add('hidden');
    $('#appView').classList.remove('hidden');
    $('#username').textContent = S.user.name;
    $('#role').textContent = S.user.role + ' workspace';
    $('#avatar').textContent = initials(S.user.name);
    $$('.admin-only').forEach(x => x.classList.toggle('hidden', S.user.role !== 'admin'));
    $$('.student-only').forEach(x => x.classList.toggle('hidden', S.user.role !== 'student'));
    const params = new URLSearchParams(window.location.search);
    const sharedExamId = Number(params.get('assessment'));
    if (S.user.role === 'student' &&
        Number.isInteger(sharedExamId) &&
        sharedExamId > 0 &&
        !window.__egSharedAssessmentHandled) {
        window.__egSharedAssessmentHandled = true;
        setTimeout(() => {
            startExam(sharedExamId);
        }, 350);
    }
}

async function studentProfilePanel() {
    const p = await api('/api/me');
    $('#dashboard').insertAdjacentHTML('beforeend', `
        <div class="panel" id="studentProfilePanel">
            <div class="panel-head">
                <div>
                    <h3>My Profile</h3>
                    <p>Update your student account information.</p>
                </div>
                <span class="pill blue">Student</span>
            </div>

            <form id="studentProfileForm" class="form-grid">
                <label>
                    Full name
                    <input id="studentProfileName"
                        value="${esc(p.name)}"
                        required minlength="2" maxlength="100"
                        autocomplete="name">
                </label>

                <label>
                    Email address
                    <input id="studentProfileEmail" type="email"
                        value="${esc(p.email)}"
                        required maxlength="254"
                        autocomplete="email">
                </label>

                <label class="wide">
                    Current password
                    <input id="studentProfilePassword" type="password"
                        required autocomplete="current-password"
                        placeholder="Verify your identity">
                </label>

                <div class="button-row wide">
                    <button id="saveStudentProfile"
                        class="btn primary" type="submit">
                        Save changes
                    </button>
                    <button class="btn outline" type="reset">
                        Reset form
                    </button>
                </div>
            </form>
        </div>
    `);
    $('#studentProfileForm').onsubmit = async (e) => {
        e.preventDefault();
        const button = $('#saveStudentProfile');
        button.disabled = true;
        button.textContent = 'Saving...';
        try {
            const result = await api('/api/profile', {
                method: 'PUT',
                body: JSON.stringify({
                    name: $('#studentProfileName').value.trim(),
                    email: $('#studentProfileEmail').value.trim(),
                    current_password: $('#studentProfilePassword').value
                })
            });
            S.user = result.user;
            $('#username').textContent = S.user.name;
            $('#avatar').textContent = initials(S.user.name);
            $('#studentProfilePassword').value = '';
            toast(result.message);
            await dashboard();
            await studentProfilePanel();
        } catch (err) {
            toast(err.message, true);
        } finally {
            if ($('#saveStudentProfile')) {
                button.disabled = false;
                button.textContent = 'Save changes';
            }
        }
    };
}