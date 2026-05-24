@echo off
echo ============================================
echo  Family PetShop - Setup inicial
echo ============================================

echo.
echo [1/4] Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO: Falha ao instalar dependencias.
    pause
    exit /b 1
)

echo.
echo [2/4] Verificando arquivo .env...
if not exist .env (
    echo ATENCAO: Arquivo .env nao encontrado!
    echo Copiando example.env para .env...
    copy example.env .env
    echo.
    echo IMPORTANTE: Edite o arquivo .env com suas credenciais antes de continuar.
    echo Execute: python scripts\gerar_hash_senha.py
    pause
    exit /b 1
)

echo.
echo [3/4] Criando banco de dados...
python -c "from app import create_app; app = create_app(); "
if errorlevel 1 (
    echo ERRO: Falha ao criar banco de dados.
    pause
    exit /b 1
)

echo.
echo [4/4] Configurando backup automatico...
echo Para backup automatico no Windows, adicione uma tarefa no Agendador de Tarefas:
echo   Programa: python
echo   Argumentos: scripts\backup.py
echo   Pasta inicial: %CD%
echo   Frequencia: Diariamente

echo.
echo ============================================
echo  Setup concluido! Execute: python run.py
echo ============================================
pause
