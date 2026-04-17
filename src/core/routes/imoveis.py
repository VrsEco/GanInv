from flask import Blueprint, jsonify, request, render_template, current_app
from werkzeug.utils import secure_filename
from src.core.models.models import Imovel, Leilao, Company, FichaFinanceira, Documentacao, Reforma, Anexo
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

@imoveis_bp.route('/', methods=['GET'])
def get_imoveis():
    session = Session()
    company_id = request.args.get('company_id', 1)
    status_filter = request.args.get('status')
    show_descartados = request.args.get('descartados', 'false') == 'true'
    motivo_filter = request.args.get('motivo')
    
    query = session.query(Imovel).filter(Imovel.company_id == company_id)
    
    if status_filter:
        query = query.filter(Imovel.status == status_filter)
    
    if not show_descartados:
        query = query.filter(Imovel.descartado == False)
    else:
        query = query.filter(Imovel.descartado == True)
        if motivo_filter:
            query = query.filter(Imovel.motivo_descarte == motivo_filter)
        
    imoveis = query.order_by(Imovel.id.desc()).all()
    
    output = []
    for i in imoveis:
        output.append({
            "id": i.id,
            "codigo": i.codigo_interno or f"GND-{i.id:03d}",
            "endereco": i.endereco,
            "cidade": i.cidade,
            "estado": i.estado,
            "status": i.status,
            "valor_avaliacao": i.valor_avaliacao or 0.0,
            "valor_estimado": i.valor_estimado_venda or 0.0,
            "leiloeiro": i.leiloeiro,
            "descartado": i.descartado,
            "motivo_descarte": i.motivo_descarte,
            "data_descarte": i.data_descarte.isoformat() if i.data_descarte else None,
            "obs_descarte": i.obs_descarte
        })
    session.close()
    return jsonify(output)

