/* ticket_detail.js - Externalized Logic for v1.2.0 */
document.addEventListener('DOMContentLoaded', function() {
    const statusSelect = document.getElementById('statusSelect');
    const assignSelect = document.getElementById('assignSelect');
    const ticketWrapper = document.getElementById('ticketDetailWrapper');
    const ticketId = ticketWrapper ? ticketWrapper.dataset.ticketId : null;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    if (!ticketId || !csrfToken) return;
    
    const reminderWrapper = document.getElementById('reminderDateWrapper');
    const editReminderInput = document.getElementById('editReminderDateInput');

    const toggleReminderField = (status) => {
        if (!reminderWrapper) return;
        if (status === 'wartet') {
            reminderWrapper.classList.remove('d-none');
        } else {
            reminderWrapper.classList.add('d-none');
            if (editReminderInput) editReminderInput.value = '';
        }
    };

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
        toggleReminderField(statusSelect.value);

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
                    toggleReminderField(newStatus);
                    
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

    // --- Ticket Basic Data Edit (Title, Priority) (UX-5 / Feature) ---
    const editBtn = document.getElementById('editTicketBtn');
    const saveBtn = document.getElementById('saveTicketBtn');
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    
    const headerStatic = document.getElementById('ticketHeaderStatic');
    const headerEdit = document.getElementById('ticketHeaderEdit');
    const priorityStatic = document.getElementById('priorityStatic');
    const priorityEdit = document.getElementById('priorityEdit');

    const editTitleInput = document.getElementById('editTitleInput');
    const editPrioritySelect = document.getElementById('editPrioritySelect');
    const editDueDateInput = document.getElementById('editDueDateInput');
    const editOrderRefInput = document.getElementById('editOrderRefInput');
    // editReminderInput already defined above

    if (editBtn && saveBtn && cancelEditBtn) {
        editBtn.addEventListener('click', () => {
            headerStatic.classList.add('d-none');
            headerEdit.classList.remove('d-none');
            priorityStatic.classList.add('d-none');
            priorityEdit.classList.remove('d-none');
            editTitleInput.focus();
        });

        cancelEditBtn.addEventListener('click', () => {
            headerStatic.classList.remove('d-none');
            headerEdit.classList.add('d-none');
            priorityStatic.classList.remove('d-none');
            priorityEdit.classList.add('d-none');
        });

        saveBtn.addEventListener('click', async () => {
            const newTitle = editTitleInput.value.trim();
            const newPrio = editPrioritySelect.value;
            const newDue = editDueDateInput ? editDueDateInput.value : null;
            const newOrderRef = editOrderRefInput ? editOrderRefInput.value.trim() : null;
            const newReminder = editReminderInput ? editReminderInput.value : null;

            if (!newTitle) {
                window.showUiAlert('Titel darf nicht leer sein.');
                return;
            }

            saveBtn.disabled = true;
            saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Speichern...';

            try {
                const response = await fetch(`${getIngress()}/api/ticket/${ticketId}/update`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ 
                        title: newTitle, 
                        priority: newPrio,
                        due_date: newDue,
                        order_reference: newOrderRef,
                        reminder_date: newReminder
                    })
                });
                const data = await response.json();
                if (data.success) {
                    // Update UI
                    document.getElementById('staticTitle').textContent = newTitle;
                    
                    // Priority Badge Update
                    const prioContainer = priorityStatic.querySelector('.badge');
                    const prioMap = { '1': 'HOCH', '2': 'MITTEL', '3': 'NIEDRIG' };
                    const classMap = { '1': 'danger', '2': 'primary', '3': 'success' };
                    
                    if (prioContainer) {
                        prioContainer.textContent = prioMap[newPrio];
                        prioContainer.className = `badge bg-${classMap[newPrio]}-subtle text-${classMap[newPrio]} rounded-pill px-3 py-2`;
                    }

                    // Reload page to reflect all changes (especially if due date changed and affects badge elsewhere)
                    // Or more elegantly update the local view. Given the complexity of date formatting, a reload is robust or we just show a success message.
                    window.location.reload(); 
                } else {
                    window.showUiAlert('Fehler: ' + data.error);
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Speichern';
                }
            } catch (err) {
                window.showUiAlert('Netzwerkfehler beim Speichern.');
                saveBtn.disabled = false;
                saveBtn.textContent = 'Speichern';
            }
        });
    }
});
