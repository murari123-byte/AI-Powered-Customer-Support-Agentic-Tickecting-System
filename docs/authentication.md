# Authentication

## How login works

```
1. Register   → a CUSTOMER account; the password is saved as an Argon2 hash
2. Login      → access token (JWT, 15 min) in the response body
                + refresh token (random, 7 days) in an httpOnly cookie
3. API calls  → header  Authorization: Bearer <access token>
4. Expired?   → POST /api/v1/auth/refresh with the cookie → new access token + new refresh token
5. Logout     → the refresh token is deleted
```

## Passwords

- Hashed with **Argon2id** (the current recommendation; slow on purpose, so cracking is expensive).
- Only the hash is stored. The API never returns it.
- 10–128 characters. The upper limit stops someone sending a huge "password" to waste CPU.
- Login errors are always the same message ("Invalid email or password"), so nobody can learn which emails exist.

## Access token (JWT)

- Signed with `JWT_SECRET_KEY` using **HS256**. The algorithm is fixed in the code, so a token saying `"alg": "none"` is rejected.
- Contains only the user id and the times (`sub`, `iat`, `exp`). **No role, no email**. Anyone can read a JWT, because it's signed, not encrypted.
- On each request the user is loaded from the database. A disabled user or a changed role takes effect immediately.

## Refresh token

- A long random string, **not** a JWT. The database stores only its **SHA-256 hash**, so a leaked database gives no usable tokens.
- **Used once:** refreshing deletes it and creates a new one. A single `DELETE … RETURNING` statement finds and deletes it together, so if the same token is sent twice at the same moment, only one request succeeds.
- Kept in a cookie that is:

| Cookie setting | Protects against |
|---|---|
| `HttpOnly` | JavaScript can't read it, so an XSS bug can't steal it |
| `Secure` | Only sent over HTTPS (browsers allow `http://localhost`) |
| `SameSite=Strict` | Not sent when another website triggers the request (CSRF) |
| `Path=/api/v1/auth` | Only sent to the auth endpoints |

## Roles

Each user has one role: `CUSTOMER`, `SUPPORT_AGENT`, `SUPPORT_MANAGER` or `ADMIN`.
Endpoints check it with `Depends(require_roles(...))`: **401** if not logged in, **403** if the role isn't allowed.
The full table of what each role can do is in [architecture.md](architecture.md#roles).

- Sign-up always creates a CUSTOMER. Sending `"role": "ADMIN"` gets a 422.
- Only an admin can change roles (`PATCH /api/v1/admin/users/{id}`).
- An admin can't demote or deactivate themselves (so the last admin can't lock everyone out).
- Deactivating a user deletes all their refresh tokens (logged out everywhere).

## The first admin

Sign-up only makes customers, so the first admin is created from the command line:

```bash
cd backend
.venv/bin/python -m app.cli create-admin --email you@example.com --name "Your Name"
```

It asks for the password (hidden, so it never lands in your shell history). For scripts, set `ADMIN_PASSWORD`.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `JWT_SECRET_KEY` | **required** (32+ characters) | Signs tokens. Changing it logs everyone out |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 15 | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 | Refresh token lifetime |
| `AUTH_COOKIE_SECURE` | true | Keep true (only the tests turn it off) |
| `RATE_LIMIT_ENABLED` | true | Login 10/min and sign-up 5/hour per IP (429 + `Retry-After`); tests turn it off |

## Rate limiting

Login (10 a minute) and sign-up (5 an hour) are limited per IP address with a Redis counter (`app/core/rate_limit.py`).
Over the limit: 429 with a `Retry-After` header. If Redis is down, requests are allowed and a warning is logged.

## Possible improvements (not built, on purpose, to keep it simple)

- Detecting a stolen refresh token being reused ("token families").
- Revoking access tokens instantly (a denylist in Redis).
