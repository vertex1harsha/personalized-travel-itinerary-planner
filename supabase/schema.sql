-- Run in Supabase SQL Editor. Keep the service-role key only on your backend.
create table if not exists public.trips (
  id text primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  destination text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);
alter table public.trips enable row level security;
-- The FastAPI server verifies the user's JWT, then writes through service role.
-- Direct browser access is denied unless you add explicit, tested RLS policies.
