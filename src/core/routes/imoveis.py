from flask import Blueprint, jsonify, request, render_template, current_app, send_file, session as flask_session
from src.core.models.models import FILTRO_AUXILIAR_OPTIONS, Imovel, Leilao, Company, FichaFinanceira, Documentacao, Reforma, Anexo
from src.intelligence.auction_parser import AuctionParser
from src.core.services.finance_service import FinanceService
from src.core.services.triagem_service import (
    STATUS_IMOVEL_APROVADO,
    TRIAGEM_STATUS_APROVADO,
    TRIAGEM_STATUS_DESCARTADO,
    TriagemService,
)
from src.core.services.storage_service import (
    UploadTooLargeError,
    UploadValidationError,
    delete_physical_file,
    format_size_bytes,
    is_single_file_category,
    normalize_category,
    resolve_absolute_path,
    save_upload,
)
from sqlalchemy import create_engine, text, or_
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus
from werkzeug.exceptions import RequestEntityTooLarge
import os
from io import BytesIO
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def _build_db_url():
    url = os.getenv('DATABASE_URL')
    if url:
        return url
    host = os.getenv('DB_HOST', '69.164.205.75')
    port = os.getenv('DB_PORT', '5432')
    user = os.getenv('DB_USER', 'gi')
    password = os.getenv('DB_PASS', '')
    name = os.getenv('DB_NAME', 'GanduInvest')
    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"

imoveis_bp = Blueprint('imoveis', __name__, url_prefix='/api/imoveis')
engine = create_engine(_build_db_url())
Session = sessionmaker(bind=engine)


def _build_anexo_url(imovel_id, anexo_id):
    return f"/api/imoveis/{imovel_id}/anexos/{anexo_id}/arquivo"


def _upload_too_large_response():
    max_mb = current_app.config.get('MAX_UPLOAD_SIZE_MB', 15)
    return jsonify({"error": f"Arquivo excede o limite configurado de {max_mb} MB."}), 413


def _serialize_anexo(anexo):
    return {
        "id": anexo.id,
        "categoria": normalize_category(anexo.categoria),
        "url": _build_anexo_url(anexo.imovel_id, anexo.id),
        "nome_original": anexo.nome_original or anexo.nome_arquivo or os.path.basename(anexo.url or '') or "arquivo",
        "nome_arquivo": anexo.nome_arquivo,
        "mime_type": anexo.mime_type or "",
        "tamanho_bytes": anexo.tamanho_bytes or 0,
        "tamanho_humano": format_size_bytes(anexo.tamanho_bytes),
        "created_at": anexo.created_at.isoformat() if anexo.created_at else None,
        "updated_at": anexo.updated_at.isoformat() if getattr(anexo, 'updated_at', None) else None,
        "eh_imagem": normalize_category(anexo.categoria) == 'Foto',
    }


def _resolve_legacy_static_path(anexo):
    url = (anexo.url or '').strip()
    prefix = '/static/uploads/'
    if not url.startswith(prefix):
        return None

    filename = url[len(prefix):]
    if not filename:
        return None

    return os.path.join(current_app.root_path, 'static', 'uploads', os.path.basename(filename))


def _resolve_anexo_path(anexo):
    storage_root = current_app.config['UPLOAD_ROOT']
    relative_path = getattr(anexo, 'storage_path', None)

    if relative_path:
        try:
            absolute_path = resolve_absolute_path(storage_root, relative_path)
            if os.path.exists(absolute_path):
                return absolute_path
        except UploadValidationError:
            return None

    legacy_path = _resolve_legacy_static_path(anexo)
    if legacy_path and os.path.exists(legacy_path):
        return legacy_path

    return None


def _delete_anexo_physical_file(anexo):
    storage_root = current_app.config['UPLOAD_ROOT']
    deleted = False

    if getattr(anexo, 'storage_path', None):
        deleted = delete_physical_file(storage_root, anexo.storage_path) or deleted

    legacy_path = _resolve_legacy_static_path(anexo)
    if legacy_path and os.path.exists(legacy_path):
        os.remove(legacy_path)
        deleted = True

    return deleted




def _normalize_filtro_auxiliar(value):
    normalized = (value or '').strip().upper()
    if not normalized:
        return None
    if normalized not in FILTRO_AUXILIAR_OPTIONS:
        raise ValueError("Filtro auxiliar inválido. Use A, B, C ou E.")
    return normalized

def _safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_triagem_label(value):
    if value in (TRIAGEM_STATUS_APROVADO, 'Aprovado'):
        return 'Aprovado'
    if value in (TRIAGEM_STATUS_DESCARTADO, 'Descartado'):
        return 'Descartado'
    return 'Pendente'


