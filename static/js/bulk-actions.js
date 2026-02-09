/**
 * Bulk Actions — select-all toggle, count tracking, action bar visibility.
 *
 * Expects:
 *   #select-all         — header checkbox
 *   input[name=selected] — row checkboxes
 *   #bulk-bar            — action bar (hidden by default)
 *   #bulk-count          — span showing selected count
 *   #bulk-form           — form wrapping the table (receives selected PKs)
 */
document.addEventListener('DOMContentLoaded', function () {
    const bar = document.getElementById('bulk-bar');
    const countEl = document.getElementById('bulk-count');
    const selectAll = document.getElementById('select-all');
    if (!bar || !selectAll) return;

    function getCheckboxes() {
        return document.querySelectorAll('input[name="selected"]');
    }

    function updateBar() {
        const boxes = getCheckboxes();
        const checked = Array.from(boxes).filter(cb => cb.checked).length;
        if (checked > 0) {
            bar.classList.remove('hidden');
            if (countEl) countEl.textContent = checked;
        } else {
            bar.classList.add('hidden');
        }
        // Sync select-all state
        selectAll.checked = boxes.length > 0 && checked === boxes.length;
        selectAll.indeterminate = checked > 0 && checked < boxes.length;
    }

    // Select-all toggle
    selectAll.addEventListener('change', function () {
        getCheckboxes().forEach(cb => { cb.checked = selectAll.checked; });
        updateBar();
    });

    // Delegate change events for row checkboxes (works with HTMX-swapped content)
    document.addEventListener('change', function (e) {
        if (e.target.name === 'selected') {
            updateBar();
        }
    });

    // After HTMX swaps table rows, reset select-all and bar
    document.body.addEventListener('htmx:afterSwap', function (e) {
        if (e.detail.target.tagName === 'TBODY') {
            selectAll.checked = false;
            selectAll.indeterminate = false;
            bar.classList.add('hidden');
        }
    });
});
