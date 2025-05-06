/* global fetch */
let audioCtx, mediaIn, recorder;
let chunks = [];
let nodes = {};
let currentAudioFile = null;

const armBtn = document.getElementById("armBtn");
const recBtn = document.getElementById("recBtn");
const stopBtn = document.getElementById("stopBtn");
const dlBtn = document.getElementById("downloadBtn");
const status = document.getElementById("status");
const playback = document.getElementById("playback");
const exportFormatSelect = document.getElementById("exportFormat");
const exportBtn = document.getElementById("exportBtn");
const pitchShiftInput = document.getElementById("pitchShift");
const autotuneBtn = document.getElementById("autotuneBtn");

armBtn.onclick = async () => {
  armBtn.disabled = true;
  status.textContent = "Requesting microphone…";

  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaIn = audioCtx.createMediaStreamSource(stream);

  buildGraph(stream);
  status.textContent = "Mic armed. Adjust FX and hit Record!";
  recBtn.disabled = false;
};

function buildGraph(stream) {
  /* core FX nodes */
  nodes.gain = audioCtx.createGain();

  nodes.eqLow = audioCtx.createBiquadFilter();
  nodes.eqLow.type = "lowshelf";

  nodes.eqHigh = audioCtx.createBiquadFilter();
  nodes.eqHigh.type = "highshelf";

  nodes.delay = audioCtx.createDelay(1.0);

  nodes.delayMix = audioCtx.createGain();
  nodes.delayMix.gain.value = 0.3;

  nodes.reverb = audioCtx.createConvolver();
  fetch("static/irs/medium-studio.wav")
    .then(r => r.arrayBuffer())
    .then(buf => audioCtx.decodeAudioData(buf, IR => nodes.reverb.buffer = IR));

  nodes.reverbMix = audioCtx.createGain();

  nodes.comp = audioCtx.createDynamicsCompressor();

  /* wire graph: mediaIn → gain → EQ → comp → destination
     also split to reverb & delay sends */
  const dry = audioCtx.createGain();
  dry.gain.value = 1;

  mediaIn.connect(nodes.gain);
  nodes.gain.connect(nodes.eqLow);
  nodes.eqLow.connect(nodes.eqHigh);
  nodes.eqHigh.connect(nodes.comp);
  nodes.comp.connect(dry).connect(audioCtx.destination);

  // delay send
  nodes.comp.connect(nodes.delay);
  nodes.delay.connect(nodes.delayMix).connect(audioCtx.destination);

  // reverb send
  nodes.comp.connect(nodes.reverb);
  nodes.reverb.connect(nodes.reverbMix).connect(audioCtx.destination);

  /* MediaRecorder for offline saving */
  recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
  recorder.ondataavailable = e => chunks.push(e.data);
  recorder.onstop = handleStop();
}

/* UI bindings */
["gain", "eqLow", "eqHigh", "reverbMix", "delayTime", "compThresh"].forEach(id => {
  document.getElementById(id).addEventListener("input", e => applyParam(id, e.target.value));
});

function applyParam(id, val) {
  switch (id) {
    case "gain":
      nodes.gain.gain.value = parseFloat(val);
      break;
    case "eqLow":
      nodes.eqLow.gain.value = parseFloat(val);
      break;
    case "eqHigh":
      nodes.eqHigh.gain.value = parseFloat(val);
      break;
    case "reverbMix":
      nodes.reverbMix.gain.value = parseFloat(val);
      break;
    case "delayTime":
      nodes.delay.delayTime.value = parseFloat(val) / 1000;
      break;
    case "compThresh":
      nodes.comp.threshold.value = parseFloat(val);
      break;
  }
}

/* Record / Stop */
recBtn.onclick = () => {
  chunks = [];
  recorder.start();
  status.textContent = "Recording…";
  recBtn.disabled = true;
  stopBtn.disabled = false;
};

stopBtn.onclick = () => {
  recorder.stop();
  stopBtn.disabled = true;
};