def _resolve_oportunidade_status(imovel):
    triagem_status = _normalize_triagem_label(TriagemService.resolve_triagem_status(imovel))
    status_operacional = getattr(imovel, 'status', '') or 'Em análise'
    if triagem_status == 'Aprovado':
        status_label = 'Oportunidade selecionada'
    elif triagem_status == 'Descartado':
        status_label = 'Oportunidade descartada'
    else:
        status_label = status_operacional
    return triagem_status, status_label


def _resolve_periodo_leiloes(periodo, start_raw=None, end_raw=None):
    periodo = (periodo or 'semana').strip().lower()
    agora = datetime.now()

    if periodo == 'custom' and start_raw and end_raw:
        start_dt = datetime.strptime(start_raw, '%Y-%m-%d')
        end_dt = datetime.strptime(end_raw, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999)
        if end_dt < start_dt:
            raise ValueError('A data final não pode ser menor que a data inicial.')
        return start_dt, end_dt, 'custom'

    if periodo == 'mes':
        return agora, agora + timedelta(days=30), 'mes'

    return agora, agora + timedelta(days=7), 'semana'


def _serialize_leilao_oportunidade(leilao, imovel):
    financeiro = imovel.financeiro
    snapshot = FinanceService.calculate_full_sheet({
        "valor_arrematacao": _safe_float(getattr(financeiro, 'valor_arrematacao', 0)),
        "comissao_leiloeiro_percent": _safe_float(getattr(financeiro, 'comissao_leiloeiro_percent', 5)),
        "outros_custos_arrematacao": _safe_float(getattr(financeiro, 'outros_custos_arrematacao', 0)),
        "itiv_percent": _safe_float(getattr(financeiro, 'itiv_percent', 0)),
        "itiv_vlr": _safe_float(getattr(financeiro, 'itiv_vlr', 0)),
        "registro_cartorio_percent": _safe_float(getattr(financeiro, 'registro_cartorio_percent', 0)),
        "registro_cartorio": _safe_float(getattr(financeiro, 'registro_cartorio', 0)),
        "iptu_atrasado": _safe_float(getattr(financeiro, 'iptu_atrasado', 0)),
        "condominio_atrasado": _safe_float(getattr(financeiro, 'condominio_atrasado', 0)),
        "condominio_futuro": _safe_float(getattr(financeiro, 'condominio_futuro', 0)),
        "desocupacao": _safe_float(getattr(financeiro, 'desocupacao', 0)),
        "reforma_prevista": _safe_float(getattr(financeiro, 'reforma_prevista', 0)),
        "honorarios_advogado": _safe_float(getattr(financeiro, 'honorarios_advogado', 0)),
        "valor_venda_projetado": _safe_float(getattr(financeiro, 'valor_venda_projetado', 0)),
        "comissao_corretor_percent": _safe_float(getattr(financeiro, 'comissao_corretor_percent', 5)),
        "impostos_venda_percent": _safe_float(getattr(financeiro, 'impostos_venda_percent', 0)),
        "despesas_operacionais": _safe_float(getattr(financeiro, 'despesas_operacionais', 0)),
        "contingencia": _safe_float(getattr(financeiro, 'contingencia', 0)),
    }) if financeiro else {}

    teto_sugerido = snapshot.get('lance_maximo_rapida') or snapshot.get('lance_maximo') or 0
    triagem_status, status_label = _resolve_oportunidade_status(imovel)

    return {
        "id": imovel.id,
        "leilao_id": leilao.id,
        "data_hora": leilao.data_hora.isoformat() if leilao.data_hora else "",
        "tipo": leilao.tipo_leilao,
        "valor_minimo": _safe_float(leilao.valor_minimo),
        "endereco": imovel.endereco,
        "cidade": imovel.cidade,
        "estado": imovel.estado,
        "codigo": imovel.codigo_interno or f"GND-{imovel.id:03d}",
        "banco": getattr(imovel, 'banco', '') or "",
        "leiloeiro": getattr(leilao, 'leiloeiro', None) or getattr(imovel, 'leiloeiro', '') or "",
        "valor_avaliacao": _safe_float(getattr(imovel, 'valor_avaliacao', 0)),
        "venda_normal": _safe_float(getattr(imovel, 'valor_venda_normal', 0)),
        "venda_rapida": _safe_float(getattr(imovel, 'valor_estimado_venda', 0)),
        "status": getattr(imovel, 'status', '') or 'Em análise',
        "filtro_auxiliar": getattr(imovel, 'filtro_auxiliar', None) or "",
        "triagem_status": triagem_status,
        "status_label": status_label,
        "venda_estimada": _safe_float(getattr(imovel, 'valor_estimado_venda', 0)),
        "teto_sugerido": max(0.0, _safe_float(teto_sugerido)),
    }

