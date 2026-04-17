from src.core.models.models import Imovel, Leilao, Company, FichaFinanceira, Documentacao, User, Anexo
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)
session = Session()

def recreate_sample():
    company = session.query(Company).first()
    if not company:
        company = Company(name="Gandu Investments")
        session.add(company)
        session.commit()

    # Usar um código único para o teste completo
    codigo_teste = "GND-UL-TEST"
    
    # Limpar se já existir para forçar atualização
    existing = session.query(Imovel).filter(Imovel.codigo_interno == codigo_teste).first()
    if existing:
        session.query(Anexo).filter_by(imovel_id=existing.id).delete()
        session.query(Leilao).filter_by(imovel_id=existing.id).delete()
        session.query(FichaFinanceira).filter_by(imovel_id=existing.id).delete()
        session.query(Documentacao).filter_by(imovel_id=existing.id).delete()
        session.delete(existing)
        session.commit()
        print(f"Limpando {codigo_teste} anterior...")

    # Criar Imóvel com todos os novos campos
    imovel = Imovel(
        company_id=company.id,
        codigo_interno=codigo_teste,
        endereco="Avenida Oceanográfica, Mansão do Sol, Ap 2401",
        bairro="Ondina",
        cidade="Salvador",
        estado="BA",
        cep="40170-110",
        tipo_imovel="Apartamento",
        modalidade_venda="Leilão Judicial",
        banco="Caixa Econômica Federal",
        comarca="Salvador - BA (8ª Vara de Relações de Consumo)",
        area_privativa=215.00,
        area_construida=245.00,
        area_terreno=0.00,
        matricula="112.455",
        cartorio="3º Registro de Imóveis de Salvador",
        comarca_cartorio="Salvador/BA",
        inscricao_imobiliaria="055.212.008-5",
        desconto=48.0,
        
        status="Em análise",
        valor_avaliacao=1500000.00,
        valor_estimado_venda=1350000.00,
        valor_venda_normal=1600000.00,
        leiloeiro="Gustavo Zukerman",
        link_leilao="https://www.zukerman.com.br/imovel-ondina-2401",
        link_edital="https://pje.tjba.jus.br/edital/998877",
        
        descritivo_predio="Torre única de alto luxo, pastilhada, infraestrutura completa com quadra de tênis, piscina aquecida e heliponto.",
        descritivo_imovel="4 Suítes amplas, varanda integrada com fechamento em reiki, 4 vagas soltas mais depósito privativo.",
        valor_condominio=2200.00,
        idade_predio=8,
        valor_m2_regiao=9500.00,
        
        ocupado=True,
        contato_morador=True,
        relato_morador="Morador de classe alta, ciente do leilão, aguarda contato para negociação de saída amigável.",
        contato_sindico=True,
        relato_sindico="Condomínio sem dívidas extras. Morador atual é adimplente com as taxas ordinárias.",
        observacoes_internas="Oportunidade rara em Ondina. Unidade com vista mar total e definitiva.",
        
        # Campos de descarte (Ficara como ativo para triagem)
        descartado=False
    )
    session.add(imovel)
    session.flush()

    # Criar Histórico de Leilões
    session.add_all([
        Leilao(imovel_id=imovel.id, company_id=company.id, tipo_leilao="1º Leilão", data_hora=datetime.utcnow() + timedelta(days=2), valor_minimo=1500000.00, resultado="Pendente", modalidade="Online", observacoes="Valor integral da avaliação."),
        Leilao(imovel_id=imovel.id, company_id=company.id, tipo_leilao="2º Leilão", data_hora=datetime.utcnow() + timedelta(days=12), valor_minimo=750000.00, resultado="Pendente", modalidade="Online", observacoes="50% de desconto. Grande potencial."),
        Leilao(imovel_id=imovel.id, company_id=company.id, tipo_leilao="Venda Direta", data_hora=datetime.utcnow() + timedelta(days=45), valor_minimo=680000.00, resultado="Pendente", modalidade="Balcão", observacoes="Oportunidade de negociação direta com o banco.")
    ])

    # Ficha Financeira (Completa)
    financeiro = FichaFinanceira(
        imovel_id=imovel.id,
        company_id=company.id,
        valor_arrematacao=820000.00,
        comissao_leiloeiro_percent=5.0,
        itiv_percent=3.0,
        registro_cartorio_percent=1.0,
        iptu_atrasado=25000.00,
        iptu_futuro=5000.00,
        condominio_atrasado=12000.00,
        condominio_futuro=6000.00,
        reforma_prevista=50000.00,
        contingencia=10000.00,
        valor_venda_projetado=1350000.00,
        comissao_corretor_percent=5.0,
        impostos_venda_percent=15.0 # Ganho de capital simulado
    )
    session.add(financeiro)

    # Documentação
    doc = Documentacao(
        imovel_id=imovel.id,
        checklist_json={
            "Edital": "Concluído",
            "Matrícula": "Concluído",
            "Certidão de Ônus": "Pendente",
            "Laudo de Avaliação": "Concluído"
        },
        status_doc="Em Análise técnica"
    )
    session.add(doc)

    # Anexos
    anexos = [
        Anexo(imovel_id=imovel.id, url="/static/uploads/edital_exemplo.pdf", categoria="Edital"),
        Anexo(imovel_id=imovel.id, url="/static/uploads/matricula_exemplo.pdf", categoria="Matricula")
    ]
    session.add_all(anexos)

    session.commit()
    print(f"Cadastro Teste Completo Gerado! ID: {imovel.id} - Código: {imovel.codigo_interno}")

    session.commit()
    print(f"Exemplo reconstruído! ID: {imovel.id}")

if __name__ == "__main__":
    recreate_sample()
    session.close()
