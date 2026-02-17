/**
 * Service Worker for Stellarr push notifications.
 * Handles background push events when the browser is closed.
 */

// Listen for push events
self.addEventListener('push', (event) => {
  if (!event.data) {
    console.log('Push event with no data');
    return;
  }

  let payload;
  try {
    payload = event.data.json();
  } catch (e) {
    payload = { title: 'Stellarr', body: event.data.text() };
  }

  const options = {
    body: payload.body || '',
    icon: payload.icon || '/icon-192.png',
    badge: '/icon-192.png',
    tag: payload.tag || 'stellarr-notification',
    renotify: true,
    requireInteraction: false,
    data: payload.data || {},
  };

  // Add image if provided (shows as large image in notification)
  if (payload.image) {
    options.image = payload.image;
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || 'Stellarr', options)
  );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  // Open the app when notification is clicked
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // If there's already a window open, focus it
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.focus();
        }
      }
      // Otherwise open a new window
      if (clients.openWindow) {
        return clients.openWindow('/');
      }
    })
  );
});

// Handle service worker installation
self.addEventListener('install', (event) => {
  console.log('Service worker installed');
  self.skipWaiting();
});

// Handle service worker activation
self.addEventListener('activate', (event) => {
  console.log('Service worker activated');
  event.waitUntil(clients.claim());
});
