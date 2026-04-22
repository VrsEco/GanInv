from datetime import datetime
from types import SimpleNamespace

from src.core.services.triagem_service import (
    STATUS_IMOVEL_APROVADO,
    STATUS_IMOVEL_DESCARTADO,
    STATUS_IMOVEL_EM_ANALISE,
    TRIAGEM_STATUS_APROVADO,
    TRIAGEM_STATUS_DESCARTADO,
    TRIAGEM_STATUS_PENDENTE,
    TriagemService,
)


class FakeQuery:
    def __init__(self, items):
        self._items = items

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class FakeSession:
    def __init__(self, items):
        self.items = items
        self.committed = False

    def query(self, model):
        return FakeQuery(self.items)

    def commit(self):
        self.committed = True


def build_imovel(**overrides):
    base = dict(
        id=1,
        company_id=1,
        codigo_interno='GND-001',
        endereco='Rua Teste, 100',
        bairro='Centro',
        cidade='Salvador',
        estado='BA',
        status=STATUS_IMOVEL_EM_ANALISE,
        descartado=False,
        motivo_descarte=None,
        obs_descarte=None,
        data_descarte=None,
        triagem_status=None,
        triagem_motivo_codigo=None,
        triagem_motivo_label=None,
        triagem_observacao=None,
        triagem_decidido_em=None,
        triagem_decidido_por=None,
        valor_avaliacao=500000.0,
        valor_venda_normal=620000.0,
        valor_estimado_venda=580000.0,
        banco='Caixa',
        filtro_auxiliar='',
        leiloeiro='Mega Leilões',
        leiloes=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_aplicar_decisao_descartar_sincroniza_campos_legados():
    imovel = build_imovel()
    session = FakeSession([imovel])

    result = TriagemService.aplicar_decisao(
        session,
        company_id=1,
        imovel_id=1,
        acao='descartar',
        motivo_codigo='documentacao_irregular',
        observacao='Matrícula inconsistente',
        decidido_por='Admin Gandu',
    )

    assert session.committed is True
    assert result.triagem_status == TRIAGEM_STATUS_DESCARTADO
    assert imovel.status == STATUS_IMOVEL_DESCARTADO
    assert imovel.descartado is True
    assert imovel.triagem_motivo_codigo == 'documentacao_irregular'
    assert imovel.triagem_motivo_label == 'Documentação irregular'
    assert imovel.motivo_descarte == 'Documentação irregular'
    assert imovel.obs_descarte == 'Matrícula inconsistente'
    assert isinstance(imovel.triagem_decidido_em, datetime)


def test_aplicar_decisao_aprovar_limpa_descarte_e_move_status():
    imovel = build_imovel(
        status=STATUS_IMOVEL_DESCARTADO,
        descartado=True,
        motivo_descarte='Documentação irregular',
        triagem_status=TRIAGEM_STATUS_DESCARTADO,
        triagem_motivo_codigo='documentacao_irregular',
        triagem_motivo_label='Documentação irregular',
    )
    session = FakeSession([imovel])

    result = TriagemService.aplicar_decisao(
        session,
        company_id=1,
        imovel_id=1,
        acao='aprovar',
        observacao='Dados saneados',
        decidido_por='Admin Gandu',
    )

    assert result.triagem_status == TRIAGEM_STATUS_APROVADO
    assert imovel.status == STATUS_IMOVEL_APROVADO
    assert imovel.descartado is False
    assert imovel.motivo_descarte is None
    assert imovel.triagem_motivo_codigo is None
    assert imovel.triagem_observacao == 'Dados saneados'


def test_build_stats_agrega_pendentes_aprovados_descartados():
    items = [
        build_imovel(id=1, triagem_status=TRIAGEM_STATUS_PENDENTE),
        build_imovel(id=2, triagem_status=TRIAGEM_STATUS_APROVADO, status=STATUS_IMOVEL_APROVADO),
        build_imovel(
            id=3,
            triagem_status=TRIAGEM_STATUS_DESCARTADO,
            status=STATUS_IMOVEL_DESCARTADO,
            descartado=True,
            triagem_motivo_label='Baixa margem esperada',
        ),
        build_imovel(
            id=4,
            triagem_status=TRIAGEM_STATUS_DESCARTADO,
            status=STATUS_IMOVEL_DESCARTADO,
            descartado=True,
            triagem_motivo_label='Baixa margem esperada',
        ),
    ]
    session = FakeSession(items)

    stats = TriagemService.build_stats(session, company_id=1)

    assert stats['total'] == 4
    assert stats['pendentes'] == 1
    assert stats['aprovados'] == 1
    assert stats['descartados'] == 2
    assert stats['taxa_aprovacao'] == 25.0
    assert stats['principais_motivos'][0]['label'] == 'Baixa margem esperada'
    assert stats['principais_motivos'][0]['quantidade'] == 2


def test_list_imoveis_filtra_por_filtro_auxiliar():
    items = [
        build_imovel(id=1, codigo_interno='GND-001', filtro_auxiliar='A'),
        build_imovel(id=2, codigo_interno='GND-002', filtro_auxiliar='B'),
        build_imovel(id=3, codigo_interno='GND-003', filtro_auxiliar='A'),
    ]
    session = FakeSession(items)

    result = TriagemService.list_imoveis(session, company_id=1, filtro_auxiliar='A')

    assert [item['codigo'] for item in result] == ['GND-001', 'GND-003']
    assert all(item['filtro_auxiliar'] == 'A' for item in result)
