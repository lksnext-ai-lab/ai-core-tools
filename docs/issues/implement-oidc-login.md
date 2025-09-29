# Issue: Implement OIDC login & authentication flow in React frontend (no backend validation yet)

## Description
We need to implement a basic OpenID Connect (OIDC) login flow in the React frontend to allow users to authenticate with external identity providers. For now, we will not perform any backend checks — the goal is to ensure users can sign in, sign out, and that authentication state (tokens, user profile) is available in the frontend.

## Requirements
- Use `react-oidc-context` (preferred) or another well-supported OIDC React library.
- Configure support for the following identity providers:
  - Microsoft (Azure AD)
  - Google
  - Keycloak (self-hosted)
- Implement a login button that redirects users to the chosen provider.
- Handle OIDC redirect/callback flow in the frontend.
- Store user session in React context (access token, ID token, basic profile info).
- Add a logout button that clears session and redirects to IdP logout.
- Show the logged-in user’s name or email in the UI after login.

## Acceptance Criteria
- User can log in via Microsoft, Google, or Keycloak, and see their profile in the app.
- Tokens are stored securely in memory (avoid `localStorage` unless necessary).
- Logout properly clears session and updates UI.
- No backend validation required at this stage.
