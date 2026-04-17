from flask import Blueprint, jsonify, request, render_template, redirect, url_prefix
from src.core.models.models import Imovel, Leilao, Company, FichaFinanceira, Documentacao, Reforma
from src.intelligence.auction_parser import AuctionParser
from src.core.services.finance_service import FinanceService
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

imoveis_bp = Blueprint('imoveis', __name__, url_prefix='/api/imoveis')
engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)

@imoveis_bp.route('/<int:id>', methods=['GET'])
def get_imovel_detail(id):
    session = Session()
    imovel = session.query(Imovel).get(id)
    if not imovel:
        session.close()
        return jsonify({"error": "Não encontrado"}), 404
        
    # Get associated data
    leiloes = session.query(Leilao).filter(Leilao.imovel_id == id).all()
    finance = session.query(FichaFinanceira).filter(FichaFinanceira.imovel_id == id).first()
    
    data = {
        "id": imovel.id,
        "codigo": imovel.codigo_interno or f"GND-{imovel.id:03d}",
        "endereco": imovel.endereco,
        "cidade": imovel.cidade,
        "estado": imovel.estado,
        "cep": imovel.cep,
        "bairro": imovel.bairro,
        "status": imovel.status,
        "valor_avaliacao": imovel.valor_avaliacao or 0,
        "valor_estimado": imovel.valor_estimado_venda or 0,
        "link_leilao": imovel.link_leilao,
        "leiloeiro": imovel.leiloeiro,
        "leiloes": [{"tipo": l.tipo_leilao, "data": l.data_hora.strftime('%d/%m/%Y %H:%M') if l.data_hora else '', "valor": l.valor_minimo, "resultado": l.resultado} for l in leiloes],
        "financeiro": {
            "itbi": finance.itbi if finance else 0,
            "reforma_prevista": finance.reforma_prevista if finance else 0,
            "registro": finance.registro_cartorio if finance else 0,
            "desocupacao": finance.desocupacao if finance else 0
        }
    }
    session.close()
    return jsonify(data)

@imoveis_bp.route('/<int:id>/status', methods=['POST'])
def update_status(id):
    session = Session()
    imovel = session.query(Imovel).get(id)
    new_status = request.json.get('status')
    if imovel and new_status:
        imovel.status = new_status
        session.commit()
    session.close()
    return jsonify({"success": True})

@imoveis_bp.route('/calendar', methods=['GET'])
def get_calendar_events():
    session = Session()
    leiloes = session.query(Leilao).filter(Leilao.data_hora != None).all()
    events = []
    for l in leiloes:
        imovel = session.query(Imovel).get(l.imovel_id)
        events.append({
            "title": f"{l.tipo_leilao} - {imovel.codigo_interno or imovel.id}",
            "start": l.data_hora.isoformat(),
            "status": l.resultado,
            "imovel_id": l.imovel_id
        })
    session.close()
    return jsonify(events)
