/* ticket_detail.js - Externalized Logic for v1.2.0 */

/** Central UI refresh after attachment count changes (upload/delete). */
function refreshAttachmentsUi() {
    const badge = document.getElementById('attachmentCountBadge');
    const grid = document.getElementById('attachmentGrid');
    const hint = document.getElementById('emptyAttachmentHint');
    if (!grid) return;
    const count = grid.querySelectorAll('.attachment-tile').length;
    if (badge) badge.textContent = count;
    if (hint) hint.classList.toggle('d-none', count > 0);
}

/** Expand attachments collapse if currently closed (after successful upload). */
function expandAttachmentsIfNeeded() {
    var collapseEl = document.getElementById('attachmentsCollapseBody');
    if (collapseEl && !collapseEl.classList.contains('show')) {
        bootstrap.Collapse.getOrCreateInstance(collapseEl).show();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    let lastDocTrigger = null;
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

    const sendStatusChange = async (newStatus, btn, waitReason) => {
        const original = statusHiddenSelect ? statusHiddenSelect.dataset.original : '';
        btn.disabled = true;
        btn.classList.add('opacity-50');

        const payload = { status: newStatus };
        if (waitReason) payload.wait_reason = waitReason;

        try {
            const response = await fetch(`${getIngress()}/api/ticket/${ticketId}/status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify(payload)
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

    // --- Wait-Reason Popover for WARTET status ---
    const waitReasonPopover = document.getElementById('waitReasonPopover');
    let _pendingWartetBtn = null;

    const showWaitReasonPopover = (btn) => {
        _pendingWartetBtn = btn;
        if (waitReasonPopover) waitReasonPopover.classList.remove('d-none');
    };

    const hideWaitReasonPopover = () => {
        _pendingWartetBtn = null;
        if (waitReasonPopover) waitReasonPopover.classList.add('d-none');
    };

    if (waitReasonPopover) {
        waitReasonPopover.querySelectorAll('[data-wait-reason]').forEach(reasonBtn => {
            reasonBtn.addEventListener('click', function() {
                const reason = this.dataset.waitReason;
                const triggerBtn = _pendingWartetBtn;
                hideWaitReasonPopover();
                if (triggerBtn) sendStatusChange('wartet', triggerBtn, reason);
            });
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && !waitReasonPopover.classList.contains('d-none')) {
                hideWaitReasonPopover();
            }
        });

        document.addEventListener('click', function(e) {
            if (!waitReasonPopover.classList.contains('d-none') &&
                !waitReasonPopover.contains(e.target) &&
                e.target !== _pendingWartetBtn) {
                hideWaitReasonPopover();
            }
        });
    }

    if (statusSegmented) {
        statusSegmented.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', function() {
                if (this.classList.contains('active')) return;
                if (this.dataset.status === 'wartet') {
                    showWaitReasonPopover(this);
                } else {
                    hideWaitReasonPopover();
                    sendStatusChange(this.dataset.status, this);
                }
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
            editTitleInput.focus();
        });

        cancelEditBtn.addEventListener('click', () => {
            headerStatic.classList.remove('d-none');
            headerEdit.classList.add('d-none');
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
                    
                    // Priority Badge Update (Grid-based)
                    const prioMap = { '1': 'HOCH', '2': 'MITTEL', '3': 'NIEDRIG' };
                    const classMap = { '1': 'danger', '2': 'primary', '3': 'success' };
                    if (priorityStatic) {
                        const c = classMap[newPrio];
                        priorityStatic.className = `rounded-3 px-2 py-1 bg-${c}-subtle`;
                        const label = priorityStatic.querySelector('small');
                        const val = priorityStatic.querySelector('span');
                        if (label) { label.className = `text-${c} x-small text-uppercase d-block meta-label`; }
                        if (val) { val.className = `fw-semibold small text-${c}`; val.textContent = prioMap[newPrio]; }
                    }

                    // AJAX UI-Updates WITHOUT Reload
                    // 1. Order Reference – Grid Badge (SEC-05: DOM API to prevent XSS)
                    const orderWrapper = document.getElementById('staticOrderRefWrapper');
                    if (orderWrapper) {
                        orderWrapper.textContent = '';
                        if (newOrderRef) {
                            const label = document.createElement('small');
                            label.className = 'text-muted x-small text-uppercase d-block meta-label';
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
                        label.className = 'text-muted x-small text-uppercase d-block meta-label';
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
                            span.className = 'badge bg-secondary-subtle text-secondary rounded-pill fw-normal text-xs';
                            span.appendChild(document.createTextNode(tag));
                            tagsWrapper.appendChild(span);
                        });
                    }

                    // 4. Switch back to static view
                    headerStatic.classList.remove('d-none');
                    headerEdit.classList.add('d-none');

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

    // --- Callback Done Button ---
    const callbackDoneBtn = document.getElementById('callbackDoneBtn');
    if (callbackDoneBtn) {
        callbackDoneBtn.addEventListener('click', async function() {
            const tId = this.dataset.ticketId;
            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Wird gespeichert...';

            try {
                const resp = await fetch(`${getIngress()}/api/ticket/${tId}/callback-done`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                });
                const data = await resp.json();
                if (data.success) {
                    window.showUiAlert('Rückruf als erledigt markiert.', 'success');
                    this.remove();
                } else {
                    const errMsg = window.extractApiError ? window.extractApiError(data) : (data.error || 'Unbekannter Fehler');
                    window.showUiAlert('Fehler: ' + errMsg);
                    this.disabled = false;
                    this.innerHTML = '<i class="bi bi-telephone-check me-1"></i>Rückruf erledigt';
                }
            } catch (e) {
                window.showUiAlert('Netzwerkfehler.');
                this.disabled = false;
                this.innerHTML = '<i class="bi bi-telephone-check me-1"></i>Rückruf erledigt';
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
        if (typeof window.trapFocus === 'function') {
            const onShown = () => {
                window.trapFocus(modalEl);
                modalEl.removeEventListener('shown.bs.modal', onShown);
            };
            modalEl.addEventListener('shown.bs.modal', onShown);
        }
    }
};

document.addEventListener('DOMContentLoaded', function() {
    // Release focus-trap when reject modal closes (attach once).
    const rejectModalEl = document.getElementById('rejectApprovalModal');
    if (rejectModalEl) {
        rejectModalEl.addEventListener('hidden.bs.modal', function() {
            if (typeof window.releaseFocus === 'function') window.releaseFocus();
        });
    }

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
                    // Update dependency locks on items that depend on this one
                    document.querySelectorAll(`.checklist-item[data-depends-on="${itemId}"]`).forEach(depDiv => {
                        const depCb = depDiv.querySelector('.checklist-toggle');
                        const depLabel = depDiv.querySelector('.form-check-label');
                        const cbWrapper = depDiv.querySelector('.position-relative');
                        let lockIcon = depDiv.querySelector('.bi-lock-fill');
                        if (data.is_completed) {
                            // Parent completed -> unlock dependent
                            depDiv.removeAttribute('data-locked');
                            if (depCb) { depCb.disabled = false; depCb.classList.remove('opacity-25'); }
                            if (depLabel) depLabel.classList.remove('text-muted', 'opacity-75');
                            if (lockIcon) lockIcon.remove();
                        } else {
                            // Parent uncompleted -> re-lock dependent
                            depDiv.setAttribute('data-locked', 'true');
                            if (depCb) { depCb.disabled = true; depCb.classList.add('opacity-25'); depCb.checked = false; }
                            if (depLabel) depLabel.classList.add('text-muted', 'opacity-75');
                            // Recreate lock icon if missing
                            if (!lockIcon && cbWrapper) {
                                const icon = document.createElement('i');
                                icon.className = 'bi bi-lock-fill position-absolute text-warning text-xs';
                                icon.title = 'Abhängigkeit nicht abgeschlossen';
                                cbWrapper.appendChild(icon);
                            }
                        }
                    });
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

    // Drag & Drop sorting for checklist items (SortableJS)
    // Only parent items (without data-depends-on) are draggable.
    // Children move together with their parent.
    const checklistContainer = document.getElementById('checklist-container');
    if (checklistContainer && typeof Sortable !== 'undefined') {
        // Helper: collect children that depend on a given parent id
        const getChildren = (parentId) =>
            Array.from(checklistContainer.querySelectorAll(
                `.checklist-item[data-depends-on="${parentId}"]`
            ));

        Sortable.create(checklistContainer, {
            animation: 150,
            draggable: '.checklist-item:not([data-depends-on])',
            ghostClass: 'bg-primary-subtle',
            // After a parent is moved, reposition its children right after it
            onEnd: async function(evt) {
                const movedEl = evt.item;
                const parentId = movedEl.dataset.id;
                // Move children directly after their parent in the DOM
                const children = getChildren(parentId);
                let insertAfter = movedEl;
                children.forEach(child => {
                    insertAfter.after(child);
                    insertAfter = child;
                });
                // Send full order to server
                const items = checklistContainer.querySelectorAll('.checklist-item[data-id]');
                const order = Array.from(items).map(el => parseInt(el.dataset.id));
                try {
                    await fetch(`${ingress}/api/ticket/${tId}/checklist/reorder`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                        body: JSON.stringify({ order })
                    });
                } catch (e) {
                    // Silently fail - order is visual until next reload
                }
            }
        });
    }

    // Attachment grid: event delegation for delete + lightbox
    const grid = document.getElementById('attachmentGrid');
    if (grid) {
        grid.addEventListener('click', async function(e) {
            // Delete button
            const deleteBtn = e.target.closest('.delete-attachment-btn');
            if (deleteBtn) {
                const attachmentId = deleteBtn.dataset.attachmentId;
                const confirmed = window.showConfirm
                    ? await window.showConfirm('Anhang löschen?', 'Möchten Sie diesen Anhang wirklich löschen?', true)
                    : confirm('Anhang wirklich löschen?');
                if (!confirmed) return;
                const originalContent = deleteBtn.innerHTML;
                deleteBtn.disabled = true;
                deleteBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
                try {
                    const resp = await fetch(`${ingress}/api/attachment/${attachmentId}`, {
                        method: 'DELETE',
                        headers: { 'X-CSRFToken': csrfToken }
                    });
                    const data = await resp.json();
                    if (data.success) {
                        const tile = deleteBtn.closest('.attachment-tile');
                        if (tile) tile.remove();
                        refreshAttachmentsUi();
                        if (window.showUiAlert) window.showUiAlert('Anhang gelöscht.', 'success');
                    } else {
                        throw new Error(data.error || 'Löschen fehlgeschlagen');
                    }
                } catch (err) {
                    deleteBtn.disabled = false;
                    deleteBtn.innerHTML = originalContent;
                    if (window.showUiAlert) window.showUiAlert('Fehler: ' + err.message, 'danger');
                }
                return;
            }
            // PDF preview trigger
            const docTrigger = e.target.closest('.doc-preview-trigger');
            if (docTrigger) {
                e.preventDefault();
                lastDocTrigger = docTrigger;
                const dialog = document.getElementById('docPreviewDialog');
                const frame = document.getElementById('docPreviewFrame');
                if (dialog && frame) {
                    document.getElementById('docPreviewTitle').textContent = docTrigger.dataset.docName;
                    document.getElementById('docPreviewDownload').href = docTrigger.dataset.docUrl;
                    frame.title = docTrigger.dataset.docName;
                    frame.src = docTrigger.dataset.docUrl;
                    dialog.showModal();
                }
                return;
            }
            // Lightbox trigger (CSP-safe)
            const trigger = e.target.closest('.lightbox-trigger');
            if (trigger) {
                e.preventDefault();
                const img = document.getElementById('lightboxImg');
                const dialog = document.getElementById('lightboxDialog');
                if (img && dialog) {
                    img.src = trigger.dataset.fullSrc;
                    dialog.showModal();
                    if (typeof window.trapFocus === 'function') window.trapFocus(dialog);
                }
            }
        });
    }

    // Shared dialog close helper
    function initDialogClose(dialog, closeBtn) {
        dialog.addEventListener('click', function(e) {
            if (e.target === dialog) dialog.close();
        });
        if (closeBtn) closeBtn.addEventListener('click', function() { dialog.close(); });
    }

    // Lightbox close handlers (CSP-safe, no inline onclick)
    const lightboxDialog = document.getElementById('lightboxDialog');
    if (lightboxDialog) {
        initDialogClose(lightboxDialog, document.getElementById('lightboxCloseBtn'));
        lightboxDialog.addEventListener('close', function() {
            if (typeof window.releaseFocus === 'function') window.releaseFocus();
        });
    }

    // PDF preview dialog close + cleanup
    const docPreviewDialog = document.getElementById('docPreviewDialog');
    if (docPreviewDialog) {
        initDialogClose(docPreviewDialog, document.getElementById('docPreviewCloseBtn'));
        docPreviewDialog.addEventListener('close', function() {
            const frame = document.getElementById('docPreviewFrame');
            if (frame) frame.removeAttribute('src');
            if (lastDocTrigger) { lastDocTrigger.focus(); lastDocTrigger = null; }
        });
    }

    // Print / PDF button
    const printBtn = document.getElementById('printTicketBtn');
    if (printBtn) {
        printBtn.addEventListener('click', function() { window.print(); });
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

    // --- System Events Toggle – default: hidden ---
    const toggleEventsBtn = document.getElementById('toggleSystemEvents');
    if (toggleEventsBtn) {
        let eventsVisible = false;
        // Hide on load
        document.querySelectorAll('.system-event').forEach(el => el.classList.add('d-none'));
        toggleEventsBtn.addEventListener('click', () => {
            eventsVisible = !eventsVisible;
            document.querySelectorAll('.system-event').forEach(el => {
                el.classList.toggle('d-none', !eventsVisible);
            });
            toggleEventsBtn.textContent = eventsVisible ? 'System-Events ausblenden' : 'System-Events anzeigen';
        });
    }
});

// --- Detail page: file upload logic ---
document.addEventListener('DOMContentLoaded', function() {
    const toggleBtn = document.getElementById('toggleUploadZone');
    const uploadZone = document.getElementById('uploadZone');
    const dropzoneEl = document.getElementById('detailDropzone');
    const fileInput = document.getElementById('detail-attachment-input');
    const uploadBtn = document.getElementById('detailUploadBtn');
    const grid = document.getElementById('attachmentGrid');
    const emptyHint = document.getElementById('emptyAttachmentHint');
    const attachSection = document.getElementById('attachmentsSection');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    const ticketId = document.getElementById('ticketDetailWrapper')?.dataset.ticketId;
    const ingress = document.querySelector('.navbar')?.getAttribute('data-ingress') || '';

    if (!toggleBtn || !uploadZone || !dropzoneEl || !fileInput || !grid) return;
    if (typeof FileUploadManager === 'undefined') return;

    const manager = new FileUploadManager({
        dropzone: dropzoneEl,
        fileInput: fileInput,
        gallery: document.getElementById('detail-attachment-gallery'),
        overlayEl: document.getElementById('detail-compress-overlay'),
        counterEl: document.getElementById('detail-compress-count'),
        workerUrl: dropzoneEl.dataset.workerUrl,
        maxFileSize: Number.parseInt(dropzoneEl.dataset.maxFileSize, 10) || 15728640,
        maxTotalSize: Number.parseInt(dropzoneEl.dataset.maxTotalSize, 10) || 52428800,
        maxFiles: Number.parseInt(dropzoneEl.dataset.maxFiles, 10) || 10
    });

    let isUploading = false;

    manager.onFilesChanged = function() {
        if (uploadBtn) uploadBtn.classList.toggle('d-none', manager.getFileCount() === 0);
    };

    // Toggle upload zone visibility
    toggleBtn.addEventListener('click', function() { uploadZone.classList.toggle('d-none'); });

    // D&D on entire attachments section opens upload zone
    if (attachSection) {
        let sectionDragCounter = 0;
        attachSection.addEventListener('dragenter', function(e) {
            if (e.dataTransfer && e.dataTransfer.types.includes('Files')) {
                sectionDragCounter++;
                uploadZone.classList.remove('d-none');
            }
        });
        attachSection.addEventListener('dragleave', function() { sectionDragCounter--; });
        attachSection.addEventListener('drop', function() { sectionDragCounter = 0; });
    }

    // Upload button click
    if (uploadBtn) {
        uploadBtn.addEventListener('click', function() {
            if (isUploading || manager.isCompressing) {
                if (manager.isCompressing && window.showUiAlert)
                    window.showUiAlert('Bitte warten – Bilder werden noch optimiert.', 'warning');
                return;
            }
            const files = manager.getFiles();
            if (files.length === 0) return;

            isUploading = true;
            uploadBtn.disabled = true;
            const origHTML = uploadBtn.innerHTML;
            uploadBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Lädt...';

            const progressWrapper = document.getElementById('detail-upload-progress');
            const progressFill = document.getElementById('detail-progress-fill');
            const progressPct = document.getElementById('detail-progress-pct');
            const progressLabel = document.getElementById('detail-progress-label');
            if (progressWrapper) progressWrapper.classList.remove('d-none');

            const fd = new FormData();
            files.forEach(function(f) { fd.append('attachments', f); });

            const xhr = new XMLHttpRequest();
            xhr.upload.addEventListener('progress', function(ev) {
                if (!ev.lengthComputable) return;
                var pct = Math.round((ev.loaded / ev.total) * 100);
                if (progressFill) progressFill.style.width = pct + '%';
                if (progressPct) progressPct.textContent = pct + '%';
                if (pct === 100 && progressLabel) progressLabel.textContent = 'Server verarbeitet...';
            });

            var resetUI = function() {
                isUploading = false;
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = origHTML;
                if (progressWrapper) progressWrapper.classList.add('d-none');
                if (progressFill) progressFill.style.width = '0%';
                if (progressPct) progressPct.textContent = '0%';
                if (progressLabel) progressLabel.textContent = 'Wird hochgeladen...';
            };

            xhr.addEventListener('load', function() {
                try {
                    var data = JSON.parse(xhr.responseText);
                    if (data.success && data.html) {
                        // Dedup: only insert tiles not already present
                        var tmp = document.createElement('div');
                        tmp.innerHTML = data.html;
                        tmp.querySelectorAll('[id^="attachment-"]').forEach(function(tile) {
                            if (!document.getElementById(tile.id))
                                grid.insertAdjacentHTML('beforeend', tile.outerHTML);
                        });
                        refreshAttachmentsUi();
                        expandAttachmentsIfNeeded();
                        manager.clearFiles();
                        uploadZone.classList.add('d-none');
                        var msg = data.count + ' Anhänge hochgeladen.';
                        if (data.skipped && data.skipped.length)
                            msg += ' Übersprungen: ' + data.skipped.map(function(s) { return s.name + ' (' + s.reason + ')'; }).join(', ');
                        if (window.showUiAlert) window.showUiAlert(msg, 'success');
                    } else {
                        if (window.showUiAlert) window.showUiAlert('Fehler: ' + (data.error || 'Upload fehlgeschlagen'), 'danger');
                    }
                } catch (_e) {
                    if (window.showUiAlert) window.showUiAlert('Fehler beim Verarbeiten.', 'danger');
                }
                resetUI();
            });
            xhr.addEventListener('error', function() {
                if (window.showUiAlert) window.showUiAlert('Netzwerkfehler beim Hochladen.', 'danger');
                resetUI();
            });

            xhr.open('POST', ingress + '/api/ticket/' + ticketId + '/attachments');
            xhr.setRequestHeader('X-CSRFToken', csrfToken);
            xhr.send(fd);
        });
    }
});
