(function () {
  'use strict';

  function setEditorSaveStatus(state, label) {
    var status = document.getElementById('editor-save-status');
    if (!status) return;
    status.dataset.state = state;
    status.textContent = label;
  }

  function initEditorAutosave() {
    var editorForm = document.getElementById('editor-form');
    if (!editorForm) return;
    if (editorForm.dataset.autosaveBound === '1') return;
    editorForm.dataset.autosaveBound = '1';
    var timer = null;
    var controller = null;
    var autosaveUrl = editorForm.getAttribute('data-autosave-url');
    if (!autosaveUrl) return;
    function setDraftRevision(value) {
      var revisionField = editorForm.querySelector('input[name="draft_revision"]');
      if (!revisionField) return;
      if (value === null || value === undefined) return;
      revisionField.value = String(value);
    }
    function autosave() {
      clearTimeout(timer);
      timer = null;
      if (controller) controller.abort();
      controller = new AbortController();
      setEditorSaveStatus('saving', 'Saving...');
      fetch(autosaveUrl, {
        method: 'POST',
        body: new FormData(editorForm),
        signal: controller.signal,
        headers: { 'X-Requested-With': 'fetch' }
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            if (!response.ok) {
              var error = new Error((payload && payload.message) || 'Autosave failed.');
              error.payload = payload || {};
              error.status = response.status;
              throw error;
            }
            return payload || {};
          });
        })
        .then(function (payload) {
          setDraftRevision(payload.draft_revision);
          setEditorSaveStatus('saved', 'Saved ✓');
        })
        .catch(function (err) {
          if (err.name === 'AbortError') return;
          var payload = err.payload || {};
          if (err.status === 409 || payload.code === 'stale_draft_revision') {
            setDraftRevision(payload.draft_revision);
            setEditorSaveStatus('error', 'Out of date');
            window.showWorkspaceIndicator(payload.message || 'Draft changed in another request.', 'warning');
            return;
          }
          setEditorSaveStatus('error', 'Save failed');
          window.showWorkspaceIndicator(err.message || 'Autosave failed.', 'error');
        });
    }
    function scheduleAutosave() {
      setEditorSaveStatus('dirty', 'Unsaved');
      clearTimeout(timer);
      timer = setTimeout(autosave, 900);
    }
    editorForm.querySelectorAll('textarea').forEach(function (field) {
      field.addEventListener('input', scheduleAutosave);
      field.addEventListener('blur', function () {
        if (timer) autosave();
      });
    });
  }

  window.setEditorSaveStatus = setEditorSaveStatus;
  window.initEditorAutosave = initEditorAutosave;
})();