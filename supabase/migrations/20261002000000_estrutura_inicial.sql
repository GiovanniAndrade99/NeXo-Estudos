-- NeXo Estudos — estrutura inicial do banco no Supabase (Postgres).
--
-- Decisões:
-- * O login continua no backend (scrypt, reCAPTCHA, limites). Por isso as políticas de RLS
--   não usam auth.uid() do Supabase Auth: o backend se conecta como o papel nexo_app e, a cada
--   pedido, informa a conta logada com set_config('app.usuario_id', ..., true). As políticas
--   comparam cada linha com nexo.usuario_atual().
-- * Tudo fica no schema "nexo", que NÃO é exposto pela API REST do Supabase (só "public" é).
--   Mesmo assim o RLS fica ativo em todas as tabelas.
-- * Operações anteriores ao login (entrar, cadastrar, recuperar senha) passam por funções
--   SECURITY DEFINER pequenas, únicas portas de acesso a essas linhas sem conta logada.

create extension if not exists pgcrypto with schema extensions;

create schema if not exists nexo;
revoke all on schema nexo from public, anon, authenticated;

-- Papel usado pelo backend. A senha é definida fora desta migração:
--   alter role nexo_app with password '...';
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'nexo_app') then
    create role nexo_app login noinherit nobypassrls;
  end if;
end $$;
grant usage on schema nexo to nexo_app;

-- ---------------------------------------------------------------------------
-- Tabelas
-- ---------------------------------------------------------------------------

create table if not exists nexo.usuarios (
  id               bigint generated always as identity primary key,
  email            text        not null unique check (email = lower(btrim(email)) and email like '%_@_%._%'),
  nome             text        not null check (length(btrim(nome)) between 1 and 80),
  senha_hash       text        not null check (senha_hash like 'scrypt$%'),
  papel            text        not null default 'usuario' check (papel in ('usuario', 'admin')),
  criado_em        timestamptz not null default now(),
  consentimento_em timestamptz,
  versao_politica  text,
  check ((consentimento_em is null) = (versao_politica is null))
);
comment on table nexo.usuarios is 'Contas do NeXo Estudos. A senha é guardada apenas como hash scrypt.';

create table if not exists nexo.tokens_senha (
  token_hash text        primary key,
  usuario_id bigint      not null references nexo.usuarios (id) on delete cascade,
  expira_em  timestamptz not null
);
create index if not exists tokens_senha_usuario_idx on nexo.tokens_senha (usuario_id);
comment on table nexo.tokens_senha is 'Links de recuperação de senha (só o hash SHA-256 do token).';

create table if not exists nexo.processamentos (
  id                uuid        primary key default gen_random_uuid(),
  usuario_id        bigint      not null references nexo.usuarios (id) on delete cascade,
  nome_arquivo      text        not null check (length(nome_arquivo) <= 300),
  pagina            integer     check (pagina > 0),
  largura           integer     check (largura > 0),
  altura            integer     check (altura > 0),
  tempo_ms          numeric(12, 2) check (tempo_ms >= 0),
  ocr_disponivel    boolean     not null default false,
  inclinacao_graus  numeric(6, 2),
  palavras          integer     not null default 0 check (palavras >= 0),
  trecho            text        not null default '' check (length(trecho) <= 400),
  assistente        jsonb       not null default '{}'::jsonb,
  miniatura_caminho text        check (miniatura_caminho like usuario_id::text || '/%'),
  criado_em         timestamptz not null default now()
);
create index if not exists processamentos_usuario_data_idx on nexo.processamentos (usuario_id, criado_em desc);
comment on table nexo.processamentos is 'Histórico de imagens processadas. A miniatura fica no Storage, bucket "miniaturas".';

-- ---------------------------------------------------------------------------
-- Conta logada (definida pelo backend em cada transação)
-- ---------------------------------------------------------------------------

create or replace function nexo.usuario_atual() returns bigint
  language sql stable
  set search_path = ''
as $$ select nullif(current_setting('app.usuario_id', true), '')::bigint $$;

-- ---------------------------------------------------------------------------
-- RLS: cada conta só enxerga e altera as próprias linhas
-- ---------------------------------------------------------------------------

-- Sem FORCE: o dono das tabelas (que executa as funções SECURITY DEFINER) não passa pelo RLS;
-- o papel nexo_app, usado pelo backend, passa sempre.
alter table nexo.usuarios       enable row level security;
alter table nexo.tokens_senha   enable row level security;
alter table nexo.processamentos enable row level security;

grant select, update, delete on nexo.usuarios to nexo_app;
grant select, insert, delete on nexo.processamentos to nexo_app;
-- tokens_senha: nenhum acesso direto; só pelas funções abaixo.

drop policy if exists usuarios_propria_linha on nexo.usuarios;
create policy usuarios_propria_linha on nexo.usuarios
  for all to nexo_app
  using (id = nexo.usuario_atual())
  with check (id = nexo.usuario_atual());

drop policy if exists processamentos_do_usuario on nexo.processamentos;
create policy processamentos_do_usuario on nexo.processamentos
  for all to nexo_app
  using (usuario_id = nexo.usuario_atual())
  with check (usuario_id = nexo.usuario_atual());

