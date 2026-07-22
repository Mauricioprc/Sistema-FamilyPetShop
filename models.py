from datetime import datetime, timezone, date, timedelta
from enum import Enum
from extensions import db


# ============================================
# ENUMS
# ============================================

class StatusAtendimento(str, Enum):
    AGENDADO = "Agendado"
    PRESENTE = "Presente"
    FALTOU = "Faltou"
    SOLICITADO_ONLINE = "Solicitado_Online"
    CANCELADO = "Cancelado"


class StatusPacote(str, Enum):
    ATIVO = "Ativo"
    CONCLUIDO = "Concluido"
    CANCELADO = "Cancelado"


class StatusPagamento(str, Enum):
    PENDENTE = "Pendente"
    PAGO = "Pago"
    PAGO_PACOTE = "Pago (Pacote)"
    CANCELADO = "Cancelado (Falta)"


# ============================================
# MODELS
# ============================================

class Cliente(db.Model):
    __tablename__ = 'cliente'

    id = db.Column(db.Integer, primary_key=True)
    nome_tutor = db.Column(db.String(100), nullable=False, index=True)
    telefone = db.Column(db.String(20), nullable=False)
    nome_pet = db.Column(db.String(100), nullable=False, index=True)
    raca_pet = db.Column(db.String(50), nullable=True)
    tipo_pet = db.Column(db.String(50), nullable=True)
    sexo_pet = db.Column(db.String(10), nullable=True)
    endereco = db.Column(db.Text, nullable=True)
    castrado = db.Column(db.String(5), nullable=True)
    temperamento = db.Column(db.String(50), nullable=True)
    peso_pet = db.Column(db.Float, nullable=True)

    ativo = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    pacotes = db.relationship('Pacote', backref='cliente', lazy='dynamic',
                              cascade='all, delete-orphan')
    atendimentos = db.relationship('Atendimento', backref='cliente', lazy='dynamic',
                                   cascade='all, delete-orphan')
    
    @property
    def tem_divida_atrasada(self):
        """Verifica se o cliente tem pacotes ou atendimentos devendo há mais de 10 dias."""
        limite_atraso = date.today() - timedelta(days=10)
        
        # 1. Checa pacotes pendentes vencidos
        pacotes_devendo = self.pacotes.filter_by(status_pagamento='Pendente').all()
        for p in pacotes_devendo:
            if p.data_vencimento and p.data_vencimento <= limite_atraso:
                return True
                
        # 2. Checa atendimentos avulsos que ocorreram (Presente) mas não foram pagos
        atendimentos_devendo = self.atendimentos.filter_by(status_pagamento='Pendente', status_presenca='Presente').all()
        for a in atendimentos_devendo:
            if a.data and a.data <= limite_atraso:
                return True
                
        return False
    
    @property
    def pacotes_em_atraso(self):
        """Retorna a lista de pacotes devendo há mais de 10 dias."""
        limite_atraso = date.today() - timedelta(days=10)
        return [p for p in self.pacotes.filter_by(status_pagamento='Pendente').all() 
                if p.data_vencimento and p.data_vencimento <= limite_atraso]

    @property
    def atendimentos_avulsos_em_atraso(self):
        """Retorna a lista de atendimentos avulsos devendo há mais de 10 dias."""
        limite_atraso = date.today() - timedelta(days=10)
        return [a for a in self.atendimentos.filter_by(status_pagamento='Pendente', status_presenca='Presente').all() 
                if a.data and a.data <= limite_atraso]

    def __repr__(self):
        return f'<Cliente {self.nome_tutor}>'

    def __str__(self):
        return f"{self.nome_tutor} - {self.nome_pet}"
    


