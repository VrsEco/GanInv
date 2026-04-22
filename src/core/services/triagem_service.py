from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from src.core.models.models import FILTRO_AUXILIAR_OPTIONS, Imovel


TRIAGEM_STATUS_PENDENTE = "Pendente"
TRIAGEM_STATUS_APROVADO = "Aprovado"
TRIAGEM_STATUS_DESCARTADO = "Descartado"

STATUS_IMOVEL_EM_ANALISE = "Em análise"
STATUS_IMOVEL_APROVADO = "Aprovado para disputa"
STATUS_IMOVEL_DESCARTADO = "Descartado"


TRIAGEM_MOTIVOS = [
    {"codigo": "localizacao_fora_radar", "label": "Localização fora do radar", "grupo": "Mercado"},
    {"codigo": "localizacao_ruim", "label": "Localização ruim", "grupo": "Mercado"},
    {"codigo": "valor_fora_faixa", "label": "Valor fora da faixa alvo", "grupo": "Preço"},
    {"codigo": "baixa_margem", "label": "Baixa margem esperada", "grupo": "Viabilidade"},
    {"codigo": "predio_sem_conservacao", "label": "Prédio sem conservação", "grupo": "Imóvel"},
    {"codigo": "documentacao_irregular", "label": "Documentação irregular", "grupo": "Jurídico"},
    {"codigo": "risco_juridico", "label": "Risco jurídico", "grupo": "Jurídico"},
    {"codigo": "sem_dados_decisao", "label": "Sem dados para decisão", "grupo": "Processo"},
    {"codigo": "ocupante_problematico", "label": "Ocupante problemático", "grupo": "Posse"},
    {"codigo": "outros", "label": "Outros", "grupo": "Geral"},
]

TRIAGEM_MOTIVOS_BY_CODE = {item["codigo"]: item for item in TRIAGEM_MOTIVOS}


@dataclass
class TriagemDecisionResult:
    imovel_id: int
    triagem_status: str
    status: str
    motivo_codigo: str | None
    motivo_label: str | None
    observacao: str | None
    decidido_em: datetime | None
    decidido_por: str | None


