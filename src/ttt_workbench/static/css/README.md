# CSS Split Plan

The app currently ships `../app.css` as one stylesheet to avoid a build step.

When CSS is split, keep plain linked stylesheets in this order:

1. `base.css`
2. `layout.css`
3. `workspace.css`
4. `editor.css`
5. `context_panel.css`
6. `chat.css`
7. `support.css`
8. `settings.css`
9. `epub.css`

Do not introduce a frontend build pipeline unless the UI migrates to a full client-side application.