@imoveis_bp.route('/<int:id>', methods=['GET'])
def get_imovel(id):
    session = Session()
    i = session.query(Imovel).get(id)
    if not i:
        session.close()
        return jsonify({"error": "Imóvel não encontrado"}), 404
        
    f = i.financeiro
    leiloes = [
        {
            "tipo": l.tipo_leilao, 
            "data": l.data_hora.isoformat() if l.data_hora else "", 
            "data_iso": l.data_hora.isoformat() if l.data_hora else "", 
            "valor": l.valor_minimo, 
            "modalidade": l.modalidade,
            "status": l.resultado,
            "observacoes": l.observacoes
        } for l in i.leiloes
    ]
    
    data = {
        "id": i.id,
        "codigo": i.codigo_interno or f"GND-{i.id:03d}",
        "endereco": i.endereco,
        "bairro": i.bairro,
        "cidade": i.cidade,
        "estado": i.estado,
        "cep": i.cep,
        "tipo_imovel": i.tipo_imovel,
        "status": i.status,
        "valor_avaliacao": i.valor_avaliacao or 0,
        "valor_estimado": i.valor_estimado_venda or 0,
        "leiloeiro": i.leiloeiro,
        "link_leilao": i.link_leilao,
        "data_arrematacao": i.data_arrematacao.isoformat() if i.data_arrematacao else "",
        "data_disponibilizacao": i.data_disponibilizacao.isoformat() if i.data_disponibilizacao else "",
        "data_venda": i.data_venda.isoformat() if i.data_venda else "",
        "leiloes": leiloes,
        "financeiro": {
            "itbi": f.itbi if f else 0,
            "registro": f.registro_cartorio if f else 0,
            "reforma": f.reforma_prevista if f else 0,
            "desocupacao": f.desocupacao if f else 0,
            "iptu_atrasado": f.iptu_atrasado if f else 0,
            "condominio_atrasado": f.condominio_atrasado if f else 0,
            "outros": (f.iptu_atrasado + f.condominio_atrasado + f.honorarios_advogado) if f else 0,
            "full_data": {
                "valor_arrematacao": f.valor_arrematacao if f else 0,
                "comissao_leiloeiro_percent": f.comissao_leiloeiro_percent if f else 5,
                "itiv_percent": f.itiv_percent if f else 0,
                "itiv_vlr": f.itiv_vlr if f else 0,
                "registro_cartorio_percent": f.registro_cartorio_percent if f else 0,
                "registro_cartorio": f.registro_cartorio if f else 0,
                "condominio_futuro": f.condominio_futuro if f else 0,
                "honorarios_advogado": f.honorarios_advogado if f else 0,
                "valor_venda_projetado": f.valor_venda_projetado if f else 0,
                "comissao_corretor_percent": f.comissao_corretor_percent if f else 5,
                "impostos_venda_percent": f.impostos_venda_percent if f else 0,
                "despesas_operacionais": f.despesas_operacionais if f else 0,
                "contingencia": f.contingencia if f else 0
            }
        },
        "kpis": FinanceService.calculate_full_sheet({
            "valor_arrematacao": f.valor_arrematacao if f else 0,
            "comissao_leiloeiro_percent": f.comissao_leiloeiro_percent if f else 5,
            "itiv_percent": f.itiv_percent if f else 0,
            "itiv_vlr": f.itiv_vlr if f else 0,
            "registro_cartorio_percent": f.registro_cartorio_percent if f else 0,
            "registro_cartorio": f.registro_cartorio if f else 0,
            "iptu_atrasado": f.iptu_atrasado if f else 0,
            "condominio_atrasado": f.condominio_atrasado if f else 0,
            "condominio_futuro": f.condominio_futuro if f else 0,
            "desocupacao": f.desocupacao if f else 0,
            "reforma_prevista": f.reforma_prevista if f else 0,
            "honorarios_advogado": f.honorarios_advogado if f else 0,
            "valor_venda_projetado": f.valor_venda_projetado if f else 0,
            "comissao_corretor_percent": f.comissao_corretor_percent if f else 5,
            "impostos_venda_percent": f.impostos_venda_percent if f else 0,
            "despesas_operacionais": f.despesas_operacionais if f else 0,
            "contingencia": f.contingencia if f else 0
        }) if f else {},
        "documentacao": {
            "checklist": i.documentacao.checklist_json if i.documentacao else {},
            "status": i.documentacao.status_doc if i.documentacao else "Pendente"
        },
        "avaliacao": {
            "inscricao_imobiliaria": i.inscricao_imobiliaria or "",
            "valor_condominio": i.valor_condominio or 0,
            "idade_predio": i.idade_predio or 0,
            "descritivo_predio": i.descritivo_predio or "",
            "descritivo_imovel": i.descritivo_imovel or "",
            "valor_m2_regiao": i.valor_m2_regiao or 0,
            "ocupado": i.ocupado,
            "contato_morador": i.contato_morador,
            "relato_morador": i.relato_morador or "",
            "contato_sindico": i.contato_sindico,
            "relato_sindico": i.relato_sindico or "",
            "observacoes_internas": i.observacoes_internas or "",
            "valor_venda_normal": i.valor_venda_normal or 0
        },
        "anexos": [{"id": a.id, "url": a.url, "categoria": a.categoria} for a in i.anexos]
    }
    session.close()
    return jsonify(data)

@imoveis_bp.route('/import', methods=['POST'])
def import_from_link():
    data = request.json
    url = data.get('url')
    if not url: return jsonify({"error": "URL missing"}), 400
        
    extracted = AuctionParser.parse_link(url)
    session = Session()
    try:
        new_im = Imovel(
            company_id=1,
            endereco=extracted.get('endereco'),
            cidade=extracted.get('cidade'),
            estado=extracted.get('estado'),
            status='Em análise',
            leiloeiro=extracted.get('leiloeiro'),
            link_leilao=url,
            valor_avaliacao=extracted.get('valor_avaliacao', 0.0),
            valor_estimado_venda=extracted.get('valor_avaliacao', 0.0) * 1.3 # Estreitativa inicial 30% acima
        )
        session.add(new_im)
        session.commit()
        
        # 1. Initialize Finance
        session.add(FichaFinanceira(imovel_id=new_im.id, company_id=1))
        
        # 2. Add first auction if found
        if extracted.get('valor_minimo'):
            session.add(Leilao(
                imovel_id=new_im.id,
                company_id=1,
                tipo_leilao="1º Leilão",
                valor_minimo=extracted.get('valor_minimo'),
                resultado="Pendente"
            ))
            
        session.commit()
        res = {"message": "Sucesso", "id": new_im.id, "extracted": extracted}
    except Exception as e:
        session.rollback()
        res = {"error": str(e)}
    finally:
        session.close()
    return jsonify(res)

