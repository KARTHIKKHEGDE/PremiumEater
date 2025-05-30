// Main JavaScript for the web scraper

document.addEventListener('DOMContentLoaded', () => {
    // Initialize any event listeners or setup here
    console.log('Web Scraper initialized');
});

async function scrapeWebsite() {
    const urlInput = document.getElementById('urlInput');
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    const resultContent = document.getElementById('resultContent');
    const error = document.getElementById('error');
    
    const url = urlInput.value.trim();
    
    if (!url) {
        showError('Please enter a valid URL');
        return;
    }
    
    // Show loading state
    loading.classList.remove('hidden');
    results.classList.add('hidden');
    error.classList.add('hidden');
    
    try {
        // Call the backend API
        const response = await fetch('/api/scrape', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url })
        });
        
        if (!response.ok) {
            throw new Error('Failed to fetch data');
        }
        
        const data = await response.json();
        
        // Display results
        displayResults(data);
        results.classList.remove('hidden');
    } catch (err) {
        console.error('Error:', err);
        showError('Failed to scrape the website. Please try again.');
    } finally {
        loading.classList.add('hidden');
    }
}

function displayResults(data) {
    const resultContent = document.getElementById('resultContent');
    
    // Simple display of the scraped data
    // You can customize this based on the actual data structure
    let html = `
        <div class="mb-4">
            <h4 class="font-semibold text-lg">${data.title || 'No title found'}</h4>
            <p class="text-gray-700">${data.description || 'No description available'}</p>
        </div>
    `;
    
    // Add more data as needed
    if (data.images && data.images.length > 0) {
        html += `
            <div class="mt-4">
                <h4 class="font-semibold mb-2">Images found (${data.images.length}):</h4>
                <div class="grid grid-cols-2 md:grid-cols-3 gap-2">
                    ${data.images.slice(0, 6).map(img => `
                        <img src="${img}" alt="Scraped content" class="rounded shadow hover:shadow-lg transition-shadow">
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    if (data.links && data.links.length > 0) {
        html += `
            <div class="mt-4">
                <h4 class="font-semibold mb-2">Links (${data.links.length}):</h4>
                <ul class="list-disc pl-5 space-y-1">
                    ${data.links.slice(0, 10).map(link => `
                        <li><a href="${link}" target="_blank" class="text-blue-600 hover:underline">${link}</a></li>
                    `).join('')}
                </ul>
            </div>
        `;
    }
    
    resultContent.innerHTML = html;
}

function showError(message) {
    const error = document.getElementById('error');
    error.textContent = message;
    error.classList.remove('hidden');
}
