// Dismiss liquidity alerts — persists in sessionStorage for current browser session
(function () {
    const STORAGE_KEY = 'dismissed_alerts';

    function getDismissed() {
        try {
            return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || [];
        } catch {
            return [];
        }
    }

    function dismiss(key) {
        const dismissed = getDismissed();
        if (!dismissed.includes(key)) {
            dismissed.push(key);
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(dismissed));
        }
    }

    function hideAlreadyDismissed() {
        const dismissed = getDismissed();
        document.querySelectorAll('[data-alert-key]').forEach(function (el) {
            if (dismissed.includes(el.getAttribute('data-alert-key'))) {
                el.style.display = 'none';
            }
        });
    }

    function bindButtons() {
        document.querySelectorAll('[data-dismiss-alert]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var alert = btn.closest('[data-alert-key]');
                if (alert) {
                    dismiss(alert.getAttribute('data-alert-key'));
                    alert.style.display = 'none';
                }
            });
        });
    }

    hideAlreadyDismissed();
    bindButtons();
})();
