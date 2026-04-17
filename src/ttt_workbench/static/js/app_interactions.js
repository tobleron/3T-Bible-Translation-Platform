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

  function init(root) {
    initHtmxFeedback();
    initSubmitGuards(root || document);
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
    perfEnabled: function () { return perfEnabled; },
  };
}());
