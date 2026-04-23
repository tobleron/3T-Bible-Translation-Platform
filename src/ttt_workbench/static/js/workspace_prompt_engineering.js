(function () {
  'use strict';

  function switchEditorialTab(button, tabName) {
    var form = button.closest('.editorial-form');
    if (!form) return;
    var tabInput = form.querySelector('#editorial-tab-input');
    if (tabInput) tabInput.value = tabName;
    form.querySelectorAll('[data-editorial-tab]').forEach(function (tabButton) {
      tabButton.classList.toggle('is-active', tabButton === button);
    });
    form.querySelectorAll('[data-editorial-panel]').forEach(function (panel) {
      var active = panel.getAttribute('data-editorial-panel') === tabName;
      panel.hidden = !active;
      panel.classList.toggle('is-active', active);
    });
    requestAnimationFrame(function () {
      form.querySelectorAll('textarea[data-auto-resize]').forEach(function (field) {
        if (typeof window.autoResize === 'function') window.autoResize(field);
      });
    });
  }

  function currentEditorialPromptValues() {
    var values = {};
    document.querySelectorAll('[data-prompt-text][data-prompt-id]').forEach(function (field) {
      var id = (field.getAttribute('data-prompt-id') || '').trim();
      if (!id) return;
      values[id] = field.value || '';
    });
    return values;
  }

  window.tttPromptEngineeringContexts = window.tttPromptEngineeringContexts || {};
  window.tttPromptEngineeringContextsFetched = false;
  window.tttPromptEngineeringPreviewSeq = 0;

  function promptEngineeringContextMeta() {
    return [
      { id: 'prompt-context-draft', key: 'draft', label: 'Draft' },
      { id: 'prompt-context-filtered', key: 'filtered', label: 'Filtered' },
      { id: 'prompt-context-avd', key: 'avd', label: 'AVD' },
      { id: 'prompt-context-hebrew', key: 'hebrew', label: 'Hebrew' },
      { id: 'prompt-context-hebrew-en', key: 'hebrew-en', label: 'Hebrew Literal' },
      { id: 'prompt-context-greek', key: 'greek', label: 'Greek' },
      { id: 'prompt-context-greek-en', key: 'greek-en', label: 'Greek Literal' }
    ];
  }

  function selectedPromptEngineeringContexts() {
    return promptEngineeringContextMeta().filter(function (meta) {
      var cb = document.getElementById(meta.id);
      return cb && cb.checked;
    });
  }

  function selectedPromptEngineeringModes() {
    return Array.from(document.querySelectorAll('[data-prompt-mode]:checked')).map(function (cb) {
      return { key: cb.value };
    });
  }

  function promptEngineeringHideLabels() {
    var cb = document.getElementById('prompt-option-hide-labels');
    return !!(cb && cb.checked);
  }

  function promptEngineeringPartSeparator(hideLabels) {
    return hideLabels ? '\n\n---\n\n' : '\n\n';
  }

  function currentStudyVerseFilterSpec() {
    return (localStorage.getItem('studyVerseFilter') || '').trim();
  }

  function filteredDraftVerseNumbers() {
    var spec = currentStudyVerseFilterSpec();
    var parsed = spec ? window.parseVerseSpec(spec) : [];
    var seen = {};
    var verses = [];
    if (parsed.length) {
      parsed.forEach(function (v) {
        if (seen[v]) return;
        var field = document.querySelector('.verse-editor-textarea[name="verse_' + v + '"]');
        if (field) {
          seen[v] = true;
          verses.push(v);
        }
      });
      return verses;
    }
    document.querySelectorAll('.verse-editor-textarea[name^="verse_"]').forEach(function (field) {
      var match = (field.getAttribute('name') || '').match(/^verse_(\d+)$/);
      if (!match) return;
      var v = parseInt(match[1], 10);
      if (seen[v]) return;
      if (field) {
        seen[v] = true;
        verses.push(v);
      }
    });
    return verses.sort(function (a, b) { return a - b; });
  }

  function syncPromptEngineeringDraftAvailability() {
    var draftCheck = document.getElementById('prompt-context-draft');
    if (draftCheck) {
      var verses = filteredDraftVerseNumbers();
      var enabled = verses.length > 0;
      draftCheck.disabled = !enabled;
      draftCheck.title = enabled ? 'Use draft verses: ' + verses.join(', ') : 'No draft verses are available.';
      if (!enabled) draftCheck.checked = false;
    }
    var filteredCheck = document.getElementById('prompt-context-filtered');
    if (filteredCheck) {
      var hasTranslations = !!document.querySelector('#study-blocks .translation-block[data-translation-alias]');
      filteredCheck.disabled = !hasTranslations;
      filteredCheck.title = hasTranslations
        ? 'Use selected Study translations; respects the active verse filter.'
        : 'Select at least one Study translation first.';
      if (!hasTranslations) filteredCheck.checked = false;
    }
  }

  function promptEngineeringAllowedVerseSet() {
    var spec = currentStudyVerseFilterSpec();
    var parsed = spec ? window.parseVerseSpec(spec) : [];
    if (!parsed.length) return null;
    var allowed = {};
    parsed.forEach(function (v) { allowed[v] = true; });
    return allowed;
  }

  function filterPromptContextByStudyVerses(text) {
    var allowed = promptEngineeringAllowedVerseSet();
    if (!allowed) return text;
    return String(text || '').split(/\r?\n/).filter(function (line) {
      var match = line.match(/^\s*(\d+)\.\s+/);
      return match && allowed[parseInt(match[1], 10)];
    }).join('\n');
  }

  function currentStudySelectedTranslationsPromptText(hideLabels) {
    var allowed = promptEngineeringAllowedVerseSet();
    var sourceOrder = {};
    document.querySelectorAll('[data-study-source-toggle]').forEach(function (input, index) {
      var alias = (input.value || '').trim();
      if (alias) sourceOrder[alias] = index;
    });
    var blocks = Array.from(document.querySelectorAll('#study-blocks .translation-block[data-translation-alias]'));
    blocks.sort(function (a, b) {
      var aAlias = (a.getAttribute('data-translation-alias') || '').trim();
      var bAlias = (b.getAttribute('data-translation-alias') || '').trim();
      var aOrder = Object.prototype.hasOwnProperty.call(sourceOrder, aAlias) ? sourceOrder[aAlias] : 9999;
      var bOrder = Object.prototype.hasOwnProperty.call(sourceOrder, bAlias) ? sourceOrder[bAlias] : 9999;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return aAlias.localeCompare(bAlias);
    });
    var sections = [];
    blocks.forEach(function (block) {
      var alias = (block.getAttribute('data-translation-alias') || '').trim();
      if (!alias) return;
      var lines = [];
      block.querySelectorAll('.translation-verse-row[data-verse]').forEach(function (row) {
        var verse = parseInt(row.getAttribute('data-verse') || '0', 10);
        if (!verse || (allowed && !allowed[verse])) return;
        var textEl = row.querySelector('.translation-verse-text');
        var text = textEl ? (textEl.textContent || '').trim() : '';
        if (!text || text === '[no text]') return;
        lines.push(verse + '. ' + text);
      });
      if (lines.length) {
        sections.push(hideLabels ? lines.join('\n') : alias + ':\n' + lines.join('\n'));
      }
    });
    return sections.join(promptEngineeringPartSeparator(hideLabels));
  }

  function currentDraftPromptText() {
    var verses = filteredDraftVerseNumbers();
    if (!verses.length) return '';
    var lines = [];
    verses.forEach(function (v) {
      var field = document.querySelector('.verse-editor-textarea[name="verse_' + v + '"]');
      if (field && (field.value || '').trim()) {
        lines.push(v + '. ' + field.value.trim());
      }
    });
    return lines.join('\n');
  }

  function promptEngineeringNeedsFetchedContexts() {
    return selectedPromptEngineeringContexts().some(function (meta) {
      return meta.key !== 'draft' && meta.key !== 'filtered';
    });
  }

  async function ensurePromptEngineeringContexts() {
    if (window.tttPromptEngineeringContextsFetched || !promptEngineeringNeedsFetchedContexts()) return;
    var endpoint = window.tttPromptEngineeringEndpoint;
    if (!endpoint) return;
    try {
      var res = await fetch(endpoint);
      if (res.ok) {
        window.tttPromptEngineeringContexts = await res.json();
        window.tttPromptEngineeringContextsFetched = true;
      }
    } catch (e) {
      console.error('Failed to fetch prompt engineering context', e);
    }
  }

  async function buildPromptEngineeringText() {
    await ensurePromptEngineeringContexts();
    var parts = [];
    var prompts = currentEditorialPromptValues();
    var copyableText = '';
    var hideLabels = promptEngineeringHideLabels();

    selectedPromptEngineeringModes().forEach(function (mode) {
      if (mode.key === 'copyable') {
        copyableText = (prompts.copyable || 'Return your response in a plain text code block.').trim();
      } else {
        var text = (prompts[mode.key] || '').trim();
        if (text) {
          parts.push(text);
        }
      }
    });

    selectedPromptEngineeringContexts().forEach(function (meta) {
      var text = '';
      if (meta.key === 'draft') {
        text = currentDraftPromptText();
      } else if (meta.key === 'filtered') {
        text = currentStudySelectedTranslationsPromptText(hideLabels);
      } else {
        text = (window.tttPromptEngineeringContexts || {})[meta.key] || '';
        text = filterPromptContextByStudyVerses(text);
      }
      text = (text || '').trim();
      if (text) {
        if (meta.key === 'filtered' || hideLabels) {
          parts.push(text);
        } else {
          parts.push(meta.label + ':\n' + text);
        }
      }
    });

    if (copyableText) {
      parts.push(copyableText);
    }

    return parts.join(promptEngineeringPartSeparator(hideLabels));
  }

  function updatePromptEngineeringPreview() {
    var preview = document.getElementById('prompt-engineering-preview');
    if (!preview) return;
    var seq = ++window.tttPromptEngineeringPreviewSeq;
    buildPromptEngineeringText().then(function (text) {
      if (seq !== window.tttPromptEngineeringPreviewSeq) return;
      preview.value = text;
      preview.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  function saveChatContextSelections() {
    var endpoint = window.tttPromptEngineeringEndpoint;
    if (!endpoint) return;
    var selections = selectedPromptEngineeringContexts().map(function (m) { return m.key; });
    var modes = selectedPromptEngineeringModes().map(function (m) { return m.key; });
    var hideLabels = promptEngineeringHideLabels();
    fetch(endpoint.replace('/prompt-text', '/context'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selections: selections, modes: modes, hide_labels: hideLabels })
    }).catch(function (e) { console.error('Failed to save chat context selections', e); });
  }

  function initPromptEngineering() {
    var panel = document.querySelector('.prompt-engineering-panel');
    if (!panel) return;
    var form = panel.querySelector('.editorial-form');
    syncPromptEngineeringDraftAvailability();
    if (panel.dataset.promptEngineeringBound === '1') {
      updatePromptEngineeringPreview();
      return;
    }
    panel.dataset.promptEngineeringBound = '1';
    panel.querySelectorAll('[data-prompt-context], [data-prompt-mode], [data-prompt-option], [data-prompt-text], [data-prompt-label]').forEach(function (el) {
      el.addEventListener('input', function () { updatePromptEngineeringPreview(); saveChatContextSelections(); });
      el.addEventListener('change', function () { updatePromptEngineeringPreview(); saveChatContextSelections(); });
    });
    var activeSelect = panel.querySelector('[data-prompt-active-select]');
    if (activeSelect) {
      var syncPromptVisibility = function () {
        var activeId = (activeSelect.value || '').trim();
        panel.querySelectorAll('[data-prompt-item]').forEach(function (item) {
          var itemId = (item.getAttribute('data-prompt-id') || '').trim();
          item.hidden = !!activeId && itemId !== activeId;
        });
      };
      activeSelect.addEventListener('change', syncPromptVisibility);
      syncPromptVisibility();
    }
    if (form && !form.dataset.promptSubmitBound) {
      form.dataset.promptSubmitBound = '1';
      form.addEventListener('submit', function (event) {
        if (event.submitter && event.submitter.name === 'action') {
          form.querySelectorAll('input[data-transient-action="1"]').forEach(function (el) { el.remove(); });
        }
      });
    }
    document.querySelectorAll('.verse-editor-textarea').forEach(function (el) {
      el.addEventListener('input', function () {
        var draftCheck = document.getElementById('prompt-context-draft');
        if (draftCheck && draftCheck.checked) { updatePromptEngineeringPreview(); saveChatContextSelections(); }
      });
    });
    updatePromptEngineeringPreview();
    saveChatContextSelections();
  }

  function setPromptDeleteId(promptId) {
    var target = document.getElementById('prompt-delete-id');
    if (target) target.value = promptId || '';
  }

  function switchActivePrompt(selectEl) {
    if (!selectEl) return;
    var form = selectEl.closest('form');
    if (!form) return;
    form.querySelectorAll('button[data-loading-label]').forEach(function (btn) {
      if (typeof window.TTTInteractions !== 'undefined' && typeof window.TTTInteractions.restoreBusy === 'function') {
        window.TTTInteractions.restoreBusy(btn);
      } else {
        if (btn.dataset.tttBusy === '1') {
          btn.disabled = false;
          btn.removeAttribute('aria-busy');
          btn.classList.remove('is-loading');
          btn.textContent = btn.dataset.tttOriginalLabel || btn.dataset.originalLabel || btn.getAttribute('data-loading-label') || btn.textContent;
          delete btn.dataset.tttBusy;
        }
      }
    });
    var tabInput = form.querySelector('#editorial-tab-input');
    if (tabInput) tabInput.value = 'prompts';
    form.querySelectorAll('input[data-transient-action="1"]').forEach(function (el) { el.remove(); });
    var transient = document.createElement('input');
    transient.type = 'hidden';
    transient.name = 'action';
    transient.value = 'switch_prompt';
    transient.setAttribute('data-transient-action', '1');
    form.appendChild(transient);
    form.requestSubmit();
  }

  function togglePromptEdit(button) {
    var item = document.querySelector('.prompt-engineering-panel .prompt-library-item');
    if (!item) return;
    var nextEditing = item.getAttribute('data-prompt-editing') !== '1';
    item.setAttribute('data-prompt-editing', nextEditing ? '1' : '0');
    item.querySelectorAll('[data-prompt-label], [data-prompt-text]').forEach(function (field) {
      field.readOnly = !nextEditing;
      if (nextEditing) {
        field.removeAttribute('readonly');
      } else {
        field.setAttribute('readonly', '');
      }
    });
    var toggle = button;
    if (!toggle || !toggle.classList || !toggle.classList.contains('prompt-toolbar-button')) {
      toggle = document.querySelector('.prompt-engineering-panel .prompt-toolbar-actions .prompt-toolbar-button');
    }
    if (toggle) {
      toggle.classList.toggle('is-active', nextEditing);
      toggle.textContent = nextEditing ? 'Done' : 'Edit';
      toggle.setAttribute('aria-label', nextEditing ? 'Lock selected prompt' : 'Edit selected prompt');
      toggle.setAttribute('title', nextEditing ? 'Lock selected prompt' : 'Edit selected prompt');
    }
    if (!nextEditing) return;
    var firstField = item.querySelector('[data-prompt-text], [data-prompt-label]');
    if (firstField) {
      firstField.focus();
      if (typeof firstField.setSelectionRange === 'function') {
        var length = (firstField.value || '').length;
        firstField.setSelectionRange(length, length);
      }
    }
  }

  function submitPromptAction(button, actionName) {
    if (!button) return;
    var form = button.closest('form');
    if (!form) return;
    form.querySelectorAll('input[data-transient-action="1"]').forEach(function (el) { el.remove(); });
    var transient = document.createElement('input');
    transient.type = 'hidden';
    transient.name = 'action';
    transient.value = String(actionName || '').trim();
    transient.setAttribute('data-transient-action', '1');
    form.appendChild(transient);
    form.requestSubmit();
  }

  function clearPromptEngineeringCombined() {
    document.querySelectorAll('[data-prompt-context], [data-prompt-mode], [data-prompt-option]').forEach(function (cb) {
      cb.checked = false;
    });
    var preview = document.getElementById('prompt-engineering-preview');
    if (preview) {
      preview.value = '';
      preview.dispatchEvent(new Event('input', { bubbles: true }));
    }
    syncPromptEngineeringDraftAvailability();
    window.showWorkspaceIndicator('Combined prompt cleared.');
  }

  function copyPromptEngineeringCombined(btn) {
    buildPromptEngineeringText().then(function (text) {
      return window.writeClipboardText(text || '').then(function () {
        showCopySuccess(btn);
        window.showWorkspaceIndicator('Combined prompt copied.');
      });
    }).catch(function () {
      window.showWorkspaceIndicator('Copy failed.');
    });
  }

  function injectPromptEngineeringIntoChat() {
    buildPromptEngineeringText().then(function (text) {
      if (!text.trim()) {
        window.showWorkspaceIndicator('Add input or select context before injecting.');
        return;
      }
      var iframe = document.querySelector('.chainlit-container iframe');
      if (!iframe) {
        window.showWorkspaceIndicator('Open the chat panel before injecting.');
        return;
      }
      var innerDoc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
      var textarea = innerDoc ? innerDoc.querySelector('#chat-input') : null;
      if (!textarea) {
        window.showWorkspaceIndicator('Chat input is still loading.');
        return;
      }
      var ownerWindow = textarea.ownerDocument && textarea.ownerDocument.defaultView ? textarea.ownerDocument.defaultView : window;
      var nativeSetter = Object.getOwnPropertyDescriptor(ownerWindow.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(textarea, text);
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      textarea.focus();
      window.showWorkspaceIndicator('Combined prompt injected into chat.');
    }).catch(function () {
      window.showWorkspaceIndicator('Inject failed.');
    });
  }

  function showCopySuccess(btn) {
    if (!btn) return;
    if (!btn.dataset.originalLabel) {
      btn.dataset.originalLabel = btn.textContent;
    }
    btn.textContent = '✓';
    btn.classList.add('copied');
    setTimeout(function () {
      btn.textContent = btn.dataset.originalLabel || '⧉';
      btn.classList.remove('copied');
    }, 1400);
  }

  window.switchEditorialTab = switchEditorialTab;
  window.currentEditorialPromptValues = currentEditorialPromptValues;
  window.selectedPromptEngineeringContexts = selectedPromptEngineeringContexts;
  window.selectedPromptEngineeringModes = selectedPromptEngineeringModes;
  window.promptEngineeringHideLabels = promptEngineeringHideLabels;
  window.filteredDraftVerseNumbers = filteredDraftVerseNumbers;
  window.syncPromptEngineeringDraftAvailability = syncPromptEngineeringDraftAvailability;
  window.updatePromptEngineeringPreview = updatePromptEngineeringPreview;
  window.buildPromptEngineeringText = buildPromptEngineeringText;
  window.clearPromptEngineeringCombined = clearPromptEngineeringCombined;
  window.copyPromptEngineeringCombined = copyPromptEngineeringCombined;
  window.injectPromptEngineeringIntoChat = injectPromptEngineeringIntoChat;
  window.initPromptEngineering = initPromptEngineering;
  window.promptEngineeringContextMeta = promptEngineeringContextMeta;
  window.currentDraftPromptText = currentDraftPromptText;
  window.currentStudySelectedTranslationsPromptText = currentStudySelectedTranslationsPromptText;
  window.setPromptDeleteId = setPromptDeleteId;
  window.switchActivePrompt = switchActivePrompt;
  window.togglePromptEdit = togglePromptEdit;
  window.submitPromptAction = submitPromptAction;
})();
