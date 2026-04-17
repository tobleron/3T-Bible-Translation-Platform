(function () {
  'use strict';

  var state = window._tttStreaming || {
    controller: null,
    done: true,
    poll: null,
    streamId: 0,
    activeStreamId: 0,
    htmxSwapOccurred: false,
    lastDomCheck: Date.now(),
    domObserver: null
  };

  window._tttStreaming = state;

  function getSendButton() {
    var form = document.getElementById('chat-stream-form');
    return form ? form.querySelector('.send-button') : document.querySelector('.send-button');
  }

  function checkAndLogButtonState(label) {
    var stopButton = document.getElementById('chat-stop-button');
    var sendButton = getSendButton();
    var snapshot = {
      time: new Date().toISOString(),
      label: label,
      stopBtnDisplay: stopButton ? stopButton.style.display : 'element_not_found',
      stopBtnExists: !!stopButton,
      sendBtnDisabled: sendButton ? sendButton.disabled : 'element_not_found',
      sendBtnExists: !!sendButton,
      sendBtnText: sendButton ? sendButton.textContent : 'element_not_found',
      streamId: state.activeStreamId,
      doneFlag: state.done,
      pollRunning: state.poll ? 'yes' : 'no'
    };
    console.log('[DOM-WATCH]', JSON.stringify(snapshot));
    return snapshot;
  }

  var observer = null;
  var domPoll = null;

  function setupObserver() {
    var workspaceShell = document.getElementById('workspace-shell');
    if (!workspaceShell) {
      console.log('[DOM-WATCH] #workspace-shell not found, skipping observer');
      return;
    }
    if (observer) observer.disconnect();
    observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var mutation = mutations[i];
        if (mutation.type !== 'childList') continue;
        mutation.removedNodes.forEach(function (node) {
          if (node.nodeType === 1 && node.id === 'workspace-shell') {
            console.log('[DOM-WATCH] #workspace-shell was removed during chat streaming');
            state.htmxSwapOccurred = true;
            checkAndLogButtonState('post_htmx_swap');
          }
        });
      }
    });
    observer.observe(workspaceShell.parentNode || document.body, { childList: true, subtree: true });
  }

  function startDomPolling() {
    if (domPoll) return;
    domPoll = setInterval(function () {
      var snapshot = checkAndLogButtonState('interval_check');
      if (snapshot.sendBtnExists && snapshot.sendBtnDisabled && state.done) {
        console.log('[DOM-WATCH] Send button disabled while stream state is done');
      }
    }, 500);
  }

  function stopDomPolling() {
    if (!domPoll) return;
    clearInterval(domPoll);
    domPoll = null;
  }

  function ensureDomWatch() {
    if (!state.domObserver) {
      state.domObserver = {
        checkAndLogButtonState: checkAndLogButtonState,
        setupObserver: setupObserver,
        startPolling: startDomPolling,
        stopPolling: stopDomPolling
      };
    }
    setupObserver();
    startDomPolling();
    return state.domObserver;
  }

  function restoreControls(options) {
    options = options || {};
    state.done = true;

    if (options.abort !== false && state.controller) {
      state.controller.abort();
      state.controller = null;
    }

    if (state.poll) {
      clearInterval(state.poll);
      state.poll = null;
    }

    document.querySelectorAll('#chat-stop-button').forEach(function (button) {
      button.style.display = 'none';
      button.classList.remove('is-animating');
    });

    document.querySelectorAll('.send-button').forEach(function (button) {
      button.disabled = false;
      button.textContent = button.dataset.originalLabel || 'Send';
      button.classList.remove('is-loading');
    });
  }

  function startStream() {
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    state.done = false;
    state.streamId += 1;
    state.activeStreamId = state.streamId;
    return {
      controller: state.controller,
      streamId: state.activeStreamId
    };
  }

  function startRecoveryPoll(streamId) {
    if (state.poll) clearInterval(state.poll);
    state.poll = setInterval(function () {
      if (!state.done) return;
      restoreControls({ abort: false });
      if (!state.poll) {
        console.log('[POLL-' + streamId + '] Buttons correct, stopped polling');
      }
    }, 200);
  }

  function createMarkdownThrottler(renderMarkdown, intervalMs) {
    var lastRenderTime = 0;
    var delay = intervalMs || 250;
    return {
      render: function (el, appendedText, rawText) {
        if (!el) return;
        var now = Date.now();
        if (now - lastRenderTime > delay || (rawText || '').length < 500) {
          el.innerHTML = renderMarkdown(rawText || '');
          lastRenderTime = now;
          return;
        }
        el.appendChild(document.createTextNode(appendedText || ''));
      },
      flush: function (el, rawText) {
        if (!el) return;
        el.innerHTML = renderMarkdown(rawText || '');
        lastRenderTime = Date.now();
      }
    };
  }

  window.TTTChatStreamController = {
    state: function () { return state; },
    ensureDomWatch: ensureDomWatch,
    restoreControls: restoreControls,
    startStream: startStream,
    startRecoveryPoll: startRecoveryPoll,
    createMarkdownThrottler: createMarkdownThrottler
  };
}());
