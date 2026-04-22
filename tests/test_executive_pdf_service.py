from io import BytesIO
from types import SimpleNamespace

from pypdf import PdfReader

from src.core.services.executive_pdf_service import ExecutivePdfService


def _build_dummy_imovel():
    financeiro = SimpleNamespace(
        valor_arrematacao=359000.0,
        comissao_leiloeiro_percent=5.0,
        outros_custos_arrematacao=1000.0,
        itiv_percent=3.0,
        registro_cartorio_percent=2.0,
        iptu_atrasado=15000.0,
        condominio_atrasado=5000.0,
        iptu_futuro=500.0,
        condominio_futuro=1000.0,
        desocupacao=10000.0,
        reforma_prevista=15000.0,
        limpeza=1000.0,
        contingencia=5000.0,
        custo_capital_meses=5,
        custo_capital_percent=1.0,
        lucro_minimo_vlr=36004.5,
        lucro_minimo_percent=10.0,
        comissao_corretor_percent=5.0,
        impostos_venda_percent=6.93,
        valor_venda_projetado=520000.0,
    )
    return SimpleNamespace(
        id=8,
        codigo_interno="GND-008",
        endereco="Teste 02",
        status="Em análise",
        cidade="Cidade Teste",
        estado="TS",
        tipo_imovel="Apartamento",
        area_privativa=50.0,
        ocupado=True,
        valor_venda_normal=550000.0,
        valor_estimado_venda=520000.0,
        financeiro=financeiro,
        anexos=[],
        leiloes=[
            SimpleNamespace(tipo_leilao="1º Leilão", data_hora=None, valor_minimo=250000.0),
            SimpleNamespace(tipo_leilao="2º Leilão", data_hora=None, valor_minimo=290000.0),
        ],
    )


def test_max_bid_formula_reaches_zero_spread():
    imovel = _build_dummy_imovel()
    snapshot = ExecutivePdfService.build_financial_snapshot(imovel, imovel.financeiro)

    com_leilao_per = imovel.financeiro.comissao_leiloeiro_percent
    itiv_per = imovel.financeiro.itiv_percent
    reg_per = imovel.financeiro.registro_cartorio_percent
    cap_percent = imovel.financeiro.custo_capital_percent
    cap_meses = imovel.financeiro.custo_capital_meses
    lucro_min = imovel.financeiro.lucro_minimo_vlr
    fixed_costs = imovel.financeiro.outros_custos_arrematacao + snapshot["common"]["sub_c"]
    acquisition_factor = 1 + ((com_leilao_per + itiv_per + reg_per) / 100)
    capital_multiplier = 1 + ((cap_percent / 100) * cap_meses)

    lance_normal = snapshot["lance_maximo"]["normal"]
    investimento_normal = ((lance_normal * acquisition_factor) + fixed_costs) * capital_multiplier
    spread_normal = snapshot["normal"]["venda_liquida"] - investimento_normal - lucro_min
    assert abs(spread_normal) < 0.02

    lance_rapida = snapshot["lance_maximo"]["rapida"]
    investimento_rapida = ((lance_rapida * acquisition_factor) + fixed_costs) * capital_multiplier
    spread_rapida = snapshot["rapida"]["venda_liquida"] - investimento_rapida - lucro_min
    assert abs(spread_rapida) < 0.02


