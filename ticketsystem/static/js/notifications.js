/**
 * In-App Notification System
 */

document.addEventListener('DOMContentLoaded', () => {
    const navNotificationBadge = document.getElementById('navNotificationBadge');
    const notificationList = document.getElementById('notificationList');
    const notificationDropdownContainer = document.getElementById('notificationDropdownContainer');

    if (!navNotificationBadge || !notificationList) return;

    const ingressPath = window.INGRESS_PATH || '';
    const POLL_INTERVAL = 30000; // 30s polling
    let isDropdownOpen = false;

    if (notificationDropdownContainer) {
        notificationDropdownContainer.addEventListener('show.bs.dropdown', () => {
            isDropdownOpen = true;
            fetchNotifications(); 
        });
        notificationDropdownContainer.addEventListener('hide.bs.dropdown', () => {
            isDropdownOpen = false;
        });
    }

    async function fetchNotifications() {
        if (document.hidden) return; // FIX-POLL: Skip fetch if tab is in background
        try {
            const res = await fetch(`${ingressPath}/api/notifications`);
            if (res.redirected || res.status === 401 || res.status === 302) {
                window.location.reload();
                return;
            }
            if (!res.ok) return;
            const data = await res.json();
            
            updateBadge(data.unread_count);
            
            if (isDropdownOpen) {
                renderNotificationList(data.notifications, data.unread_count);
            }
        } catch (e) {
            console.error('Failed to fetch notifications', e);
        }
    }

    function updateBadge(count) {
        if (count > 0) {
            navNotificationBadge.textContent = count;
            navNotificationBadge.classList.remove('d-none');
            navNotificationBadge.classList.add('animate-pulse');
        } else {
            navNotificationBadge.textContent = '0';
            navNotificationBadge.classList.add('d-none');
            navNotificationBadge.classList.remove('animate-pulse');
        }
    }

    function renderNotificationList(notifications, unreadCount) {
        notificationList.innerHTML = '';
        
        const header = document.createElement('li');
        header.innerHTML = `
            <div class="dropdown-header fw-bold bg-light py-2 border-bottom text-dark d-flex justify-content-between align-items-center">
                <span>Benachrichtigungen</span>
                ${unreadCount > 0 ? `<button class="btn btn-sm btn-link text-decoration-none p-0 text-primary" id="markAllReadBtn" style="font-size: 0.75rem;">Alle als gelesen markieren</button>` : ''}
            </div>
        `;
        notificationList.appendChild(header);

        if (notifications.length === 0) {
            const empty = document.createElement('li');
            empty.innerHTML = `<span class="dropdown-item-text text-muted small text-center py-4 d-block">Keine aktuellen Meldungen</span>`;
            notificationList.appendChild(empty);
            return;
        }

        notifications.forEach(n => {
            const li = document.createElement('li');
            const isReadClass = n.is_read ? 'bg-transparent text-secondary' : 'bg-primary-subtle text-dark cursor-pointer fw-semibold border-start border-4 border-primary';
            
            // Format time string if available natively or fallback
            let timeStr = 'Aktuell';
            
            // SEC-07: Use textContent (never innerHTML) to prevent XSS from DB-stored messages
            const anchor = document.createElement('a');
            anchor.className = `dropdown-item border-bottom px-3 py-2 ${isReadClass}`;
            anchor.style.whiteSpace = 'normal';
            anchor.href = 'javascript:void(0)';
            anchor.dataset.id = n.id;
            anchor.dataset.link = `${ingressPath}${n.link}`;

            const headerRow = document.createElement('div');
            headerRow.className = 'd-flex w-100 justify-content-between align-items-center mb-1';
            const titleSmall = document.createElement('small');
            titleSmall.className = `fw-bold ${n.is_read ? 'text-muted' : 'text-primary'}`;
            titleSmall.innerHTML = '<i class="bi bi-info-circle-fill me-1"></i>';
            titleSmall.appendChild(document.createTextNode('System'));
            const timeSmall = document.createElement('small');
            timeSmall.className = 'text-muted';
            timeSmall.style.fontSize = '0.65rem';
            timeSmall.textContent = timeStr;
            headerRow.appendChild(titleSmall);
            headerRow.appendChild(timeSmall);

            const msgP = document.createElement('p');
            msgP.className = 'mb-0 small';
            msgP.style.lineHeight = '1.3';
            msgP.textContent = n.message; // textContent prevents XSS

            anchor.appendChild(headerRow);
            anchor.appendChild(msgP);
            li.appendChild(anchor);
            notificationList.appendChild(li);
        });

        // Click handlers for notifications
        notificationList.querySelectorAll('a.dropdown-item[data-id]').forEach(el => {
            el.addEventListener('click', async (e) => {
                e.preventDefault();
                await markAsRead(el.dataset.id);
                if(el.dataset.link !== ingressPath + '#') {
                    window.location.href = el.dataset.link;
                } else {
                    fetchNotifications();
                }
            });
        });

        const markAllBtn = document.getElementById('markAllReadBtn');
        if (markAllBtn) {
            markAllBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                e.preventDefault();
                await markAllAsRead();
                fetchNotifications();
            });
        }

        // M-10: Footer — overflow hint + profile link
        const footer = document.createElement('li');
        const hiddenCount = unreadCount > notifications.length ? unreadCount - notifications.length : 0;
        footer.innerHTML =
            '<div class="dropdown-item-text border-top py-2 px-3 d-flex justify-content-between align-items-center">' +
              (hiddenCount > 0
                ? `<small class="text-muted">+ ${hiddenCount} weitere ungelesene</small>`
                : '<small class="text-muted">&nbsp;</small>') +
              `<a href="${ingressPath}/profile#notifications" class="btn btn-link btn-sm text-decoration-none p-0 small fw-bold">Alle anzeigen <i class="bi bi-arrow-right ms-1"></i></a>` +
            '</div>';
        notificationList.appendChild(footer);
    }

    // SEC-07 fix: Read CSRF token from meta-tag (always present), not form input (may be absent)
    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    async function markAsRead(id) {
        try {
            await fetch(`${ingressPath}/api/notifications/${id}/read`, { 
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() }
            });
        } catch(e) {}
    }

    async function markAllAsRead() {
        try {
            await fetch(`${ingressPath}/api/notifications/read_all`, { 
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() }
            });
        } catch(e) {}
    }

    setInterval(fetchNotifications, POLL_INTERVAL);
});

// ---------------------------------------------------------------------------
// WebPush subscription manager (runs independently of the notification UI)
// ---------------------------------------------------------------------------

(function initWebPush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

    const ingress = window.INGRESS_PATH || '';

    function getCsrf() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    async function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        const raw = atob(base64);
        return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
    }

    async function subscribe() {
        try {
            const keyResp = await fetch(ingress + '/api/push/vapid-key');
            if (!keyResp.ok) return;
            const { public_key } = await keyResp.json();
            if (!public_key) return;

            const reg = await navigator.serviceWorker.ready;
            const existing = await reg.pushManager.getSubscription();
            if (existing) return; // already subscribed

            const permission = await Notification.requestPermission();
            if (permission !== 'granted') return;

            const sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: await urlBase64ToUint8Array(public_key),
            });

            await fetch(ingress + '/api/push/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
                body: JSON.stringify(sub.toJSON()),
            });
        } catch(e) {
            // WebPush setup is optional — log but don't break the page
            console.debug('[WebPush] subscribe error:', e);
        }
    }

    // Trigger subscription after a short delay so it doesn't block page load
    setTimeout(subscribe, 3000);
})();
