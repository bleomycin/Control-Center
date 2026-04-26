/**
 * Custom Drive Browser Modal — replaces Google's hosted Picker iframe.
 *
 * Variant B (Search First). Reads config from any .gdrive-bulk-picker-btn:
 *   data-entity-type      — entity slug (property, stakeholder, …)
 *   data-entity-pk        — entity primary key
 *   data-bookmarks-url    — GET endpoint for bookmark list
 *   data-bookmark-create  — POST endpoint to create a bookmark
 *   data-folder-url       — GET ?folder_id=… for folder contents
 *   data-search-url       — GET ?q=… for global search
 *   data-path-url         — GET ?folder_id=… for breadcrumb resolution
 *   data-post-url         — POST endpoint that creates+links Documents
 *   data-target           — CSS selector to swap with the response HTML
 *
 * The bookmark rename/delete URLs are derived from the create URL by
 * substituting the bookmark id (server URL pattern: …/<pk>/rename/, …/<pk>/delete/).
 */
(function () {
    'use strict';

    var FOLDER_MIME = 'application/vnd.google-apps.folder';

    var modalEl = null;
    var triggerBtn = null;
    var state = {
        mode: 'browse',          // 'browse' or 'search'
        folderId: 'root',
        breadcrumb: [{ id: 'root', name: 'My Drive' }],
        selected: {},            // { fileId: {id,name,mimeType,url} }
        bookmarks: [],
        searchQuery: '',
        pillMenuTarget: null,    // bookmark obj for the right-click menu
    };
    var searchDebounce = null;
    var labelInputTarget = null; // 'create' or { type:'rename', bookmark }

    function csrf() {
        return (typeof CSRF_TOKEN_GLOBAL !== 'undefined') ? CSRF_TOKEN_GLOBAL : '';
    }

    function $(sel, root) { return (root || modalEl).querySelector(sel); }
    function $$(sel, root) { return Array.prototype.slice.call((root || modalEl).querySelectorAll(sel)); }

    // ---- Open / close ----

    function open(btn) {
        triggerBtn = btn;
        modalEl = document.getElementById('gdrive-browser-modal');
        if (!modalEl) {
            console.warn('[gdrive-browser] modal element not found');
            return;
        }
        state.selected = {};
        state.searchQuery = '';
        state.mode = 'browse';
        state.folderId = 'root';
        state.breadcrumb = [{ id: 'root', name: 'My Drive' }];
        $('#gdb-search').value = '';
        $('#gdb-error').classList.add('hidden');
        $('#gdb-results-badge').classList.add('hidden');
        hideLabelRow();
        hidePillMenu();
        modalEl.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
        updateFooter();
        renderBreadcrumb();
        renderPills();
        updateStarButton();
        loadBookmarks();
        loadFolder('root');
        // Defer focus so the open transition completes
        setTimeout(function () { $('#gdb-search').focus(); }, 30);
    }

    function close() {
        if (!modalEl) return;
        modalEl.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
        hidePillMenu();
        if (searchDebounce) { clearTimeout(searchDebounce); searchDebounce = null; }
    }

    // ---- Networking ----

    function fetchJSON(url, opts) {
        opts = opts || {};
        opts.headers = opts.headers || {};
        opts.headers['X-Requested-With'] = 'XMLHttpRequest';
        return fetch(url, opts).then(function (resp) {
            return resp.json().then(function (data) {
                if (!resp.ok) {
                    var msg = (data && data.error) || ('Request failed (' + resp.status + ')');
                    var err = new Error(msg);
                    err.status = resp.status;
                    throw err;
                }
                return data;
            });
        });
    }

    function postForm(url, fields) {
        var body = new URLSearchParams();
        Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
        return fetchJSON(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrf(),
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: body.toString(),
        });
    }

    function postJSON(url, payload) {
        return fetchJSON(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrf(),
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
    }

    function showError(msg) {
        var el = $('#gdb-error');
        el.textContent = msg;
        el.classList.remove('hidden');
        setTimeout(function () { el.classList.add('hidden'); }, 6000);
    }

    // ---- Bookmarks ----

    function loadBookmarks() {
        return fetchJSON(triggerBtn.dataset.bookmarksUrl)
            .then(function (data) {
                state.bookmarks = data.bookmarks || [];
                renderPills();
            })
            .catch(function (err) { showError('Failed to load bookmarks: ' + err.message); });
    }

    function createBookmark(label, folderId) {
        return postForm(triggerBtn.dataset.bookmarkCreate, {
            label: label,
            folder_id: folderId,
        });
    }

    function bookmarkUrlFor(action, pk) {
        // Derive /api/gdrive-bookmarks/<pk>/<action>/ from the create URL.
        var base = triggerBtn.dataset.bookmarkCreate.replace(/create\/?$/, '');
        return base + pk + '/' + action + '/';
    }

    function renameBookmark(pk, label) {
        return postForm(bookmarkUrlFor('rename', pk), { label: label });
    }

    function deleteBookmark(pk) {
        return postForm(bookmarkUrlFor('delete', pk), {});
    }

    function renderPills() {
        var container = $('#gdb-pills');
        container.innerHTML = '';

        // "My Drive" pill — always first
        container.appendChild(buildHomePill());

        state.bookmarks.forEach(function (bm) {
            container.appendChild(buildBookmarkPill(bm));
        });
    }

    function buildHomePill() {
        var btn = document.createElement('button');
        btn.type = 'button';
        var isActive = state.folderId === 'root' && state.mode === 'browse';
        btn.className = pillClasses(isActive);
        btn.innerHTML =
            '<svg class="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">' +
            '<path d="M12 2 2 22h20L12 2z"/></svg>' +
            'My Drive';
        btn.addEventListener('click', function () {
            navigateTo('root', [{ id: 'root', name: 'My Drive' }]);
        });
        return btn;
    }

    function buildBookmarkPill(bm) {
        var btn = document.createElement('button');
        btn.type = 'button';
        var isActive = state.folderId === bm.folder_id && state.mode === 'browse';
        btn.className = pillClasses(isActive);
        btn.dataset.bookmarkId = bm.id;
        btn.innerHTML =
            '<svg class="w-2.5 h-2.5 text-amber-400" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">' +
            '<path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>' +
            escapeHtml(bm.label);
        btn.addEventListener('click', function () { jumpToBookmark(bm); });
        btn.addEventListener('contextmenu', function (e) {
            e.preventDefault();
            showPillMenu(e.clientX, e.clientY, bm);
        });
        return btn;
    }

    function pillClasses(isActive) {
        var base = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs whitespace-nowrap border transition-colors cursor-pointer';
        if (isActive) {
            return base + ' bg-emerald-500/10 border-emerald-500/40 text-emerald-300';
        }
        return base + ' bg-gray-900/60 border-gray-700 text-gray-300 hover:bg-gray-700 hover:text-white hover:border-gray-600';
    }

    function jumpToBookmark(bm) {
        // Resolve the breadcrumb path so the user lands with full navigation context.
        var url = triggerBtn.dataset.pathUrl + '?folder_id=' + encodeURIComponent(bm.folder_id);
        showFileListLoading();
        fetchJSON(url)
            .then(function (data) {
                navigateTo(bm.folder_id, data.path || [{ id: bm.folder_id, name: bm.label }]);
            })
            .catch(function (err) {
                if (err.status === 404) {
                    handleMissingBookmark(bm);
                } else {
                    showError('Could not open folder: ' + err.message);
                    showFileListEmpty('Failed to load folder.');
                }
            });
    }

    function handleMissingBookmark(bm) {
        var list = $('#gdb-file-list');
        list.innerHTML = '';
        var wrap = document.createElement('div');
        wrap.className = 'p-6 text-center';
        wrap.innerHTML =
            '<p class="text-sm text-gray-300 mb-3">The folder for <strong class="text-white">' + escapeHtml(bm.label) + '</strong> no longer exists in Drive.</p>' +
            '<button type="button" class="px-3 py-1.5 text-xs font-medium bg-red-500/20 text-red-300 border border-red-500/40 rounded-md hover:bg-red-500/30">Remove this bookmark</button>';
        wrap.querySelector('button').addEventListener('click', function () {
            deleteBookmark(bm.id)
                .then(loadBookmarks)
                .then(function () {
                    navigateTo('root', [{ id: 'root', name: 'My Drive' }]);
                })
                .catch(function (err) { showError('Could not remove bookmark: ' + err.message); });
        });
        list.appendChild(wrap);
    }

    // ---- Pill right-click menu ----

    function showPillMenu(x, y, bm) {
        state.pillMenuTarget = bm;
        var menu = $('#gdb-pill-menu');
        menu.classList.remove('hidden');
        // Clamp inside viewport
        var rect = menu.getBoundingClientRect();
        var maxX = window.innerWidth - rect.width - 8;
        var maxY = window.innerHeight - rect.height - 8;
        menu.style.left = Math.min(x, maxX) + 'px';
        menu.style.top = Math.min(y, maxY) + 'px';
    }

    function hidePillMenu() {
        var menu = modalEl ? $('#gdb-pill-menu') : null;
        if (menu) menu.classList.add('hidden');
        state.pillMenuTarget = null;
    }

    // ---- Folder browse ----

    function navigateTo(folderId, breadcrumb) {
        state.mode = 'browse';
        state.folderId = folderId;
        state.breadcrumb = breadcrumb && breadcrumb.length ? breadcrumb : [{ id: 'root', name: 'My Drive' }];
        $('#gdb-search').value = '';
        $('#gdb-results-badge').classList.add('hidden');
        renderBreadcrumb();
        renderPills();      // refresh active state
        updateStarButton();
        loadFolder(folderId);
    }

    function loadFolder(folderId) {
        showFileListLoading();
        var url = triggerBtn.dataset.folderUrl + '?folder_id=' + encodeURIComponent(folderId);
        return fetchJSON(url)
            .then(function (data) {
                if (state.mode !== 'browse' || state.folderId !== folderId) return;
                renderFiles(data.files || [], { allowFolders: true });
            })
            .catch(function (err) {
                if (state.mode !== 'browse' || state.folderId !== folderId) return;
                showFileListEmpty('Failed to load folder.');
                showError(err.message);
            });
    }

    function renderBreadcrumb() {
        var bc = $('#gdb-breadcrumb');
        bc.innerHTML = '';
        state.breadcrumb.forEach(function (crumb, i) {
            if (i > 0) {
                var sep = document.createElement('span');
                sep.className = 'text-gray-600';
                sep.textContent = '›';
                bc.appendChild(sep);
            }
            var isLast = i === state.breadcrumb.length - 1;
            if (isLast) {
                var span = document.createElement('span');
                span.className = 'text-white font-medium truncate max-w-[200px]';
                span.textContent = crumb.name;
                bc.appendChild(span);
            } else {
                var a = document.createElement('button');
                a.type = 'button';
                a.className = 'text-gray-400 hover:text-blue-400 transition-colors truncate max-w-[140px]';
                a.textContent = crumb.name;
                a.addEventListener('click', function () {
                    var newCrumbs = state.breadcrumb.slice(0, i + 1);
                    navigateTo(crumb.id, newCrumbs);
                });
                bc.appendChild(a);
            }
        });
    }

    function updateStarButton() {
        var star = $('#gdb-star');
        var atRoot = state.folderId === 'root';
        var alreadyBookmarked = state.bookmarks.some(function (b) { return b.folder_id === state.folderId; });
        star.disabled = atRoot || alreadyBookmarked || state.mode === 'search';
        if (alreadyBookmarked) {
            star.classList.add('text-amber-400');
            star.title = 'Already bookmarked';
        } else {
            star.classList.remove('text-amber-400');
            star.title = atRoot ? 'Cannot bookmark My Drive root' : 'Bookmark this folder';
        }
    }

    // ---- Search ----

    function runSearch(q) {
        state.mode = 'search';
        state.searchQuery = q;
        showFileListLoading();
        var url = triggerBtn.dataset.searchUrl + '?q=' + encodeURIComponent(q);
        fetchJSON(url)
            .then(function (data) {
                if (state.mode !== 'search' || state.searchQuery !== q) return;
                $('#gdb-results-badge').classList.remove('hidden');
                renderFiles(data.files || [], { allowFolders: false });
                updateStarButton();
            })
            .catch(function (err) {
                showFileListEmpty('Search failed.');
                showError(err.message);
            });
    }

    function exitSearch() {
        $('#gdb-results-badge').classList.add('hidden');
        navigateTo(state.folderId, state.breadcrumb);
    }

    // ---- File list rendering ----

    function showFileListLoading() {
        var list = $('#gdb-file-list');
        list.innerHTML =
            '<div class="p-8 text-center text-sm text-gray-500">' +
            '<svg class="w-5 h-5 mx-auto mb-2 animate-spin text-gray-400" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-dasharray="40" stroke-linecap="round"/></svg>' +
            'Loading…' +
            '</div>';
    }

    function showFileListEmpty(msg) {
        var list = $('#gdb-file-list');
        list.innerHTML = '<div class="p-8 text-center text-sm text-gray-500">' + escapeHtml(msg || 'No files found.') + '</div>';
    }

    function renderFiles(files, opts) {
        var list = $('#gdb-file-list');
        list.innerHTML = '';
        if (!files.length) {
            showFileListEmpty(state.mode === 'search' ? 'No matches.' : 'This folder is empty.');
            return;
        }
        var allowFolders = opts && opts.allowFolders;
        files.forEach(function (f) {
            list.appendChild(buildFileRow(f, allowFolders));
        });
    }

    function buildFileRow(f, allowNavigateFolders) {
        var isFolder = f.mimeType === FOLDER_MIME;
        var row = document.createElement('div');
        var isSelected = !!state.selected[f.id];
        row.className = fileRowClasses(isSelected);
        row.dataset.fileId = f.id;
        row.setAttribute('role', 'option');
        row.setAttribute('aria-selected', isSelected ? 'true' : 'false');

        // Checkbox (hidden for folders)
        var cb = document.createElement('span');
        cb.className = 'flex-shrink-0 w-[18px] h-[18px] rounded border-[1.5px] flex items-center justify-center transition-colors ' +
            (isSelected
                ? 'bg-blue-500 border-blue-500 text-white'
                : 'bg-gray-900/60 border-gray-600');
        if (isFolder) cb.style.visibility = 'hidden';
        if (isSelected) {
            cb.innerHTML = '<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>';
        }
        row.appendChild(cb);

        // Icon
        var icon = document.createElement('span');
        icon.className = 'flex-shrink-0 w-5 h-5 ' + iconColor(f.mimeType);
        icon.innerHTML = iconSvg(f.mimeType);
        row.appendChild(icon);

        // Name
        var name = document.createElement('span');
        name.className = 'flex-1 min-w-0 text-sm truncate ' + (isFolder ? 'text-white font-medium' : 'text-gray-200');
        name.textContent = f.name || '(untitled)';
        row.appendChild(name);

        // Meta
        var meta = document.createElement('span');
        meta.className = 'flex-shrink-0 text-xs text-gray-500 hidden sm:inline w-[95px] truncate text-right';
        meta.textContent = formatDate(f.modifiedTime);
        row.appendChild(meta);

        // Owner
        var owner = document.createElement('span');
        owner.className = 'flex-shrink-0 text-xs text-gray-500 hidden md:inline w-[100px] truncate text-right';
        owner.textContent = formatOwner(f.owners);
        row.appendChild(owner);

        // Folder arrow
        if (isFolder) {
            var arrow = document.createElement('span');
            arrow.className = 'flex-shrink-0 w-4 h-4 text-gray-500';
            arrow.innerHTML = '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="9 6 15 12 9 18"/></svg>';
            row.appendChild(arrow);
        }

        row.addEventListener('click', function () {
            if (isFolder) {
                if (!allowNavigateFolders) {
                    // Search mode: clicking a folder jumps into browse mode there.
                    var url = triggerBtn.dataset.pathUrl + '?folder_id=' + encodeURIComponent(f.id);
                    fetchJSON(url)
                        .then(function (data) {
                            navigateTo(f.id, data.path || [{ id: f.id, name: f.name }]);
                        })
                        .catch(function () {
                            navigateTo(f.id, [{ id: 'root', name: 'My Drive' }, { id: f.id, name: f.name }]);
                        });
                    return;
                }
                var newCrumbs = state.breadcrumb.concat([{ id: f.id, name: f.name }]);
                navigateTo(f.id, newCrumbs);
            } else {
                toggleSelection(f);
            }
        });

        return row;
    }

    function fileRowClasses(isSelected) {
        var base = 'flex items-center gap-3 px-5 py-2 border-b border-gray-700/50 cursor-pointer select-none transition-colors';
        if (isSelected) {
            return base + ' bg-blue-500/10 hover:bg-blue-500/15';
        }
        return base + ' hover:bg-gray-700/40';
    }

    function toggleSelection(f) {
        if (state.selected[f.id]) {
            delete state.selected[f.id];
        } else {
            state.selected[f.id] = {
                id: f.id,
                name: f.name || '',
                mimeType: f.mimeType || '',
                url: f.webViewLink || ('https://drive.google.com/file/d/' + f.id + '/view'),
            };
        }
        // Re-render the row in place
        var row = $('#gdb-file-list').querySelector('[data-file-id="' + cssEscape(f.id) + '"]');
        if (row) {
            var newRow = buildFileRow(f, state.mode === 'browse');
            row.parentNode.replaceChild(newRow, row);
        }
        updateFooter();
    }

    function updateFooter() {
        var n = Object.keys(state.selected).length;
        var label = n + ' file' + (n === 1 ? '' : 's');
        $('#gdb-count').textContent = label;
        var linkBtn = $('#gdb-link');
        linkBtn.textContent = 'Link ' + n + ' file' + (n === 1 ? '' : 's');
        linkBtn.disabled = n === 0;
    }

    // ---- Submit ----

    function linkSelected() {
        var files = Object.keys(state.selected).map(function (k) { return state.selected[k]; });
        if (!files.length) return;
        var btn = $('#gdb-link');
        var originalLabel = btn.textContent;

        // Optional in-page callback path:
        //   data-callback="window-function-name"
        // When present, hand the picked files to the callback and close the
        // modal instead of POSTing. The POST/swap path stays the default for
        // entity-attach buttons (data-post-url + data-target) — see _gdrive_bulk_button.html.
        var callbackName = triggerBtn.dataset.callback;
        if (callbackName) {
            var cb = window[callbackName];
            if (typeof cb === 'function') {
                try { cb(files); } catch (err) { showError('Callback failed: ' + err.message); return; }
                close();
                return;
            }
            showError('Callback "' + callbackName + '" is not a function on window.');
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Linking…';

        var postUrl = triggerBtn.dataset.postUrl;
        var targetSel = triggerBtn.dataset.target;

        fetch(postUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrf(),
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ files: files }),
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error('Bulk link failed (' + resp.status + ')');
                return resp.text();
            })
            .then(function (html) {
                var target = document.querySelector(targetSel);
                if (target) target.innerHTML = html;
                close();
            })
            .catch(function (err) {
                showError('Could not link files: ' + err.message);
                btn.disabled = false;
                btn.textContent = originalLabel;
            });
    }

    // ---- Inline label input (bookmark create / rename) ----

    function showLabelRow(target, defaultValue) {
        labelInputTarget = target;
        var row = $('#gdb-label-row');
        var input = $('#gdb-label-input');
        row.classList.remove('hidden');
        input.value = defaultValue || '';
        input.focus();
        input.select();
    }

    function hideLabelRow() {
        if (modalEl) {
            $('#gdb-label-row').classList.add('hidden');
            $('#gdb-label-input').value = '';
        }
        labelInputTarget = null;
    }

    function commitLabelRow() {
        var label = $('#gdb-label-input').value.trim();
        if (!label) return;
        if (labelInputTarget === 'create') {
            createBookmark(label, state.folderId)
                .then(loadBookmarks)
                .then(function () { updateStarButton(); hideLabelRow(); })
                .catch(function (err) { showError('Could not create bookmark: ' + err.message); });
        } else if (labelInputTarget && labelInputTarget.type === 'rename') {
            var bm = labelInputTarget.bookmark;
            renameBookmark(bm.id, label)
                .then(loadBookmarks)
                .then(hideLabelRow)
                .catch(function (err) { showError('Could not rename: ' + err.message); });
        }
    }

    // ---- Helpers ----

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function cssEscape(s) {
        return String(s).replace(/"/g, '\\"');
    }

    function formatDate(iso) {
        if (!iso) return '';
        var d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return months[d.getMonth()] + ' ' + d.getDate() + ', ' + d.getFullYear();
    }

    function formatOwner(owners) {
        if (!owners || !owners.length) return '';
        var o = owners[0];
        return o.displayName || o.emailAddress || '';
    }

    function iconColor(mime) {
        if (mime === FOLDER_MIME) return 'text-amber-400';
        if (mime === 'application/pdf') return 'text-red-400';
        if (mime && mime.indexOf('spreadsheet') > -1) return 'text-emerald-400';
        if (mime && mime.indexOf('document') > -1) return 'text-blue-400';
        if (mime && mime.indexOf('presentation') > -1) return 'text-amber-500';
        return 'text-gray-400';
    }

    function iconSvg(mime) {
        if (mime === FOLDER_MIME) {
            return '<svg fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>';
        }
        return '<svg fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6z"/></svg>';
    }

    // ---- Wiring ----

    function attachModalHandlers() {
        if (!modalEl || modalEl.dataset.gdbWired === '1') return;
        modalEl.dataset.gdbWired = '1';

        // Close handlers
        $$('[data-gdb-close]', modalEl).forEach(function (el) {
            el.addEventListener('click', close);
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modalEl && !modalEl.classList.contains('hidden')) {
                close();
            }
        });

        // Search input
        $('#gdb-search').addEventListener('input', function (e) {
            var q = e.target.value.trim();
            if (searchDebounce) clearTimeout(searchDebounce);
            if (!q) {
                if (state.mode === 'search') exitSearch();
                return;
            }
            searchDebounce = setTimeout(function () { runSearch(q); }, 300);
        });

        // Star button — open label-input row
        $('#gdb-star').addEventListener('click', function () {
            if ($('#gdb-star').disabled) return;
            var current = state.breadcrumb[state.breadcrumb.length - 1];
            showLabelRow('create', current ? current.name : '');
        });

        // Label row save / cancel
        $('#gdb-label-save').addEventListener('click', commitLabelRow);
        $('#gdb-label-cancel').addEventListener('click', hideLabelRow);
        $('#gdb-label-input').addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); commitLabelRow(); }
            else if (e.key === 'Escape') { e.preventDefault(); hideLabelRow(); }
        });

        // Link button
        $('#gdb-link').addEventListener('click', linkSelected);

        // Pill menu actions
        $('#gdb-pill-rename').addEventListener('click', function () {
            var bm = state.pillMenuTarget;
            hidePillMenu();
            if (bm) showLabelRow({ type: 'rename', bookmark: bm }, bm.label);
        });
        $('#gdb-pill-remove').addEventListener('click', function () {
            var bm = state.pillMenuTarget;
            hidePillMenu();
            if (!bm) return;
            if (!confirm('Remove bookmark "' + bm.label + '"?')) return;
            deleteBookmark(bm.id)
                .then(loadBookmarks)
                .then(updateStarButton)
                .catch(function (err) { showError('Could not remove: ' + err.message); });
        });

        // Click outside pill menu to dismiss
        document.addEventListener('click', function (e) {
            var menu = $('#gdb-pill-menu');
            if (menu && !menu.classList.contains('hidden') && !menu.contains(e.target)) {
                hidePillMenu();
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var buttons = document.querySelectorAll('.gdrive-bulk-picker-btn');
        if (!buttons.length) return;
        // Prep modal element + handlers (does nothing if no modal in DOM yet)
        modalEl = document.getElementById('gdrive-browser-modal');
        attachModalHandlers();

        Array.prototype.forEach.call(buttons, function (btn) {
            btn.addEventListener('click', function () { open(btn); });
        });
    });
})();
