import calendar
from datetime import date, timedelta
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func
from extensions import db
from models import Atendimento, Pacote, Despesa
from services.previsao_service import gerar_previsao_recebimento, listar_vencendo_no_mes

dashboard_bp = Blueprint('dashboard', __name__)

# Função auxiliar para colocar a máscara de dinheiro (ex: 1.500,00)
def formata_brl(valor):
    if not valor: valor = 0
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    hoje = date.today()
    
    # Capturar Filtros de Mês e Ano
    mes_sel = int(request.args.get('mes', hoje.month))
    ano_sel = int(request.args.get('ano', hoje.year))

    inicio_mes = date(ano_sel, mes_sel, 1)
    ultimo_dia = calendar.monthrange(ano_sel, mes_sel)[1]
    fim_mes = date(ano_sel, mes_sel, ultimo_dia)

    fim_mes_anterior = inicio_mes - timedelta(days=1)
    inicio_mes_anterior = date(fim_mes_anterior.year, fim_mes_anterior.month, 1)

    # --- 1. FINANCEIRO: FATURAMENTO E TAXAS ---
    fat_atend = db.session.query(
        func.sum(Atendimento.preco).label('bruto'),
        func.sum(Atendimento.taxa_maquina).label('taxa')
    ).filter(
        Atendimento.status_pagamento == 'Pago',
        Atendimento.data_pagamento.between(inicio_mes, fim_mes)
    ).first()

    fat_pacote = db.session.query(
        func.sum(Pacote.preco_pacote).label('bruto'),
        func.sum(Pacote.taxa_maquina).label('taxa')
    ).filter(
        Pacote.status_pagamento == 'Pago',
        Pacote.data_pagamento.between(inicio_mes, fim_mes)
    ).first()

    recebido_bruto = (fat_atend.bruto or 0) + (fat_pacote.bruto or 0)
    perda_taxas = (fat_atend.taxa or 0) + (fat_pacote.taxa or 0)
    
    # CORREÇÃO: O líquido agora é matematicamente exato (Bruto - Taxa)
    recebido_liquido = recebido_bruto - perda_taxas

    # --- 2 e 3. DESPESAS E LUCRO ---
    todas_despesas = db.session.query(func.sum(Despesa.valor)).filter(
        Despesa.data.between(inicio_mes, fim_mes)
    ).scalar() or 0

    # Filtra as despesas específicas do Petshop (case-insensitive)
    despesas_petshop = db.session.query(func.sum(Despesa.valor)).filter(
        Despesa.data.between(inicio_mes, fim_mes),
        Despesa.tipo.ilike('%Petshop%') 
    ).scalar() or 0

    # Lucros calculados
    lucro_operacional = recebido_liquido - despesas_petshop
    lucro_real = recebido_liquido - todas_despesas

    # --- 5. DINHEIRO NA RUA (Pendente +10 dias) ---
    limite_atraso = hoje - timedelta(days=10)
    
    pend_atend = db.session.query(func.sum(Atendimento.preco)).filter(
        Atendimento.status_pagamento == 'Pendente',
        Atendimento.status_presenca == 'Presente',
        Atendimento.data <= limite_atraso
    ).scalar() or 0
    
    pend_pacote = db.session.query(func.sum(Pacote.preco_pacote)).filter(
        Pacote.status_pagamento == 'Pendente',
        Pacote.data_vencimento <= limite_atraso
    ).scalar() or 0
    
    dinheiro_na_rua = pend_atend + pend_pacote

    # --- 8. PRODUTIVIDADE ---
    serv_atual = Atendimento.query.filter(
        Atendimento.status_presenca == 'Presente',
        Atendimento.data.between(inicio_mes, fim_mes)
    ).count()

    serv_anterior = Atendimento.query.filter(
        Atendimento.status_presenca == 'Presente',
        Atendimento.data.between(inicio_mes_anterior, fim_mes_anterior)
    ).count()

    if serv_anterior > 0:
        var_servicos = round(((serv_atual - serv_anterior) / serv_anterior) * 100, 1)
    else:
        var_servicos = 100 if serv_atual > 0 else 0

    # --- 6. GRÁFICO ---
    receita_avulso = (fat_atend.bruto or 0) - (fat_atend.taxa or 0)
    receita_pacote = (fat_pacote.bruto or 0) - (fat_pacote.taxa or 0)

    # --- 9. PREVISÃO DE RECEBIMENTO ---
    meses_nomes = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho',
                   'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

    modo_previsao = request.args.get('modo', 'previsao')
    mes_previsao_sel = int(request.args.get('mes_previsao', hoje.month))
    ano_previsao_sel = int(request.args.get('ano_previsao', hoje.year))

    previsao = None
    vencendo_itens = None

    if modo_previsao == 'vencendo':
        vencendo_itens = listar_vencendo_no_mes(mes_previsao_sel, ano_previsao_sel)
    else:
        previsao = gerar_previsao_recebimento(mes_previsao_sel, ano_previsao_sel)

    # Enviamos os valores já formatados como strings (R$ 1.500,00)
    return render_template('dashboard.html',
                           hoje=hoje,
                           mes_selecionado=mes_sel, ano_selecionado=ano_sel, ano_atual=hoje.year,
                           recebido_bruto=formata_brl(recebido_bruto),
                           recebido_liquido=formata_brl(recebido_liquido),
                           perda_taxas=formata_brl(perda_taxas),
                           despesas_petshop=formata_brl(despesas_petshop),
                           todas_despesas=formata_brl(todas_despesas),
                           lucro_operacional=formata_brl(lucro_operacional),
                           lucro_real=formata_brl(lucro_real),
                           dinheiro_na_rua=formata_brl(dinheiro_na_rua),
                           servicos_concluidos=serv_atual,
                           var_servicos=var_servicos,
                           receita_avulso=receita_avulso,
                           receita_pacote=receita_pacote,
                           modo_previsao=modo_previsao,
                           mes_previsao_sel=mes_previsao_sel,
                           ano_previsao_sel=ano_previsao_sel,
                           nome_mes_previsao=meses_nomes[mes_previsao_sel - 1],
                           previsao=previsao,
                           vencendo_itens=vencendo_itens,
                           formata_brl=formata_brl)