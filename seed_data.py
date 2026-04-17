from src.core.models.models import Base, Company, User, Imovel, Leilao, FichaFinanceira, Documentacao, Reforma, Anexo, datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

def create_db_if_not_exists():
    base_url = "postgresql://postgres:%2AParaiso1978@localhost:5432/postgres"
    engine_temp = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with engine_temp.connect() as conn:
        try:
            conn.execute(text("CREATE DATABASE \"GanduInvest\""))
            print("Banco 'GanduInvest' criado.")
        except Exception as e:
            if "already exists" in str(e): print("Banco 'GanduInvest' já existe.")
            else: raise e

def seed():
    create_db_if_not_exists()
    engine = create_engine(os.getenv('DATABASE_URL'))
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Reset
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    
    gandu = Company(name="Gandu Investimentos")
    session.add(gandu)
    session.commit()
    
    admin = User(company_id=gandu.id, name="Admin", email="admin@ganduinvest.com.br")
    session.add(admin)

    estagios = [
        ("GND-001", "Rua das Flores, 10", "São Paulo", "SP", "Arrematado", 800000, 1200000),
        ("GND-002", "Av. Paulista, 500", "São Paulo", "SP", "Em análise", 2500000, 3500000),
        ("GND-003", "Rua Bahia, 44", "Rio de Janeiro", "RJ", "Em reforma", 600000, 950000),
        ("GND-004", "Rua XV de Novembro", "Curitiba", "PR", "Vendido", 400000, 650000),
        ("GND-005", "Al. Santos, 120", "São Paulo", "SP", "Leilão agendado", 1500000, 2100000),
    ]

    for cod, end, cid, uf, st, va, ve in estagios:
        im = Imovel(
            company_id=gandu.id, codigo_interno=cod, endereco=end, cidade=cid, estado=uf, 
            status=st, valor_avaliacao=va, valor_estimado_venda=ve, leiloeiro="Zukerman"
        )
        session.add(im)
        session.flush()
        
        # Add a auction
        session.add(Leilao(
            imovel_id=im.id, company_id=gandu.id, tipo_leilao="1º Leilão",
            data_hora=datetime(2026, 6, 15, 14, 0), valor_minimo=va * 0.8,
            resultado="Ganhamos" if st in ["Arrematado", "Em reforma", "Vendido"] else "Pendente"
        ))
        
        # Finance
        session.add(FichaFinanceira(
            imovel_id=im.id, company_id=gandu.id,
            itbi=va * 0.02, reforma_prevista=50000 if st == "Em reforma" else 0
        ))

    session.commit()
    session.close()
    print("Full Seed Finalizado!")

if __name__ == "__main__":
    seed()
