from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Company(Base):
    __tablename__ = 'companies'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255))
    role = Column(String(50), default='Operacional') # Admin, Financeiro, Comercial, Consulta
    
    company = relationship("Company")

class Imovel(Base):
    __tablename__ = 'imoveis'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    
    # Cadastral
    codigo_interno = Column(String(50), unique=True)
    endereco = Column(String(255), nullable=False)
    bairro = Column(String(100))
    cidade = Column(String(100))
    estado = Column(String(2))
    cep = Column(String(10))
    tipo_imovel = Column(String(50)) # Casa, Apartamento, etc
    modalidade_venda = Column(String(100)) # Leilão, Venda Direta, etc
    area_terreno = Column(Float)
    area_privativa = Column(Float)
    area_construida = Column(Float)
    
    matricula = Column(String(100))
    cartorio = Column(String(100))
    comarca = Column(String(100))
    comarca_cartorio = Column(String(100))
    banco = Column(String(100))
    inscricao_imobiliaria = Column(String(50))
    desconto = Column(Float, default=0.0)
    
    ocupado = Column(Boolean, default=True)
    
    # Detalhes de Avaliação (Novos campos)
    valor_condominio = Column(Float, default=0.0)
    idade_predio = Column(Integer)
    descritivo_predio = Column(Text)
    descritivo_imovel = Column(Text)
    valor_m2_regiao = Column(Float, default=0.0)
    
    # Diligência
    contato_morador = Column(Boolean, default=False)
    relato_morador = Column(Text)
    contato_sindico = Column(Boolean, default=False)
    relato_sindico = Column(Text)
    outros_debitos = Column(Float, default=0.0)
    observacoes_internas = Column(Text)
    
    # Status Pipeline
    status = Column(String(50), default='Em análise') 
    descartado = Column(Boolean, default=False)
    motivo_descarte = Column(String(100))
    data_descarte = Column(DateTime)
    obs_descarte = Column(Text)
    triagem_status = Column(String(20), default='Pendente')
    triagem_motivo_codigo = Column(String(50))
    triagem_motivo_label = Column(String(120))
    triagem_observacao = Column(Text)
    triagem_decidido_em = Column(DateTime)
    triagem_decidido_por = Column(String(255))
    
    # Preços e Avaliação
    valor_avaliacao = Column(Float)
    valor_estimado_venda = Column(Float) # Venda Rápida
    valor_venda_normal = Column(Float)   # Venda Normal
    lance_maximo_recomendado = Column(Float)
    
    # Origem
    leiloeiro = Column(String(100))
    link_leilao = Column(Text)
    link_edital = Column(Text)
    
    # Comercial e Venda
    comprador_nome = Column(String(255))
    corretor_nome = Column(String(255))
    valor_venda_fechado = Column(Float)
    # Datas de Processo
    data_arrematacao = Column(DateTime)
    data_disponibilizacao = Column(DateTime) # Para venda
    data_venda = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    leiloes = relationship("Leilao", back_populates="imovel", cascade="all, delete-orphan")
    financeiro = relationship("FichaFinanceira", back_populates="imovel", uselist=False)
    documentacao = relationship("Documentacao", back_populates="imovel", uselist=False)
    reforma = relationship("Reforma", back_populates="imovel", uselist=False)
    anexos = relationship("Anexo", back_populates="imovel")

