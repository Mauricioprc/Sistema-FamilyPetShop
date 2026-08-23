# Family PetShop — Sistema de Gestão

Sistema de agendamento e gestão para pet shop. Desenvolvido em Flask + SQLite.

---

## Setup inicial

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar o arquivo .env

```bash
# Copiar o template
copy example.env .env   # Windows
cp example.env .env     # Linux/Mac

# Gerar as credenciais
python scripts/gerar_hash_senha.py
```

Preencha o `.env` com os valores gerados:

```
SECRET_KEY=<gerado pelo script>
ADMIN_USERNAME=seu_usuario
ADMIN_PASSWORD_HASH=<gerado pelo script>
FLASK_ENV=development
```

> ⚠️ **NUNCA** compartilhe o arquivo `.env` nem o inclua em ZIPs ou commits.

### 3. Rodar a migration (apenas uma vez)

```bash
python migrations_manual/add_avaliacao_data.py
```

### 4. Iniciar o sistema

```bash
python run.py
```

Acesse: http://127.0.0.1:5000

---

## Backup do banco de dados

```bash
# Fazer backup agora
python scripts/backup.py

# Listar backups existentes
python scripts/backup.py listar
```

**Configurar backup automático no Windows (recomendado):**
1. Abrir o Agendador de Tarefas
2. Criar tarefa básica: diária às 03:00
3. Programa: `python`
4. Argumentos: `scripts\backup.py`
5. Pasta inicial: caminho completo do projeto

**Enviar cópia automática para o Google Drive (opcional):**

Além da cópia local em `instance/backups`, o `scripts/backup.py` também pode
enviar o backup do dia para uma pasta do Google Drive, usando uma
**Service Account** do Google. Essa abordagem funciona tanto local quanto
no **PythonAnywhere Free** (que só libera acesso à internet para uma lista
de domínios conhecidos — as APIs do Google estão nela), sem precisar de
login interativo no servidor.

1. No [Google Cloud Console](https://console.cloud.google.com/), crie um
   projeto (ou use um existente) e ative a **Google Drive API**
   (menu "APIs e serviços" → "Ativar APIs e serviços" → busque "Google Drive API").
2. Em "Credenciais" → "Criar credenciais" → **Conta de serviço**, dê um nome
   (ex: `petshop-backup`) e conclua sem adicionar papéis/permissões extras.
3. Abra a conta de serviço criada → aba "Chaves" → "Adicionar chave" →
   "Criar nova chave" → formato **JSON**. Isso baixa um arquivo `.json`.
4. Copie esse arquivo para `instance/google-service-account.json` no projeto
   (essa pasta já é ignorada pelo git — nunca vai parar no GitHub).
5. No Google Drive normal (com sua conta pessoal), crie uma pasta, ex:
   "PetShopBackups". Clique em Compartilhar e adicione o **e-mail da conta
   de serviço** (algo como `petshop-backup@SEU-PROJETO.iam.gserviceaccount.com`,
   encontrado no arquivo JSON no campo `client_email`) com permissão de
   **Editor**.
6. Pegue o **ID da pasta**: abra a pasta no navegador e copie o trecho final
   da URL (`https://drive.google.com/drive/folders/`**`ESSE_TRECHO_AQUI`**).
7. No `.env` (local) ou nas variáveis de ambiente do PythonAnywhere, defina:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=instance/google-service-account.json
   GOOGLE_DRIVE_FOLDER_ID=id_copiado_no_passo_6
   ```
8. Rode `pip install -r requirements.txt` para instalar as dependências do
   Google (`google-api-python-client`, `google-auth`).
9. Pronto — a partir do próximo backup, o arquivo também é enviado ao Drive
   automaticamente. Se essas variáveis não estiverem configuradas, o backup
   local continua funcionando normalmente e o envio ao Drive é apenas pulado.

**Em produção (PythonAnywhere Free — sem aba Tasks disponível):**

Contas Free do PythonAnywhere não têm a aba Tasks (agendamento automático é
recurso pago), então o backup em produção é feito pelo **aviso dentro do
próprio sistema**: todo dia, ao logar, o admin vê um modal lembrando de
clicar em "Sim, baixar agora" (`GET /backup/download`). Esse clique já:
1. Baixa o `.db` para o computador de quem está logado
2. Envia automaticamente uma cópia para o Google Drive (se
   `GOOGLE_SERVICE_ACCOUNT_FILE`/`GOOGLE_DRIVE_FOLDER_ID` estiverem
   configurados nas variáveis de ambiente do PythonAnywhere)
3. Marca a data do backup, então o aviso só volta a aparecer no dia seguinte

Se sua conta do PythonAnywhere for paga (Hacker ou superior), prefira
agendar `python scripts/backup.py` na aba Tasks diariamente — é totalmente
automático e não depende de alguém estar logado no sistema naquele dia.

---

## Rodar os testes

```bash
python -m pytest tests/ -v
```

---

## Estrutura do projeto

```
sistema_pet/
├── app.py               # Factory da aplicação
├── config.py            # Configurações por ambiente
├── extensions.py        # Flask extensions (db, csrf, limiter...)
├── models.py            # Models do banco de dados
├── utils.py             # Funções utilitárias
├── run.py               # Ponto de entrada
├── .env                 # Credenciais (NÃO versionar)
├── example.env          # Template do .env
├── .gitignore           # Arquivos a ignorar no Git
├── requirements.txt     # Dependências Python
├── rotas/               # Blueprints (agenda, clientes, pacotes...)
├── services/            # Lógica de negócio separada das rotas
├── templates/           # HTML (Jinja2)
├── static/              # CSS, imagens
├── instance/            # Banco de dados e logs (NÃO versionar)
├── scripts/             # Utilitários (backup, gerar hash...)
├── migrations_manual/   # Migrations avulsas
└── tests/               # Testes automatizados (pytest)
```

---

## Segurança implementada

- ✅ CSRF em todos os formulários (Flask-WTF)
- ✅ Rate limiting em rotas públicas (Flask-Limiter)
- ✅ Senhas com hash PBKDF2-SHA256 (600k iterações)
- ✅ Proteção contra open redirect no login
- ✅ Validação de magic bytes em uploads de imagem
- ✅ SECRET_KEY e credenciais somente via variáveis de ambiente
- ✅ Banco de dados em caminho único (`instance/petshop.db`)

---

## Trocar a senha do administrador

```bash
python scripts/gerar_hash_senha.py
```

Cole os valores gerados no `.env` e reinicie o sistema.
