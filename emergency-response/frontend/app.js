// app.js - Handles emergency form submission and communicates with backend
console.log('App loaded');

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('emergencyForm');
  const statusDiv = document.getElementById('statusMessage');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    statusDiv.textContent = 'Submitting report...';
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
        statusDiv.textContent = 'Report submitted successfully!';
        console.log('Backend response:', result);
        form.reset();
      } else {
        const errText = await response.text();
        statusDiv.textContent = `Error submitting report: ${response.status}`;
        console.error('Submission error:', errText);
      }
    } catch (err) {
      statusDiv.textContent = 'Network error while submitting report.';
      console.error('Fetch error:', err);
    }
  });
});
