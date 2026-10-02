# Banco de dados no Supabase

Estrutura do banco do NeXo Estudos, versionada como migrações SQL.

## O que existe

| Objeto | Função |
|---|---|
| Schema `nexo` | Tudo do projeto; não é exposto pela API REST do Supabase |
| `nexo.usuarios` | Contas: e-mail, nome, hash scrypt da senha, papel e aceite da Política de Privacidade |
| `nexo.tokens_senha` | Links de recuperação de senha (só o hash SHA-256 do token) |
| `nexo.processamentos` | Histórico de cada conta (até 50 registros, os mais antigos são apagados pelo backend) |
| Bucket `miniaturas` | Storage privado com as miniaturas JPEG, em `<id da conta>/<id do registro>.jpg` |
| Papel `nexo_app` | Usuário de banco do backend: sem `BYPASSRLS`, só com as permissões necessárias |

## Como o RLS funciona aqui

O login é feito pelo próprio backend (não pelo Supabase Auth), então as políticas não usam `auth.uid()`.
Em cada operação de uma conta logada, o backend abre uma transação e executa
`select set_config('app.usuario_id', '<id>', true)`. As políticas comparam cada linha com
`nexo.usuario_atual()`: mesmo que o código do backend erre um filtro, o banco recusa dados de outra conta.

Antes do login (entrar, cadastrar, recuperar senha) o acesso passa apenas por funções `SECURITY DEFINER`
pequenas (`conta_por_email`, `criar_conta`, `criar_token_senha`, `redefinir_senha`...). A tabela de tokens
não pode ser lida diretamente, e um gatilho impede o aplicativo de mudar o papel de uma conta.

## Aplicar as migrações num projeto novo

1. Copie `.env.example` para `.env` e preencha `SUPABASE_URL`, `SUPABASE_DB_URL` (Session pooler, porta 5432)
   e `SUPABASE_SERVICE_ROLE_KEY`.
2. Aplique os arquivos de `migrations/` em ordem (pelo SQL Editor do painel ou com `psql`).
3. Defina a senha do papel do backend e monte a `NEXO_DB_URL`:
   ```sql
   alter role nexo_app with password 'uma-senha-longa-e-aleatoria';
   ```
   `NEXO_DB_URL=postgresql://nexo_app.<id-do-projeto>:<senha>@<host-do-pooler>:5432/postgres`
4. Para trazer contas de um `contas.db` existente: `python tools/migrar_contas_para_supabase.py`.
   Para criar o administrador do zero: `python -m backend.contas`.
