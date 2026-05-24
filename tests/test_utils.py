"""
Testes unitarios para utils.py
Execute: python -m pytest tests/ -v
"""
import pytest
from datetime import date, timedelta


# ---- parse_preco ----

def test_parse_preco_valor_normal():
    from utils import parse_preco
    assert parse_preco('50,00') == 50.0  # formato brasileiro

def test_parse_preco_formato_brasileiro():
    from utils import parse_preco
    assert parse_preco('1.250,50') == 1250.5

def test_parse_preco_com_rs():
    from utils import parse_preco
    assert parse_preco('R$ 99,90') == 99.9

def test_parse_preco_vazio():
    from utils import parse_preco
    assert parse_preco('') == 0.0

def test_parse_preco_none():
    from utils import parse_preco
    assert parse_preco(None) == 0.0

def test_parse_preco_zero():
    from utils import parse_preco
    assert parse_preco('0') == 0.0


# ---- formatar_telefone_whatsapp ----

def test_telefone_sem_codigo_pais():
    from utils import formatar_telefone_whatsapp
    assert formatar_telefone_whatsapp('11999887766') == '5511999887766'

def test_telefone_com_formatacao():
    from utils import formatar_telefone_whatsapp
    assert formatar_telefone_whatsapp('(11) 99988-7766') == '5511999887766'

def test_telefone_ja_tem_55():
    from utils import formatar_telefone_whatsapp
    assert formatar_telefone_whatsapp('5511999887766') == '5511999887766'


# ---- validar_telefone ----

def test_telefone_valido():
    from utils import validar_telefone
    assert validar_telefone('11999887766') is True

def test_telefone_curto():
    from utils import validar_telefone
    assert validar_telefone('123') is False

def test_telefone_com_mascara():
    from utils import validar_telefone
    assert validar_telefone('(11) 9988-7766') is True


# ---- consumir_credito / devolver_credito ----

class PacoteMock:
    def __init__(self, usados, totais, status='Ativo'):
        self.creditos_usados = usados
        self.creditos_totais = totais
        self.status = status

def test_consumir_credito_normal():
    from utils import consumir_credito
    p = PacoteMock(3, 5)
    concluido = consumir_credito(p)
    assert p.creditos_usados == 4
    assert concluido is False
    assert p.status == 'Ativo'

def test_consumir_credito_ultimo():
    from utils import consumir_credito
    p = PacoteMock(4, 5)
    concluido = consumir_credito(p)
    assert p.creditos_usados == 5
    assert concluido is True
    assert p.status == 'Concluido'

def test_consumir_credito_ja_cheio():
    from utils import consumir_credito
    p = PacoteMock(5, 5)
    concluido = consumir_credito(p)
    assert p.creditos_usados == 5  # nao muda
    assert concluido is False

def test_devolver_credito():
    from utils import devolver_credito
    p = PacoteMock(3, 5)
    devolver_credito(p)
    assert p.creditos_usados == 2

def test_devolver_credito_concluido_reabre():
    from utils import devolver_credito
    p = PacoteMock(5, 5, status='Concluido')
    devolver_credito(p)
    assert p.creditos_usados == 4
    assert p.status == 'Ativo'

def test_devolver_credito_zero_nao_nega():
    from utils import devolver_credito
    p = PacoteMock(0, 5)
    devolver_credito(p)
    assert p.creditos_usados == 0  # nao vai para -1


# ---- calcular_datas_pacote ----

def test_calcular_datas_semanal():
    from utils import calcular_datas_pacote
    inicio = date(2025, 1, 6)  # segunda-feira
    datas = calcular_datas_pacote(inicio, 4, 'semanal', 0)  # 0 = segunda
    assert len(datas) == 4
    for i in range(1, len(datas)):
        assert (datas[i] - datas[i-1]).days == 7

def test_calcular_datas_quinzenal():
    from utils import calcular_datas_pacote
    inicio = date(2025, 1, 6)
    datas = calcular_datas_pacote(inicio, 3, 'quinzenal', 0)
    assert len(datas) == 3
    for i in range(1, len(datas)):
        assert (datas[i] - datas[i-1]).days == 14

def test_calcular_datas_dia_correto():
    from utils import calcular_datas_pacote
    inicio = date(2025, 1, 1)  # quarta
    datas = calcular_datas_pacote(inicio, 3, 'semanal', 4)  # 4 = sexta
    for d in datas:
        assert d.weekday() == 4  # todas sextas