@imoveis_bp.route('/stats', methods=['GET'])
def get_stats():
    session = Session()
    company_id = request.args.get('company_id', 1)
    total = session.query(Imovel).filter(Imovel.company_id == company_id).count()
    arrematados = session.query(Imovel).filter(Imovel.company_id == company_id, Imovel.status == 'Arrematado').count()
    em_analise = session.query(Imovel).filter(Imovel.company_id == company_id, Imovel.status == 'Em análise').count()
    session.close()
    return jsonify({"total": total,"arrematados": arrematados,"em_analise": em_analise})

@imoveis_bp.route('/<int:id>/documentacao', methods=['POST'])
def update_documentacao(id):
    session = Session()
    try:
        data = request.json
        imovel = session.query(Imovel).get(id)
        if not imovel:
            return jsonify({"error": "Imóvel não encontrado"}), 404
            
        doc = imovel.documentacao
        if not doc:
            doc = Documentacao(imovel_id=id)
            session.add(doc)
            
        doc.checklist_json = data.get('checklist', {})
        doc.status_doc = data.get('status_doc', 'Em andamento')
        
        session.commit()
        res = {"message": "Sucesso ao salvar documentação"}
    except Exception as e:
        session.rollback()
        res = {"error": str(e)}
    finally:
        session.close()
    return jsonify(res)

