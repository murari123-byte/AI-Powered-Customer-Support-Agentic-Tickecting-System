# Frontend

React 19 + TypeScript + Vite + React Router 7 + Axios. No UI library: plain CSS (`src/index.css`, light and dark mode).

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 (needs the backend on :8000)
npm test         # Vitest + React Testing Library
npm run build    # type-check + production build into dist/
npm run lint     # oxlint
```

## Pages

| Route | Who | What |
|---|---|---|
| `/login`, `/register` | everyone | Sign in / create a customer account |
| `/tickets` | logged in | Customers: **My tickets**. Staff: **Ticket queue** with search, status, priority and "assigned to me" filters |
| `/tickets/new` | customers | Raise a ticket (optional category; the AI classifies it anyway) |
| `/tickets/:id` | owner, staff | Conversation, reply, status buttons. Staff also get: priority, team/person assignment (managers), "take this ticket" (agents), escalation, the **AI panel** and the history |
| `/knowledge` | staff | Ask the knowledge base (answer + expandable sources); admins upload and delete documents |
| `/admin` | admins | Users (role, active) and teams (create, add/remove members) |

### The AI panel (ticket page, staff)

- **Auto-triage**: what the classifier said (category, priority, confidence, reasoning) and what the code did with it.
- **Suggest a reply**: RAG answer with its sources; "Use as reply" copies it into the reply box. **Nothing is sent** until the person clicks Send.
- **Let the AI agent work it**: queues an agent run, then checks every 5 seconds until it's done. Shows every tool call
  (✓ done, ⛔ blocked with the reason), the summary, and the draft reply ("Use draft as reply").

## Code layout

```
src/
├── api/client.ts      the one Axios instance: token, auto-refresh, error messages
├── api/endpoints.ts   every backend call (pages never build URLs)
├── api/types.ts       response shapes, mirroring the backend schemas
├── auth/              AuthProvider (session state) + useAuth hook
├── components/        Layout (role-aware menu), RequireAuth (route guard), StatusBadge, ErrorBox
├── pages/             one file per page
└── test/              Vitest tests
```

## Login and tokens in the browser

| What | Where | Why |
|---|---|---|
| Access token | **a variable in memory** (`api/client.ts`) | Not in localStorage, where any injected script could read it. It's lost on reload, which is fine because of the next row |
| Refresh token | **httpOnly cookie**, sent by the browser (`withCredentials: true`) | JavaScript can't read it at all |
| After a page reload | `AuthProvider` calls `/auth/refresh` | You stay logged in without storing the token |
| Access token expired (401) | The Axios interceptor refreshes **once** and repeats the call | Several calls failing together share **one** refresh, because a refresh token works only once |
| Refresh fails | The session ends and you go to `/login` | |

## Roles in the UI

The menu and routes hide pages a role can't use, and buttons only appear when they make sense (e.g. status moves are
mirrored from the backend rules). **This is only for convenience: the backend checks the role on every call**, so a
hidden button or a hand-typed URL can't do anything the API wouldn't allow.

## Tests (`npm test`: 11)

| File | Checks |
|---|---|
| `src/test/client.test.ts` | Token sent; 401 → one refresh → call repeated with the new token; two calls at once share one refresh; failed refresh ends the session; readable error messages |
| `src/test/components.test.tsx` | `RequireAuth`: visitors → login, wrong role → tickets, right role → page; `StatusBadge` |