@imoveis_bp.route('/', methods=['GET'])
def get_imoveis():
    session = Session()
    company_id = request.args.get('company_id', 1)
    status_filter = request.args.get('status')
    bairro_filter = request.args.get('bairro')
    show_descartados = request.args.get('descartados', 'false') == 'true'
    motivo_filter = request.args.get('motivo')
    try:
        filtro_auxiliar = _normalize_filtro_auxiliar(request.args.get('filtro_auxiliar'))
    except ValueError as err:
        session.close()
        return jsonify({"error": str(err)}), 400
    
    query = session.query(Imovel).filter(Imovel.company_id == company_id)
    
    if status_filter:
        query = query.filter(Imovel.status == status_filter)
    
    if bairro_filter:
        query = query.filter(Imovel.bairro == bairro_filter)

    if filtro_auxiliar:
        query = query.filter(Imovel.filtro_auxiliar == filtro_auxiliar)
    
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
            "filtro_auxiliar": i.filtro_auxiliar or "",
            "valor_avaliacao": i.valor_avaliacao or 0.0,
            "valor_estimado": i.valor_estimado_venda or 0.0,
            "leiloeiro": i.leiloeiro,
            "descartado": i.descartado,
            "motivo_descarte": i.motivo_descarte,
            "data_descarte": i.data_descarte.isoformat() if i.data_descarte else None,
            "obs_descarte": i.obs_descarte,
            "triagem_status": TriagemService.resolve_triagem_status(i),
            "triagem_motivo_codigo": i.triagem_motivo_codigo,
            "triagem_motivo_label": i.triagem_motivo_label,
            "triagem_observacao": i.triagem_observacao,
            "triagem_decidido_em": i.triagem_decidido_em.isoformat() if i.triagem_decidido_em else None,
        })
    session.close()
    return jsonify(output)


@imoveis_bp.route('/triagem', methods=['GET'])
def get_triagem():
    session = Session()
    try:
        company_id = int(request.args.get('company_id', 1))
        triagem_status = request.args.get('triagem_status', '')
        motivo_codigo = request.args.get('motivo_codigo', '')
        cidade = request.args.get('cidade', '')
        banco = request.args.get('banco', '')
        filtro_auxiliar = request.args.get('filtro_auxiliar', '')
        search = request.args.get('search', '')
        items = TriagemService.list_imoveis(
            session,
            company_id=company_id,
            triagem_status=triagem_status,
            motivo_codigo=motivo_codigo,
            cidade=cidade,
            banco=banco,
            filtro_auxiliar=filtro_auxiliar,
            search=search,
        )
        return jsonify(items)
    finally:
        session.close()


@imoveis_bp.route('/triagem/filtros', methods=['GET'])
def get_triagem_filtros():
    session = Session()
    try:
        company_id = int(request.args.get('company_id', 1))
        return jsonify(TriagemService.build_filters(session, company_id=company_id))
    finally:
        session.close()


@imoveis_bp.route('/triagem/stats', methods=['GET'])
def get_triagem_stats():
    session = Session()
    try:
        company_id = int(request.args.get('company_id', 1))
        return jsonify(TriagemService.build_stats(session, company_id=company_id))
    finally:
        session.close()

