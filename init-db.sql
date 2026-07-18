-- Whale Database Initialization Script
-- Creates all tables, indexes, and initial data

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(15) UNIQUE NOT NULL,
    password_hash VARCHAR(200) NOT NULL,
    profile_pic VARCHAR(200) DEFAULT 'default.png',
    totp_secret VARCHAR(32),
    totp_enabled BOOLEAN DEFAULT FALSE,
    backup_codes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE
);

-- Index for username lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at);

-- Tweets table
CREATE TABLE IF NOT EXISTS tweets (
    id SERIAL PRIMARY KEY,
    body VARCHAR(140) NOT NULL,
    image VARCHAR(200),
    timestamp TIMESTAMP DEFAULT NOW(),
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    retweet_id INTEGER REFERENCES tweets (id) ON DELETE SET NULL
);

-- Indexes for tweet queries
CREATE INDEX IF NOT EXISTS idx_tweets_user_id ON tweets (user_id);

CREATE INDEX IF NOT EXISTS idx_tweets_timestamp ON tweets (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tweets_user_timestamp ON tweets (user_id, timestamp DESC);

-- Composite index for timeline queries
CREATE INDEX IF NOT EXISTS idx_tweets_feed ON tweets (user_id, timestamp DESC)
WHERE
    retweet_id IS NULL;

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL,
    tweet_id INTEGER REFERENCES tweets (id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT NOW(),
    read BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications (user_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications (user_id, read)
WHERE
    read = FALSE;

-- Messages table (encrypted)
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    sender_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    encrypted_body TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    read BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (
    sender_id,
    recipient_id,
    timestamp ASC
);

CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages (
    recipient_id,
    read,
    timestamp DESC
);

-- Followers association table
CREATE TABLE IF NOT EXISTS followers (
    follower_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    followed_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (follower_id, followed_id)
);

CREATE INDEX IF NOT EXISTS idx_followers_followed ON followers (followed_id);

CREATE INDEX IF NOT EXISTS idx_followers_follower ON followers (follower_id);

-- Likes association table
CREATE TABLE IF NOT EXISTS likes (
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    tweet_id INTEGER NOT NULL REFERENCES tweets (id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, tweet_id)
);

CREATE INDEX IF NOT EXISTS idx_likes_tweet ON likes (tweet_id);

-- Bookmarks association table
CREATE TABLE IF NOT EXISTS bookmarks (
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    tweet_id INTEGER NOT NULL REFERENCES tweets (id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, tweet_id)
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_tweet ON bookmarks (tweet_id);

-- Chat Groups table
CREATE TABLE IF NOT EXISTS chat_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(200) DEFAULT '',
    encrypted_key VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    creator_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    is_private BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_groups_creator ON chat_groups (creator_id);

-- Group Members table
CREATE TABLE IF NOT EXISTS group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES chat_groups (id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role VARCHAR(20) DEFAULT 'member',
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members (group_id);

CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members (user_id);

-- Group Messages table (encrypted)
CREATE TABLE IF NOT EXISTS group_messages (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES chat_groups (id) ON DELETE CASCADE,
    sender_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    encrypted_body TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_group_messages_group_timestamp ON group_messages (group_id, timestamp ASC);

-- Security audit log table
CREATE TABLE IF NOT EXISTS security_audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    ip_address INET,
    user_agent TEXT,
    details JSONB,
    severity VARCHAR(20) DEFAULT 'info'
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON security_audit_log (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_event_type ON security_audit_log (event_type);

CREATE INDEX IF NOT EXISTS idx_audit_user_id ON security_audit_log (user_id);

-- Insert default admin user (password: admin123 - CHANGE IN PRODUCTION)
-- Password hash for 'admin123' with pbkdf2:sha256:600000
INSERT INTO
    users (
        username,
        password_hash,
        is_admin,
        created_at
    )
VALUES (
        'admin',
        'pbkdf2:sha256:600000$dummy$dummy',
        TRUE,
        NOW()
    ) ON CONFLICT (username) DO NOTHING;

-- Create function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.timestamp = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for automatic timestamp updates
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tweets_updated_at BEFORE UPDATE ON tweets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO whale_user;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO whale_user;

-- Vacuum analyze for query optimization
VACUUM ANALYZE;