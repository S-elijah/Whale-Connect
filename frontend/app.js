// Simple Frontend MVP - No Backend
let currentUser = JSON.parse(localStorage.getItem('currentUser')) || null;
let allTweets = JSON.parse(localStorage.getItem('allTweets')) || [];
let users = JSON.parse(localStorage.getItem('users')) || [];

// Init
window.addEventListener('DOMContentLoaded', () => {
    if (currentUser) showTimeline();
    updateUI();
});

// Auth
function showLogin() {
    document.getElementById('login-modal').style.display = 'flex';
    document.getElementById('signup-modal').style.display = 'none';
}

function showSignup() {
    document.getElementById('signup-modal').style.display = 'flex';
    document.getElementById('login-modal').style.display = 'none';
}

function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    
    const user = users.find(u => u.username === username && u.password === password);
    if (!user) {
        alert('Invalid credentials');
        return;
    }
    
    currentUser = user;
    localStorage.setItem('currentUser', JSON.stringify(currentUser));
    document.getElementById('login-modal').style.display = 'none';
    showTimeline();
    updateUI();
}

function handleSignup(e) {
    e.preventDefault();
    const username = document.getElementById('signup-username').value;
    const password = document.getElementById('signup-password').value;
    
    if (users.some(u => u.username === username)) {
        alert('Username taken');
        return;
    }
    
    if (password.length < 8) {
        alert('Password must be 8+ chars');
        return;
    }
    
    const newUser = {
        id: Date.now(),
        username,
        password,
        followers: [],
        following: []
    };
    
    users.push(newUser);
    localStorage.setItem('users', JSON.stringify(users));
    
    currentUser = newUser;
    localStorage.setItem('currentUser', JSON.stringify(currentUser));
    document.getElementById('signup-modal').style.display = 'none';
    showTimeline();
    updateUI();
}

function logout() {
    currentUser = null;
    localStorage.removeItem('currentUser');
    document.getElementById('timeline').style.display = 'none';
    document.getElementById('profile-page').style.display = 'none';
    document.getElementById('login-modal').style.display = 'flex';
    updateUI();
}

// UI
function updateUI() {
    const authButtons = document.getElementById('auth-buttons');
    const userMenu = document.getElementById('user-menu');
    
    if (currentUser) {
        authButtons.style.display = 'none';
        userMenu.style.display = 'flex';
        document.getElementById('current-user').textContent = `@${currentUser.username}`;
    } else {
        authButtons.style.display = 'flex';
        userMenu.style.display = 'none';
    }
}

function showTimeline() {
    document.getElementById('timeline').style.display = 'block';
    document.getElementById('profile-page').style.display = 'none';
    renderTweets();
}

// Tweets
function postTweet() {
    const input = document.getElementById('tweet-input');
    const body = input.value.trim();
    
    if (!body) return;
    
    const tweet = {
        id: Date.now(),
        author: currentUser.username,
        body,
        likes: 0,
        timestamp: new Date().toLocaleString(),
        liked: false
    };
    
    allTweets.unshift(tweet);
    localStorage.setItem('allTweets', JSON.stringify(allTweets));
    input.value = '';
    document.getElementById('char-count').textContent = '0/280';
    renderTweets();
}

function renderTweets() {
    const feed = document.getElementById('tweets-feed');
    
    if (allTweets.length === 0) {
        feed.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🐋</div><p>No tweets yet. Be the first to splash!</p></div>';
        return;
    }
    
    feed.innerHTML = allTweets.map(tweet => `
        <div class="tweet">
            <div class="tweet-header">
                <div class="tweet-avatar">🐋</div>
                <div class="tweet-info">
                    <div class="tweet-author">
                        <span class="tweet-name">${tweet.author}</span>
                        <span class="tweet-handle">@${tweet.author}</span>
                        <span class="tweet-time">${tweet.timestamp}</span>
                    </div>
                </div>
            </div>
            <div class="tweet-body">${tweet.body}</div>
            <div class="tweet-actions">
                <div class="tweet-action" onclick="toggleLike(${tweet.id})">❤️ ${tweet.likes}</div>
                <div class="tweet-action">💬 0</div>
                <div class="tweet-action">🔄 0</div>
                <div class="tweet-action">📤</div>
            </div>
        </div>
    `).join('');
}

function toggleLike(tweetId) {
    const tweet = allTweets.find(t => t.id === tweetId);
    if (tweet) {
        tweet.liked = !tweet.liked;
        tweet.likes += tweet.liked ? 1 : -1;
        localStorage.setItem('allTweets', JSON.stringify(allTweets));
        renderTweets();
    }
}

// Char counter
document.addEventListener('DOMContentLoaded', () => {
    const textarea = document.getElementById('tweet-input');
    if (textarea) {
        textarea.addEventListener('input', (e) => {
            document.getElementById('char-count').textContent = `${e.target.value.length}/280`;
        });
    }
});
