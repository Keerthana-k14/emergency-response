console.log('Command Center Loaded v6');

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('emergencyForm');
  const submitBtn = document.getElementById('submitBtn');
  const logContent = document.getElementById('logContent');
  const instructionsPanel = document.getElementById('instructionsPanel');
  const instructionsList = document.getElementById('instructionsList');
  
  const micBtn = document.getElementById('micBtn');
  const descriptionInput = document.getElementById('description');
  const liveTranscript = document.getElementById('liveTranscript');

  let isRecording = false;
  let recognition;

  // Voice Input Setup
  if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    
    recognition.onstart = () => {
      isRecording = true;
      micBtn.classList.add('recording');
      liveTranscript.innerText = "Listening...";
    };
    
    recognition.onresult = (event) => {
      let interim = '';
      let finalStr = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalStr += event.results[i][0].transcript + ' ';
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      
      // Show interim live
      liveTranscript.innerText = interim || finalStr;
      
      // Append final to text box
      if (finalStr) {
        const currentVal = descriptionInput.value;
        descriptionInput.value = (currentVal + (currentVal ? " " : "") + finalStr).trim();
      }
    };
    
    recognition.onerror = (e) => {
      console.warn('Speech error:', e.error);
      isRecording = false;
      micBtn.classList.remove('recording');
      liveTranscript.innerText = `Error: ${e.error}. Try typing.`;
    };
    
    recognition.onend = () => {
      if (isRecording) {
         // Some browsers auto-stop after silence. Restart if we didn't toggle it off.
         recognition.start();
      } else {
         micBtn.classList.remove('recording');
         liveTranscript.innerText = "";
      }
    };
  } else {
    micBtn.style.display = 'none';
    liveTranscript.innerText = "Speech API not supported in this browser.";
  }

  micBtn.addEventListener('click', () => {
    if (recognition) {
      if (isRecording) {
        isRecording = false;
        recognition.stop();
      } else {
        recognition.start();
      }
    }
  });

  // Helper to add log entries
  function addLog(message, type = 'system') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    const time = new Date().toLocaleTimeString([], { hour12: false });
    entry.innerHTML = `<span class="timestamp">[${time}]</span> ${message}`;
    logContent.appendChild(entry);
    logContent.scrollTop = logContent.scrollHeight;
  }

  // Animation Helpers
  function setNodeState(nodeId, state) {
    const node = document.getElementById(nodeId);
    if (!node) return;
    node.className = `node ${nodeId.replace('node-', '')}-node ${state}`;
  }

  function firePacket(packetId, onComplete) {
    const pkt = document.getElementById(packetId);
    if (!pkt) {
       if(onComplete) onComplete();
       return;
    }
    
    // reset animation
    pkt.classList.remove('animating');
    void pkt.offsetWidth; 
    pkt.classList.add('animating');
    
    setTimeout(() => {
      pkt.classList.remove('animating');
      if (onComplete) onComplete();
    }, 1200);
  }

  function updateConsole(consoleId, dataMap) {
    const card = document.getElementById(consoleId);
    if (!card) return;
    card.classList.add('active');
    
    for (const [cls, val] of Object.entries(dataMap)) {
      const el = card.querySelector(`.${cls}`);
      if (el) {
        el.innerText = val;
        el.classList.remove('flash');
        void el.offsetWidth;
        el.classList.add('flash');
      }
    }
    
    setTimeout(() => card.classList.remove('active'), 2000);
  }

  function resetVisualizer() {
    ['node-user', 'node-coord', 'node-fire', 'node-amb', 'node-pol', 'node-hosp'].forEach(id => setNodeState(id, ''));
    document.querySelectorAll('.console-card').forEach(c => {
      c.classList.remove('active');
      c.querySelectorAll('.val').forEach(v => v.innerText = '--');
    });
    
    instructionsPanel.classList.add('hidden');
    instructionsList.innerHTML = '';
    logContent.innerHTML = '';
    addLog('System initialized. Awaiting SOS payload...', 'system');
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    
    // Stop recording if active before sending
    if (isRecording && recognition) {
        isRecording = false;
        recognition.stop();
    }
    
    resetVisualizer();
    submitBtn.disabled = true;
    submitBtn.querySelector('.btn-text').innerText = 'TRANSMITTING...';
    
    const data = {
      name: document.getElementById('name').value,
      location: document.getElementById('location').value,
      description: document.getElementById('description').value,
    };
    
    addLog(`Uplink established. Transmitting SOS from ${data.name}...`, 'system');
    setNodeState('node-user', 'processing');

    // Fire packet from user to coord
    firePacket('pkt-user-coord', () => {
       setNodeState('node-user', 'success');
       setNodeState('node-coord', 'processing');
       addLog('Coordinator Agent received payload. Analyzing context...', 'coordinator');
    });

    try {
      const response = await fetch('http://localhost:8000/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      
      if (response.ok) {
        const result = await response.json();
        let delay = 2000;
        
        if (result.outputs && result.outputs.length > 0) {
          result.outputs.forEach((out) => {
            setTimeout(() => {
              let agentType = 'system';
              let nodeId = null;
              let packetId = null;
              let consoleId = null;
              let consoleUpdates = {};

              // Match against the exact backend agent output strings
              if (out.includes('[Fire Department]')) { 
                agentType = 'fire'; nodeId = 'node-fire'; packetId = 'pkt-coord-fire'; consoleId = 'console-fire';
                consoleUpdates = { 'status-val': 'DISPATCHED', 'route-val': 'Engine 4 En Route', 'eta-val': 'ETA 4m' };
              }
              else if (out.includes('[Ambulance/EMS]')) { 
                agentType = 'ambulance'; nodeId = 'node-amb'; packetId = 'pkt-coord-amb'; consoleId = 'console-amb';
                consoleUpdates = { 'status-val': 'DISPATCHED', 'route-val': 'Calculated', 'eta-val': 'ETA 5m' };
              }
              else if (out.includes('[Police Department]')) { 
                agentType = 'police'; nodeId = 'node-pol'; packetId = 'pkt-coord-pol'; consoleId = 'console-pol';
                consoleUpdates = { 'status-val': 'DISPATCHED', 'units-val': '2 Patrols Active', 'eta-val': 'ETA 3m' };
              }
              else if (out.includes('[Hospital Coordinator]')) { 
                agentType = 'hospital'; nodeId = 'node-hosp'; packetId = 'pkt-coord-hosp'; consoleId = 'console-hosp';
                consoleUpdates = { 'status-val': 'PREPPING ER', 'patient-val': '1 Trauma Inbound', 'prep-val': 'Level 1 Trauma' };
              }
              
              if (packetId) {
                // Fire packet from Coord to Agent
                firePacket(packetId, () => {
                  if (nodeId) setNodeState(nodeId, 'processing');
                  if (consoleId) updateConsole(consoleId, consoleUpdates);
                  addLog(out.replace(/\[(.*?)\]/, '<strong>[$1]</strong>'), agentType);
                  
                  setTimeout(() => {
                    if (nodeId) setNodeState(nodeId, 'success');
                  }, 1500);
                });
              } else {
                 addLog(out.replace(/\[(.*?)\]/, '<strong>[$1]</strong>'), agentType);
              }
            }, delay);
            delay += 2500; // time between agent processing
          });
        }
        
        // Finish Sequence
        setTimeout(() => {
          setNodeState('node-coord', 'success');
          addLog('Swarm execution complete. Logistics routed.', 'success-msg');
          
          if (result.instructions && result.instructions.length > 0) {
             instructionsPanel.classList.remove('hidden');
             result.instructions.forEach(inst => {
               const li = document.createElement('li');
               li.textContent = inst;
               instructionsList.appendChild(li);
             });
          }
          
          submitBtn.disabled = false;
          submitBtn.querySelector('.btn-text').innerText = 'INITIATE SWARM';
        }, delay + 500);
        
      } else {
        throw new Error(`Server returned: ${response.status}`);
      }
    } catch (err) {
      addLog(`CRITICAL ERROR: ${err.message}`, 'error');
      setNodeState('node-user', '');
      submitBtn.disabled = false;
      submitBtn.querySelector('.btn-text').innerText = 'INITIATE SWARM';
    }
  });
});
