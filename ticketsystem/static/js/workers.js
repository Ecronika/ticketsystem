/* workers.js - Worker Management Logic for v1.2.0 */
document.addEventListener('DOMContentLoaded', function() {
    const editModalEl = document.getElementById('editWorkerModal');
    if (editModalEl) {
        const editModal = new bootstrap.Modal(editModalEl);
        
        document.querySelectorAll('.edit-worker-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const id = this.getAttribute('data-id');
                const role = this.getAttribute('data-role');
                
                document.getElementById('edit_worker_id').value = id;
                document.getElementById('edit_name').value = this.getAttribute('data-name');
                document.getElementById('edit_role').value = role || 'worker';
                const emailEl = document.getElementById('edit_email');
                if (emailEl) emailEl.value = this.getAttribute('data-email') || '';
                
                // P0-1 (v1.5.1): Set worker ID for both possible reset form targets
                ['reset_pin_worker_id', 'reset_pin_worker_id_hidden'].forEach(fieldId => {
                    const el = document.getElementById(fieldId);
                    if (el) el.value = id;
                });

                // Pass relatedTarget so Bootstrap returns focus to trigger button on close
                editModal.show(this);
            });
        });
        
        document.querySelectorAll('.reset-pin-trigger').forEach(btn => {
            btn.addEventListener('click', async function() {
                const confirmed = await window.showConfirm(
                    'PIN zurücksetzen?',
                    'Möchten Sie den PIN wirklich auf 0000 zurücksetzen?',
                    true
                );
                if (confirmed) {
                    document.getElementById('reset_pin_form').submit();
                }
            });
        });
    }
});
