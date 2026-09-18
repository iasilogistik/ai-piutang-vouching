-- Supabase-specific production authorization/storage setup.
-- Keep outside Alembic because this depends on Supabase auth/storage schemas.
do $$ begin create type public.app_role as enum ('ADMIN','AUDITOR','REVIEWER','VIEWER'); exception when duplicate_object then null; end $$;
create table if not exists public.user_roles (
 user_id uuid primary key references auth.users(id) on delete cascade,
 role public.app_role not null default 'VIEWER',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.user_roles enable row level security;
create or replace function public.current_app_role() returns public.app_role language sql stable security invoker
as $$ select coalesce((select role from public.user_roles where user_id=auth.uid()),'VIEWER'::public.app_role) $$;
revoke all on public.documents,public.import_batches,public.sap_billing,public.physical_billing,public.billing_reconciliation,public.spj,public.vouching_result,public.audit_trail from anon;
grant select on public.documents,public.import_batches,public.sap_billing,public.physical_billing,public.billing_reconciliation,public.spj,public.vouching_result,public.audit_trail,public.user_roles to authenticated;
drop policy if exists user_roles_read_own on public.user_roles;
create policy user_roles_read_own on public.user_roles for select to authenticated using(user_id=auth.uid());
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('audit-documents','audit-documents',false,52428800,array['application/pdf','image/jpeg','image/png'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
drop policy if exists audit_documents_read on storage.objects;
create policy audit_documents_read on storage.objects for select to authenticated using(bucket_id='audit-documents');
drop policy if exists audit_documents_insert on storage.objects;
create policy audit_documents_insert on storage.objects for insert to authenticated with check(bucket_id='audit-documents' and public.current_app_role() in ('ADMIN','AUDITOR'));
drop policy if exists audit_documents_update on storage.objects;
create policy audit_documents_update on storage.objects for update to authenticated using(bucket_id='audit-documents' and public.current_app_role() in ('ADMIN','AUDITOR')) with check(bucket_id='audit-documents' and public.current_app_role() in ('ADMIN','AUDITOR'));
