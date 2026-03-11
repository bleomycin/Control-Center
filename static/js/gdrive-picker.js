/**
 * Google Drive Picker integration for document forms.
 *
 * Config via #gdrive-config data attributes:
 *   data-api-key            — Google API key (for Picker quota)
 *   data-project-number     — Google Cloud project number (numeric, for setAppId)
 *   data-token-url          — Backend endpoint returning {access_token: "..."}
 */
document.addEventListener('DOMContentLoaded', function () {
    var config = document.getElementById('gdrive-config');
    if (!config) return;

    var API_KEY = config.dataset.apiKey;
    var PROJECT_NUMBER = config.dataset.projectNumber;
    var TOKEN_URL = config.dataset.tokenUrl;

    var pickerBtn = document.getElementById('gdrive-picker-btn');
    var clearBtn = document.getElementById('gdrive-clear-btn');
    var selectedDiv = document.getElementById('gdrive-selected-file');
    var selectedName = document.getElementById('gdrive-selected-name');
    var selectedType = document.getElementById('gdrive-selected-type');
    var errorDiv = document.getElementById('gdrive-picker-error');
    var debugPanel = document.getElementById('gdrive-debug');

    if (!pickerBtn) return;

    var pickerApiLoaded = false;
    var btnOriginalHTML = pickerBtn.innerHTML;
    var cachedToken = null;  // store last fetched token for diagnostic tests

    // ─── Debug logging ──────────────────────────────────────────────
    function debugLog(label, value) {
        console.log('[GDrive Picker]', label, value);
        if (debugPanel) {
            var line = document.createElement('div');
            line.className = 'font-mono text-xs';
            var ts = new Date().toLocaleTimeString();
            var valStr = (typeof value === 'object') ? JSON.stringify(value, null, 2) : String(value);
            line.innerHTML = '<span class="text-gray-500">' + ts + '</span> '
                + '<span class="text-blue-400">' + label + '</span> '
                + '<pre class="text-gray-300 whitespace-pre-wrap inline">' + valStr.replace(/</g, '&lt;') + '</pre>';
            debugPanel.appendChild(line);
            debugPanel.scrollTop = debugPanel.scrollHeight;
        }
    }

    debugLog('CONFIG', {
        apiKey: API_KEY ? (API_KEY.substring(0, 12) + '...') : '(empty)',
        projectNumber: PROJECT_NUMBER || '(empty)',
        tokenUrl: TOKEN_URL,
        origin: window.location.origin,
    });

    // ─── Intercept iframe errors ────────────────────────────────────
    var iframeObserver = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
            m.addedNodes.forEach(function (node) {
                if (node.tagName === 'IFRAME') {
                    debugLog('IFRAME ADDED', { src: (node.src || '').substring(0, 200) + '...' });
                    node.addEventListener('load', function () {
                        debugLog('IFRAME LOADED', 'OK');
                    });
                }
            });
        });
    });
    iframeObserver.observe(document.body, { childList: true, subtree: true });

    window.addEventListener('message', function (evt) {
        if (evt.origin && evt.origin.indexOf('google') !== -1) {
            var preview = '';
            try { preview = (typeof evt.data === 'string') ? evt.data.substring(0, 300) : JSON.stringify(evt.data).substring(0, 300); } catch(e) {}
            debugLog('POSTMESSAGE', { origin: evt.origin, data: preview });
        }
    });

    // Load the Google Picker API (once)
    function loadPickerApi() {
        return new Promise(function (resolve, reject) {
            if (pickerApiLoaded) { resolve(); return; }
            if (typeof gapi === 'undefined') {
                setTimeout(function () { reject(new Error('Google APIs not loaded.')); }, 400);
                return;
            }
            gapi.load('picker', {
                callback: function () { pickerApiLoaded = true; debugLog('LOADED', 'Picker API ready'); resolve(); },
                onerror: function () { reject(new Error('Failed to load Picker API')); }
            });
        });
    }

    // Fetch a fresh access token from Django backend
    function fetchToken() {
        debugLog('TOKEN', 'Fetching...');
        return fetch(TOKEN_URL, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (resp) {
            if (!resp.ok) throw new Error('Token request failed (' + resp.status + ')');
            return resp.json();
        })
        .then(function (data) {
            if (data.error) throw new Error(data.error);
            debugLog('TOKEN OK', {
                tokenPrefix: data.access_token ? data.access_token.substring(0, 20) + '...' : '(empty)',
                scopes: data.scopes,
                expired: data.expired,
                project_number: data.project_number,
                client_id_prefix: data.client_id_prefix,
            });
            cachedToken = data.access_token;
            return data.access_token;
        });
    }

    // Create and show the Picker with specific config
    function createPicker(accessToken, options) {
        options = options || {};
        var useAppId = options.appId !== false;
        var useOrigin = options.origin !== false;
        var useDevKey = options.devKey !== false;

        var docsView = new google.picker.DocsView()
            .setIncludeFolders(true)
            .setSelectFolderEnabled(false);

        var configDesc = {
            devKey: useDevKey,
            appId: useAppId ? (PROJECT_NUMBER || '(empty!)') : false,
            origin: useOrigin ? window.location.origin : false,
        };
        debugLog('BUILDING PICKER', configDesc);

        var builder = new google.picker.PickerBuilder()
            .addView(docsView)
            .addView(google.picker.ViewId.RECENTLY_PICKED)
            .setOAuthToken(accessToken)
            .setCallback(pickerCallback)
            .setTitle('Select a file from Google Drive')
            .setMaxItems(1);

        if (useDevKey && API_KEY) {
            builder.setDeveloperKey(API_KEY);
        }
        if (useAppId && PROJECT_NUMBER) {
            builder.setAppId(PROJECT_NUMBER);
        }
        if (useOrigin) {
            builder.setOrigin(window.location.protocol + '//' + window.location.host);
        }

        builder.build().setVisible(true);
        debugLog('PICKER VISIBLE', 'Displayed');
    }

    // Handle file selection
    function pickerCallback(data) {
        debugLog('CALLBACK', { action: data.action, docs: data.docs });
        if (data.action === google.picker.Action.PICKED) {
            populateForm(data.docs[0]);
        }
    }

    function populateForm(file) {
        document.getElementById('id_gdrive_file_id').value = file.id;
        document.getElementById('id_gdrive_mime_type').value = file.mimeType || '';
        document.getElementById('id_gdrive_file_name').value = file.name || '';
        var url = file.url || ('https://drive.google.com/file/d/' + file.id + '/view');
        document.getElementById('id_gdrive_url').value = url;
        var titleInput = document.getElementById('id_title');
        if (titleInput && !titleInput.value.trim()) {
            var name = file.name || '';
            var dotIndex = name.lastIndexOf('.');
            titleInput.value = dotIndex > 0 ? name.substring(0, dotIndex) : name;
        }
        showSelected(file.name, file.mimeType);
        hideError();
    }

    function showSelected(name, mimeType) {
        selectedName.textContent = name || 'Selected file';
        selectedType.textContent = mimeType || '';
        selectedDiv.classList.remove('hidden');
    }

    function clearSelection() {
        document.getElementById('id_gdrive_file_id').value = '';
        document.getElementById('id_gdrive_mime_type').value = '';
        document.getElementById('id_gdrive_file_name').value = '';
        document.getElementById('id_gdrive_url').value = '';
        selectedDiv.classList.add('hidden');
    }

    function showError(msg) { errorDiv.textContent = msg; errorDiv.classList.remove('hidden'); }
    function hideError() { errorDiv.classList.add('hidden'); }

    // Main button handler — default: no appId, no origin (known working config)
    pickerBtn.addEventListener('click', function () {
        hideError();
        if (debugPanel) debugPanel.innerHTML = '';
        pickerBtn.disabled = true;
        pickerBtn.innerHTML = '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg><span>Loading...</span>';

        debugLog('CLICK', 'Pick from Google Drive (appId + devKey, no origin)');

        Promise.all([loadPickerApi(), fetchToken()])
            .then(function (results) {
                createPicker(results[1], { appId: true, origin: false, devKey: true });
            })
            .catch(function (err) { showError('Could not open Picker: ' + err.message); })
            .finally(function () { pickerBtn.disabled = false; pickerBtn.innerHTML = btnOriginalHTML; });
    });

    if (clearBtn) { clearBtn.addEventListener('click', clearSelection); }

    // Edit mode: show feedback if Drive data already exists
    var existingFileId = document.getElementById('id_gdrive_file_id');
    var existingFileName = document.getElementById('id_gdrive_file_name');
    if (existingFileId && existingFileId.value) {
        var existingMimeType = document.getElementById('id_gdrive_mime_type');
        showSelected(
            existingFileName ? existingFileName.value : '',
            existingMimeType ? existingMimeType.value : ''
        );
    }

    // ─── Diagnostic test buttons ────────────────────────────────────
    // Expose functions for diagnostic buttons in the debug panel
    window._gdriveDebug = {
        testDriveApi: function () {
            if (!cachedToken) {
                debugLog('TEST', 'No token cached — click Pick first');
                return;
            }
            debugLog('TEST', 'Calling Drive API v3/files directly...');
            var url = 'https://www.googleapis.com/drive/v3/files?pageSize=1&fields=files(id,name)&key=' + API_KEY;
            fetch(url, { headers: { 'Authorization': 'Bearer ' + cachedToken } })
            .then(function (r) {
                debugLog('DRIVE API STATUS', r.status);
                return r.json();
            })
            .then(function (data) { debugLog('DRIVE API RESPONSE', data); })
            .catch(function (e) { debugLog('DRIVE API ERROR', e.message); });
        },
        testPickerWithAppId: function () {
            if (!cachedToken) { debugLog('TEST', 'No token cached — click Pick first'); return; }
            if (!pickerApiLoaded) { debugLog('TEST', 'Picker API not loaded yet'); return; }
            debugLog('TEST', 'Opening Picker WITH appId + origin...');
            createPicker(cachedToken, { appId: true, origin: true, devKey: true });
        },
        testPickerAppIdOnly: function () {
            if (!cachedToken) { debugLog('TEST', 'No token cached — click Pick first'); return; }
            if (!pickerApiLoaded) { debugLog('TEST', 'Picker API not loaded yet'); return; }
            debugLog('TEST', 'Opening Picker WITH appId, WITHOUT origin...');
            createPicker(cachedToken, { appId: true, origin: false, devKey: true });
        },
        testPickerNoDevKey: function () {
            if (!cachedToken) { debugLog('TEST', 'No token cached — click Pick first'); return; }
            if (!pickerApiLoaded) { debugLog('TEST', 'Picker API not loaded yet'); return; }
            debugLog('TEST', 'Opening Picker WITH appId + origin, WITHOUT developerKey...');
            createPicker(cachedToken, { appId: true, origin: true, devKey: false });
        },
        testPickerOriginOnly: function () {
            if (!cachedToken) { debugLog('TEST', 'No token cached — click Pick first'); return; }
            if (!pickerApiLoaded) { debugLog('TEST', 'Picker API not loaded yet'); return; }
            debugLog('TEST', 'Opening Picker WITHOUT appId, WITH origin...');
            createPicker(cachedToken, { appId: false, origin: true, devKey: true });
        },
    };
});
