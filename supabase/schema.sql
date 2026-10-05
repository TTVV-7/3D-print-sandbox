-- Saved history for the generators (public/account.js).
-- Run once in Supabase > SQL Editor.  One row per download: the form's
-- settings, not the file -- the generators rebuild the same part from them.

create table if not exists public.generations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  site        text,           -- which site saved it: its hostname, e.g. printyours.ca
  kind        text not null,
  title       text not null,
  format      text,
  params      jsonb not null,
  created_at  timestamptz not null default now()
);

create index if not exists generations_user_created
  on public.generations (user_id, created_at desc);

-- The anon key is public, so this is the lock: a signed-in person sees,
-- adds and deletes their own rows and nobody else's.
alter table public.generations enable row level security;

create policy "own rows: read"   on public.generations for select using (auth.uid() = user_id);
create policy "own rows: add"    on public.generations for insert with check (auth.uid() = user_id);
create policy "own rows: delete" on public.generations for delete using (auth.uid() = user_id);
