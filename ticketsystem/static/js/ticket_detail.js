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

    // Status select is now handled by segmented controls above
    if (statusSelect) {
        toggleReminderField(statusSelect.value);
    }

    if (assignSelect) {
        assignSelect.addEventListener('change', async function() {
            const workerId = this.value;
            const workerName = this.options[this.selectedIndex].text;
            const originalValue = this.dataset.original;

            // Find spinner in wrapper
            const wrapper = this.closest('.position-relative');
            const spinner = wrapper ? wrapper.querySelector('.select-spinner') : null;

            this.disabled = true;
            this.classList.add('opacity-50');
            if (spinner) spinner.classList.remove('d-none');

            // Build payload: handle team_ prefix for team assignment
            const payload = {};
            if (workerId && workerId.startsWith('team_')) {
                payload.worker_id = null;
                payload.team_id = parseInt(workerId.substring(5));
            } else {
                payload.worker_id = workerId ? parseInt(workerId) : null;
            }

            try {
                const response = await fetch(`${getIngress()}/api/ticket/${ticketId}/assign`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                
                if (spinner) spinner.classList.add('d-none');
                
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
                if (spinner) spinner.classList.add('d-none');
                window.showUiAlert('Netzwerkfehler bei der Zuweisung.');
                this.disabled = false;
                this.classList.remove('opacity-50');
                this.value = originalValue;
            }
        });
    }

    // --- Segmented Status Controls (UX Redesign Vorschlag 7) ---
    const statusSegmented = document.getElementById('statusSegmented');
    const statusDoneBtn = document.getElementById('statusDoneBtn');
    const statusHiddenSelect = document.getElementById('statusSelect');

    const updateStatusUI = (newStatus) => {
        // Update segmented buttons active state
        if (statusSegmented) {
            statusSegmented.querySelectorAll('button').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.status === newStatus);
            });
        }
        // Update done button
        if (statusDoneBtn) {
            statusDoneBtn.classList.toggle('active', newStatus === 'erledigt');
        }
        // Update hidden select for compatibility
        if (statusHiddenSelect) {
            statusHiddenSelect.value = newStatus;
            statusHiddenSelect.dataset.original = newStatus;
        }
        toggleReminderField(newStatus);
    };

    const sendStatusChange = async (newStatus, btn) => {
        const original = statusHiddenSelect ? statusHiddenSelect.dataset.original : '';
        btn.disabled = true;
        btn.classList.add('opacity-50');

        try {
            const response = await fetch(`${getIngress()}/api/ticket/${ticketId}/status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ status: newStatus })
            });
            const data = await response.json();
            if (data.success) {
                updateStatusUI(newStatus);
                window.showUiAlert('Status erfolgreich aktualisiert.', 'success');
            } else {
                window.showUiAlert('Fehler: ' + data.error);
                updateStatusUI(original);
            }
        } catch (error) {
            window.showUiAlert('Netzwerkfehler beim Aktualisieren.');
            updateStatusUI(original);
        } finally {
            btn.disabled = false;
            btn.classList.remove('opacity-50');
        }
    };

    if (statusSegmented) {
        statusSegmented.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', function() {
                if (this.classList.contains('active')) return;
                sendStatusChange(this.dataset.status, this);
            });
        });
    }
    if (statusDoneBtn) {
        statusDoneBtn.addEventListener('click', async function() {
            if (this.classList.contains('active')) return;
            const confirmed = await window.showConfirm('Ticket abschließen', 'Möchten Sie dieses Ticket wirklich als erledigt markieren?');
            if (!confirmed) return;
            sendStatusChange('erledigt', this);
        });
    }

    // --- Description Truncate (UX Redesign Vorschlag 2) ---
    const descWrapper = document.getElementById('descriptionWrapper');
    const descToggle = document.getElementById('descriptionToggle');
    const descGradient = document.getElementById('descriptionGradient');
    if (descWrapper && descToggle) {
        const checkOverflow = () => {
            if (descWrapper.scrollHeight > 130) {
                descGradient.classList.remove('d-none');
                descToggle.classList.remove('d-none');
            }
        };
        checkOverflow();
        let expanded = false;
        descToggle.addEventListener('click', () => {
            expanded = !expanded;
            if (expanded) {
                descWrapper.style.maxHeight = descWrapper.scrollHeight + 'px';
                descGradient.classList.add('d-none');
                descToggle.textContent = 'Weniger anzeigen';
            } else {
                descWrapper.style.maxHeight = '120px';
                descGradient.classList.remove('d-none');
                descToggle.textContent = 'Mehr lesen';
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
    const editRecurrenceRule = document.getElementById('editRecurrenceRule');
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
            const newRecurrenceRule = editRecurrenceRule ? editRecurrenceRule.value : null;

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
                        tags: newTags,
                        recurrence_rule: newRecurrenceRule
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
                    // 1. Order Reference – Grid Badge (SEC-05: DOM API to prevent XSS)
                    const orderWrapper = document.getElementById('staticOrderRefWrapper');
                    if (orderWrapper) {
                        orderWrapper.textContent = '';
                        if (newOrderRef) {
                            const label = document.createElement('small');
                            label.className = 'text-muted x-small text-uppercase d-block';
                            label.style.cssText = 'font-size: 0.6rem; line-height: 1;';
                            label.textContent = 'Auftrag';
                            orderWrapper.appendChild(label);
                            const val = document.createElement('span');
                            val.className = 'fw-semibold small';
                            val.textContent = newOrderRef;
                            orderWrapper.appendChild(val);
                        }
                    }

                    // 2. Due Date – Grid Badge (FIX-16: DOM API eliminates innerHTML)
                    const dueWrapper = document.getElementById('staticDueWrapper');
                    if (dueWrapper) {
                        dueWrapper.textContent = '';
                        const label = document.createElement('small');
                        label.className = 'text-muted x-small text-uppercase d-block';
                        label.style.cssText = 'font-size: 0.6rem; line-height: 1;';
                        label.textContent = 'Fällig';
                        dueWrapper.appendChild(label);
                        if (newDue) {
                            const parts = newDue.split('-');
                            const formatted = `${parts[2]}.${parts[1]}.${parts[0]}`;
                            const dateSpan = document.createElement('span');
                            dateSpan.className = 'fw-semibold small';
                            dateSpan.textContent = formatted;
                            dueWrapper.appendChild(dateSpan);
                        } else {
                            const noDate = document.createElement('span');
                            noDate.className = 'small text-muted';
                            noDate.textContent = 'Keine Deadline';
                            dueWrapper.appendChild(noDate);
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
            const spinner = itemDiv.querySelector('.loading-indicator');
            const labelText = itemDiv.querySelector('.item-title-text');
            
            cb.disabled = true;
            cb.classList.add('opacity-0');
            if (spinner) spinner.classList.remove('d-none');
            
            try {
                const response = await fetch(`${ingress}/api/checklist/${itemId}/toggle`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                });
                const data = await response.json();
                
                cb.classList.remove('opacity-0');
                if (spinner) spinner.classList.add('d-none');
                
                if (data.success) {
                    cb.disabled = false;
                    if (data.is_completed) {
                        labelText.classList.add('text-decoration-line-through', 'text-muted');
                        labelText.classList.remove('fw-semibold', 'text-body');
                    } else {
                        labelText.classList.remove('text-decoration-line-through', 'text-muted');
                        labelText.classList.add('fw-semibold', 'text-body');
                    }
                } else {
                    window.showUiAlert('Fehler: ' + data.error);
                    cb.checked = !cb.checked;
                    cb.disabled = false;
                }
            } catch (err) {
                cb.classList.remove('opacity-0');
                if (spinner) spinner.classList.add('d-none');
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

    // Apply Template
    const applyTplBtn = document.getElementById('apply-template-btn');
    const applyTplSelect = document.getElementById('apply-template-select');
    if (applyTplBtn && applyTplSelect) {
        applyTplBtn.addEventListener('click', async () => {
            const templateId = applyTplSelect.value;
            if (!templateId) return;
            
            applyTplBtn.disabled = true;
            applyTplBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>...';
            
            try {
                const response = await fetch(`${ingress}/api/ticket/${tId}/apply_template`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ template_id: parseInt(templateId) })
                });
                const data = await response.json();
                if (data.success) {
                    location.reload();
                } else {
                    window.showUiAlert('Fehler: ' + data.error);
                    applyTplBtn.disabled = false;
                    applyTplBtn.textContent = 'Anwenden';
                }
            } catch (e) {
                applyTplBtn.disabled = false;
                applyTplBtn.textContent = 'Anwenden';
            }
        });
    }
});

// CSP-Safe Event Listeners (v1.26.4 Hardening)
document.addEventListener('DOMContentLoaded', function() {
    const commentForm = document.getElementById('commentForm');
    const commentText = commentForm ? commentForm.querySelector('textarea[name="text"]') : null;

    // 1. Shortcut Buttons
    document.querySelectorAll('.shortcut-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const shortcut = this.getAttribute('data-shortcut');
            if (commentText) {
                // Clear active state from others
                document.querySelectorAll('.shortcut-btn').forEach(b => b.classList.remove('btn-secondary', 'active'));
                this.classList.add('btn-secondary', 'active');
                
                commentText.value = shortcut;
                commentText.focus();
            }
        });
    });

    // 2. Approval Actions (Generalized to Classes)
    document.querySelectorAll('.approve-ticket-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const tid = this.getAttribute('data-ticket-id');
            if (window.approveTicket) window.approveTicket(tid);
        });
    });

    document.querySelectorAll('.reject-ticket-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const tid = this.getAttribute('data-ticket-id');
            if (window.showRejectModal) window.showRejectModal(tid);
        });
    });

    document.querySelectorAll('.request-approval-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const tid = this.getAttribute('data-ticket-id');
            if (window.requestApproval) window.requestApproval(tid);
        });
    });
});

// Contact edit logic
document.addEventListener('DOMContentLoaded', function() {
    const saveContactBtn = document.getElementById('saveContactBtn');
    if (!saveContactBtn) return;

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const ingress = document.querySelector('.navbar')?.getAttribute('data-ingress') || '';
    const ticketId = saveContactBtn.dataset.ticketId;

    // Toggle callback-due field visibility
    const callbackCheckbox = document.getElementById('editCallbackRequested');
    const callbackDueWrapper = document.getElementById('editCallbackDueWrapper');
    if (callbackCheckbox && callbackDueWrapper) {
        callbackCheckbox.addEventListener('change', function() {
            if (this.checked) {
                callbackDueWrapper.classList.remove('d-none');
            } else {
                callbackDueWrapper.classList.add('d-none');
                const dueInput = document.getElementById('editCallbackDue');
                if (dueInput) dueInput.value = '';
            }
        });
    }

    saveContactBtn.addEventListener('click', async function() {
        const channelSelect = document.getElementById('editContactChannel');
        const channel = channelSelect ? channelSelect.value : '';
        const name = document.getElementById('editContactName')?.value.trim() || '';
        const phone = document.getElementById('editContactPhone')?.value.trim() || '';
        const email = document.getElementById('editContactEmail')?.value.trim() || '';
        const callbackReq = document.getElementById('editCallbackRequested')?.checked || false;
        const callbackDue = document.getElementById('editCallbackDue')?.value || null;

        this.disabled = true;
        this.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Speichern...';

        try {
            const response = await fetch(`${ingress}/api/ticket/${ticketId}/update_contact`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({
                    contact_name: name || null,
                    contact_phone: phone || null,
                    contact_email: email || null,
                    contact_channel: channel || null,
                    callback_requested: callbackReq,
                    callback_due: callbackDue || null,
                })
            });
            const data = await response.json();
            if (data.success) {
                window.showUiAlert('Kundenkontakt gespeichert.', 'success');
                // Collapse the form and reload to refresh display
                const collapseEl = document.getElementById('contactEditForm');
                if (collapseEl) {
                    bootstrap.Collapse.getOrCreateInstance(collapseEl).hide();
                }
                setTimeout(() => location.reload(), 600);
            } else {
                window.showUiAlert('Fehler: ' + (data.error || 'Unbekannter Fehler'));
                this.disabled = false;
                this.textContent = 'Speichern';
            }
        } catch (e) {
            window.showUiAlert('Netzwerkfehler beim Speichern.');
            this.disabled = false;
            this.textContent = 'Speichern';
        }
    });

    // Note: Duplicate button handler is in ticket_detail.html inline script
    // to avoid issues with JS caching across version updates.

    // --- System Events Toggle (UX Redesign Vorschlag 15) ---
    const toggleEventsBtn = document.getElementById('toggleSystemEvents');
    if (toggleEventsBtn) {
        let eventsVisible = true;
        toggleEventsBtn.addEventListener('click', () => {
            eventsVisible = !eventsVisible;
            document.querySelectorAll('.system-event').forEach(el => {
                el.classList.toggle('d-none', !eventsVisible);
            });
            toggleEventsBtn.textContent = eventsVisible ? 'System-Events ausblenden' : 'System-Events anzeigen';
        });
    }
});