def test_render_pdf_generates_single_page_with_core_sections(tmp_path):
    payload = {
        "id": 8,
        "codigo": "GND-008",
        "endereco": "Teste 02",
        "status": "Em análise",
        "cidade_uf": "Cidade Teste - TS",
        "tipo": "Apartamento",
        "area_privativa": "50 m²",
        "ocupacao": "Ocupado",
        "foto_path": r"C:\GanduInvest\static\img\placeholder-imovel.jpg",
        "gerado_em": "21/04/2026",
        "report_id": "GND-008-20260421103000",
        "leiloes": [
            {"tipo": "1º Leilão", "data": "25/04/2026, 10:00", "valor": "R$ 250.000,00"},
            {"tipo": "2º Leilão", "data": "29/04/2026, 10:00", "valor": "R$ 290.000,00"},
        ],
        "analise": {
            "lance_normal": 339571.86,
            "lance_rapida": 316696.54,
            "lance_considerado": 359000.0,
            "comissao_corretor_percent": 5.0,
            "impostos_venda_percent": 6.93,
            "rows": [
                ("Preço de Venda", 550000.0, 520000.0, "money", "primary"),
                ("Comissões de Venda", 27500.0, 26000.0, "money", "negative"),
                ("Impostos Sobre Vendas", 38115.0, 36036.0, "money", "negative"),
                ("Vendas Líquidas", 484385.0, 457964.0, "money", "positive"),
                ("A. Arrematação", 377950.0, 377950.0, "money", "default"),
                ("B. Impostos e Taxas", 17950.0, 17950.0, "money", "default"),
                ("C. Custos Operacionais", 52500.0, 52500.0, "money", "warning"),
                ("D. Custo de Capital", 22322.50, 22322.50, "money", "primary"),
                ("Total (A+B+C+D)", 470722.5, 470722.5, "money", "total"),
                ("Resultado", 13662.5, -12758.5, "money", "result"),
            ],
        },
    }

    output_path = tmp_path / "executivo.pdf"
    pdf_bytes = ExecutivePdfService.render_pdf(payload, output_path=str(output_path))

    assert pdf_bytes.startswith(b"%PDF")
    assert output_path.exists()

    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert "Histórico de Pregões" in text
    assert "Análise do Negócio" in text
    assert "Sugestão de Lance Máximo" in text


def test_render_mobile_pdf_generates_phone_optimized_single_page(tmp_path):
    payload = {
        "id": 8,
        "codigo": "GND-008",
        "endereco": "Teste 02",
        "status": "Em análise",
        "cidade_uf": "Cidade Teste - TS",
        "tipo": "Apartamento",
        "area_privativa": "50 m²",
        "ocupacao": "Ocupado",
        "foto_path": r"C:\GanduInvest\static\img\placeholder-imovel.jpg",
        "gerado_em": "21/04/2026",
        "report_id": "GND-008-20260421103000",
        "leiloes": [
            {"tipo": "1º Leilão", "data": "25/04/2026, 10:00", "valor": "R$ 250.000,00"},
            {"tipo": "2º Leilão", "data": "29/04/2026, 10:00", "valor": "R$ 290.000,00"},
        ],
        "analise": {
            "lance_normal": 339571.86,
            "lance_rapida": 316696.54,
            "lance_considerado": 359000.0,
            "comissao_corretor_percent": 5.0,
            "impostos_venda_percent": 6.93,
            "rows": [
                ("Preço de Venda", 550000.0, 520000.0, "money", "primary"),
                ("Comissões de Venda", 27500.0, 26000.0, "money", "negative"),
                ("Impostos Sobre Vendas", 38115.0, 36036.0, "money", "negative"),
                ("Vendas Líquidas", 484385.0, 457964.0, "money", "positive"),
                ("A. Arrematação", 377950.0, 377950.0, "money", "default"),
                ("B. Impostos e Taxas", 17950.0, 17950.0, "money", "default"),
                ("C. Custos Operacionais", 52500.0, 52500.0, "money", "warning"),
                ("D. Custo de Capital", 22322.50, 22322.50, "money", "primary"),
                ("Total (A+B+C+D)", 470722.5, 470722.5, "money", "total"),
                ("Resultado", 13662.5, -12758.5, "money", "result"),
            ],
        },
    }

    output_path = tmp_path / "executivo-mobile.pdf"
    pdf_bytes = ExecutivePdfService.render_mobile_pdf(payload, output_path=str(output_path))

    assert pdf_bytes.startswith(b"%PDF")
    assert output_path.exists()

    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert round(float(page.mediabox.width)) == 390
    assert round(float(page.mediabox.height)) == 844
    text = page.extract_text()
    assert "Analise do Negocio" in text
    assert "PDF Executivo Mobile" in text