@imoveis_bp.route('/<int:id>/cadastro', methods=['POST'])
def update_cadastro(id):
    session = Session()
    try:
        data = request.json
        i = session.query(Imovel).get(id)
        if not i: return jsonify({"error": "Imóvel não encontrado"}), 404

        # Dados Básicos
        i.endereco = data.get('endereco')
        i.cidade = data.get('cidade')
        i.estado = data.get('estado')
        i.valor_avaliacao = float(data.get('valor_avaliacao') or 0)
        i.desconto = float(data.get('desconto') or 0)
        i.modalidade_venda = data.get('modalidade_venda')
        i.tipo_imovel = data.get('tipo_imovel')
        i.banco = data.get('banco')
        i.area_privativa = float(data.get('area_privativa') or 0)
        i.area_construida = float(data.get('area_construida') or 0)
        i.area_terreno = float(data.get('area_terreno') or 0)
        i.descritivo_imovel = data.get('descritivo_imovel')
        i.inscricao_imobiliaria = data.get('inscricao_imobiliaria')
        i.matricula = data.get('matricula')
        i.comarca = data.get('comarca')
        i.link_leilao = data.get('link_leilao')

        # Sincronização Dinâmica de Leilões
        session.query(Leilao).filter_by(imovel_id=id).delete()
        leiloes_data = data.get('leiloes', [])
        for l_data in leiloes_data:
            l_obj = Leilao(
                imovel_id=id,
                company_id=i.company_id,
                tipo_leilao=l_data.get('tipo'),
                valor_minimo=float(l_data.get('valor') or 0),
                modalidade=l_data.get('modalidade'),
                observacoes=l_data.get('observacoes')
            )
            if l_data.get('data'):
                from datetime import datetime
                try:
                    l_obj.data_hora = datetime.fromisoformat(l_data.get('data'))
                except:
                    pass
            session.add(l_obj)

        session.commit()
        return jsonify({"message": "Cadastro atualizado!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@imoveis_bp.route('/<int:id>/avaliacao', methods=['POST'])
def update_avaliacao(id):
    session = Session()
    try:
        data = request.json
        imovel = session.query(Imovel).get(id)
        if not imovel:
            return jsonify({"error": "Imóvel não encontrado"}), 404
            
        # Update fields
        imovel.inscricao_imobiliaria = data.get('inscricao_imobiliaria')
        imovel.valor_condominio = float(data.get('valor_condominio', 0) or 0)
        imovel.idade_predio = int(data.get('idade_predio', 0) or 0)
        imovel.descritivo_predio = data.get('descritivo_predio')
        imovel.descritivo_imovel = data.get('descritivo_imovel')
        imovel.valor_m2_regiao = float(data.get('valor_m2_regiao', 0) or 0)
        imovel.ocupado = data.get('ocupado') == 'true' or data.get('ocupado') is True
        imovel.contato_morador = data.get('contato_morador') == 'true' or data.get('contato_morador') is True
        imovel.relato_morador = data.get('relato_morador')
        imovel.contato_sindico = data.get('contato_sindico') == 'true' or data.get('contato_sindico') is True
        imovel.relato_sindico = data.get('relato_sindico')
        imovel.observacoes_internas = data.get('observacoes_internas')
        imovel.valor_venda_normal = float(data.get('valor_venda_normal', 0) or 0)
        imovel.valor_estimado_venda = float(data.get('valor_estimado_venda', 0) or 0)
        
        # Finance updates (debts)
        f = imovel.financeiro
        if not f:
            f = FichaFinanceira(imovel_id=id, company_id=imovel.company_id)
            session.add(f)
        
        f.condominio_atrasado = float(data.get('debitos_condominio', f.condominio_atrasado) or 0)
        f.iptu_atrasado = float(data.get('debitos_iptu', f.iptu_atrasado) or 0)
        
        session.commit()
        res = {"message": "Avaliação salva com sucesso"}
    except Exception as e:
        session.rollback()
        res = {"error": str(e)}
    finally:
        session.close()
    return jsonify(res)

@imoveis_bp.route('/leiloes-semana', methods=['GET'])
def get_leiloes_semana():
    session = Session()
    try:
        from datetime import datetime, timedelta
        hoje = datetime.utcnow()
        fim_semana = hoje + timedelta(days=7)
        
        leiloes = session.query(Leilao).filter(
            Leilao.data_hora >= hoje,
            Leilao.data_hora <= fim_semana
        ).order_by(Leilao.data_hora.asc()).all()
        
        output = []
        for l in leiloes:
            i = l.imovel
            f = i.financeiro
            
            # Simple teto calculation for the view
            teto = 0
            if i.valor_estimado_venda:
                costs = (f.iptu_atrasado or 0) + (f.condominio_atrasado or 0) + (f.reforma_prevista or 0)
                teto = (i.valor_estimado_venda * 0.7) - costs

            output.append({
                "id": i.id,
                "leilao_id": l.id,
                "data_hora": l.data_hora.isoformat(),
                "tipo": l.tipo_leilao,
                "valor_minimo": l.valor_minimo,
                "endereco": i.endereco,
                "cidade": i.cidade,
                "codigo": i.codigo_interno or f"GND-{i.id:03d}",
                "venda_estimada": i.valor_estimado_venda or 0,
                "teto_sugerido": max(0, teto)
            })
        res = output
    except Exception as e:
        res = {"error": str(e)}
    finally:
        session.close()
    return jsonify(res)

@imoveis_bp.route('/<int:id>/financeiro', methods=['POST'])
def update_financeiro(id):
    session = Session()
    try:
        data = request.json
        imovel = session.query(Imovel).get(id)
        if not imovel:
            return jsonify({"error": "Não encontrado"}), 404
            
        f = imovel.financeiro
        if not f:
            f = FichaFinanceira(imovel_id=id, company_id=imovel.company_id)
            session.add(f)
            
        # Update Finance Fields
        f.valor_arrematacao = float(data.get('valor_arrematacao', 0) or 0)
        f.comissao_leiloeiro_percent = float(data.get('comissao_leiloeiro_percent', 5) or 0)
        
        f.itiv_percent = float(data.get('itiv_percent', 0) or 0)
        f.itiv_vlr = f.valor_arrematacao * (f.itiv_percent / 100)
        
        f.registro_cartorio_percent = float(data.get('registro_cartorio_percent', 0) or 0)
        f.registro_cartorio = f.valor_arrematacao * (f.registro_cartorio_percent / 100)
        
        f.iptu_atrasado = float(data.get('iptu_atrasado', 0) or 0)
        f.iptu_futuro = float(data.get('iptu_futuro', 0) or 0)
        f.condominio_atrasado = float(data.get('condominio_atrasado', 0) or 0)
        f.condominio_futuro = float(data.get('condominio_futuro', 0) or 0)
        
        f.reforma_prevista = float(data.get('reforma_prevista', 0) or 0)
        f.contingencia = float(data.get('contingencia', 0) or 0)
        
        f.valor_venda_projetado = float(data.get('valor_venda_projetado', 0) or 0)
        f.comissao_corretor_percent = float(data.get('comissao_corretor_percent', 5) or 0)
        f.comissao_corretor_vlr = f.valor_venda_projetado * (f.comissao_corretor_percent / 100)
        
        f.impostos_venda_percent = float(data.get('impostos_venda_percent', 0) or 0)
        f.impostos_venda_vlr = f.valor_venda_projetado * (f.impostos_venda_percent / 100)
        
        # Update Imovel Dates
        if data.get('data_arrematacao'):
            imovel.data_arrematacao = datetime.fromisoformat(data['data_arrematacao'].replace('Z', '+00:00'))
        if data.get('data_disponibilizacao'):
            imovel.data_disponibilizacao = datetime.fromisoformat(data['data_disponibilizacao'].replace('Z', '+00:00'))
        if data.get('data_venda'):
            imovel.data_venda = datetime.fromisoformat(data['data_venda'].replace('Z', '+00:00'))

        session.commit()
        res = {"message": "Ficha financeira atualizada"}
    except Exception as e:
        session.rollback()
        res = {"error": str(e)}
    finally:
        session.close()
    return jsonify(res)

@imoveis_bp.route('/calendar', methods=['GET'])
def get_calendar():
    session = Session()
    leiloes = session.query(Leilao).all()
    events = []
    for l in leiloes:
        im = l.imovel
        events.append({
            "id": im.id,
            "title": f"{im.codigo_interno or im.id} - {l.tipo_leilao}",
            "start": l.data_hora.strftime("%Y-%m-%d") if l.data_hora else "",
            "color": "#10b981" if l.resultado == 'Ganhamos' else "#f59e0b" if l.resultado == 'Pendente' else "#ef4444"
        })
    session.close()
    return jsonify(events)

@imoveis_bp.route('/<int:id>/upload', methods=['POST'])
def upload_arquivo(id):
    session = Session()
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Nenhum arquivo enviado"}), 400
            
        file = request.files['file']
        categoria = request.form.get('categoria', 'Outros')
        
        if file.filename == '':
            return jsonify({"error": "Nome do arquivo vazio"}), 400
            
        filename = secure_filename(file.filename)
        # Prepend id and category to avoid collisions
        unique_name = f"imov_{id}_{categoria.lower()}_{filename}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
        file.save(file_path)
        
        # Save to DB
        anexo = Anexo(
            imovel_id=id,
            url=f"/static/uploads/{unique_name}",
            categoria=categoria
        )
        session.add(anexo)
        session.commit()
        
        return jsonify({"message": "Upload realizado com sucesso", "url": anexo.url, "categoria": categoria})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@imoveis_bp.route('/<int:id>/descartar', methods=['POST'])
def descartar_imovel(id):
    session = Session()
    try:
        data = request.json
        i = session.query(Imovel).get(id)
        if not i: return jsonify({"error": "Não encontrado"}), 404
        
        i.descartado = True
        i.motivo_descarte = data.get('motivo')
        i.obs_descarte = data.get('observacao')
        i.data_descarte = datetime.utcnow()
        i.status = 'Descartado'
        
        session.commit()
        return jsonify({"message": "Imóvel descartado do funil"})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()
