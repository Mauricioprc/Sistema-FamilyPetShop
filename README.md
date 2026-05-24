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
