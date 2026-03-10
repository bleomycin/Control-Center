/**
 * Google Drive Picker integration for document forms.
 *
 * Config via #gdrive-config data attributes:
 *   data-api-key            — Google API key (for Picker quota)
 *   data-project-number     — Google Cloud project number (numeric, for setAppId)
 *   data-token-url          — Backend endpoint returning {access_token: "..."}
 *
 * DOM elements (IDs):
 *   gdrive-picker-btn     — button to open the picker
 *   gdrive-clear-btn      — button to clear selection
 *   gdrive-selected-file  — feedback div (hidden by default)
 *   gdrive-selected-name  — filename display
 *   gdrive-selected-type  — MIME type display
 *   gdrive-picker-error   — error display
 *   id_title              — Django form title input
 *   id_gdrive_url         — Django form URL input
 *   id_gdrive_file_id     — Django form hidden input
 *   id_gdrive_mime_type   — Django form hidden input
 *   id_gdrive_file_name   — Django form hidden input
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
                + '<span class="text-gray-300">' + valStr.replace(/</g, '&lt;') + '</span>';
            debugPanel.appendChild(line);
            debugPanel.scrollTop = debugPanel.scrollHeight;
        }
    }

    debugLog('CONFIG', {
        apiKey: API_KEY ? (API_KEY.substring(0, 8) + '...') : '(empty)',
        projectNumber: PROJECT_NUMBER || '(empty)',
        tokenUrl: TOKEN_URL,
        origin: window.location.origin,
    });

    // ─── Intercept iframe errors ────────────────────────────────────
    // Watch for new iframes (the Picker creates one on docs.google.com)
    var iframeObserver = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
            m.addedNodes.forEach(function (node) {
                if (node.tagName === 'IFRAME') {
                    debugLog('IFRAME ADDED', {
                        src: node.src || '(empty)',
                        id: node.id || '(none)',
                        className: node.className || '(none)',
                    });
                    node.addEventListener('load', function () {
                        debugLog('IFRAME LOADED', { src: node.src });
                    });
                }
            });
        });
    });
    iframeObserver.observe(document.body, { childList: true, subtree: true });

    // Capture console errors that might come from picker
    var origConsoleError = console.error;
    console.error = function () {
        var args = Array.prototype.slice.call(arguments);
        debugLog('CONSOLE.ERROR', args.map(function (a) {
            return (typeof a === 'object') ? JSON.stringify(a) : String(a);
        }).join(' '));
        origConsoleError.apply(console, arguments);
    };

    // Capture unhandled errors
    window.addEventListener('error', function (evt) {
        debugLog('WINDOW ERROR', {
            message: evt.message,
            filename: evt.filename,
            lineno: evt.lineno,
        });
    });

    // Capture postMessage events from the Picker iframe
    window.addEventListener('message', function (evt) {
        if (evt.origin && evt.origin.indexOf('google') !== -1) {
            var dataPreview = '';
            try {
                dataPreview = (typeof evt.data === 'string')
                    ? evt.data.substring(0, 500)
                    : JSON.stringify(evt.data).substring(0, 500);
            } catch (e) {
                dataPreview = '(unable to serialize)';
            }
            debugLog('POSTMESSAGE from ' + evt.origin, dataPreview);
        }
    });

    // Load the Google Picker API (once)
    function loadPickerApi() {
        return new Promise(function (resolve, reject) {
            if (pickerApiLoaded) { resolve(); return; }
            if (typeof gapi === 'undefined') {
                debugLog('ERROR', 'gapi not loaded');
                setTimeout(function () {
                    reject(new Error('Google APIs not loaded. Check your internet connection.'));
                }, 400);
                return;
            }
            debugLog('LOADING', 'gapi.load("picker") starting...');
            gapi.load('picker', {
                callback: function () {
                    pickerApiLoaded = true;
                    debugLog('LOADED', 'Picker API ready');
                    resolve();
                },
                onerror: function () {
                    debugLog('ERROR', 'gapi.load("picker") failed');
                    reject(new Error('Failed to load Picker API'));
                }
            });
        });
    }

    // Fetch a fresh access token from Django backend
    function fetchToken() {
        debugLog('TOKEN', 'Fetching from ' + TOKEN_URL);
        return fetch(TOKEN_URL, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (resp) {
            debugLog('TOKEN RESPONSE', { status: resp.status, ok: resp.ok });
            if (!resp.ok) throw new Error('Token request failed (' + resp.status + ')');
            return resp.json();
        })
        .then(function (data) {
            if (data.error) {
                debugLog('TOKEN ERROR', data.error);
                throw new Error(data.error);
            }
            debugLog('TOKEN OK', {
                tokenPrefix: data.access_token ? data.access_token.substring(0, 20) + '...' : '(empty)',
                scopes: data.scopes || '(not returned)',
            });
            return data.access_token;
        });
    }

    // Create and show the Picker
    function createPicker(accessToken) {
        var docsView = new google.picker.DocsView()
            .setIncludeFolders(true)
            .setSelectFolderEnabled(false);

        var builderConfig = {
            views: ['DocsView(includeFolders=true)', 'RECENTLY_PICKED'],
            hasOAuthToken: !!accessToken,
            hasDeveloperKey: !!API_KEY,
            hasAppId: !!PROJECT_NUMBER,
            appId: PROJECT_NUMBER || '(not set)',
            origin: window.location.protocol + '//' + window.location.host,
        };

        debugLog('BUILDING PICKER', builderConfig);

        var builder = new google.picker.PickerBuilder()
            .addView(docsView)
            .addView(google.picker.ViewId.RECENTLY_PICKED)
            .setOAuthToken(accessToken)
            .setCallback(pickerCallback)
            .setTitle('Select a file from Google Drive')
            .setMaxItems(1);

        if (API_KEY) {
            builder.setDeveloperKey(API_KEY);
        }
        if (PROJECT_NUMBER) {
            builder.setAppId(PROJECT_NUMBER);
        }
        builder.setOrigin(window.location.protocol + '//' + window.location.host);

        debugLog('SHOWING PICKER', 'build() + setVisible(true)');
        var picker = builder.build();
        picker.setVisible(true);
        debugLog('PICKER VISIBLE', 'Picker should now be displayed');
    }

    // Handle file selection
    function pickerCallback(data) {
        debugLog('PICKER CALLBACK', { action: data.action, docs: data.docs });
        if (data.action === google.picker.Action.PICKED) {
            var file = data.docs[0];
            populateForm(file);
        } else if (data.action === google.picker.Action.CANCEL) {
            debugLog('PICKER', 'User cancelled');
        }
    }

    function populateForm(file) {
        debugLog('SELECTED FILE', {
            id: file.id,
            name: file.name,
            mimeType: file.mimeType,
            url: file.url,
        });

        // Hidden fields
        document.getElementById('id_gdrive_file_id').value = file.id;
        document.getElementById('id_gdrive_mime_type').value = file.mimeType || '';
        document.getElementById('id_gdrive_file_name').value = file.name || '';

        // URL field
        var url = file.url || ('https://drive.google.com/file/d/' + file.id + '/view');
        document.getElementById('id_gdrive_url').value = url;

        // Auto-populate title if empty
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

    function showError(msg) {
        errorDiv.textContent = msg;
        errorDiv.classList.remove('hidden');
    }

    function hideError() {
        errorDiv.classList.add('hidden');
    }

    // Main button handler
    pickerBtn.addEventListener('click', function () {
        hideError();
        if (debugPanel) {
            debugPanel.innerHTML = '';  // Clear previous debug output
        }
        pickerBtn.disabled = true;
        pickerBtn.innerHTML = '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg><span>Loading...</span>';

        debugLog('CLICK', 'Pick from Google Drive button clicked');

        Promise.all([loadPickerApi(), fetchToken()])
            .then(function (results) {
                debugLog('READY', 'Picker API loaded + token acquired');
                createPicker(results[1]);
            })
            .catch(function (err) {
                debugLog('FATAL ERROR', err.message);
                showError('Could not open Picker: ' + err.message);
            })
            .finally(function () {
                pickerBtn.disabled = false;
                pickerBtn.innerHTML = btnOriginalHTML;
            });
    });

    // Clear button
    if (clearBtn) {
        clearBtn.addEventListener('click', clearSelection);
    }

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
});