@imoveis_bp.route('/bairros', methods=['GET'])
def get_bairros():
    session = Session()
    company_id = request.args.get('company_id', 1)
    bairros = session.query(Imovel.bairro).filter(
        Imovel.company_id == company_id,
        Imovel.bairro != None,
        Imovel.bairro != ""
    ).distinct().all()
    session.close()
    return jsonify([b[0] for b in bairros if b[0]])

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
            "leiloeiro": l.leiloeiro or "",
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
        "filtro_auxiliar": i.filtro_auxiliar or "",
        "banco": i.banco or "",
        "area_privativa": i.area_privativa or 0,
        "area_construida": i.area_construida or 0,
        "area_terreno": i.area_terreno or 0,
        "matricula": i.matricula or "",
        "comarca": i.comarca or "",
        "descritivo_imovel": i.descritivo_imovel or "",
        "inscricao_imobiliaria": i.inscricao_imobiliaria or "",
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
            "itbi": f.itiv_vlr if f else 0,
            "registro": f.registro_cartorio if f else 0,
            "reforma": f.reforma_prevista if f else 0,
            "desocupacao": f.desocupacao if f else 0,
            "iptu_atrasado": f.iptu_atrasado if f else 0,
            "condominio_atrasado": f.condominio_atrasado if f else 0,
            "outros": ((f.iptu_atrasado or 0) + (f.condominio_atrasado or 0) + (f.honorarios_advogado or 0)) if f else 0,
                "full_data": {
                    "valor_arrematacao": f.valor_arrematacao if f else 0,
                    "comissao_leiloeiro_percent": f.comissao_leiloeiro_percent if f else 5,
                    "outros_custos_arrematacao": (f.outros_custos_arrematacao or 0) if f else 0,
                    "itiv_percent": f.itiv_percent if f else 0,
                    "itiv_vlr": f.itiv_vlr if f else 0,
                "registro_cartorio_percent": f.registro_cartorio_percent if f else 0,
                "registro_cartorio": f.registro_cartorio if f else 0,
                "iptu_futuro": (f.iptu_futuro or 0) if f else 0,
                "iptu_futuro_meses": (f.iptu_futuro_meses or 0) if f else 0,
                "iptu_atrasado_ate": (f.iptu_atrasado_ate or "") if f else "",
                "iptu_atrasado_obs": (f.iptu_atrasado_obs or "") if f else "",
                "condo_atrasado_ate": (f.condo_atrasado_ate or "") if f else "",
                "condo_atrasado_obs": (f.condo_atrasado_obs or "") if f else "",
                "condo_futuro_meses": (f.condo_futuro_meses or 0) if f else 0,
                "condominio_futuro": (f.condominio_futuro or 0) if f else 0,
                "desocupacao": (f.desocupacao or 0) if f else 0,
                "desocupacao_obs": (f.desocupacao_obs or "") if f else "",
                "reforma_prevista": (f.reforma_prevista or 0) if f else 0,
                "reforma_obs": (f.reforma_obs or "") if f else "",
                "limpeza": (f.limpeza or 0) if f else 0,
                "limpeza_obs": (f.limpeza_obs or "") if f else "",
                "contingencia": (f.contingencia or 0) if f else 0,
                "contingencia_obs": (f.contingencia_obs or "") if f else "",
                "custo_capital_meses": (f.custo_capital_meses or 0) if f else 0,
                "custo_capital_percent": (f.custo_capital_percent or 0) if f else 0,
                "lucro_minimo_percent": (f.lucro_minimo_percent or 0) if f else 0,
                "lucro_minimo_vlr": (f.lucro_minimo_vlr or 0) if f else 0,
                "honorarios_advogado": (f.honorarios_advogado or 0) if f else 0,
                "valor_venda_projetado": f.valor_venda_projetado if f else 0,
                "comissao_corretor_percent": f.comissao_corretor_percent if f else 5,
                "impostos_venda_percent": f.impostos_venda_percent if f else 0,
                "despesas_operacionais": f.despesas_operacionais if f else 0
            }
        },
        "kpis": FinanceService.calculate_full_sheet({
            "valor_arrematacao": f.valor_arrematacao if f else 0,
            "comissao_leiloeiro_percent": f.comissao_leiloeiro_percent if f else 5,
            "outros_custos_arrematacao": (f.outros_custos_arrematacao or 0) if f else 0,
            "itiv_percent": f.itiv_percent if f else 0,
            "itiv_vlr": f.itiv_vlr if f else 0,
            "registro_cartorio_percent": f.registro_cartorio_percent if f else 0,
            "registro_cartorio": f.registro_cartorio if f else 0,
            "iptu_atrasado": f.iptu_atrasado if f else 0,
            "condominio_atrasado": (f.condominio_atrasado or 0) if f else 0,
            "condominio_futuro": (f.condominio_futuro or 0) if f else 0,
            "desocupacao": (f.desocupacao or 0) if f else 0,
            "reforma_prevista": (f.reforma_prevista or 0) if f else 0,
            "honorarios_advogado": (f.honorarios_advogado or 0) if f else 0,
            "valor_venda_projetado": (f.valor_venda_projetado or 0) if f else 0,
            "comissao_corretor_percent": (f.comissao_corretor_percent or 0) if f else 5,
            "impostos_venda_percent": (f.impostos_venda_percent or 0) if f else 0,
            "despesas_operacionais": (f.despesas_operacionais or 0) if f else 0,
            "contingencia": (f.contingencia or 0) if f else 0
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
            "valor_venda_normal": i.valor_venda_normal or 0,
            "outros_debitos": i.outros_debitos or 0
        },
        "anexos": [_serialize_anexo(a) for a in i.anexos]
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
            endereco=extracted.get('endereco') or "Pendente de análise profunda",
            cidade=extracted.get('cidade') or "??",
            estado=extracted.get('estado') or "??",
            status='Em análise',
            triagem_status='Pendente',
            filtro_auxiliar=_normalize_filtro_auxiliar(extracted.get('filtro_auxiliar')),
            leiloeiro=extracted.get('leiloeiro') or "Desconhecido",
            link_leilao=url,
            valor_avaliacao=float(extracted.get('valor_avaliacao') or 0.0),
            valor_estimado_venda=float(extracted.get('valor_avaliacao') or 0.0) * 1.3
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
    
@imoveis_bp.route('/manual', methods=['POST'])
def register_manual():
    data = request.json
    session = Session()
    try:
        new_im = Imovel(
            company_id=1,
            endereco=data.get('endereco'),
            bairro=data.get('bairro'),
            cidade=data.get('cidade'),
            estado=data.get('estado'),
            status='Em análise',
            triagem_status='Pendente',
            filtro_auxiliar=_normalize_filtro_auxiliar(data.get('filtro_auxiliar')),
            valor_avaliacao=float(data.get('valor_avaliacao') or 0.0),
            valor_estimado_venda=float(data.get('valor_avaliacao') or 0.0) * 1.3
        )
        session.add(new_im)
        session.commit()
        
        # Initialize Finance
        session.add(FichaFinanceira(imovel_id=new_im.id, company_id=1))
        session.commit()
        
        return jsonify({"message": "Sucesso", "id": new_im.id})
    except ValueError as e:
        session.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

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
        i.bairro = data.get('bairro')
        i.cidade = data.get('cidade')
        i.estado = data.get('estado')
        i.valor_avaliacao = float(data.get('valor_avaliacao') or 0)
        i.desconto = float(data.get('desconto') or 0)
        i.modalidade_venda = data.get('modalidade_venda')
        i.tipo_imovel = data.get('tipo_imovel')
        i.filtro_auxiliar = _normalize_filtro_auxiliar(data.get('filtro_auxiliar'))
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
                leiloeiro=l_data.get('leiloeiro'),
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
    except ValueError as e:
        session.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        session.rollback()
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
        imovel.outros_debitos = float(data.get('outros_debitos', 0) or 0)
        
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
        company_id = int(request.args.get('company_id', 1))
        periodo = request.args.get('periodo', 'semana')
        start_raw = request.args.get('start')
        end_raw = request.args.get('end')
        filtro_auxiliar = _normalize_filtro_auxiliar(request.args.get('filtro_auxiliar'))
        inicio, fim, periodo_resolvido = _resolve_periodo_leiloes(periodo, start_raw, end_raw)

        query = session.query(Leilao).join(Imovel).filter(
            Imovel.company_id == company_id,
            Leilao.data_hora != None,
            Leilao.data_hora >= inicio,
            Leilao.data_hora <= fim,
            or_(
                Imovel.triagem_status == TRIAGEM_STATUS_APROVADO,
                Imovel.status == STATUS_IMOVEL_APROVADO,
            )
        )
        if filtro_auxiliar:
            query = query.filter(Imovel.filtro_auxiliar == filtro_auxiliar)

        leiloes = query.order_by(Leilao.data_hora.asc()).all()

        output = [_serialize_leilao_oportunidade(leilao, leilao.imovel) for leilao in leiloes]
        res = {
            "items": output,
            "periodo": periodo_resolvido,
            "start": inicio.date().isoformat(),
            "end": fim.date().isoformat(),
            "total": len(output),
        }
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
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
        f.outros_custos_arrematacao = float(data.get('outros_custos_arrematacao', 0) or 0)
        
        f.itiv_percent = float(data.get('itiv_percent', 0) or 0)
        f.itiv_vlr = f.valor_arrematacao * (f.itiv_percent / 100)
        
        f.registro_cartorio_percent = float(data.get('registro_cartorio_percent', 0) or 0)
        f.registro_cartorio = f.valor_arrematacao * (f.registro_cartorio_percent / 100)
        
        f.iptu_atrasado = float(data.get('iptu_atrasado', 0) or 0)
        f.iptu_atrasado_ate = data.get('iptu_atrasado_ate', '')
        f.iptu_atrasado_obs = data.get('iptu_atrasado_obs', '')
        f.iptu_futuro = float(data.get('iptu_futuro', 0) or 0)
        f.iptu_futuro_meses = int(data.get('iptu_futuro_meses', 0) or 0)
        f.condominio_atrasado = float(data.get('condominio_atrasado', 0) or 0)
        f.condo_atrasado_ate = data.get('condo_atrasado_ate', '')
        f.condo_atrasado_obs = data.get('condo_atrasado_obs', '')
        f.condominio_futuro = float(data.get('condominio_futuro', 0) or 0)
        f.condo_futuro_meses = int(data.get('condo_futuro_meses', 0) or 0)
        f.desocupacao = float(data.get('desocupacao', 0) or 0)
        f.desocupacao_obs = data.get('desocupacao_obs', '')
        f.reforma_prevista = float(data.get('reforma_prevista', 0) or 0)
        f.reforma_obs = data.get('reforma_obs', '')
        f.limpeza = float(data.get('limpeza', 0) or 0)
        f.limpeza_obs = data.get('limpeza_obs', '')
        f.contingencia = float(data.get('contingencia', 0) or 0)
        f.contingencia_obs = data.get('contingencia_obs', '')
        f.custo_capital_meses = int(data.get('custo_capital_meses', 0) or 0)
        f.custo_capital_percent = float(data.get('custo_capital_percent', 0) or 0)
        f.lucro_minimo_percent = float(data.get('lucro_minimo_percent', 0) or 0)
        f.lucro_minimo_vlr = float(data.get('lucro_minimo_vlr', 0) or 0)
        
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

@imoveis_bp.route('/<int:id>/resultado-leilao', methods=['POST'])
def update_resultado_leilao(id):
    session = Session()
    try:
        data = request.json
        imovel = session.query(Imovel).get(id)
        if not imovel:
            return jsonify({"error": "Imóvel não encontrado"}), 404
        
        imovel.status = data.get('status')
        
        # Se arrematado, garante que o valor vá para a ficha financeira
        f = imovel.financeiro
        if not f:
            f = FichaFinanceira(imovel_id=id, company_id=imovel.company_id)
            session.add(f)
        
        f.valor_arrematacao = float(data.get('valor_arrematado') or 0)
        
        session.commit()
        return jsonify({"message": "Resultado do leilão atualizado com sucesso!"})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@imoveis_bp.route('/calendar', methods=['GET'])
def get_calendar():
    session = Session()
    try:
        company_id = int(request.args.get('company_id', 1))
        filtro_auxiliar = _normalize_filtro_auxiliar(request.args.get('filtro_auxiliar'))
        query = session.query(Leilao).join(Imovel).filter(
            Imovel.company_id == company_id,
            Leilao.data_hora != None,
        )
        if filtro_auxiliar:
            query = query.filter(Imovel.filtro_auxiliar == filtro_auxiliar)
        leiloes = query.order_by(Leilao.data_hora.asc()).all()
        events = []
        for l in leiloes:
            im = l.imovel
            triagem_status, status_label = _resolve_oportunidade_status(im)
            color = "#10b981" if triagem_status == 'Aprovado' else "#f59e0b" if triagem_status == 'Pendente' else "#ef4444"
            events.append({
                "id": im.id,
                "title": f"{im.codigo_interno or f'GND-{im.id:03d}'} · {l.tipo_leilao}",
                "start": l.data_hora.isoformat() if l.data_hora else "",
                "color": color,
                "extendedProps": {
                    "codigo": im.codigo_interno or f"GND-{im.id:03d}",
                    "tipo_leilao": l.tipo_leilao,
                    "triagem_status": triagem_status,
                    "status_label": status_label,
                    "status_operacional": getattr(im, 'status', '') or 'Em análise',
                    "filtro_auxiliar": getattr(im, 'filtro_auxiliar', None) or "",
                    "cidade": getattr(im, 'cidade', '') or '',
                    "estado": getattr(im, 'estado', '') or '',
                    "valor_minimo": _safe_float(getattr(l, 'valor_minimo', 0)),
                }
            })
        return jsonify(events)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        session.close()

@imoveis_bp.route('/<int:id>/upload', methods=['POST'])
def upload_arquivo(id):
    session = Session()
    saved_absolute_path = None
    old_files_to_delete = []
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Nenhum arquivo enviado"}), 400

        file = request.files['file']
        categoria = normalize_category(request.form.get('categoria', 'Outros'))
        replace_anexo_id = request.form.get('replace_anexo_id', type=int)
        if file.filename == '':
            return jsonify({"error": "Nome do arquivo vazio"}), 400

        imovel = session.query(Imovel).get(id)
        if not imovel:
            return jsonify({"error": "Imóvel não encontrado"}), 404

        upload_root = current_app.config['UPLOAD_ROOT']
        max_size_bytes = current_app.config['MAX_UPLOAD_SIZE_BYTES']
        anexo = None
        mensagem = "Upload realizado com sucesso"

        if replace_anexo_id:
            anexo = session.query(Anexo).filter(
                Anexo.id == replace_anexo_id,
                Anexo.imovel_id == id
            ).first()
            if not anexo:
                return jsonify({"error": "Anexo para substituição não encontrado"}), 404
            old_files_to_delete.append(Anexo(
                id=anexo.id,
                imovel_id=anexo.imovel_id,
                company_id=anexo.company_id,
                url=anexo.url,
                categoria=anexo.categoria,
                nome_original=anexo.nome_original,
                nome_arquivo=anexo.nome_arquivo,
                storage_path=anexo.storage_path,
                mime_type=anexo.mime_type,
                tamanho_bytes=anexo.tamanho_bytes,
            ))
            mensagem = "Arquivo substituído com sucesso"
        elif is_single_file_category(categoria):
            antigos = session.query(Anexo).filter(
                Anexo.imovel_id == id,
                Anexo.categoria == categoria
            ).order_by(Anexo.id.asc()).all()

            if antigos:
                old_files_to_delete.extend(antigos)

        if anexo is None:
            anexo = Anexo(
                imovel_id=id,
                company_id=imovel.company_id,
                categoria=categoria,
            )
            session.add(anexo)
            session.flush()

        saved = save_upload(
            file,
            upload_root=upload_root,
            company_id=imovel.company_id,
            imovel_id=id,
            category=categoria,
            max_size_bytes=max_size_bytes,
            anexo_id=anexo.id,
        )
        saved_absolute_path = saved.absolute_path

        anexo.company_id = imovel.company_id
        anexo.categoria = saved.category
        anexo.url = _build_anexo_url(id, anexo.id)
        anexo.nome_original = saved.original_filename
        anexo.nome_arquivo = saved.stored_filename
        anexo.storage_path = saved.relative_path
        anexo.mime_type = saved.mime_type
        anexo.tamanho_bytes = saved.size_bytes
        anexo.updated_at = datetime.utcnow()

        for antigo in old_files_to_delete:
            if antigo.id != anexo.id:
                session.delete(antigo)

        session.commit()

        for antigo in old_files_to_delete:
            if antigo.id != anexo.id or replace_anexo_id:
                _delete_anexo_physical_file(antigo)

        return jsonify({
            "message": mensagem,
            "anexo": _serialize_anexo(anexo),
            "categoria": categoria,
            "limite_mb": current_app.config['MAX_UPLOAD_SIZE_MB'],
        })
    except UploadTooLargeError as e:
        session.rollback()
        if saved_absolute_path and os.path.exists(saved_absolute_path):
            os.remove(saved_absolute_path)
        return jsonify({"error": str(e)}), 413
    except UploadValidationError as e:
        session.rollback()
        if saved_absolute_path and os.path.exists(saved_absolute_path):
            os.remove(saved_absolute_path)
        return jsonify({"error": str(e)}), 400
    except RequestEntityTooLarge:
        session.rollback()
        if saved_absolute_path and os.path.exists(saved_absolute_path):
            os.remove(saved_absolute_path)
        return _upload_too_large_response()
    except Exception as e:
        session.rollback()
        if saved_absolute_path and os.path.exists(saved_absolute_path):
            os.remove(saved_absolute_path)
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@imoveis_bp.route('/<int:id>/anexos/<int:anexo_id>/arquivo', methods=['GET'])
def get_anexo_arquivo(id, anexo_id):
    session = Session()
    try:
        anexo = session.query(Anexo).filter(
            Anexo.id == anexo_id,
            Anexo.imovel_id == id
        ).first()
        if not anexo:
            return jsonify({"error": "Anexo não encontrado"}), 404

        absolute_path = _resolve_anexo_path(anexo)
        if not absolute_path:
            return jsonify({"error": "Arquivo físico não encontrado"}), 404

        with open(absolute_path, 'rb') as file_stream:
            content = file_stream.read()

        return send_file(
            BytesIO(content),
            mimetype=anexo.mime_type or None,
            as_attachment=False,
            download_name=anexo.nome_original or anexo.nome_arquivo or os.path.basename(absolute_path),
            max_age=0,
        )
    finally:
        session.close()


@imoveis_bp.route('/<int:id>/anexos/<int:anexo_id>/replace', methods=['POST'])
def replace_anexo(id, anexo_id):
    session = Session()
    saved_absolute_path = None
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Nenhum arquivo enviado"}), 400

        anexo = session.query(Anexo).filter(
            Anexo.id == anexo_id,
            Anexo.imovel_id == id
        ).first()
        if not anexo:
            return jsonify({"error": "Anexo não encontrado"}), 404

        file = request.files['file']
        categoria = normalize_category(request.form.get('categoria') or anexo.categoria or 'Outros')
        imovel = session.query(Imovel).get(id)
        if not imovel:
            return jsonify({"error": "Imóvel não encontrado"}), 404

        saved = save_upload(
            file,
            upload_root=current_app.config['UPLOAD_ROOT'],
            company_id=imovel.company_id,
            imovel_id=id,
            category=categoria,
            max_size_bytes=current_app.config['MAX_UPLOAD_SIZE_BYTES'],
            anexo_id=anexo.id,
        )
        saved_absolute_path = saved.absolute_path

        antigo = Anexo(
            id=anexo.id,
            imovel_id=anexo.imovel_id,
            company_id=anexo.company_id,
            url=anexo.url,
            categoria=anexo.categoria,
            nome_original=anexo.nome_original,
            nome_arquivo=anexo.nome_arquivo,
            storage_path=anexo.storage_path,
            mime_type=anexo.mime_type,
            tamanho_bytes=anexo.tamanho_bytes,
        )

        anexo.company_id = imovel.company_id
        anexo.categoria = saved.category
        anexo.url = _build_anexo_url(id, anexo.id)
        anexo.nome_original = saved.original_filename
        anexo.nome_arquivo = saved.stored_filename
        anexo.storage_path = saved.relative_path
        anexo.mime_type = saved.mime_type
        anexo.tamanho_bytes = saved.size_bytes
        anexo.updated_at = datetime.utcnow()

        session.commit()
        _delete_anexo_physical_file(antigo)
        return jsonify({"message": "Arquivo substituído com sucesso", "anexo": _serialize_anexo(anexo)})
    except UploadTooLargeError as e:
        session.rollback()
        if saved_absolute_path and os.path.exists(saved_absolute_path):
            os.remove(saved_absolute_path)
        return jsonify({"error": str(e)}), 413
    except UploadValidationError as e:
        session.rollback()
        if saved_absolute_path and os.path.exists(saved_absolute_path):
            os.remove(saved_absolute_path)
        return jsonify({"error": str(e)}), 400
    except RequestEntityTooLarge:
        session.rollback()
        if saved_absolute_path and os.path.exists(saved_absolute_path):
            os.remove(saved_absolute_path)
        return _upload_too_large_response()
    except Exception as e:
        session.rollback()
        if saved_absolute_path and os.path.exists(saved_absolute_path):
            os.remove(saved_absolute_path)
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@imoveis_bp.route('/<int:id>/anexos/<int:anexo_id>', methods=['DELETE'])
def delete_anexo(id, anexo_id):
    session = Session()
    try:
        anexo = session.query(Anexo).filter(
            Anexo.id == anexo_id,
            Anexo.imovel_id == id
        ).first()
        if not anexo:
            return jsonify({"error": "Anexo não encontrado"}), 404

        _delete_anexo_physical_file(anexo)
        session.delete(anexo)
        session.commit()
        return jsonify({"message": "Anexo excluído com sucesso"})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@imoveis_bp.route('/<int:id>', methods=['DELETE'])
def excluir_imovel(id):
    session = Session()
    try:
        i = session.query(Imovel).get(id)
        if not i:
            return jsonify({"error": "Não encontrado"}), 404

        session.query(Leilao).filter_by(imovel_id=id).delete()
        session.query(FichaFinanceira).filter_by(imovel_id=id).delete()
        session.query(Documentacao).filter_by(imovel_id=id).delete()
        session.query(Reforma).filter_by(imovel_id=id).delete()
        anexos = session.query(Anexo).filter_by(imovel_id=id).all()
        for anexo in anexos:
            _delete_anexo_physical_file(anexo)
            session.delete(anexo)
        session.delete(i)
        session.commit()
        return jsonify({"message": "Imóvel excluído com sucesso"})
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
        result = TriagemService.aplicar_decisao(
            session,
            company_id=int(request.args.get('company_id', 1)),
            imovel_id=id,
            acao='descartar',
            motivo_codigo=data.get('motivo'),
            observacao=data.get('observacao'),
            decidido_por=(flask_session.get('user_name') or '').strip() or None,
        )
        return jsonify({
            "message": "Imóvel descartado do funil",
            "triagem_status": result.triagem_status,
            "status": result.status,
        })
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@imoveis_bp.route('/<int:id>/triagem/decisao', methods=['POST'])
def decidir_triagem_imovel(id):
    session = Session()
    try:
        data = request.json or {}
        result = TriagemService.aplicar_decisao(
            session,
            company_id=int(request.args.get('company_id', 1)),
            imovel_id=id,
            acao=data.get('acao'),
            motivo_codigo=data.get('motivo_codigo'),
            observacao=data.get('observacao'),
            decidido_por=(flask_session.get('user_name') or '').strip() or None,
        )
        return jsonify({
            "message": "Decisão de triagem registrada com sucesso.",
            "imovel_id": result.imovel_id,
            "triagem_status": result.triagem_status,
            "status": result.status,
            "motivo_codigo": result.motivo_codigo,
            "motivo_label": result.motivo_label,
            "observacao": result.observacao,
            "decidido_em": result.decidido_em.isoformat() if result.decidido_em else None,
            "decidido_por": result.decidido_por,
        })
    except ValueError as e:
        session.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()
