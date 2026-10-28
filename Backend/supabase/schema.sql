-- New dedicated project only. Run through Supabase SQL editor after review.
create table if not exists public.records (
  id uuid primary key,
  owner_id uuid not null references auth.users(id),
  kind text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists records_owner_kind on public.records(owner_id, kind);
alter table public.records enable row level security;
create policy records_owner on public.records for select to authenticated
  using ((select auth.uid()) = owner_id);
revoke insert, update, delete on public.records from anon, authenticated;
grant select on public.records to authenticated;
grant all on public.records to service_role;
create or replace function public.write_records(p_owner uuid, p_rows jsonb)
returns void language plpgsql security invoker set search_path = public as $$
declare r jsonb;
begin
  for r in select * from jsonb_array_elements(p_rows) loop
    if exists(select 1 from public.records where id=(r->>'id')::uuid and owner_id<>p_owner) then
      raise exception 'record ownership mismatch';
    end if;
    insert into public.records(id, owner_id, kind, payload)
    values((r->>'id')::uuid, p_owner, r->>'kind', r->'payload')
    on conflict(id) do update set payload=excluded.payload;
  end loop;
end; $$;
revoke all on function public.write_records(uuid,jsonb) from public, anon, authenticated;
grant execute on function public.write_records(uuid,jsonb) to service_role;
insert into storage.buckets(id,name,public,file_size_limit)
values('evidence','evidence',false,10485760) on conflict(id) do nothing;
-- No browser access to storage: authenticated FastAPI owner-checks mediate every operation.
