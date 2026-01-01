// API base URL
const API_BASE = '';

// DOM elements
const connectSection = document.getElementById('connect-section');
const fetchSection = document.getElementById('fetch-section');
const resultsSection = document.getElementById('results-section');
const oauthForm = document.getElementById('oauth-form');
const openOAuthBtn = document.getElementById('open-oauth-btn');
const oauthStatus = document.getElementById('oauth-status');
const fetchBtn = document.getElementById('fetch-btn');
const fetchStatus = document.getElementById('fetch-status');
const fetchProgress = document.getElementById('fetch-progress');
const resultsContent = document.getElementById('results-content');

let currentSessionId = null;
let isAuthenticated = false;

// Open OAuth flow
openOAuthBtn.addEventListener('click', async () => {
    // Get a session ID from backend
    let sessionId = null;
    try {
        const sessionResponse = await fetch(`${API_BASE}/api/spotify/get-session`);
        const sessionData = await sessionResponse.json();
        sessionId = sessionData.session_id;
    } catch (error) {
        console.error('Failed to get session ID:', error);
        sessionId = Math.random().toString(36).substring(7);
    }
    
    // Get OAuth authorization URL
    let authUrl = null;
    try {
        const authResponse = await fetch(`${API_BASE}/api/spotify/oauth/authorize?session_id=${sessionId}`);
        const authData = await authResponse.json();
        
        // Check if OAuth is not available
        if (!authResponse.ok || authData.error || !authData.auth_url) {
            oauthStatus.className = 'status-message error';
            oauthStatus.textContent = authData.message || 'OAuth initialization failed. Please check server configuration.';
            oauthStatus.style.display = 'block';
            return;
        }
        
        authUrl = authData.auth_url;
    } catch (error) {
        oauthStatus.className = 'status-message error';
        oauthStatus.textContent = `OAuth error: ${error.message}. Please check your Spotify Client ID configuration.`;
        oauthStatus.style.display = 'block';
        return;
    }
    
    // Open OAuth popup
    const width = 500;
    const height = 700;
    const left = (window.screen.width / 2) - (width / 2);
    const top = (window.screen.height / 2) - (height / 2);
    
    const popup = window.open(
        authUrl,
        'Spotify Login',
        `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no,scrollbars=yes,resizable=yes`
    );
    
    if (!popup) {
        oauthStatus.className = 'status-message error';
        oauthStatus.textContent = 'Popup blocked. Please allow popups for this site.';
        oauthStatus.style.display = 'block';
        return;
    }
    
    oauthStatus.className = 'status-message info';
    oauthStatus.textContent = 'Waiting for you to authorize Spotify...';
    oauthStatus.style.display = 'block';
    
    // Listen for messages from popup (OAuth success)
    const messageHandler = async (event) => {
        if (event.data.type === 'spotify-oauth-success') {
            window.removeEventListener('message', messageHandler);
            clearInterval(checkInterval);
            popup.close();
            
            // Store session ID from callback
            currentSessionId = event.data.session_id || event.data.tokens?.session_id;
            
            oauthStatus.className = 'status-message success';
            oauthStatus.textContent = 'Successfully connected via OAuth!';
            isAuthenticated = true;
            connectSection.style.display = 'none';
            fetchSection.style.display = 'block';
        }
    };
    window.addEventListener('message', messageHandler);
    
    // Stop polling after 5 minutes
    const checkInterval = setTimeout(() => {
        window.removeEventListener('message', messageHandler);
        if (!popup.closed) {
            popup.close();
        }
        if (!isAuthenticated) {
            oauthStatus.className = 'status-message error';
            oauthStatus.textContent = 'Login window was closed. Please try again.';
        }
    }, 300000);
});

// Fetch Spotify data
fetchBtn.addEventListener('click', async () => {
    if (!currentSessionId) {
        fetchStatus.className = 'status-message error';
        fetchStatus.textContent = 'No session ID available. Please connect first.';
        fetchStatus.style.display = 'block';
        return;
    }
    
    fetchBtn.disabled = true;
    fetchStatus.className = 'status-message info';
    fetchStatus.textContent = 'Fetching Spotify data...';
    fetchStatus.style.display = 'block';
    fetchProgress.style.display = 'block';
    
    try {
        const response = await fetch(`${API_BASE}/api/spotify/fetch`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: currentSessionId
            }),
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to fetch data');
        }
        
        fetchStatus.className = 'status-message success';
        fetchStatus.textContent = 'Data fetched successfully!';
        fetchProgress.style.display = 'none';
        
        // Show results
        displayResults(data);
        resultsSection.style.display = 'block';
        
    } catch (error) {
        fetchStatus.className = 'status-message error';
        fetchStatus.textContent = `Error: ${error.message}`;
        fetchProgress.style.display = 'none';
    } finally {
        fetchBtn.disabled = false;
    }
});

// Display results
function displayResults(data) {
    const summary = data.summary || {};
    const enriched = data.enriched || {};
    
    let html = `
        <div class="summary-stats">
            <div class="stat-card">
                <div class="stat-value">${summary.total_playlists || 0}</div>
                <div class="stat-label">Playlists</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${summary.total_tracks || 0}</div>
                <div class="stat-label">Tracks</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${summary.total_artists || 0}</div>
                <div class="stat-label">Artists</div>
            </div>
        </div>
    `;
    
    if (enriched.music_preferences) {
        html += `
            <div class="result-item">
                <h3>🎵 Music Preferences</h3>
                <pre>${JSON.stringify(enriched.music_preferences, null, 2)}</pre>
            </div>
        `;
    }
    
    if (enriched.profile_summary) {
        html += `
            <div class="result-item">
                <h3>👤 Profile Summary</h3>
                <pre>${JSON.stringify(enriched.profile_summary, null, 2)}</pre>
            </div>
        `;
    }
    
    if (data.session_id) {
        html += `
            <div class="result-item">
                <h3>💾 Database</h3>
                <p>Session ID: <strong>${data.session_id}</strong></p>
                <p>Data saved to: <code>test_sp.db</code></p>
            </div>
        `;
    }
    
    resultsContent.innerHTML = html;
}
