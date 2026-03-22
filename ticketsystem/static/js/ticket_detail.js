/* ticket_detail.js - Externalized Logic for v1.2.0 */
document.addEventListener('DOMContentLoaded', function() {
    const statusSelect = document.getElementById('statusSelect');
    const assignSelect = document.getElementById('assignSelect');
    const ticketWrapper = document.getElementById('ticketDetailWrapper');
    const ticketId = ticketWrapper ? ticketWrapper.dataset.ticketId : null;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    if (!ticketId || !csrfToken) return;

    const getIngress = () => document.querySelector('.navbar')?.getAttribute('data-ingress') || '';

    const applySelectColor = (sel) => {
        const map = {
            offen: 'var(--bg-danger-subtle)',
            in_bearbeitung: 'var(--bg-warning-subtle)',
            wartet: 'var(--border-color)',
            erledigt: 'var(--bg-success-subtle)'
        };
        sel.style.backgroundColor = map[sel.value] || '';
    };

    if (statusSelect) {
        applySelectColor(statusSelect);
        statusSelect.addEventListener('change', async function() {
            const newStatus = this.value;
            const originalValue = this.dataset.original;

            if (newStatus === 'erledigt') {
                const confirmed = await window.showConfirm('Ticket abschließen', 'Möchten Sie dieses Ticket wirklich als erledigt markieren?');
                if (!confirmed) {
                    this.value = originalValue;
                    return;
                }
            }

            this.disabled = true;
            this.classList.add('opacity-50');
            
            try {
                const response = await fetch(`${getIngress()}/api/ticket/${ticketId}/status`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ status: newStatus })
                });
                const data = await response.json();
                if (data.success) {
                    this.dataset.original = newStatus;
                    this.disabled = false;
                    this.classList.remove('opacity-50');
                    applySelectColor(this);
                    
                    // UX Update: Badge in header
                    const statusBadge = document.getElementById('ticketStatusBadge');
                    if (statusBadge) {
                        const STATUS_LABELS = {
                            'offen': 'OFFEN',
                            'in_bearbeitung': 'IN BEARBEITUNG',
                            'wartet': 'WARTET',
                            'erledigt': 'ERLEDIGT'
                        };
                        statusBadge.textContent = STATUS_LABELS[newStatus] || newStatus.toUpperCase();
                        
                        statusBadge.className = 'badge-subtle-danger';
                        if (newStatus === 'in_bearbeitung') statusBadge.className = 'badge-subtle-warning';
                        if (newStatus === 'wartet') statusBadge.className = 'badge-subtle-secondary';
                        if (newStatus === 'erledigt') statusBadge.className = 'badge-subtle-success';
                    }
                    window.showUiAlert('Status erfolgreich aktualisiert.', 'success');
                } else {
                    window.showUiAlert('Fehler: ' + data.error);
                    this.disabled = false;
                    this.classList.remove('opacity-50');
                    this.value = originalValue;
                    applySelectColor(this);
                }
            } catch (error) {
                window.showUiAlert('Netzwerkfehler beim Aktualisieren.');
                this.disabled = false;
                this.classList.remove('opacity-50');
                this.value = originalValue;
                applySelectColor(this);
            }
        });
    }

    if (assignSelect) {
        assignSelect.addEventListener('change', async function() {
            const workerId = this.value;
            const workerName = this.options[this.selectedIndex].text;
            const originalValue = this.dataset.original;
            
            this.disabled = true;
            this.classList.add('opacity-50');

            try {
                const response = await fetch(`${getIngress()}/api/ticket/${ticketId}/assign`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ worker_id: workerId ? parseInt(workerId) : null })
                });
                const data = await response.json();
                if (data.success) {
                    this.dataset.original = workerId || '';
                    this.disabled = false;
                    this.classList.remove('opacity-50');
                    
                    // UX Update: Header Badge
                    const assignBadge = document.getElementById('ticketAssigneeBadge');
                    if (assignBadge) {
                        assignBadge.textContent = workerId ? workerName : 'NICHT ZUGEWIESEN';
                    }
                    
                    window.showUiAlert('Zuweisung erfolgreich aktualisiert.', 'success');
                } else {
                    window.showUiAlert('Fehler: ' + data.error);
                    this.disabled = false;
                    this.classList.remove('opacity-50');
                    this.value = originalValue;
                }
            } catch (error) {
                window.showUiAlert('Netzwerkfehler bei der Zuweisung.');
                this.disabled = false;
                this.classList.remove('opacity-50');
                this.value = originalValue;
            }
        });
    }
});
