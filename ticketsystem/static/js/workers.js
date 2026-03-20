/* workers.js - Worker Management Logic for v1.2.0 */
document.addEventListener('DOMContentLoaded', function() {
    const editModalEl = document.getElementById('editWorkerModal');
    if (editModalEl) {
        const editModal = new bootstrap.Modal(editModalEl);
        
        document.querySelectorAll('.edit-worker-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const id = this.getAttribute('data-id');
                const name = this.getAttribute('data-name');
                const isAdmin = this.getAttribute('data-admin') === 'true';
                
                document.getElementById('edit_worker_id').value = id;
                document.getElementById('edit_name').value = name;
                document.getElementById('edit_is_admin').checked = isAdmin;

                // Pass relatedTarget so Bootstrap returns focus to trigger button on close
                editModal.show(this);
            });
        });
    }
});
