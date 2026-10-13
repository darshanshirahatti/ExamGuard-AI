
(() => {
  "use strict";

  // ExamGuard AI - optimized background proctoring
  // Public functions preserved for compatibility with app.js.
  const CONFIG = {
    faceCheckIntervalMs: 200, // Maximum 5 face checks per second
    missingFaceWarningMs: 5000,
    soundCheckIntervalMs: 500,
    soundThreshold: 0.08,
    soundSustainMs: 2500,
    warningCooldownMs: 10000,
    movementThreshold: 0.055
  };

  let cameraStream = null;
  let microphoneStream = null;
  let screenStream = null;
  let hiddenVideo = null;

  let audioContext = null;
  let analyser = null;
  let audioSource = null;
  let faceLandmarker = null;

  let faceTimer = null;
  let soundTimer = null;

  let permissionGranted = false;
  let examActive = false;
  let initializing = false;
  let cleanupInProgress = false;

  let previousNose = null;
  let lastWarningAt = {};
  let faceMissingSince = null;
  let soundDetectedSince = null;
  let multipleFaceWarningAt = 0;

  // --------------------------------------------------
  // Warning UI
  // --------------------------------------------------

  function warn(type, message) {
    if (!examActive) return;

    const now = Date.now();
    const last = lastWarningAt[type] || 0;

    if (now - last < CONFIG.warningCooldownMs) return;
    lastWarningAt[type] = now;

    document.getElementById("examguard-warning")?.remove();

    const banner = document.createElement("div");
    banner.id = "examguard-warning";
    banner.className = "examguard-warning";
    banner.setAttribute("role", "alert");

    const heading = document.createElement("strong");
    heading.textContent = "Assessment warning";

    const messageNode = document.createElement("span");
    messageNode.textContent = message;

    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "Dismiss";
    close.addEventListener("click", () => banner.remove());

    banner.append(heading, messageNode, close);
    document.body.appendChild(banner);

    window.dispatchEvent(
      new CustomEvent("examguard:warning", {
        detail: {
          type,
          message,
          timestamp: new Date().toISOString()
        }
      })
    );

    console.warn(`[ExamGuard] ${type}: ${message}`);
  }

  // --------------------------------------------------
  // Hidden camera video
  // --------------------------------------------------

  function createHiddenVideo(stream) {
    // Reuse the existing video if it already uses this stream.
    if (hiddenVideo && hiddenVideo.srcObject === stream) {
      return hiddenVideo;
    }

    removeHiddenVideo();

    const video = document.createElement("video");
    video.id = "examguard-hidden-camera";
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.setAttribute("aria-hidden", "true");
    video.tabIndex = -1;

    // Keep the video active for frame processing without showing it.
    // Do not use display:none or visibility:hidden because some browsers
    // may stop or throttle video rendering when it is not rendered.
    Object.assign(video.style, {
      position: "fixed",
      width: "2px",
      height: "2px",
      left: "-20px",
      top: "-20px",
      opacity: "0",
      pointerEvents: "none",
      border: "0",
      zIndex: "-1"
    });

    video.srcObject = stream;
    document.body.appendChild(video);
    hiddenVideo = video;

    return video;
  }

  function removeHiddenVideo() {
    if (!hiddenVideo) return;

    hiddenVideo.pause();
    hiddenVideo.srcObject = null;
    hiddenVideo.remove();
    hiddenVideo = null;
  }

  // --------------------------------------------------
  // Permission and instruction screen
  // --------------------------------------------------

  function openAssessmentGate(onStart) {
    if (examActive || initializing) return;

    if (!navigator.mediaDevices?.getUserMedia) {
      alert(
        "Camera and microphone access require a supported browser and HTTPS or localhost."
      );
      return;
    }

    document.getElementById("examguard-gate")?.remove();

    const gate = document.createElement("div");
    gate.id = "examguard-gate";
    gate.className = "examguard-gate";

    gate.innerHTML = `
      <section class="examguard-card"
               role="dialog"
               aria-modal="true"
               aria-labelledby="examguard-title">

        <div class="examguard-kicker">
          EXAMGUARD AI · PRE-ASSESSMENT
        </div>

        <h2 id="examguard-title">Before you begin</h2>

        <p>
          Read the instructions and approve the permissions required
          for this monitored assessment.
        </p>

        <div class="examguard-rules">
          <div>
            <b>Camera</b>
            <span>
              Checks face presence and noticeable movement.
              The camera preview will remain hidden during the test.
            </span>
          </div>

          <div>
            <b>Microphone</b>
            <span>
              Measures sound levels locally. It does not identify speakers
              or transcribe conversations.
            </span>
          </div>

          <div>
            <b>Screen sharing</b>
            <span>
              Select the screen or window requested by the assessment.
              Stopping sharing may trigger a warning.
            </span>
          </div>

          <div>
            <b>Exam tab</b>
            <span>
              Switching away from or hiding the assessment tab may
              trigger a warning.
            </span>
          </div>
        </div>

        <div class="examguard-privacy">
          <b>Privacy notice</b>
          <p>
            This feature processes face landmarks and microphone levels
            locally. It does not record or upload raw camera, microphone
            or screen content.
          </p>
          <p>
            Browser restrictions prevent reliable detection of every
            background application or website. Warnings can be inaccurate
            and should not be treated as proof of cheating.
          </p>
        </div>

        <label class="examguard-consent">
          <input id="examguard-consent" type="checkbox">
          <span>
            I have read the instructions and agree to the requested
            camera, microphone and screen-sharing checks.
          </span>
        </label>

        <p id="examguard-status"
           class="examguard-status"
           aria-live="polite">
          Permissions have not been granted.
        </p>

        <div class="examguard-actions">
          <button id="examguard-cancel"
                  type="button"
                  class="eg-secondary">
            Cancel
          </button>

          <button id="examguard-permissions"
                  type="button"
                  disabled>
            Grant permissions
          </button>

          <button id="examguard-start"
                  type="button"
                  disabled>
            Start assessment
          </button>
        </div>
      </section>
    `;

    document.body.appendChild(gate);

    const consent = gate.querySelector("#examguard-consent");
    const permissionButton =
      gate.querySelector("#examguard-permissions");
    const startButton = gate.querySelector("#examguard-start");
    const status = gate.querySelector("#examguard-status");

    consent.addEventListener("change", () => {
      permissionButton.disabled = !consent.checked;
      updateStartButton(startButton, consent);
    });

    gate.querySelector("#examguard-cancel").onclick = () => {
      stopAssessmentProctoring();
      gate.remove();
    };

    permissionButton.onclick = async () => {
      if (!consent.checked || initializing) return;

      initializing = true;
      permissionButton.disabled = true;
      status.textContent = "Requesting screen-sharing permission…";

      try {
        if (!navigator.mediaDevices.getDisplayMedia) {
          throw new Error(
            "Screen sharing is unavailable in this browser."
          );
        }

        // Request screen sharing directly from the user click.
        screenStream = await navigator.mediaDevices.getDisplayMedia({
          video: true,
          audio: false
        });

        screenStream.getVideoTracks().forEach(track => {
          track.addEventListener("ended", () => {
            if (examActive) {
              warn(
                "screen-share-stopped",
                "Screen sharing stopped. Resume sharing if required."
              );
            }
          });
        });

        status.textContent = "Requesting camera and microphone…";

        // Request camera once, with modest resolution and frame rate.
        // Reuse this stream for the entire assessment.
        const mediaStream =
          await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: "user",
              width: { ideal: 640 },
              height: { ideal: 480 },
              frameRate: { ideal: 15, max: 20 }
            },
            audio: true
          });

        cameraStream = new MediaStream(
          mediaStream.getVideoTracks()
        );

        microphoneStream = new MediaStream(
          mediaStream.getAudioTracks()
        );

        // Prepare the hidden video and microphone only once.
        createHiddenVideo(cameraStream);

        await hiddenVideo.play();
        await initializeMicrophone();

        status.textContent =
          "Loading face detection. Please wait…";

        await initializeFaceModel();

        permissionGranted = true;
        status.textContent =
          "Ready. Your camera preview will stay hidden during the exam.";
        status.classList.add("eg-success");

        updateStartButton(startButton, consent);
      } catch (error) {
        console.error("ExamGuard permission setup failed:", error);

        stopAssessmentProctoring();

        status.textContent =
          "Setup failed or permission was denied. Allow the requested access and try again.";

        permissionButton.disabled = !consent.checked;
      } finally {
        initializing = false;
      }
    };

    startButton.onclick = () => {
      if (!permissionGranted || !consent.checked || examActive) {
        return;
      }

      // IMPORTANT: Do not request media again here.
      // The existing camera, microphone and model are reused.
      examActive = true;

      gate.remove();

      startTabMonitoring();
      startFaceMonitoring();
      startSoundMonitoring();

      try {
        if (typeof onStart === "function") {
          onStart();
        }
      } catch (error) {
        console.error("Assessment start failed:", error);
        stopAssessmentProctoring();
        alert("The assessment could not be started. Please try again.");
      }
    };
  }

  function updateStartButton(button, consent) {
    button.disabled = !(permissionGranted && consent.checked);
  }

  // --------------------------------------------------
  // Face model: load once, reuse for every frame
  // --------------------------------------------------

  async function initializeFaceModel() {
    const video = hiddenVideo;

    if (!video || !cameraStream) {
      throw new Error("Camera stream is unavailable.");
    }

    // If the model is already loaded, do not recreate it.
    if (faceLandmarker) return;

    const vision = await import(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/+esm"
    );

    const fileset =
      await vision.FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
      );

    faceLandmarker =
      await vision.FaceLandmarker.createFromOptions(fileset, {
        baseOptions: {
          modelAssetPath:
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
        },
        runningMode: "VIDEO",
        numFaces: 2
      });

    if (video.readyState < 2) {
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error("Camera video timed out.")),
          10000
        );

        video.addEventListener(
          "loadeddata",
          () => {
            clearTimeout(timeout);
            resolve();
          },
          { once: true }
        );
      });
    }
  }

  function startFaceMonitoring() {
    if (!examActive || !faceLandmarker || !hiddenVideo) return;

    let busy = false;

    faceTimer = setInterval(() => {
      if (
        !examActive ||
        busy ||
        !faceLandmarker ||
        !hiddenVideo ||
        hiddenVideo.readyState < 2
      ) {
        return;
      }

      busy = true;

      try {
        const result = faceLandmarker.detectForVideo(
          hiddenVideo,
          performance.now()
        );

        inspectFaceResult(result);
      } catch (error) {
        console.warn("Face detection frame failed:", error);
      } finally {
        busy = false;
      }
    }, CONFIG.faceCheckIntervalMs);
  }

  function inspectFaceResult(result) {
    if (!examActive) return;

    const faces = result.faceLandmarks || [];

    if (faces.length === 0) {
      if (faceMissingSince === null) {
        faceMissingSince = Date.now();
      }

      if (
        Date.now() - faceMissingSince >=
        CONFIG.missingFaceWarningMs
      ) {
        warn(
          "face-not-detected",
          "No face was detected for several seconds. Please face the screen."
        );
      }

      previousNose = null;
      return;
    }

    faceMissingSince = null;

    if (faces.length > 1) {
      if (Date.now() - multipleFaceWarningAt > 15000) {
        multipleFaceWarningAt = Date.now();
        warn(
          "multiple-faces",
          "Multiple faces appear in the camera view. Please check your surroundings."
        );
      }
    }

    const nose = faces[0][1];
    if (!nose) return;

    if (previousNose) {
      const dx = nose.x - previousNose.x;
      const dy = nose.y - previousNose.y;
      const distance = Math.hypot(dx, dy);

      if (distance > CONFIG.movementThreshold) {
        warn(
          "face-movement",
          "Noticeable face movement was detected. Please look toward the screen. Normal movement can also trigger this warning."
        );
      }
    }

    previousNose = { x: nose.x, y: nose.y };
  }

  // --------------------------------------------------
  // Microphone: analyze sound levels only
  // --------------------------------------------------

  async function initializeMicrophone() {
    if (!microphoneStream) {
      throw new Error("Microphone stream is unavailable.");
    }

    const AudioContextClass =
      window.AudioContext || window.webkitAudioContext;

    if (!AudioContextClass) {
      throw new Error("Web Audio is not supported by this browser.");
    }

    if (audioContext) return;

    audioContext = new AudioContextClass();

    audioSource =
      audioContext.createMediaStreamSource(microphoneStream);

    analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;

    audioSource.connect(analyser);

    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }
  }

  function startSoundMonitoring() {
    if (!examActive || !analyser) return;

    const samples = new Uint8Array(analyser.fftSize);

    soundTimer = setInterval(() => {
      if (!examActive || !analyser) return;

      analyser.getByteTimeDomainData(samples);

      let sum = 0;

      for (let i = 0; i < samples.length; i++) {
        const normalized = (samples[i] - 128) / 128;
        sum += normalized * normalized;
      }

      const rms = Math.sqrt(sum / samples.length);

      if (rms > CONFIG.soundThreshold) {
        if (soundDetectedSince === null) {
          soundDetectedSince = Date.now();
        }

        if (
          Date.now() - soundDetectedSince >=
          CONFIG.soundSustainMs
        ) {
          warn(
            "microphone-sound",
            "Sustained sound was detected. Please keep the room quiet. This check does not identify speech or its source."
          );

          soundDetectedSince = Date.now();
        }
      } else {
        soundDetectedSince = null;
      }
    }, CONFIG.soundCheckIntervalMs);
  }

  // --------------------------------------------------
  // Tab / window focus warnings
  // --------------------------------------------------

  function onVisibilityChange() {
    if (examActive && document.hidden) {
      warn(
        "tab-hidden",
        "The assessment tab is no longer visible. Return to the exam."
      );
    }
  }

  function onWindowBlur() {
    if (examActive) {
      warn(
        "window-focus",
        "The assessment window lost focus. Please return to the test."
      );
    }
  }

  function startTabMonitoring() {
    document.addEventListener(
      "visibilitychange",
      onVisibilityChange
    );

    window.addEventListener("blur", onWindowBlur);
  }

  // --------------------------------------------------
  // Stop and release resources
  // --------------------------------------------------

  function stopAssessmentProctoring() {
    if (cleanupInProgress) return;
    cleanupInProgress = true;

    examActive = false;
    permissionGranted = false;
    initializing = false;

    if (faceTimer !== null) {
      clearInterval(faceTimer);
      faceTimer = null;
    }

    if (soundTimer !== null) {
      clearInterval(soundTimer);
      soundTimer = null;
    }

    document.removeEventListener(
      "visibilitychange",
      onVisibilityChange
    );

    window.removeEventListener("blur", onWindowBlur);

    [cameraStream, microphoneStream, screenStream].forEach(stream => {
      if (stream) {
        stream.getTracks().forEach(track => {
          try {
            track.stop();
          } catch (_) {}
        });
      }
    });

    removeHiddenVideo();

    if (audioSource) {
      try {
        audioSource.disconnect();
      } catch (_) {}
    }

    if (analyser) {
      try {
        analyser.disconnect();
      } catch (_) {}
    }

    if (audioContext) {
      audioContext.close().catch(() => {});
    }

    if (faceLandmarker) {
      try {
        faceLandmarker.close();
      } catch (_) {}
    }

    document.getElementById("examguard-warning")?.remove();

    cameraStream = null;
    microphoneStream = null;
    screenStream = null;
    audioContext = null;
    audioSource = null;
    analyser = null;
    faceLandmarker = null;

    previousNose = null;
    faceMissingSince = null;
    soundDetectedSince = null;
    multipleFaceWarningAt = 0;
    lastWarningAt = {};

    cleanupInProgress = false;
  }

  // Keep these names compatible with the earlier app.js integration.
  window.openAssessmentGate = openAssessmentGate;
  window.stopAssessmentProctoring = stopAssessmentProctoring;
})();
