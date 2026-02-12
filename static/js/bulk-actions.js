/**
 * Bulk Actions — select-all toggle, count tracking, action bar visibility.
 *
 * Expects:
 *   #select-all         — header checkbox (may appear later via HTMX swap)
 *   input[name=selected] — row checkboxes
 *   #bulk-bar            — action bar (hidden by default)
 *   #bulk-count          — span showing selected count
 *
 * All DOM lookups are dynamic so elements swapped in by HTMX are found.
 */
document.addEventListener('DOMContentLoaded', function () {

    function getBar() {
        return document.getElementById('bulk-bar');
    }

    function getCountEl() {
        return document.getElementById('bulk-count');
    }

    function getSelectAll() {
        return document.getElementById('select-all');
    }

    function getCheckboxes() {
        return document.querySelectorAll('input[name="selected"]');
    }

    function updateBar() {
        const bar = getBar();
        const countEl = getCountEl();
        const selectAll = getSelectAll();
        const boxes = getCheckboxes();
        const checked = Array.from(boxes).filter(cb => cb.checked).length;
        if (bar) {
            if (checked > 0) {
                bar.classList.remove('hidden');
                if (countEl) countEl.textContent = checked;
            } else {
                bar.classList.add('hidden');
            }
        }
        // Sync select-all state
        if (selectAll) {
            selectAll.checked = boxes.length > 0 && checked === boxes.length;
            selectAll.indeterminate = checked > 0 && checked < boxes.length;
        }
    }

    // Delegate change events — handles both select-all and row checkboxes
    // even when they appear after HTMX swaps
    document.addEventListener('change', function (e) {
        if (e.target.id === 'select-all') {
            getCheckboxes().forEach(cb => { cb.checked = e.target.checked; });
            updateBar();
        } else if (e.target.name === 'selected') {
            updateBar();
        }
    });

    // After HTMX swaps table rows, reset select-all and bar
    document.body.addEventListener('htmx:afterSwap', function (e) {
        if (e.detail.target.tagName === 'TBODY' || e.detail.target.id === 'note-content' || e.detail.target.id === 'task-content' || e.detail.target.id === 'note-card-list' || e.detail.target.id === 'asset-content') {
            const selectAll = getSelectAll();
            if (selectAll) {
                selectAll.checked = false;
                selectAll.indeterminate = false;
            }
            const bar = getBar();
            if (bar) bar.classList.add('hidden');
        }
    });
});
