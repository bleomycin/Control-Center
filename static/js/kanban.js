/**
 * Kanban Board — SortableJS drag-and-drop for task status management.
 *
 * Initializes Sortable on each .kanban-column, enabling cross-column drag.
 * On drop, POSTs the new status to the kanban-update endpoint.
 */
document.addEventListener('DOMContentLoaded', function () {
    initKanban();
});

// Re-init after HTMX swaps (e.g. filter changes)
document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target.id === 'task-content') {
        initKanban();
    }
});

function initKanban() {
    var columns = document.querySelectorAll('.kanban-column');
    if (!columns.length || typeof Sortable === 'undefined') return;

    columns.forEach(function (col) {
        // Destroy existing Sortable instance if any
        if (col.sortableInstance) {
            col.sortableInstance.destroy();
        }
        col.sortableInstance = Sortable.create(col, {
            group: 'kanban',
            animation: 150,
            ghostClass: 'opacity-30',
            dragClass: 'ring-2 ring-blue-500 rounded-lg',
            filter: '.kanban-empty',
            onEnd: function (evt) {
                var taskId = evt.item.dataset.taskId;
                var newStatus = evt.to.dataset.status;
                var oldStatus = evt.from.dataset.status;
                if (newStatus === oldStatus) return;

                // Remove empty placeholders from target column
                var empties = evt.to.querySelectorAll('.kanban-empty');
                empties.forEach(function (el) { el.remove(); });

                // Add placeholder to source if now empty
                if (evt.from.children.length === 0) {
                    var placeholder = document.createElement('div');
                    placeholder.className = 'kanban-empty border-2 border-dashed border-gray-700 rounded-lg p-4 text-center text-xs text-gray-500';
                    placeholder.textContent = 'Drop tasks here';
                    evt.from.appendChild(placeholder);
                }

                // Update column count badges
                updateColumnCounts();

                // POST status update
                var csrfToken = document.querySelector('[hx-headers]');
                var token = '';
                if (csrfToken) {
                    try {
                        token = JSON.parse(csrfToken.getAttribute('hx-headers'))['X-CSRFToken'];
                    } catch (e) {}
                }

                fetch('/tasks/' + taskId + '/kanban-update/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': token,
                    },
                    body: 'status=' + encodeURIComponent(newStatus),
                }).then(function (resp) {
                    if (!resp.ok) {
                        // Revert on failure — move card back
                        evt.from.appendChild(evt.item);
                        updateColumnCounts();
                    }
                });
            },
        });
    });
}

function updateColumnCounts() {
    document.querySelectorAll('.kanban-column').forEach(function (col) {
        var count = col.querySelectorAll('.kanban-card').length;
        // The count badge is the sibling span in the header above
        var wrapper = col.closest('div').parentElement;
        var badge = wrapper ? wrapper.querySelector('.rounded-full') : null;
        if (badge) badge.textContent = count;
    });
}