class Pacote(db.Model):
    __tablename__ = 'pacote'

    id = db.Column(db.Integer, primary_key=True)
    nome_servico = db.Column(db.String(100), nullable=False)
    creditos_totais = db.Column(db.Integer, nullable=False)
    creditos_usados = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(50), default=StatusPacote.ATIVO.value,
                       nullable=False, index=True)
    preco_pacote = db.Column(db.Float, nullable=False)
    status_pagamento = db.Column(db.String(50), default=StatusPagamento.PENDENTE.value,
                                 nullable=False, index=True)
    data_pagamento = db.Column(db.Date, nullable=True)
    data_vencimento = db.Column(db.Date, nullable=True)
    vencimento_customizado = db.Column(db.Boolean, default=False, nullable=False)
    metodo_pagamento = db.Column(db.String(50), nullable=True)
    dia_semana_fixo = db.Column(db.Integer, nullable=True)
    tipo_agendamento = db.Column(db.String(20), nullable=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'),
                           nullable=False, index=True)
    taxa_maquina = db.Column(db.Float, default=0.0)
    valor_liquido = db.Column(db.Float, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    atendimentos = db.relationship('Atendimento', backref='pacote', lazy='dynamic',
                                   cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Pacote {self.id} - {self.nome_servico}>'

    def creditos_restantes(self):
        return self.creditos_totais - self.creditos_usados


class Atendimento(db.Model):
    __tablename__ = 'atendimento'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    nome_servico = db.Column(db.String(100), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    observacao = db.Column(db.Text, nullable=True)
    status_pagamento = db.Column(db.String(50), default=StatusPagamento.PENDENTE.value,
                                 nullable=False, index=True)
    data_pagamento = db.Column(db.Date, nullable=True)
    metodo_pagamento = db.Column(db.String(50), nullable=True)
    status_presenca = db.Column(db.String(50), default=StatusAtendimento.AGENDADO.value,
                                nullable=False, index=True)
    horario_preferido = db.Column(db.String(20), nullable=True)
    transporte = db.Column(db.String(50), nullable=True)
    endereco_busca = db.Column(db.Text, nullable=True)
    adicionais = db.Column(db.String(200), nullable=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'),
                           nullable=False, index=True)
    pacote_id = db.Column(db.Integer, db.ForeignKey('pacote.id'),
                          nullable=True, index=True)
    taxa_maquina = db.Column(db.Float, default=0.0)
    valor_liquido = db.Column(db.Float, nullable=True)

    # Indica se o serviço já terminou e o pet está pronto para ser
    # buscado. Conceito independente de status_presenca: este último
    # trata de "o pet chegou/faltou no início do atendimento", enquanto
    # pronto_para_buscar trata do fim do atendimento. Só faz sentido
    # operacionalmente quando o tutor é quem vai buscar o pet (ver
    # property eh_busca_pelo_tutor abaixo) — daí o default False e o uso
    # restrito a esse cenário nas telas que consomem este campo.
    pronto_para_buscar = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f'<Atendimento {self.id} - {self.data}>'

    def __str__(self):
        return f"{self.cliente.nome_pet} - {self.nome_servico} em {self.data}"
    
    @property
    def eh_solicitacao_online(self):
        """Verifica se este atendimento foi originado pelo site."""
        # Se tem horario preferido, adicionais ou transporte, assumimos que veio do site
        return bool(self.horario_preferido or self.transporte or self.adicionais)

    @property
    def eh_busca_pelo_tutor(self):
        """
        True quando é o próprio tutor quem busca o pet no petshop (ele NÃO
        usa Táxi Dog neste atendimento).

        Fonte de verdade principal: Cliente.endereco. O cadastro de
        cliente (form_cliente.html) usa a presença de endereço como sinal
        de que o cliente "usa Táxi Dog" — o campo de tela 'usa_taxi' é só
        um controle de UI (não tem 'name', nunca é enviado no submit); o
        que de fato persiste é o endereço preenchido ou vazio. Cliente
        COM endereço = usa Táxi Dog = petshop busca e leva = este
        atendimento NÃO entra no fluxo de "pronto para buscar".

        Quando o atendimento veio do formulário público de solicitação
        online, ele tem o campo 'transporte' preenchido de forma
        explícita para aquele pedido específico ('Eu vou levar' ou
        'Táxi Dog') — nesse caso, damos prioridade a esse dado mais
        específico (cobre o caso de um cliente que normalmente usa Táxi
        Dog, mas numa ocasião pontual escolheu ele mesmo levar e buscar).
        """
        if self.transporte:
            return self.transporte == 'Eu vou levar'
        return not bool(self.cliente.endereco)



class Despesa(db.Model):
    __tablename__ = 'despesa'

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    tipo = db.Column(db.String(50), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f'<Despesa {self.descricao} - R${self.valor:.2f}>'


class Avaliacao(db.Model):
    __tablename__ = 'avaliacao'

    id = db.Column(db.Integer, primary_key=True)
    aprovada = db.Column(db.Boolean, default=True, nullable=False)
    nome_cliente = db.Column(db.String(100), nullable=False)
    nome_pet = db.Column(db.String(100), nullable=True)
    avaliacao_texto = db.Column(db.Text, nullable=False)
    nota = db.Column(db.Integer, nullable=False)  # 1-5
    imagem_pet = db.Column(db.String(200), nullable=True)

    # CORRIGIDO: coluna 'data' adicionada (estava faltando e causava erro)
    data = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f'<Avaliacao {self.nome_cliente} - {self.nota} estrelas>'
