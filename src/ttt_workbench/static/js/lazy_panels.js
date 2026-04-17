(function () {
  'use strict';

  function ensureJsonModal() {
    var existing = document.getElementById('jsonModal');
    if (existing) return existing;

    var overlay = document.createElement('div');
    overlay.className = 'json-modal-overlay';
    overlay.id = 'jsonModal';
    overlay.style.display = 'none';
    overlay.addEventListener('click', function (event) {
      hideJsonPreview(event);
    });

    var content = document.createElement('div');
    content.className = 'json-modal-content';
    content.addEventListener('click', function (event) {
      event.stopPropagation();
    });

    var head = document.createElement('div');
    head.className = 'json-modal-head';

    var title = document.createElement('h3');
    title.id = 'jsonModalTitle';
    title.textContent = 'Book JSON';

    var closeButton = document.createElement('button');
    closeButton.className = 'json-modal-close';
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', 'Close JSON browser');
    closeButton.innerHTML = '&times;';
    closeButton.addEventListener('click', function () {
      hideJsonPreview();
    });

    head.appendChild(title);
    head.appendChild(closeButton);

    var layout = document.createElement('div');
    layout.className = 'json-browser-layout';

    var tree = document.createElement('nav');
    tree.className = 'json-tree';
    tree.id = 'jsonTree';
    tree.setAttribute('aria-label', 'Book JSON chapters');

    var body = document.createElement('pre');
    body.className = 'json-modal-body';
    body.id = 'jsonPreviewBody';
    body.textContent = 'Loading...';

    layout.appendChild(tree);
    layout.appendChild(body);
    content.appendChild(head);
    content.appendChild(layout);
    overlay.appendChild(content);
    document.body.appendChild(overlay);
    return overlay;
  }

  function showBookJsonBrowser() {
    var overlay = ensureJsonModal();
    overlay.style.display = 'flex';
    var body = document.getElementById('jsonPreviewBody');
    var tree = document.getElementById('jsonTree');
    var title = document.getElementById('jsonModalTitle');
    if (title) title.textContent = 'Book JSON';
    if (body) body.textContent = 'Loading...';
    if (tree) tree.textContent = 'Loading...';

    fetch(window.location.pathname + '/json-book-tree')
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!tree || !body) return;
        if (title) title.textContent = (data.book || 'Book') + ' JSON';
        tree.innerHTML = '';
        var heading = document.createElement('div');
        heading.className = 'json-tree-heading';
        heading.textContent = data.book || 'Selected book';
        tree.appendChild(heading);
        (data.chapters || []).forEach(function (item, index) {
          var button = document.createElement('button');
          button.type = 'button';
          button.className = 'json-tree-item' + (index === 0 ? ' is-active' : '');
          button.textContent = 'Chapter ' + item.chapter;
          button.dataset.chapter = item.chapter;
          button.addEventListener('click', function () {
            tree.querySelectorAll('.json-tree-item').forEach(function (el) {
              el.classList.remove('is-active');
            });
            button.classList.add('is-active');
            loadBookJsonChapter(item.chapter);
          });
          tree.appendChild(button);
        });
        if (data.chapters && data.chapters.length) {
          loadBookJsonChapter(data.chapters[0].chapter);
        } else {
          body.textContent = 'No JSON chapters found for this book.';
        }
      })
      .catch(function (err) {
        if (body) body.textContent = 'Failed to load JSON: ' + err.message;
      });
  }

  function showJsonPreview() {
    showBookJsonBrowser();
  }

  function loadBookJsonChapter(chapter) {
    var body = document.getElementById('jsonPreviewBody');
    if (!body) return;
    body.textContent = 'Loading chapter ' + chapter + '...';
    fetch(window.location.pathname + '/json-book-chapter/' + encodeURIComponent(chapter))
      .then(function (response) { return response.json(); })
      .then(function (data) {
        body.textContent = JSON.stringify(data, null, 2);
      })
      .catch(function (err) {
        body.textContent = 'Failed to load chapter JSON: ' + err.message;
      });
  }

  function hideJsonPreview(event) {
    if (event && event.target !== event.currentTarget) return;
    var overlay = document.getElementById('jsonModal');
    if (overlay) overlay.style.display = 'none';
  }

  window.TTTLazyPanels = {
    ensureJsonModal: ensureJsonModal,
    showBookJsonBrowser: showBookJsonBrowser,
    showJsonPreview: showJsonPreview,
    loadBookJsonChapter: loadBookJsonChapter,
    hideJsonPreview: hideJsonPreview
  };
  window.showBookJsonBrowser = showBookJsonBrowser;
  window.showJsonPreview = showJsonPreview;
  window.loadBookJsonChapter = loadBookJsonChapter;
  window.hideJsonPreview = hideJsonPreview;
}());
