# Wanderwise — Personalized Travel Itinerary Planner

A full-stack AI travel-planning MVP aligned to the visible SkillWallet brief: React + Vite frontend, FastAPI backend, Supabase-ready trip storage/auth, Groq-powered itinerary drafts, and optional Unsplash photos.

## What is implemented

- Trip preferences: destination, date range, budget, number of travelers, interests, pace, and travel style.
- Day-by-day itinerary generation with activities, suggested times, estimated activity costs, and budget breakdown.
- Groq API integration (server-side key only), JSON parsing/validation, date normalization, and a clearly labelled demo-plan fallback when no AI key is set or the AI response is invalid.
- Save/list trips: SQLite local fallback; optional Supabase persistence for authenticated users.
- Optional Supabase email/password sign-up and sign-in from the UI.
- Optional Unsplash destination image lookup.
- Responsive dashboard, saved trips view, itinerary edit-by-regeneration, and user-facing verification notices.
- API input validation (including 1–14 day limit) and API health endpoint.

## Run locally

Requirements: Node.js 20+, Python 3.10+.

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The app works without keys in demo mode. Add `GROQ_API_KEY` to `backend/.env` to enable live AI. Optionally configure `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`; never put the service-role key in frontend variables or commit it. Optional `UNSPLASH_ACCESS_KEY` enables photos.

### 2. Frontend (new terminal)

```bash
cd ..
npm install
cp .env.example .env.local
npm run dev
```

Open the Vite URL printed by the command. Vite proxies `/api` to the local FastAPI service.

### Supabase setup

1. Create a Supabase project.
2. Run `supabase/schema.sql` in its SQL Editor.
3. Set backend URL, anon key, and service-role key in `backend/.env`.
4. The frontend reads the public Supabase URL and anon key from the backend `/api/config` endpoint at runtime, so the same setup works in local development and on Render without a frontend rebuild.
5. Sign up in the app. The API verifies the Supabase access token before writing trip rows to Supabase. Without a verified user/configuration, saving uses workspace-scoped local SQLite.

## Publish a demo URL (Render)

This repository includes a `Dockerfile` that builds the Vite frontend and serves it from FastAPI on one origin, so one Render Web Service gives you one demo URL.

1. Push the project to a GitHub repository (commands below).
2. In Render, choose **New → Web Service**, connect that repository, and select **Docker**. Render detects the `Dockerfile`.
3. Add environment variables in Render's dashboard: `GROQ_API_KEY` for real AI; optionally `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `UNSPLASH_ACCESS_KEY`. Never place the service-role key in frontend variables.
4. Deploy. Render will show a URL such as `https://your-service.onrender.com`. Open and test that URL, then submit it as the **Demo Link** in SkillWallet.
5. Submit the public GitHub repository URL (for example `https://github.com/your-name/your-repo`) as the **GitHub Link**.

GitHub push commands from the extracted project folder (replace the URL with your own empty repository):

```bash
git init
git add .
git commit -m "Build personalized travel itinerary planner"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Do not upload `.env` files or API keys. `.gitignore` excludes local secrets. The free hosting tier may sleep or use temporary disk; configure Supabase for cloud trip storage or a persistent disk if needed.

## API

- `GET /api/health` — service status and configured AI/storage mode.
- `POST /api/plan` — validate preferences and return a structured itinerary.
- `GET /api/trips` — list locally stored trips or the authenticated user's Supabase trips.
- `POST /api/trips` — persist a trip (Supabase when configured and authenticated, otherwise SQLite).
- `GET /api/photo?query=...` — optional Unsplash photo lookup.

## Notes on correctness and live travel facts

AI-generated itineraries are drafts, not bookings or verified live data. Places, opening hours, safety conditions, routes, availability, and prices can change or be inaccurate. The interface warns travelers to verify these using current local/official sources. The no-key demo mode intentionally uses generic suggestions rather than asserting unverified venue names. Budget allocation is a planning estimate, not a quote.

The provided brief's architecture names Groq, while its system-requirements screenshot also mentions local Transformer/TensorFlow files. This implementation follows the visible architecture (hosted Groq API), so a GPU/local model download is not required for the core demo. Exact collapsed workspace tasks were not visible in the supplied PDF screenshots.

## Important security note

Do not commit `.env`, API keys, or Supabase service-role credentials. This is a project MVP; before public production deployment, add rate limiting, stronger ownership checks for every data operation, logging/monitoring, and privacy/retention policies.
