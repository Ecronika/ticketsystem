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

            // Tags Handling: Convert comma-separated string to Array
            const tagsInput = document.getElementById('editTagsInput');
            const newTags = tagsInput ? tagsInput.value.split(',').map(t => t.trim()).filter(t => t !== '') : [];

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
                        reminder_date: newReminder,
                        tags: newTags
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

                    // AJAX UI-Updates WITHOUT Reload
                    // 1. Order Reference (SEC-05: DOM API to prevent XSS)
                    const orderWrapper = document.getElementById('staticOrderRefWrapper');
                    if (orderWrapper) {
                        orderWrapper.textContent = '';
                        if (newOrderRef) {
                            orderWrapper.appendChild(document.createTextNode('\u2022 '));
                            const badge = document.createElement('span');
                            badge.className = 'badge bg-light text-dark border';
                            const icon = document.createElement('i');
                            icon.className = 'bi bi-hash me-1';
                            badge.appendChild(icon);
                            badge.appendChild(document.createTextNode(newOrderRef));
                            orderWrapper.appendChild(badge);
                        }
                    }

                    // 2. Due Date (FIX-16: DOM API eliminates innerHTML with date strings)
                    const dueWrapper = document.getElementById('staticDueWrapper');
                    if (dueWrapper) {
                        dueWrapper.textContent = '';
                        if (newDue) {
                            // Date formatting helper for JS (YYYY-MM-DD -> DD.MM.YYYY)
                            const parts = newDue.split('-');
                            const formatted = `${parts[2]}.${parts[1]}.${parts[0]}`;
                            dueWrapper.appendChild(document.createTextNode('Fällig am '));
                            const dateSpan = document.createElement('span');
                            dateSpan.className = 'fw-bold';
                            dateSpan.textContent = formatted;
                            dueWrapper.appendChild(dateSpan);
                        } else {
                            dueWrapper.textContent = 'Keine Deadline';
                        }
                    }

                    // 3. Tags Update (SEC-06: DOM API prevents XSS)
                    const tagsInput = document.getElementById('editTagsInput');
                    const tagsWrapper = document.getElementById('staticTagsWrapper');
                    if (tagsInput && tagsWrapper) {
                        const tagsList = tagsInput.value.split(',').map(t => t.trim()).filter(t => t !== '');
                        tagsWrapper.innerHTML = '';
                        tagsList.forEach(tag => {
                            const span = document.createElement('span');
                            span.className = 'badge bg-secondary-subtle text-secondary rounded-pill fw-normal';
                            span.style.fontSize = '0.7rem';
                            const icon = document.createElement('i');
                            icon.className = 'bi bi-tag me-1';
                            span.appendChild(icon);
                            span.appendChild(document.createTextNode(tag));
                            tagsWrapper.appendChild(span);
                        });
                    }

                    // 4. Switch back to static view
                    headerStatic.classList.remove('d-none');
                    headerEdit.classList.add('d-none');
                    priorityStatic.classList.remove('d-none');
                    priorityEdit.classList.add('d-none');

                    window.showUiAlert('Ticket erfolgreich aktualisiert.', 'success');
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

