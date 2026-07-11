# Fiyox — Frontend

The web client for Fiyox: a Next.js (App Router) + TypeScript + Tailwind PWA that
talks to the FastAPI backend. Design identity is a navy-and-brass "school register"
(Space Grotesk display, Inter body), built mobile-first for low-end devices.

## What's here (this slice)

- **Login** (`/login`) — email + password against the backend's OAuth2 endpoint.
- **Protected shell** (`/dashboard`) — validates the token via `/api/auth/me`,
  role-aware sidebar, sign out.
- **Overview** (`/dashboard`) — greeting + live student count for staff.
- **Students** (`/dashboard/students`) — the register, fetched live from
  `/api/students`, with search and status badges.

Auth token is stored in `localStorage` and sent as a Bearer header. (A future
hardening step can move this to an httpOnly cookie.)

## Run it

The backend must be running first (default `http://localhost:8000`).

```bash
npm install
cp .env.example .env.local        # sets NEXT_PUBLIC_API_URL
npm run dev                       # http://localhost:3000
```

Sign in with the seeded demo accounts (from the backend's `python seed.py`):

| Role         | Email                | Password |
|--------------|----------------------|----------|
| School admin | admin@gss-ikeja.ng   | admin123 |
| Super admin  | owner@fiyox.ng       | owner123 |

## Configuration

`NEXT_PUBLIC_API_URL` — base URL of the Fiyox backend. Set it in `.env.local`
for dev and in your host's environment for production.

## Structure

```
app/
  layout.tsx            fonts + metadata
  page.tsx              routes to /login or /dashboard
  login/page.tsx        sign-in
  dashboard/
    layout.tsx          protected shell (token check, nav, sign out)
    page.tsx            overview
    students/page.tsx   live students table
  manifest.ts           PWA manifest
  globals.css           Tailwind v4 theme tokens (navy/brass palette)
lib/
  api.ts                base URL, token handling, typed fetch, login/me
```

## Build

```bash
npm run build     # production build (also what CI runs)
```