/* Handle finished take */
function handleStop() {
  return () => {
    const blob = new Blob(chunks, { type: "audio/webm" });
    playback.src = URL.createObjectURL(blob);
    playback.style.display = "block";
    dlBtn.disabled = false;
    exportBtn.disabled = false;
    
    if (document.getElementById("pitchControls")) {
      document.getElementById("pitchControls").style.display = "block";
    }
    
    status.textContent = "Take complete – saving…";

    const fd = new FormData();
    fd.append("audio", blob);
    fetch("/save", { method: "POST", body: fd })
      .then(r => r.json())
      .then(({ filename, filepath }) => {
        status.textContent = `Saved as ${filename}`;
        currentAudioFile = filepath;
      });
  };
}

dlBtn.onclick = () => {
  const a = document.createElement("a");
  a.href = playback.src;
  a.download = "take.webm";
  a.click();
};

// Export functionality - convert webm to WAV or MP3
if (exportBtn) {
  exportBtn.onclick = async () => {
    if (!currentAudioFile) {
      status.textContent = "No recording available to export";
      return;
    }
    
    status.textContent = "Converting audio...";
    
    try {
      const format = exportFormatSelect.value;
      const response = await fetch('/convert-audio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: currentAudioFile, format: format })
      });
      
      const data = await response.json();
      
      if (data.status === 'success') {
        status.textContent = `Converted to ${format.toUpperCase()}: ${data.filename}`;
        
        // Provide download link
        const a = document.createElement("a");
        a.href = `/download?file=${encodeURIComponent(data.file)}`;
        a.download = data.filename;
        a.click();
      } else {
        status.textContent = `Error: ${data.error || 'Conversion failed'}`;
      }
    } catch (error) {
      status.textContent = `Error: ${error.message}`;
      console.error(error);
    }
  };
}

// Pitch shifting / Autotune functionality
if (autotuneBtn) {
  autotuneBtn.onclick = async () => {
    if (!currentAudioFile) {
      status.textContent = "No recording available to process";
      return;
    }
    
    status.textContent = "Applying autotune...";
    
    try {
      // Get value from input
      const pitchAmount = parseFloat(pitchShiftInput.value);
      
      const response = await fetch('/process-pitch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          file: currentAudioFile, 
          amount: pitchAmount,
          correction: true // Enable autotune
        })
      });
      
      const data = await response.json();
      
      if (data.status === 'success') {
        status.textContent = `Applied autotune to ${data.filename}`;
        
        // Update audio player with new processed audio
        playback.src = `/download?file=${encodeURIComponent(data.file)}`;
        
        // Update current file reference
        currentAudioFile = data.file;
      } else {
        status.textContent = `Error: ${data.error || 'Processing failed'}`;
      }
    } catch (error) {
      status.textContent = `Error: ${error.message}`;
      console.error(error);
    }
  };
}

// Pitch shift functionality
if (document.getElementById("pitchShiftBtn")) {
  document.getElementById("pitchShiftBtn").onclick = async () => {
    if (!currentAudioFile) {
      status.textContent = "No recording available to process";
      return;
    }
    
    status.textContent = "Applying pitch shift...";
    
    try {
      // Get value from input
      const pitchAmount = parseFloat(pitchShiftInput.value);
      
      const response = await fetch('/process-pitch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          file: currentAudioFile, 
          amount: pitchAmount,
          correction: false // Regular pitch shift
        })
      });
      
      const data = await response.json();
      
      if (data.status === 'success') {
        status.textContent = `Applied pitch shift to ${data.filename}`;
        
        // Update audio player with new processed audio
        playback.src = `/download?file=${encodeURIComponent(data.file)}`;
        
        // Update current file reference
        currentAudioFile = data.file;
      } else {
        status.textContent = `Error: ${data.error || 'Processing failed'}`;
      }
    } catch (error) {
      status.textContent = `Error: ${error.message}`;
      console.error(error);
    }
  };
}