class TriagemService:
    @staticmethod
    def list_motivos():
        return TRIAGEM_MOTIVOS

    @staticmethod
    def resolve_triagem_status(imovel: Imovel) -> str:
        triagem_status = (getattr(imovel, "triagem_status", None) or "").strip()
        if triagem_status in {TRIAGEM_STATUS_PENDENTE, TRIAGEM_STATUS_APROVADO, TRIAGEM_STATUS_DESCARTADO}:
            return triagem_status

        if bool(getattr(imovel, "descartado", False)) or (getattr(imovel, "status", "") or "").strip() == STATUS_IMOVEL_DESCARTADO:
            return TRIAGEM_STATUS_DESCARTADO

        if (getattr(imovel, "status", "") or "").strip() == STATUS_IMOVEL_APROVADO:
            return TRIAGEM_STATUS_APROVADO

        return TRIAGEM_STATUS_PENDENTE

    @staticmethod
    def _serialize_imovel(imovel: Imovel):
        triagem_status = TriagemService.resolve_triagem_status(imovel)
        auction_date = None
        if getattr(imovel, "leiloes", None):
            ordered = sorted(
                [item for item in imovel.leiloes if item.data_hora],
                key=lambda item: item.data_hora,
            )
            if ordered:
                auction_date = ordered[0].data_hora

        return {
            "id": imovel.id,
            "codigo": imovel.codigo_interno or f"GND-{imovel.id:03d}",
            "endereco": imovel.endereco,
            "bairro": imovel.bairro or "",
            "cidade": imovel.cidade or "",
            "estado": imovel.estado or "",
            "status": imovel.status or STATUS_IMOVEL_EM_ANALISE,
            "filtro_auxiliar": (getattr(imovel, "filtro_auxiliar", None) or ""),
            "triagem_status": triagem_status,
            "triagem_motivo_codigo": getattr(imovel, "triagem_motivo_codigo", None),
            "triagem_motivo_label": getattr(imovel, "triagem_motivo_label", None) or getattr(imovel, "motivo_descarte", None),
            "triagem_observacao": getattr(imovel, "triagem_observacao", None) or getattr(imovel, "obs_descarte", None),
            "triagem_decidido_em": getattr(imovel, "triagem_decidido_em", None).isoformat() if getattr(imovel, "triagem_decidido_em", None) else (imovel.data_descarte.isoformat() if imovel.data_descarte else None),
            "triagem_decidido_por": getattr(imovel, "triagem_decidido_por", None),
            "valor_avaliacao": imovel.valor_avaliacao or 0.0,
            "valor_venda_normal": imovel.valor_venda_normal or 0.0,
            "valor_venda_rapida": imovel.valor_estimado_venda or 0.0,
            "banco": imovel.banco or "",
            "leiloeiro": imovel.leiloeiro or "",
            "data_primeiro_leilao": auction_date.isoformat() if auction_date else None,
            "descartado": bool(getattr(imovel, "descartado", False)),
        }

    @staticmethod
    def list_imoveis(session, *, company_id: int, triagem_status: str = "", motivo_codigo: str = "", cidade: str = "", banco: str = "", filtro_auxiliar: str = "", search: str = ""):
        query = session.query(Imovel).filter(Imovel.company_id == company_id).order_by(Imovel.id.desc())
        items = query.all()

        normalized_status = (triagem_status or "").strip().title()
        normalized_motivo = (motivo_codigo or "").strip()
        normalized_city = (cidade or "").strip().lower()
        normalized_bank = (banco or "").strip().lower()
        normalized_filtro_auxiliar = (filtro_auxiliar or "").strip().upper()
        if normalized_filtro_auxiliar not in FILTRO_AUXILIAR_OPTIONS:
            normalized_filtro_auxiliar = ""
        normalized_search = (search or "").strip().lower()

        filtered = []
        for imovel in items:
            resolved_status = TriagemService.resolve_triagem_status(imovel)
            if normalized_status and resolved_status != normalized_status:
                continue

            motivo_atual = (getattr(imovel, "triagem_motivo_codigo", None) or "").strip()
            if normalized_motivo and motivo_atual != normalized_motivo:
                continue

            if normalized_city and normalized_city not in (imovel.cidade or "").lower():
                continue

            if normalized_bank and normalized_bank not in (imovel.banco or "").lower():
                continue

            if normalized_filtro_auxiliar and (getattr(imovel, "filtro_auxiliar", None) or "").strip().upper() != normalized_filtro_auxiliar:
                continue

            haystack = " ".join([
                imovel.codigo_interno or "",
                imovel.endereco or "",
                imovel.cidade or "",
                imovel.estado or "",
                imovel.banco or "",
                imovel.leiloeiro or "",
                getattr(imovel, "filtro_auxiliar", None) or "",
            ]).lower()
            if normalized_search and normalized_search not in haystack:
                continue

            filtered.append(TriagemService._serialize_imovel(imovel))

        return filtered

    @staticmethod
    def build_filters(session, *, company_id: int):
        imoveis = session.query(Imovel).filter(Imovel.company_id == company_id).all()
        cidades = sorted({(item.cidade or "").strip() for item in imoveis if (item.cidade or "").strip()})
        bancos = sorted({(item.banco or "").strip() for item in imoveis if (item.banco or "").strip()})
        return {
            "cidades": cidades,
            "bancos": bancos,
            "motivos": TriagemService.list_motivos(),
            "filtros_auxiliares": list(FILTRO_AUXILIAR_OPTIONS),
            "triagem_status": [
                TRIAGEM_STATUS_PENDENTE,
                TRIAGEM_STATUS_APROVADO,
                TRIAGEM_STATUS_DESCARTADO,
            ],
        }

    @staticmethod
    def build_stats(session, *, company_id: int):
        imoveis = session.query(Imovel).filter(Imovel.company_id == company_id).all()
        serialized = [TriagemService._serialize_imovel(item) for item in imoveis]
        total = len(serialized)
        pending = sum(1 for item in serialized if item["triagem_status"] == TRIAGEM_STATUS_PENDENTE)
        approved = sum(1 for item in serialized if item["triagem_status"] == TRIAGEM_STATUS_APROVADO)
        discarded = sum(1 for item in serialized if item["triagem_status"] == TRIAGEM_STATUS_DESCARTADO)
        approval_rate = round((approved / total) * 100, 1) if total else 0.0

        reasons_counter = Counter(
            item["triagem_motivo_label"] for item in serialized
            if item["triagem_status"] == TRIAGEM_STATUS_DESCARTADO and item["triagem_motivo_label"]
        )

        principais_motivos = [
            {"label": label, "quantidade": quantidade}
            for label, quantidade in reasons_counter.most_common(5)
        ]

        return {
            "total": total,
            "pendentes": pending,
            "aprovados": approved,
            "descartados": discarded,
            "taxa_aprovacao": approval_rate,
            "principais_motivos": principais_motivos,
        }

    @staticmethod
    def _resolve_motivo(motivo_codigo: str | None):
        if not motivo_codigo:
            return None, None
        motivo = TRIAGEM_MOTIVOS_BY_CODE.get(motivo_codigo)
        if not motivo:
            raise ValueError("Motivo de triagem inválido.")
        return motivo["codigo"], motivo["label"]

    @staticmethod
    def aplicar_decisao(session, *, company_id: int, imovel_id: int, acao: str, motivo_codigo: str | None = None, observacao: str | None = None, decidido_por: str | None = None):
        imovel = session.query(Imovel).filter(
            Imovel.id == imovel_id,
            Imovel.company_id == company_id,
        ).first()

        if not imovel:
            raise ValueError("Imóvel não encontrado.")

        action = (acao or "").strip().lower()
        motivo_codigo = (motivo_codigo or "").strip() or None
        observacao = (observacao or "").strip() or None
        agora = datetime.utcnow()

        if action == "aprovar":
            imovel.triagem_status = TRIAGEM_STATUS_APROVADO
            imovel.status = STATUS_IMOVEL_APROVADO
            imovel.descartado = False
            imovel.motivo_descarte = None
            imovel.obs_descarte = None
            imovel.data_descarte = None
            imovel.triagem_motivo_codigo = None
            imovel.triagem_motivo_label = None
            imovel.triagem_observacao = observacao
        elif action == "descartar":
            motivo_codigo_resolvido, motivo_label = TriagemService._resolve_motivo(motivo_codigo)
            if not motivo_codigo_resolvido:
                raise ValueError("Selecione um motivo de descarte.")
            imovel.triagem_status = TRIAGEM_STATUS_DESCARTADO
            imovel.status = STATUS_IMOVEL_DESCARTADO
            imovel.descartado = True
            imovel.motivo_descarte = motivo_label
            imovel.obs_descarte = observacao
            imovel.data_descarte = agora
            imovel.triagem_motivo_codigo = motivo_codigo_resolvido
            imovel.triagem_motivo_label = motivo_label
            imovel.triagem_observacao = observacao
        elif action in {"reabrir", "pendente"}:
            imovel.triagem_status = TRIAGEM_STATUS_PENDENTE
            imovel.status = STATUS_IMOVEL_EM_ANALISE
            imovel.descartado = False
            imovel.motivo_descarte = None
            imovel.obs_descarte = None
            imovel.data_descarte = None
            imovel.triagem_motivo_codigo = None
            imovel.triagem_motivo_label = None
            imovel.triagem_observacao = observacao
        else:
            raise ValueError("Ação de triagem inválida.")

        imovel.triagem_decidido_em = agora
        imovel.triagem_decidido_por = (decidido_por or "").strip() or None
        session.commit()

        return TriagemDecisionResult(
            imovel_id=imovel.id,
            triagem_status=imovel.triagem_status,
            status=imovel.status,
            motivo_codigo=imovel.triagem_motivo_codigo,
            motivo_label=imovel.triagem_motivo_label,
            observacao=imovel.triagem_observacao,
            decidido_em=imovel.triagem_decidido_em,
            decidido_por=imovel.triagem_decidido_por,
        )
