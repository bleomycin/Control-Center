/**
 * Google Drive Picker integration for document forms.
 *
 * Config via #gdrive-config data attributes:
 *   data-api-key     — Google API key (for Picker quota)
 *   data-client-id   — OAuth2 client ID
 *   data-token-url   — Backend endpoint returning {access_token: "..."}
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
    var CLIENT_ID = config.dataset.clientId;
    var TOKEN_URL = config.dataset.tokenUrl;
    // Extract numeric project number from client ID (e.g. "209074347755-xxx.apps..." → "209074347755")
    var APP_ID = CLIENT_ID ? CLIENT_ID.split('-')[0] : '';

    var pickerBtn = document.getElementById('gdrive-picker-btn');
    var clearBtn = document.getElementById('gdrive-clear-btn');
    var selectedDiv = document.getElementById('gdrive-selected-file');
    var selectedName = document.getElementById('gdrive-selected-name');
    var selectedType = document.getElementById('gdrive-selected-type');
    var errorDiv = document.getElementById('gdrive-picker-error');

    if (!pickerBtn) return;

    var pickerApiLoaded = false;
    var btnOriginalHTML = pickerBtn.innerHTML;

    // Load the Google Picker API (once)
    function loadPickerApi() {
        return new Promise(function (resolve, reject) {
            if (pickerApiLoaded) { resolve(); return; }
            if (typeof gapi === 'undefined') {
                // Defer rejection so the loading spinner is briefly visible
                setTimeout(function () {
                    reject(new Error('Google APIs not loaded. Check your internet connection.'));
                }, 400);
                return;
            }
            gapi.load('picker', {
                callback: function () { pickerApiLoaded = true; resolve(); },
                onerror: function () { reject(new Error('Failed to load Picker API')); }
            });
        });
    }

    // Fetch a fresh access token from Django backend
    function fetchToken() {
        return fetch(TOKEN_URL, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (resp) {
            if (!resp.ok) throw new Error('Token request failed (' + resp.status + ')');
            return resp.json();
        })
        .then(function (data) {
            if (data.error) throw new Error(data.error);
            return data.access_token;
        });
    }

    // Create and show the Picker
    function createPicker(accessToken) {
        var docsView = new google.picker.DocsView()
            .setIncludeFolders(true)
            .setSelectFolderEnabled(false);

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
        if (APP_ID) {
            builder.setAppId(APP_ID);
        }

        builder.build().setVisible(true);
    }

    // Handle file selection
    function pickerCallback(data) {
        if (data.action === google.picker.Action.PICKED) {
            var file = data.docs[0];
            populateForm(file);
        }
    }

    function populateForm(file) {
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
        pickerBtn.disabled = true;
        pickerBtn.innerHTML = '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg><span>Loading...</span>';

        Promise.all([loadPickerApi(), fetchToken()])
            .then(function (results) {
                createPicker(results[1]);
            })
            .catch(function (err) {
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
