

document.getElementById('youtubeForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const youtubeUrl = document.getElementById('youtubeUrl').value;
    const submitButton = document.querySelector('#youtubeForm button[type="submit"]');
    submitButton.disabled = true; // Disable the button
    submitButton.textContent = 'Processing...'; // Optional: Change button text
    removeVocals(youtubeUrl);
});

// Add this function to handle button clicks when disabled
document.querySelector('#youtubeForm button[type="submit"]').addEventListener('click', function(e) {
    if (this.disabled) {
        alert('Please wait until the current process has finished.');
    }
});

function enableSubmitButton() {
    const submitButton = document.querySelector('#youtubeForm button[type="submit"]');
    submitButton.disabled = false; // Enable the button
    submitButton.textContent = 'Remove Vocals'; // Reset button text
}

function removeVocals(youtubeUrl) {
    document.getElementById('downloadLink').innerHTML = ''; // Clear any existing download link
    document.getElementById('status').textContent = ''; // Clear any previous status messages
    document.getElementById('status').classList.remove('error', 'success'); // Clear any previous status classes
    const startTime = Date.now(); // Store the start time
    fetch('/remove-vocals', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({youtube_url: youtubeUrl}),
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            document.getElementById('status').textContent = `Error: ${data.error}`;
            document.getElementById('status').classList.add('error'); // Add error class
            enableSubmitButton(); // Re-enable the button in case of error
            return; // Exit the function to prevent further execution
        }

        const requestId = data.request_id;

        checkStatus(requestId, startTime); // Pass the startTime to checkStatus
    })
    .catch((error) => {
        console.error('Error:', error);
        document.getElementById('status').textContent = 'Error: Unable to process the request.';
        document.getElementById('status').classList.add('error'); // Add error class
        enableSubmitButton(); // Re-enable the button in case of error
    });
}

function checkStatus(requestId, startTime) {
    fetch(`/check-status/${requestId}`)
    .then(response => response.json())
    .then(data => {
        const elapsedTime = ((Date.now() - startTime) / 1000).toFixed(2); // Calculate elapsed time in seconds
        if (data.status === 'success' || data.status === 'error') {
            enableSubmitButton(); // Re-enable the button when process is finished
            if (data.status === 'success') {
                document.getElementById('status').classList.remove('error'); 
                document.getElementById('status').classList.add('success');

                const filename = data.filename;
                document.getElementById('status').textContent = `Processing complete. ${filename} is ready for download.`;
                const downloadButton = `<a href="${data.output_path}" download="${filename}"><button>Download File</button></a>`;
                document.getElementById('downloadLink').innerHTML = downloadButton;
            } else {
                document.getElementById('status').textContent = `Error: ${data.error_message}`;
                document.getElementById('status').classList.add('error'); // Add error class
            }
        } else {
            document.getElementById('status').textContent = ` Elapsed time: ${elapsedTime} seconds. Current status: ${data.status}. Progress: ${data.progress}`;
            document.getElementById('status').classList.remove('error'); // Ensure error class is removed during processing
            setTimeout(() => checkStatus(requestId, startTime), 1000); // Poll every second, keep passing startTime
        }
    })
    .catch((error) => {
        console.error('Error:', error);
        document.getElementById('status').textContent = 'Error: Unable to check the status.';
        document.getElementById('status').classList.add('error'); // Add error class
        enableSubmitButton(); // Re-enable the button in case of error
    });
}