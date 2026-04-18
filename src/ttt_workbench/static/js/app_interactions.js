(function () {
  'use strict';

  var perfEnabled = false;
  try {
    perfEnabled = localStorage.getItem('tttPerf') === '1';
  } catch (_) {
    perfEnabled = false;
  }

  var activeRequests = new WeakMap();

  function now() {
    return (window.performance && performance.now) ? performance.now() : Date.now();
  }

  function logPerf(label, payload) {
    if (!perfEnabled || !window.console) return;
    console.debug('[TTT-PERF] ' + label, payload || {});
  }

  function toast(message, tone) {
    if (typeof window.showWorkspaceIndicator === 'function') {
      window.showWorkspaceIndicator(message, tone);
      return;
    }
    var indicator = document.getElementById('workspaceToast');
    if (!indicator) return;
    indicator.className = 'workspace-toast is-visible is-' + (tone || 'info');
    indicator.textContent = message;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(function () {
      indicator.classList.remove('is-visible');
    }, 3000);
  }

  function closestButton(elt) {
    if (!elt) return null;
    if (elt.matches && elt.matches('button, input[type="submit"]')) return elt;
    if (elt.querySelector) return elt.querySelector('button[type="submit"], [data-loading-label]');
    return null;
  }

  function requestControl(elt) {
    if (!elt) return null;
    var explicit = elt.matches && elt.matches('[data-loading-label]') ? elt : null;
    if (!explicit && elt.querySelector) explicit = elt.querySelector('[data-loading-label]');
    return explicit || closestButton(elt);
  }

  function setBusy(button, label) {
    if (!button || button.dataset.tttBusy === '1') return;
    button.dataset.tttBusy = '1';
    button.dataset.tttOriginalLabel = button.dataset.tttOriginalLabel || button.textContent;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.classList.add('is-loading');
    if (label) button.textContent = label;
  }

  function restoreBusy(button) {
    if (!button || button.dataset.tttBusy !== '1') return;
    button.disabled = false;
    button.removeAttribute('aria-busy');
    button.classList.remove('is-loading');
    button.textContent = button.dataset.tttOriginalLabel || button.textContent;
    delete button.dataset.tttBusy;
  }

  function responseBytes(event) {
    var xhr = event.detail && event.detail.xhr;
    if (!xhr || typeof xhr.responseText !== 'string') return 0;
    return xhr.responseText.length;
  }

  function requestPath(event) {
    if (event.detail && event.detail.pathInfo && event.detail.pathInfo.requestPath) {
      return event.detail.pathInfo.requestPath;
    }
    if (event.detail && event.detail.xhr && event.detail.xhr.responseURL) {
      return event.detail.xhr.responseURL;
    }
    return '';
  }

  function initHtmxFeedback() {
    if (!window.htmx || window.tttHtmxActionFeedbackBound) return;
    window.tttHtmxActionFeedbackBound = true;

    document.body.addEventListener('htmx:beforeRequest', function (event) {
      var elt = event.detail && event.detail.elt;
      if (!elt) return;

      var sourcePicks = elt.closest && elt.closest('.source-picks');
      if (sourcePicks) {
        var contextPanel = document.getElementById('context-panel');
        if (contextPanel) {
          contextPanel.dataset.tttStudyScrollTop = String(contextPanel.scrollTop || 0);
          contextPanel.classList.add('is-updating-study');
        }
        sourcePicks.querySelectorAll('.source-chip').forEach(function (chip) {
          var input = chip.querySelector('input[type="checkbox"]');
          if (input) chip.classList.toggle('is-selected', input.checked);
        });
      }
      if (elt.closest && elt.closest('.workspace-nav-form')) {
        document.body.dataset.tttTopNavSwap = '1';
      }

      if (activeRequests.has(elt)) {
        if (event.preventDefault) event.preventDefault();
        return;
      }

      var startedAt = now();
      var button = requestControl(elt);
      var loadingLabel = button && button.getAttribute('data-loading-label');
      activeRequests.set(elt, { startedAt: startedAt, button: button });
      setBusy(button, loadingLabel || 'Working...');
      logPerf('request:start', {
        path: requestPath(event),
        target: event.detail && event.detail.target ? event.detail.target.id || event.detail.target.className : '',
      });
    });

    document.body.addEventListener('htmx:afterRequest', function (event) {
      var elt = event.detail && event.detail.elt;
      var state = elt ? activeRequests.get(elt) : null;
      if (elt) activeRequests.delete(elt);
      if (state) restoreBusy(state.button);

      var duration = state ? Math.round(now() - state.startedAt) : null;
      var ok = event.detail && event.detail.successful;
      logPerf('request:end', {
        path: requestPath(event),
        durationMs: duration,
        ok: ok,
        bytes: responseBytes(event),
      });

      if (!ok) {
        toast('Action failed.', 'error');
        return;
      }
      var path = requestPath(event);
      if (path.indexOf('/commit/apply') !== -1) {
        toast('Draft committed.', 'success');
      } else if (path.indexOf('/editor/mode') !== -1) {
        toast('Draft ready.', 'success');
      } else if (duration !== null && duration > 1200) {
        toast('Updated.', 'success');
      }
    });

    ['htmx:responseError', 'htmx:sendError', 'htmx:timeout'].forEach(function (name) {
      document.body.addEventListener(name, function (event) {
        var elt = event.detail && event.detail.elt;
        var state = elt ? activeRequests.get(elt) : null;
        if (elt) activeRequests.delete(elt);
        if (state) restoreBusy(state.button);
        toast(name === 'htmx:timeout' ? 'Action timed out.' : 'Action failed.', 'error');
      });
    });

    document.body.addEventListener('htmx:afterSettle', function (event) {
      var target = event.detail && event.detail.target;
      if (target && target.id === 'workspace-shell' && document.body.dataset.tttTopNavSwap === '1') {
        delete document.body.dataset.tttTopNavSwap;
        window.requestAnimationFrame(function () {
          var shell = document.getElementById('workspace-shell');
          if (shell && shell.scrollIntoView) {
            shell.scrollIntoView({ block: 'start' });
          } else {
            window.scrollTo(0, 0);
          }
        });
      }
      if (!target || target.id !== 'study-blocks') return;
      var contextPanel = document.getElementById('context-panel');
      if (contextPanel) {
        var scrollTop = parseInt(contextPanel.dataset.tttStudyScrollTop || '0', 10);
        if (!Number.isNaN(scrollTop)) contextPanel.scrollTop = scrollTop;
        contextPanel.classList.remove('is-updating-study');
        delete contextPanel.dataset.tttStudyScrollTop;
      }
      if (typeof window.TTTInteractions !== 'undefined') {
        window.TTTInteractions.applyCurrentStudyPreferences();
      }
      if (typeof window.syncPromptEngineeringDraftAvailability === 'function') {
        window.syncPromptEngineeringDraftAvailability();
      }
      if (typeof window.updatePromptEngineeringPreview === 'function') {
        window.updatePromptEngineeringPreview();
      }
    });
  }

  function initSubmitGuards(root) {
    (root || document).querySelectorAll('form').forEach(function (form) {
      if (form.dataset.tttSubmitGuardBound === '1') return;
      form.dataset.tttSubmitGuardBound = '1';
      form.addEventListener('submit', function (event) {
        var submitter = event.submitter;
        if (!submitter || submitter.dataset.tttBusy !== '1') return;
        event.preventDefault();
      });
    });
  }

  function syncSourceChipStates(form) {
    if (!form) return;
    form.querySelectorAll('.source-chip').forEach(function (chip) {
      var input = chip.querySelector('input[type="checkbox"]');
      if (!input) return;
      chip.classList.toggle('is-selected', input.checked || input.indeterminate);
    });
    syncSourceRowToggles(form);
  }

  function sourceRowControls(form, row) {
    return Array.prototype.slice.call(form.querySelectorAll('[data-study-source-toggle][data-source-row="' + row + '"]'));
  }

  function syncSourceRowToggles(form) {
    if (!form) return;
    form.querySelectorAll('[data-study-source-row-toggle]').forEach(function (toggle) {
      var row = toggle.getAttribute('data-source-row');
      var controls = sourceRowControls(form, row).filter(function (control) { return !control.disabled; });
      var checked = controls.filter(function (control) { return control.checked; }).length;
      toggle.checked = controls.length > 0 && checked === controls.length;
      toggle.indeterminate = checked > 0 && checked < controls.length;
      var chip = toggle.closest('.source-chip');
      if (chip) chip.classList.toggle('is-selected', toggle.checked || toggle.indeterminate);
    });
  }

  function applyCurrentStudyPreferences() {
    var fontSize = localStorage.getItem('studyFontSize') || '16';
    if (typeof window.applyStudyFontSize === 'function') {
      window.applyStudyFontSize(fontSize);
    }
    var sizeSelect = document.getElementById('study-font-size');
    if (sizeSelect) sizeSelect.value = fontSize;

    var verseFilterValue = localStorage.getItem('studyVerseFilter') || '';
    var verseFilter = document.getElementById('study-verse-filter');
    if (verseFilter) verseFilter.value = verseFilterValue;
    if (verseFilterValue && typeof window.applyStudyVerseFilter === 'function') {
      window.applyStudyVerseFilter();
    }
  }

  function restoreStudyState() {
    applyCurrentStudyPreferences();
    if (typeof window.syncPromptEngineeringDraftAvailability === 'function') {
      window.syncPromptEngineeringDraftAvailability();
    }
    if (typeof window.updatePromptEngineeringPreview === 'function') {
      window.updatePromptEngineeringPreview();
    }
  }

  function replaceTranslationBlocks(html) {
    var sheet = document.getElementById('study-blocks');
    if (!sheet) return;
    sheet.querySelectorAll('.translation-block').forEach(function (block) {
      block.remove();
    });
    var template = document.createElement('template');
    template.innerHTML = html || '';
    sheet.appendChild(template.content);
    restoreStudyState();
  }

  function replaceStudyWordAnalysis(html) {
    var current = document.getElementById('study-word-analysis');
    var template = document.createElement('template');
    template.innerHTML = html || '';
    var next = template.content.querySelector('#study-word-analysis');
    if (current && next) {
      current.replaceWith(next);
    } else if (current) {
      current.remove();
    } else if (next) {
      var studyArticle = document.querySelector('.study-article');
      if (studyArticle) studyArticle.insertAdjacentElement('afterend', next);
    }
  }

  function studySourcesUrl(form) {
    var source = form && form.querySelector('[data-study-source-toggle]');
    return source ? source.getAttribute('data-study-sources-url') : '';
  }

  function submitStudySourceForm(form) {
    var url = studySourcesUrl(form);
    if (!form || !url) return;
    var contextPanel = document.getElementById('context-panel');
    var controls = Array.prototype.slice.call(form.querySelectorAll('[data-study-source-toggle]'));
    var rowControls = Array.prototype.slice.call(form.querySelectorAll('[data-study-source-row-toggle]'));
    var busyControls = controls.concat(rowControls);
    var previous = controls.map(function (control) { return control.checked; });
    var previousDisabled = busyControls.map(function (control) { return control.disabled; });
    var formData = new FormData(form);
    syncSourceChipStates(form);
    if (contextPanel) contextPanel.classList.add('is-updating-study');
    busyControls.forEach(function (control) {
      control.disabled = true;
      control.setAttribute('aria-busy', 'true');
    });
    fetch(url, {
      method: 'POST',
      body: formData,
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'fetch'
      }
    })
      .then(function (response) {
        return response.json().then(function (payload) {
          return { ok: response.ok, payload: payload };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.payload.ok) {
          throw new Error(result.payload.message || 'Could not update study sources.');
        }
        replaceTranslationBlocks(result.payload.translation_blocks_html || '');
        replaceStudyWordAnalysis(result.payload.word_analysis_html || '');
      })
      .catch(function (err) {
        controls.forEach(function (control, index) {
          control.checked = previous[index];
        });
        syncSourceChipStates(form);
        toast(err.message || 'Could not update study sources.', 'error');
      })
      .finally(function () {
        busyControls.forEach(function (control, index) {
          control.disabled = previousDisabled[index];
          control.removeAttribute('aria-busy');
        });
        syncSourceChipStates(form);
        if (contextPanel) contextPanel.classList.remove('is-updating-study');
      });
  }

  function initStudySourceControls(root) {
    (root || document).querySelectorAll('[data-study-source-toggle]').forEach(function (input) {
      if (input.dataset.tttStudySourceBound === '1') return;
      input.dataset.tttStudySourceBound = '1';
      input.addEventListener('change', function () {
        var form = input.closest('.source-picks');
        submitStudySourceForm(form);
      });
    });
    (root || document).querySelectorAll('[data-study-source-row-toggle]').forEach(function (input) {
      if (input.dataset.tttStudySourceRowBound === '1') return;
      input.dataset.tttStudySourceRowBound = '1';
      input.addEventListener('change', function () {
        var form = input.closest('.source-picks');
        if (!form) return;
        sourceRowControls(form, input.getAttribute('data-source-row')).forEach(function (control) {
          if (!control.disabled) control.checked = input.checked;
        });
        syncSourceChipStates(form);
        submitStudySourceForm(form);
      });
    });
    (root || document).querySelectorAll('.source-picks').forEach(syncSourceChipStates);
  }

  function init(root) {
    initHtmxFeedback();
    initSubmitGuards(root || document);
    initStudySourceControls(root || document);
  }

  document.addEventListener('DOMContentLoaded', function () { init(document); });
  document.addEventListener('htmx:afterSettle', function (event) {
    init(event.target || document);
  });

  window.TTTInteractions = {
    init: init,
    toast: toast,
    setBusy: setBusy,
    restoreBusy: restoreBusy,
    replaceTranslationBlocks: replaceTranslationBlocks,
    applyCurrentStudyPreferences: applyCurrentStudyPreferences,
    perfEnabled: function () { return perfEnabled; },
  };
}());
