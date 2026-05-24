"""
Utilitario para gerar hash de senha para o .env
Uso: python scripts/gerar_hash_senha.py
"""
from werkzeug.security import generate_password_hash
import secrets
import sys

print("=" * 50)
print("Gerador de credenciais para o .env")
print("=" * 50)

if len(sys.argv) > 1:
    senha = sys.argv[1]
else:
    senha = input("\nDigite a nova senha do administrador: ")

if len(senha) < 6:
    print("ERRO: Senha deve ter ao menos 6 caracteres.")
    sys.exit(1)

hash_senha = generate_password_hash(senha)
secret_key = secrets.token_hex(32)

print(f"\n✅ Adicione estas linhas ao seu .env:\n")
print(f"SECRET_KEY={secret_key}")
print(f"ADMIN_PASSWORD_HASH={hash_senha}")
print("\n⚠️  Nunca compartilhe o arquivo .env!")
