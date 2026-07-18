// Whale - Service Worker for PWA Support
const CACHE_NAME = 'whale-v1.0.0';
const STATIC_CACHE = 'whale-static-v1';
const DYNAMIC_CACHE = 'whale-dynamic-v1';

// Assets to cache immediately
const STATIC_ASSETS = [
    '/',
    '/static/style.css',
    '/static/manifest.json',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[SW] Installing service worker...');
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => {
                console.log('[SW] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating service worker...');
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== STATIC_CACHE && key !== DYNAMIC_CACHE) {
                        console.log('[SW] Deleting old cache:', key);
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Skip non-GET requests
    if (request.method !== 'GET') return;

    // Skip API requests (always fetch from network)
    if (url.pathname.startsWith('/api/')) return;

    // Skip auth endpoints
    if (url.pathname.includes('/login') || url.pathname.includes('/signup')) return;

    event.respondWith(
        caches.match(request)
            .then((cachedResponse) => {
                if (cachedResponse) {
                    // Return cached version
                    return cachedResponse;
                }

                // Fetch from network
                return fetch(request)
                    .then((response) => {
                        // Don't cache non-successful responses
                        if (!response || response.status !== 200 || response.type !== 'basic') {
                            return response;
                        }

                        // Clone the response
                        const responseToCache = response.clone();

                        // Cache dynamic content
                        caches.open(DYNAMIC_CACHE)
                            .then((cache) => {
                                cache.put(request, responseToCache);
                            });

                        return response;
                    })
                    .catch(() => {
                        // Offline fallback
                        if (request.destination === 'document') {
                            return caches.match('/');
                        }
                    });
            })
    );
});

// Background sync for offline messages
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-messages') {
        event.waitUntil(syncMessages());
    }
});

// Push notifications
self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : { title: 'Whale', body: 'New notification' };
    
    const options = {
        body: data.body || 'You have a new notification',
        icon: '/static/icons/icon-192x192.png',
        badge: '/static/icons/icon-72x72.png',
        vibrate: [100, 50, 100],
        data: data.url || '/',
        actions: [
            { action: 'view', title: 'View' },
            { action: 'close', title: 'Close' }
        ]
    };

    event.waitUntil(
        self.registration.showNotification(data.title || 'Whale', options)
    );
});

// Notification click
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    if (event.action === 'close') return;
    
    event.waitUntil(
        clients.openWindow(event.notification.data || '/')
    );
});

// Helper function for syncing messages
async function syncMessages() {
    console.log('[SW] Syncing messages...');
    // Implementation for offline message sync
    return Promise.resolve();
}