class Leilao(Base):
    __tablename__ = 'leiloes'
    
    id = Column(Integer, primary_key=True)
    imovel_id = Column(Integer, ForeignKey('imoveis.id'), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    
    tipo_leilao = Column(String(20)) # 1º, 2º, 3º, etc
    data_hora = Column(DateTime)
    valor_minimo = Column(Float)
    modalidade = Column(String(100))
    leiloeiro = Column(String(100))
    valor_arrematado = Column(Float)
    resultado = Column(String(50)) # Pendente, Ganhamos, Perdemos, Suspenso
    observacoes = Column(Text)
    
    imovel = relationship("Imovel", back_populates="leiloes")

class FichaFinanceira(Base):
    __tablename__ = 'fichas_financeiras'
    id = Column(Integer, primary_key=True)
    imovel_id = Column(Integer, ForeignKey('imoveis.id'), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    
    # Custos
    valor_arrematacao = Column(Float, default=0.0) # Valor do lance
    comissao_leiloeiro_percent = Column(Float, default=5.0)
    outros_custos_arrematacao = Column(Float, default=0.0)
    
    itiv_percent = Column(Float, default=0.0) # ITBI/ITIV em %
    itiv_vlr = Column(Float, default=0.0)
    
    registro_cartorio_percent = Column(Float, default=0.0)
    registro_cartorio = Column(Float, default=0.0)
    
    desocupacao = Column(Float, default=0.0)
    desocupacao_obs = Column(Text)
    reforma_prevista = Column(Float, default=0.0)
    reforma_obs = Column(Text)
    limpeza = Column(Float, default=0.0)
    limpeza_obs = Column(Text)
    iptu_atrasado = Column(Float, default=0.0)
    iptu_atrasado_ate = Column(String(7))
    iptu_atrasado_obs = Column(Text)
    iptu_futuro = Column(Float, default=0.0)
    iptu_futuro_meses = Column(Integer, default=0)
    condominio_atrasado = Column(Float, default=0.0)
    condo_atrasado_ate = Column(String(7))
    condo_atrasado_obs = Column(Text)
    condominio_futuro = Column(Float, default=0.0)
    condo_futuro_meses = Column(Integer, default=0)
    honorarios_advogado = Column(Float, default=0.0)
    contingencia = Column(Float, default=0.0)
    contingencia_obs = Column(Text)
    custo_capital_meses = Column(Integer, default=0)
    custo_capital_percent = Column(Float, default=0.0)
    lucro_minimo_percent = Column(Float, default=0.0)
    lucro_minimo_vlr = Column(Float, default=0.0)

    # Venda
    valor_venda_projetado = Column(Float, default=0.0)
    comissao_corretor_percent = Column(Float, default=5.0)
    comissao_corretor_vlr = Column(Float, default=0.0)
    impostos_venda_percent = Column(Float, default=0.0)
    impostos_venda_vlr = Column(Float, default=0.0)
    despesas_operacionais = Column(Float, default=0.0)
    
    imovel = relationship("Imovel", back_populates="financeiro")

class Documentacao(Base):
    __tablename__ = 'documentacao'
    id = Column(Integer, primary_key=True)
    imovel_id = Column(Integer, ForeignKey('imoveis.id'), nullable=False)
    
    checklist_json = Column(JSON) # {"matrícula": true, "carta": false}
    status_doc = Column(String(50))
    
    imovel = relationship("Imovel", back_populates="documentacao")

class Reforma(Base):
    __tablename__ = 'reformas'
    id = Column(Integer, primary_key=True)
    imovel_id = Column(Integer, ForeignKey('imoveis.id'), nullable=False)
    
    orcamento_aprovado = Column(Float, default=0.0)
    valor_gasto = Column(Float, default=0.0)
    data_inicio = Column(DateTime)
    data_fim_prevista = Column(DateTime)
    descricao = Column(Text)
    
    imovel = relationship("Imovel", back_populates="reforma")

class Anexo(Base):
    __tablename__ = 'anexos'
    id = Column(Integer, primary_key=True)
    imovel_id = Column(Integer, ForeignKey('imoveis.id'), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id'))
    url = Column(String(512))
    categoria = Column(String(50)) # Foto, Edital, Contrato
    nome_original = Column(String(255))
    nome_arquivo = Column(String(255))
    storage_path = Column(String(1024))
    mime_type = Column(String(255))
    tamanho_bytes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    imovel = relationship("Imovel", back_populates="anexos")