window.approveTicket = async function(tId) {
    if (!confirm('Dieses Ticket kaufmännisch freigeben?')) return;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const ingress = document.querySelector('.navbar')?.getAttribute('data-ingress') || '';
    
    try {
        const response = await fetch(`${ingress}/api/ticket/${tId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
        });
        const data = await response.json();
        if (data.success) {
            window.showUiAlert('Ticket freigegeben!', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            window.showUiAlert('Fehler: ' + data.error);
        }
    } catch (e) {
        window.showUiAlert('Netzwerkfehler');
    }
};

window.requestApproval = async function(tId) {
    if (!confirm('Freigabe für dieses Ticket anfordern?')) return;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const ingress = document.querySelector('.navbar')?.getAttribute('data-ingress') || '';
    
    try {
        const response = await fetch(`${ingress}/api/ticket/${tId}/request_approval`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
        });
        const data = await response.json();
        if (data.success) {
            window.showUiAlert('Freigabe erfolgreich angefordert.', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            window.showUiAlert('Fehler: ' + data.error);
        }
    } catch (e) {
        window.showUiAlert('Netzwerkfehler');
    }
};

window.showRejectModal = function(tId) {
    const modalEl = document.getElementById('rejectApprovalModal');
    if (modalEl) {
        document.getElementById('rejectTicketId').value = tId;
        document.getElementById('rejectReasonInput').value = '';
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();
    }
};

document.addEventListener('DOMContentLoaded', function() {
    const submitRejectBtn = document.getElementById('submitRejectBtn');
    if (submitRejectBtn) {
        submitRejectBtn.addEventListener('click', async function() {
            const tId = document.getElementById('rejectTicketId').value;
            const reason = document.getElementById('rejectReasonInput').value.trim();
            if (!reason) {
                window.showUiAlert('Bitte geben Sie einen Grund an.', 'warning');
                return;
            }
            
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            const ingress = document.querySelector('.navbar')?.getAttribute('data-ingress') || '';
            
            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Wird abgelehnt...';
            
            try {
                const response = await fetch(`${ingress}/api/ticket/${tId}/reject`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ reason: reason })
                });
                const data = await response.json();
                if (data.success) {
                    window.showUiAlert('Ticket wurde abgelehnt.', 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    window.showUiAlert('Fehler: ' + data.error);
                    this.disabled = false;
                    this.textContent = 'Ablehnen';
                }
            } catch (e) {
                window.showUiAlert('Netzwerkfehler');
                this.disabled = false;
                this.textContent = 'Ablehnen';
            }
        });
    }
});

// Checklist Logic
document.addEventListener('DOMContentLoaded', function() {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const ingress = document.querySelector('.navbar')?.getAttribute('data-ingress') || '';
    const ticketWrapper = document.getElementById('ticketDetailWrapper');
    const tId = ticketWrapper ? ticketWrapper.dataset.ticketId : null;
    
    if (!tId) return;

    // Add Checklist Item
    const addBtn = document.getElementById('add-checklist-btn');
    if (addBtn) {
        addBtn.addEventListener('click', async () => {
            const titleInput = document.getElementById('new-checklist-title');
            const assignInput = document.getElementById('new-checklist-assignee');
            const teamInput = document.getElementById('new-checklist-team');
            const dueInput = document.getElementById('new-checklist-due');
            const dependInput = document.getElementById('new-checklist-depends');
            
            const title = titleInput.value.trim();
            const assignee = assignInput ? assignInput.value : '';
            const team = teamInput ? teamInput.value : '';
            const due = dueInput ? dueInput.value : '';
            const depend = dependInput ? dependInput.value : '';
            
            if (!title) return;
            addBtn.disabled = true;
            
            const payload = { 
                title: title, 
                assigned_to_id: assignee,
                assigned_team_id: team,
                due_date: due,
                depends_on_item_id: depend
            };
            
            try {
                const response = await fetch(`${ingress}/api/ticket/${tId}/checklist`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (data.success) {
                    location.reload();
                } else {
                    window.showUiAlert('Fehler: ' + data.error);
                    addBtn.disabled = false;
                }
            } catch (e) {
                addBtn.disabled = false;
            }
        });
    }

    // Toggle Checklist items
    document.querySelectorAll('.checklist-toggle').forEach(el => {
        el.addEventListener('change', async (e) => {
            const cb = e.target;
            const itemDiv = cb.closest('.checklist-item');
            const itemId = itemDiv.dataset.id;
            cb.disabled = true;
            
            try {
                const response = await fetch(`${ingress}/api/checklist/${itemId}/toggle`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                });
                const data = await response.json();
                if (data.success) {
                    cb.disabled = false;
                    const label = itemDiv.querySelector('label');
                    if (data.is_completed) {
                        label.classList.add('text-decoration-line-through', 'text-muted');
                        label.classList.remove('fw-semibold');
                    } else {
                        label.classList.remove('text-decoration-line-through', 'text-muted');
                        label.classList.add('fw-semibold');
                    }
                } else {
                    cb.checked = !cb.checked; // revert
                    cb.disabled = false;
                }
            } catch (err) {
                cb.checked = !cb.checked;
                cb.disabled = false;
            }
        });
    });

    // Delete Checklist items
    document.querySelectorAll('.checklist-delete').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            if (!confirm('Unteraufgabe löschen?')) return;
            const itemDiv = e.target.closest('.checklist-item');
            const itemId = itemDiv.dataset.id;
            
            try {
                const response = await fetch(`${ingress}/api/checklist/${itemId}`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                });
                const data = await response.json();
                if (data.success) {
                    itemDiv.remove();
                    if (document.querySelectorAll('.checklist-item').length === 0) {
                        location.reload(); // To show empty state
                    }
                } else {
                    window.showUiAlert('Fehler: ' + data.error);
                }
            } catch (err) {}
        });
    });

    // Command Palette hotkey (Cmd+K) for advanced checklists
    const clTitleInput = document.getElementById('new-checklist-title');
    if (clTitleInput) {
        clTitleInput.addEventListener('keydown', (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                const collapseEl = document.getElementById('advancedChecklistOptions');
                if (collapseEl) {
                    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(collapseEl);
                    bsCollapse.toggle();
                }
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (addBtn) addBtn.click();
            }
        });
    }
});
