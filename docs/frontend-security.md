# Frontend Security Notes

Current SPA (`app/static/index.html`):

- Renders assistant answers with `textContent` only (no `innerHTML`)
- Bearer token kept in a page-local JS variable (not `localStorage`)
- Document titles/classifications also use `textContent`
- Design/layout unchanged; only security-necessary status text for pending approvals

Trusted Types readiness: if the UI later introduces dynamic HTML, enable Trusted Types
and keep model/retrieved output on text nodes only.

If cookie sessions are introduced later, require `Secure`, `HttpOnly`, `SameSite`
cookies plus CSRF protection. Current auth is Authorization bearer header based,
so CSRF for API mutations is not applicable in the same way.