-- Impede que o próprio usuário promova a conta a admin pelo UPDATE liberado acima.
create or replace function nexo.proteger_papel() returns trigger
  language plpgsql
  set search_path = ''
as $$
begin
  if new.papel is distinct from old.papel and current_user = 'nexo_app' then
    raise exception 'papel da conta não pode ser alterado pelo aplicativo';
  end if;
  return new;
end $$;
drop trigger if exists usuarios_proteger_papel on nexo.usuarios;
create trigger usuarios_proteger_papel before update on nexo.usuarios
  for each row execute function nexo.proteger_papel();

-- ---------------------------------------------------------------------------
-- Funções de acesso antes do login (SECURITY DEFINER)
-- ---------------------------------------------------------------------------

-- Login e recuperação de senha: busca a conta pelo e-mail (inclui o hash para o backend conferir).
create or replace function nexo.conta_por_email(p_email text) returns setof nexo.usuarios
  language sql stable security definer
  set search_path = ''
as $$ select * from nexo.usuarios where email = lower(btrim(p_email)) $$;

create or replace function nexo.criar_conta(
  p_email text, p_nome text, p_senha_hash text, p_versao_politica text
) returns nexo.usuarios
  language sql security definer
  set search_path = ''
as $$
  insert into nexo.usuarios (email, nome, senha_hash, consentimento_em, versao_politica)
  values (lower(btrim(p_email)), left(btrim(p_nome), 80), p_senha_hash,
          case when p_versao_politica is null then null else now() end, p_versao_politica)
  returning *
$$;

-- Refaz o hash com o custo atual logo após um login bem-sucedido.
create or replace function nexo.atualizar_hash(p_usuario_id bigint, p_senha_hash text) returns void
  language sql security definer
  set search_path = ''
as $$ update nexo.usuarios set senha_hash = p_senha_hash where id = p_usuario_id $$;

create or replace function nexo.criar_token_senha(p_email text, p_token_hash text, p_validade interval)
  returns boolean
  language plpgsql security definer
  set search_path = ''
as $$
declare
  v_id bigint;
begin
  select id into v_id from nexo.usuarios where email = lower(btrim(p_email));
  if v_id is null then
    return false;
  end if;
  delete from nexo.tokens_senha where usuario_id = v_id or expira_em < now();
  insert into nexo.tokens_senha (token_hash, usuario_id, expira_em) values (p_token_hash, v_id, now() + p_validade);
  return true;
end $$;

-- Troca a senha pelo link de recuperação: o token vale uma vez e precisa estar dentro da validade.
create or replace function nexo.redefinir_senha(p_token_hash text, p_senha_hash text) returns setof nexo.usuarios
  language plpgsql security definer
  set search_path = ''
as $$
declare
  v_id bigint;
begin
  delete from nexo.tokens_senha
   where token_hash = p_token_hash and expira_em >= now()
  returning usuario_id into v_id;
  if v_id is null then
    return;
  end if;
  delete from nexo.tokens_senha where usuario_id = v_id;
  return query update nexo.usuarios set senha_hash = p_senha_hash where id = v_id returning *;
end $$;

-- Troca de senha estando logado: invalida também os links de recuperação pendentes.
create or replace function nexo.trocar_senha(p_senha_hash text) returns void
  language plpgsql security definer
  set search_path = ''
as $$
begin
  if nexo.usuario_atual() is null then
    raise exception 'nenhuma conta logada';
  end if;
  update nexo.usuarios set senha_hash = p_senha_hash where id = nexo.usuario_atual();
  delete from nexo.tokens_senha where usuario_id = nexo.usuario_atual();
end $$;

-- Exportação LGPD: quantos links de recuperação pendentes a conta logada tem.
create or replace function nexo.tokens_pendentes() returns integer
  language sql stable security definer
  set search_path = ''
as $$ select count(*)::integer from nexo.tokens_senha where usuario_id = nexo.usuario_atual() and expira_em >= now() $$;

revoke all on function
  nexo.conta_por_email(text), nexo.criar_conta(text, text, text, text), nexo.atualizar_hash(bigint, text),
  nexo.criar_token_senha(text, text, interval), nexo.redefinir_senha(text, text), nexo.trocar_senha(text),
  nexo.tokens_pendentes(), nexo.usuario_atual(), nexo.proteger_papel()
  from public, anon, authenticated;
grant execute on function
  nexo.conta_por_email(text), nexo.criar_conta(text, text, text, text), nexo.atualizar_hash(bigint, text),
  nexo.criar_token_senha(text, text, interval), nexo.redefinir_senha(text, text), nexo.trocar_senha(text),
  nexo.tokens_pendentes(), nexo.usuario_atual()
  to nexo_app;

-- ---------------------------------------------------------------------------
-- Storage: miniaturas do histórico (bucket privado, só JPEG até 2 MB)
-- O backend envia e lê com a chave de serviço; nenhum acesso público.
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('miniaturas', 'miniaturas', false, 2097152, array['image/jpeg'])
on conflict (id) do update
  set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;
