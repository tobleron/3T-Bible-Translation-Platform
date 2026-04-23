(function () {
  'use strict';

  function setModelButtonBusy(button, loadingLabel) {
    if (!button) return null;
    if (!button.dataset.originalLabel) {
      button.dataset.originalLabel = button.textContent;
    }
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.classList.add('is-loading');
    button.textContent = loadingLabel || 'Working...';
    return {
      restore: function () {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        button.classList.remove('is-loading');
        button.textContent = button.dataset.originalLabel || button.textContent;
      }
    };
  }

  function initModelActionForms() {
    document.querySelectorAll('.model-action-form').forEach(function (form) {
      if (form.dataset.modelActionBound === '1') return;
      form.dataset.modelActionBound = '1';
      form.addEventListener('submit', function (event) {
        var submitter = event.submitter;
        if (!submitter) return;
        var label = submitter.getAttribute('data-loading-label');
        if (!label) return;
        setModelButtonBusy(submitter, label);
      });
    });
  }

  function autoResize(el) {
    if (!el || el.tagName.toLowerCase() !== 'textarea') return;
    if (!el.matches('.verse-editor-textarea, [data-inline-format-field], [data-auto-resize]')) return;

    var setHeight = function (target) {
      target.style.height = 'auto';
      target.style.height = target.scrollHeight + 'px';
    };

    setHeight(el);

    if (el.dataset.autoResizeBound) return;
    el.dataset.autoResizeBound = '1';

    el.addEventListener('input', function () {
      var scrollLeft = window.scrollX || window.pageXOffset;
      var scrollTop = window.scrollY || window.pageYOffset;
      setHeight(this);
      window.scrollTo(scrollLeft, scrollTop);
    });
  }

  function chunkEditorialEndpoint() {
    return window.location.pathname.replace(/\/$/, '') + '/editorial/enhance-field';
  }

  function runEnhancementRequest(payload) {
    var body = new FormData();
    Object.keys(payload).forEach(function (key) {
      body.append(key, payload[key]);
    });
    var prompts = window.currentEditorialPromptValues ? window.currentEditorialPromptValues() : {};
    Object.keys(prompts).forEach(function (promptId) {
      body.append('prompt_text_' + promptId, prompts[promptId] || '');
    });
    return fetch(chunkEditorialEndpoint(), { method: 'POST', body: body })
      .then(function (response) { return response.json().then(function (data) { return { status: response.status, data: data }; }); })
      .then(function (result) {
        if (!result.data || !result.data.ok) {
          throw new Error((result.data && result.data.message) || 'Enhancement failed.');
        }
        return result.data;
      });
  }

  function enhanceEditorVerse(btn, mode) {
    var row = btn.closest('.verse-editor-row');
    var field = row ? row.querySelector('.verse-editor-textarea') : null;
    if (!field) return;
    var busy = setModelButtonBusy(btn, '...');
    runEnhancementRequest({
      mode: mode,
      context_label: 'Bible draft verse',
      text: field.value || ''
    }).then(function (data) {
      field.value = data.text || '';
      field.dispatchEvent(new Event('input', { bubbles: true }));
      window.showWorkspaceIndicator((data.label || 'Rewrite') + ' applied.');
    }).catch(function (err) {
      window.showWorkspaceIndicator(err.message || 'Enhancement failed.');
    }).finally(function () {
      if (busy) busy.restore();
    });
  }

  function enhanceSupportField(trigger, mode) {
    var field = window.findSupportFormatField ? window.findSupportFormatField(trigger) : null;
    if (!field) return;
    var form = trigger.closest('form');
    if (!form) return;
    var customPromptField = form.querySelector('[name="justify_custom_prompt"], [name="footnote_custom_prompt"]');
    var contextLabel = form.querySelector('[name="reason"]')
      ? 'translation justification prose'
      : 'translation footnote prose';
    var busy = setModelButtonBusy(trigger, trigger.getAttribute('data-loading-label') || 'Working...');
    runEnhancementRequest({
      mode: mode,
      context_label: contextLabel,
      text: field.value || '',
      custom_prompt: customPromptField ? customPromptField.value || '' : ''
    }).then(function (data) {
      field.value = data.text || '';
      field.dispatchEvent(new Event('input', { bubbles: true }));
      window.showWorkspaceIndicator((data.label || 'Rewrite') + ' applied.');
    }).catch(function (err) {
      window.showWorkspaceIndicator(err.message || 'Enhancement failed.');
    }).finally(function () {
      if (busy) busy.restore();
    });
  }

  function copyTranslationVerse(btn, text) {
    window.writeClipboardText(text).then(function () {
      btn.textContent = '✓';
      btn.classList.add('copied');
      try { window.showGlossCopiedIndicator(text); } catch (err) { console.warn('Copied indicator failed', err); }
      setTimeout(function () {
        btn.textContent = 'Copy';
        btn.classList.remove('copied');
      }, 1500);
    }, function () {
      btn.textContent = 'Failed';
    });
  }

  function initTranslationCopyButtons() {
    if (document.body.dataset.translationCopyBound === '1') return;
    document.body.dataset.translationCopyBound = '1';
    document.body.addEventListener('click', function (event) {
      var btn = event.target.closest('.translation-copy-btn[data-copy-text]');
      if (!btn) return;
      copyTranslationVerse(btn, btn.dataset.copyText || '');
    });
  }

  function initTranslationApplyButtons() {
    if (document.body.dataset.translationApplyBound === '1') return;
    document.body.dataset.translationApplyBound = '1';
    document.body.addEventListener('click', function (event) {
      var btn = event.target.closest('.translation-apply-btn[data-translation-alias]');
      if (!btn) return;
      applyStudyTranslationToDraft(btn);
    });
  }

  function applyStudyTranslationToDraft(btn) {
    var alias = btn.dataset.translationAlias || '';
    var block = btn.closest('.translation-block');
    var form = document.getElementById('editor-form');
    var editorMode = form ? form.querySelector('input[name="editor_mode"]') : null;
    if (!alias || !block || !form) return;
    if (!editorMode || editorMode.value !== 'draft') {
      window.showWorkspaceIndicator('Switch to Draft before loading a translation into the draft buffer.');
      return;
    }
    var rows = block.querySelectorAll('.translation-verse-row[data-verse]');
    if (!rows.length) return;

    var scrollLeft = window.scrollX || window.pageXOffset;
    var scrollTop = window.scrollY || window.pageYOffset;
    var applied = 0;

    rows.forEach(function (row) {
      var verse = row.dataset.verse || '';
      if (!verse) return;
      var target = form.querySelector('textarea[name="verse_' + verse + '"]');
      if (!target) return;
      var textEl = row.querySelector('.translation-verse-text');
      var nextText = textEl ? textEl.textContent : '';
      if (nextText === '[no text]') nextText = '';
      target.value = nextText;
      target.dispatchEvent(new Event('input', { bubbles: true }));
      applied += 1;
    });

    window.scrollTo(scrollLeft, scrollTop);
    if (!applied) return;

    btn.textContent = 'Applied';
    btn.classList.add('applied');
    window.showWorkspaceIndicator('Loaded ' + alias + ' into ' + applied + ' draft verse' + (applied === 1 ? '' : 's') + '.');
    setTimeout(function () {
      btn.textContent = 'Use In Draft';
      btn.classList.remove('applied');
    }, 1600);
  }

  function generateEpubDownload(btn) {
    if (!btn || btn.disabled) return;
    var originalLabel = btn.dataset.label || btn.textContent;
    btn.dataset.label = originalLabel;
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    btn.classList.add('is-loading');
    btn.textContent = 'Generating...';
    window.showWorkspaceIndicator('Generating EPUB...', 'info');

    fetch('/epub/generate-download', {
      method: 'POST',
      headers: {
        'X-Requested-With': 'fetch'
      }
    })
      .then(function (response) {
        var contentType = response.headers.get('content-type') || '';
        if (!response.ok || contentType.indexOf('application/epub+zip') === -1) {
          if (contentType.indexOf('application/json') !== -1) {
            return response.json().then(function (payload) {
              throw new Error(payload.message || 'EPUB generation failed.');
            });
          }
          throw new Error('EPUB generation failed.');
        }
        return Promise.all([Promise.resolve(response), response.blob()]);
      })
      .then(function (parts) {
        var response = parts[0];
        var blob = parts[1];
        var disposition = response.headers.get('content-disposition') || '';
        var match = disposition.match(/filename="?([^";]+)"?/i);
        var filename = match ? match[1] : 'translation.epub';
        var url = window.URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () {
          window.URL.revokeObjectURL(url);
        }, 1000);
        window.showWorkspaceIndicator('Downloaded ' + filename + '.', 'success');
      })
      .catch(function (err) {
        window.showWorkspaceIndicator(err.message || 'EPUB generation failed.', 'error');
      })
      .finally(function () {
        btn.disabled = false;
        btn.removeAttribute('aria-busy');
        btn.classList.remove('is-loading');
        btn.textContent = originalLabel;
      });
  }

  window.autoResize = autoResize;
  window.setModelButtonBusy = setModelButtonBusy;
  window.initModelActionForms = initModelActionForms;
  window.enhanceEditorVerse = enhanceEditorVerse;
  window.enhanceSupportField = enhanceSupportField;
  window.copyTranslationVerse = copyTranslationVerse;
  window.initTranslationCopyButtons = initTranslationCopyButtons;
  window.initTranslationApplyButtons = initTranslationApplyButtons;
  window.applyStudyTranslationToDraft = applyStudyTranslationToDraft;
  window.generateEpubDownload = generateEpubDownload;
})();
