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
        try {
            const res = await fetch(`${ingressPath}/api/notifications`);
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
            
            li.innerHTML = `
                <a class="dropdown-item border-bottom px-3 py-2 ${isReadClass}" style="white-space: normal;" href="javascript:void(0)" data-id="${n.id}" data-link="${ingressPath}${n.link}">
                    <div class="d-flex w-100 justify-content-between align-items-center mb-1">
                        <small class="fw-bold ${n.is_read ? 'text-muted' : 'text-primary'}"><i class="bi bi-info-circle-fill me-1"></i>System</small>
                        <small class="text-muted" style="font-size: 0.65rem;">${timeStr}</small>
                    </div>
                    <p class="mb-0 small" style="line-height: 1.3;">${n.message}</p>
                </a>
            `;
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
    }

    // Use CSRF Token from standard ticket system forms (e.g. logout form)
    function getCsrfToken() {
        const tokenInput = document.querySelector('input[name="csrf_token"]');
        return tokenInput ? tokenInput.value : '';
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
