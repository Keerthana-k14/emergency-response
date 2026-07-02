// app.js - Handles emergency form submission and communicates with backend
console.log('App loaded v4');

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('emergencyForm');
  const statusDiv = document.getElementById('statusMessage');
  const submitBtn = document.getElementById('submitBtn');
  const micBtn = document.getElementById('micBtn');
  const descriptionInput = document.getElementById('description');

  // Voice Input Setup
  let recognition;
  if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    
    recognition.onstart = () => {
      micBtn.classList.add('recording');
    };
    
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      descriptionInput.value = (descriptionInput.value + " " + transcript).trim();
    };
    
    recognition.onerror = (event) => {
      console.error('Speech recognition error', event.error);
      micBtn.classList.remove('recording');
    };
    
    recognition.onend = () => {
      micBtn.classList.remove('recording');
    };
  } else {
    micBtn.style.display = 'none'; // Hide if not supported
  }

  micBtn.addEventListener('click', () => {
    if (recognition) {
      if (micBtn.classList.contains('recording')) {
        recognition.stop();
      } else {
        recognition.start();
      }
    }
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    
    // UI Loading state
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Connecting to AI Dispatch...';
    
    statusDiv.style.display = 'none';
    statusDiv.className = 'status-box';
    
    const data = {
      name: document.getElementById('name').value,
      location: document.getElementById('location').value,
      description: document.getElementById('description').value,
    };
    
    try {
      const response = await fetch('http://localhost:8000/report', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: data.name,
          location: data.location,
          description: data.description,
        }),
      });
      
      if (response.ok) {
        const result = await response.json();
        
        statusDiv.classList.add('success');
        statusDiv.innerHTML = '<h3>✅ AI Triage Initiated</h3><ul id="liveOutputList" class="output-list"></ul>';
        statusDiv.style.display = 'block';
        
        const listEl = document.getElementById('liveOutputList');
        
        // Simulation Engine: Display outputs with delays
        let delay = 500;
        
        if (result.outputs && result.outputs.length > 0) {
          result.outputs.forEach((out, index) => {
            setTimeout(() => {
              const li = document.createElement('li');
              li.className = 'output-item';
              li.innerHTML = out.replace(/\[(.*?)\]/, '<strong>[$1]</strong>');
              listEl.appendChild(li);
              
              // Scroll to bottom of status box
              statusDiv.scrollTop = statusDiv.scrollHeight;
            }, delay);
            delay += 1000; // 1 second between each dispatch
          });
        }
        
        // Render Instructions at the end of the simulation
        if (result.instructions && result.instructions.length > 0) {
          setTimeout(() => {
            const instrDiv = document.createElement('div');
            instrDiv.className = 'instruction-box';
            let instrHtml = '<h4>⚠️ Live Instructions (Follow immediately)</h4><ul class="instruction-list">';
            result.instructions.forEach(inst => {
              instrHtml += `<li>${inst}</li>`;
            });
            instrHtml += '</ul>';
            instrDiv.innerHTML = instrHtml;
            statusDiv.appendChild(instrDiv);
            statusDiv.scrollTop = statusDiv.scrollHeight;
            
            // Reset button state
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Report';
            form.reset();
            
          }, delay + 500);
        } else {
            setTimeout(() => {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit Report';
                form.reset();
            }, delay);
        }
        
      } else {
        const errText = await response.text();
        statusDiv.classList.add('error');
        statusDiv.innerHTML = `<h3>❌ Error</h3><p>Server returned: ${response.status}</p>`;
        statusDiv.style.display = 'block';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit Report';
      }
    } catch (err) {
      statusDiv.classList.add('error');
      statusDiv.innerHTML = `<h3>❌ Network Error</h3><p>Failed to connect to the AI dispatcher.</p>`;
      statusDiv.style.display = 'block';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit Report';
    }
  });
});
