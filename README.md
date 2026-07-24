# 🐋 Whale — Minimal Social Network MVP

**Beautiful Frontend. Zero Backend. 100% Local.**

A lightweight, responsive social network MVP built with vanilla HTML, CSS, and JavaScript. No server required—everything runs locally using browser storage.

---

## 🚀 Quick Start

### Option 1: Direct Browser
Simply open `frontend/index.html` in any modern web browser.

### Option 2: Local Server
```bash
# Python 3
python -m http.server 8000

# Node.js (optional)
npx http-server

# Then visit: http://localhost:8000/frontend/index.html
```

---

## ✨ Features

### Core Functionality
- ✅ **User Authentication** - Sign up & login (stored locally)
- ✅ **Tweet Composer** - Share thoughts up to 280 characters
- ✅ **Tweet Feed** - Real-time feed of all tweets
- ✅ **Like/Unlike** - Engage with tweets
- ✅ **User Profiles** - View user details
- ✅ **Responsive Design** - Works on mobile & desktop

### Technical
- 🔐 **Local Storage Only** - No backend, no database
- ⚡ **Vanilla JavaScript** - Zero dependencies
- 🎨 **Modern UI** - Twitter/X inspired dark theme
- 📱 **Mobile Friendly** - Fully responsive layout
- 🌙 **Dark Mode** - Easy on the eyes

---

## 📁 Project Structure

```
frontend/
├── index.html       # Main HTML (login, signup, timeline, profile)
├── style.css        # Dark theme stylesheet
└── app.js           # Pure JavaScript logic
```

---

## 🎯 How It Works

### Data Storage
All data is stored in **browser localStorage**:
- `users` - User accounts with username/password
- `currentUser` - Logged-in user session
- `allTweets` - All tweets from all users

### User Flow
1. **Sign Up** - Create username (8+ char password)
2. **Login** - Enter credentials
3. **Tweet** - Share up to 280 characters
4. **Like** - Click heart to like/unlike tweets
5. **Logout** - Clear session

---

## 🛠️ File Breakdown

### `index.html` (350 lines)
- Modal for login/signup
- Tweet composer with char counter
- Tweet feed rendering
- Profile page skeleton

### `style.css` (400+ lines)
- CSS variables for theming
- Dark theme colors
- Responsive grid layout
- Button & modal styles
- Tweet card components

### `app.js` (250 lines)
- `handleLogin()` / `handleSignup()` - Auth
- `postTweet()` - Create tweets
- `renderTweets()` - Display feed
- `toggleLike()` - Like functionality
- `logout()` - Clear session

---

## 🎨 Design

**Theme:** Dark mode inspired by Twitter/X
- Background: `#000000`
- Primary: `#1da1f2` (blue)
- Text: `#e1e8ed` (light gray)
- Accent: Purple & green

**Layout:** 
- Max width: 600px (like Twitter feed)
- Sticky navbar
- Responsive on mobile

---

## 💾 Local Storage Schema

```javascript
// users array
[
  {
    id: 1234567890,
    username: "elijah",
    password: "Password123!",
    followers: [],
    following: []
  }
]

// allTweets array
[
  {
    id: 1234567890,
    author: "elijah",
    body: "Hello Whale! 🐋",
    likes: 5,
    timestamp: "7/24/2026, 5:00 PM",
    liked: false
  }
]
```

---

## 🔒 Security Note

⚠️ **This is a demo MVP** - Passwords are stored in plain text in localStorage. For production:
- Use a proper backend
- Hash passwords (bcrypt)
- Implement JWT tokens
- Use HTTPS
- Add server-side validation

---

## 🚀 Future Enhancements

- [ ] Backend integration (Flask/Node)
- [ ] Database persistence (PostgreSQL)
- [ ] User profiles with avatars
- [ ] Follow/unfollow system
- [ ] Retweets
- [ ] Replies & comments
- [ ] Notifications
- [ ] Direct messaging
- [ ] Trending hashtags
- [ ] Search functionality

---

## 📋 MVP Checklist

- ✅ User authentication
- ✅ Tweet creation & display
- ✅ Like system
- ✅ Responsive UI
- ✅ No backend required
- ✅ Clean, modern design
- ✅ Working demo ready

---

## 🎓 Learning Resources

- **LocalStorage Docs:** https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage
- **Vanilla JS:** https://javascript.info
- **CSS Grid/Flexbox:** https://css-tricks.com

---

## 📝 License

MIT - Free to use and modify

---

## 🆘 Support

For issues or questions about the MVP, check the `/frontend/` folder and review `app.js` logic.

---

**Built for rapid prototyping & UI/UX testing. No servers. No complexity. Just code.** 🚀
