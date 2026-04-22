import os
import re
from datetime import datetime
from io import BytesIO

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from src.core.models.models import Imovel
from src.core.services.storage_service import UploadValidationError, normalize_category, resolve_absolute_path


class ExecutivePdfService:
    PAGE_SIZE = landscape(A4)
    PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE
    PAGE_MARGIN = 22
    MOBILE_PAGE_SIZE = (390, 844)
    MOBILE_MARGIN = 14

    COLOR_BG = colors.HexColor("#F3F6FB")
    COLOR_CARD = colors.white
    COLOR_BORDER = colors.HexColor("#D7E0EB")
    COLOR_TEXT = colors.HexColor("#0F172A")
    COLOR_MUTED = colors.HexColor("#64748B")
    COLOR_HEADER = colors.HexColor("#0B1324")
    COLOR_HEADER_SOFT = colors.HexColor("#1D2942")
    COLOR_EMERALD = colors.HexColor("#10B981")
    COLOR_EMERALD_SOFT = colors.HexColor("#E7F9F3")
    COLOR_BLUE = colors.HexColor("#3B82F6")
    COLOR_BLUE_SOFT = colors.HexColor("#EAF2FF")
    COLOR_RED = colors.HexColor("#DC2626")
    COLOR_RED_SOFT = colors.HexColor("#FEE2E2")
    COLOR_AMBER = colors.HexColor("#D97706")
    COLOR_AMBER_SOFT = colors.HexColor("#FEF3C7")
    COLOR_GRAY_SOFT = colors.HexColor("#F8FAFC")

    TITLE_STYLE = ParagraphStyle(
        "executive_title",
        fontName="Helvetica-Bold",
        fontSize=23,
        leading=25,
        textColor=colors.white,
    )

    @staticmethod
    def sanitize_text(value):
        text = str(value or "--").strip()
        replacements = {
            "\u2014": "-",
            "\u2013": "-",
            "\u2011": "-",
            "\u00a0": " ",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    @classmethod
    def format_currency(cls, value):
        amount = float(value or 0)
        negative = amount < 0
        amount = abs(amount)
        formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"- R$ {formatted}" if negative else f"R$ {formatted}"

    @classmethod
    def format_area(cls, value):
        area = float(value or 0)
        if area <= 0:
            return "--"
        if area.is_integer():
            return f"{int(area)} m²"
        return f"{area:.2f}".replace(".", ",") + " m²"

    @classmethod
    def format_date_br(cls, value):
        if not value:
            return "--"
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return cls.sanitize_text(value)
            value = parsed
        return value.strftime("%d/%m/%Y")

    @classmethod
    def format_datetime_br(cls, value):
        if not value:
            return "--"
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return cls.sanitize_text(value)
            value = parsed
        return value.strftime("%d/%m/%Y, %H:%M")

    @staticmethod
    def status_theme(status):
        normalized = (status or "").strip().lower()
        if "arremat" in normalized:
            return colors.HexColor("#D1FAE5"), colors.HexColor("#047857")
        if "análise" in normalized or "analise" in normalized:
            return colors.HexColor("#DBEAFE"), colors.HexColor("#1D4ED8")
        if "venda" in normalized:
            return colors.HexColor("#FEF3C7"), colors.HexColor("#B45309")
        return colors.HexColor("#E2E8F0"), colors.HexColor("#334155")

    @staticmethod
    def _slugify_filename(value):
        text = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "relatorio")).strip("-")
        return text.lower() or "relatorio"

    @staticmethod
    def _get_scenario_price(primary, fallback):
        primary_value = float(primary or 0)
        if primary_value > 0:
            return primary_value
        return float(fallback or 0)

    @staticmethod
    def build_sale_scenario(preco_venda, comissao_venda_per, imposto_venda_per, investimento_total):
        preco = float(preco_venda or 0)
        comissao_venda = preco * (float(comissao_venda_per or 0) / 100)
        imposto_venda = preco * (float(imposto_venda_per or 0) / 100)
        venda_liquida = preco - comissao_venda - imposto_venda
        resultado = venda_liquida - float(investimento_total or 0)
        roi = (resultado / investimento_total * 100) if float(investimento_total or 0) > 0 else 0
        return {
            "preco": preco,
            "comissao_venda": comissao_venda,
            "imposto_venda": imposto_venda,
            "venda_liquida": venda_liquida,
            "resultado": resultado,
            "roi": roi,
        }

    @staticmethod
    def calculate_max_bid_for_zero_spread(venda_liquida, lucro_min_vlr, acquisition_percent_factor, fixed_acquisition_costs, capital_rate_factor):
        venda_liquida_num = float(venda_liquida or 0)
        lucro_min_num = float(lucro_min_vlr or 0)
        acquisition_factor = 1 + float(acquisition_percent_factor or 0)
        capital_multiplier = 1 + float(capital_rate_factor or 0)
        fixed_costs = float(fixed_acquisition_costs or 0)

        if acquisition_factor <= 0 or capital_multiplier <= 0:
            return 0

        max_bid = (((venda_liquida_num - lucro_min_num) / capital_multiplier) - fixed_costs) / acquisition_factor
        return max(0, max_bid or 0)

    @classmethod
    def build_financial_snapshot(cls, imovel, financeiro):
        financeiro = financeiro or getattr(imovel, "financeiro", None)
        lance = float(getattr(financeiro, "valor_arrematacao", 0) or 0)
        com_leilao_per = float(getattr(financeiro, "comissao_leiloeiro_percent", 0) or 0)
        outros_custos_arrem = float(getattr(financeiro, "outros_custos_arrematacao", 0) or 0)
        itiv_per = float(getattr(financeiro, "itiv_percent", 0) or 0)
        reg_per = float(getattr(financeiro, "registro_cartorio_percent", 0) or 0)

        vlr_com_leilao = lance * (com_leilao_per / 100)
        sub_a = lance + vlr_com_leilao + outros_custos_arrem

        vlr_itiv = lance * (itiv_per / 100)
        vlr_reg = lance * (reg_per / 100)
        sub_b = vlr_itiv + vlr_reg

        iptu_attr = float(getattr(financeiro, "iptu_atrasado", 0) or 0)
        condo_attr = float(getattr(financeiro, "condominio_atrasado", 0) or 0)
        iptu_fut = float(getattr(financeiro, "iptu_futuro", 0) or 0)
        condo_fut = float(getattr(financeiro, "condominio_futuro", 0) or 0)
        desocupacao = float(getattr(financeiro, "desocupacao", 0) or 0)
        reforma = float(getattr(financeiro, "reforma_prevista", 0) or 0)
        limpeza = float(getattr(financeiro, "limpeza", 0) or 0)
        contingencia = float(getattr(financeiro, "contingencia", 0) or 0)
        sub_c = iptu_attr + condo_attr + iptu_fut + condo_fut + desocupacao + reforma + limpeza + contingencia

        abc_total = sub_a + sub_b + sub_c
        cap_meses = int(getattr(financeiro, "custo_capital_meses", 0) or 0)
        cap_percent = float(getattr(financeiro, "custo_capital_percent", 0) or 0)
        custo_capital = abc_total * (cap_percent / 100) * cap_meses
        investimento_total = abc_total + custo_capital

        lucro_min_vlr = float(getattr(financeiro, "lucro_minimo_vlr", 0) or 0)
        lucro_min_per = float(getattr(financeiro, "lucro_minimo_percent", 0) or 0)
        com_corr_per = float(getattr(financeiro, "comissao_corretor_percent", 0) or 0)
        imp_venda_per = float(getattr(financeiro, "impostos_venda_percent", 0) or 0)

        venda_proj_informada = float(getattr(financeiro, "valor_venda_projetado", 0) or 0)
        fallback_venda = cls._get_scenario_price(imovel.valor_estimado_venda, imovel.valor_venda_normal)
        valor_venda_base = venda_proj_informada if venda_proj_informada > 0 else fallback_venda
        preco_normal = cls._get_scenario_price(imovel.valor_venda_normal, valor_venda_base)
        preco_rapida = cls._get_scenario_price(imovel.valor_estimado_venda, valor_venda_base)

        normal = cls.build_sale_scenario(preco_normal, com_corr_per, imp_venda_per, investimento_total)
        rapida = cls.build_sale_scenario(preco_rapida, com_corr_per, imp_venda_per, investimento_total)

        acquisition_percent_factor = (com_leilao_per + itiv_per + reg_per) / 100
        capital_rate_factor = (cap_percent / 100) * cap_meses
        fixed_acquisition_costs = outros_custos_arrem + sub_c

        lance_normal = cls.calculate_max_bid_for_zero_spread(
            normal["venda_liquida"],
            lucro_min_vlr,
            acquisition_percent_factor,
            fixed_acquisition_costs,
            capital_rate_factor,
        )
        lance_rapida = cls.calculate_max_bid_for_zero_spread(
            rapida["venda_liquida"],
            lucro_min_vlr,
            acquisition_percent_factor,
            fixed_acquisition_costs,
            capital_rate_factor,
        )

        return {
            "common": {
                "sub_a": sub_a,
                "sub_b": sub_b,
                "sub_c": sub_c,
                "custo_capital": custo_capital,
                "investimento_total": investimento_total,
                "lucro_min_vlr": lucro_min_vlr,
                "lucro_min_per": lucro_min_per,
                "valor_lance_considerado": lance,
                "comissao_corretor_percent": com_corr_per,
                "impostos_venda_percent": imp_venda_per,
            },
            "normal": normal,
            "rapida": rapida,
            "lance_maximo": {
                "normal": lance_normal,
                "rapida": lance_rapida,
            },
        }

    @classmethod
    def resolve_anexo_path(cls, anexo, root_path, upload_root):
        storage_path = getattr(anexo, "storage_path", None)
        if storage_path:
            try:
                absolute_path = resolve_absolute_path(upload_root, storage_path)
                if os.path.exists(absolute_path):
                    return absolute_path
            except UploadValidationError:
                pass

        url = str(getattr(anexo, "url", "") or "").strip()
        if url.startswith("/static/uploads/"):
            candidate = os.path.join(root_path, "static", "uploads", os.path.basename(url[len("/static/uploads/"):]))
            if os.path.exists(candidate):
                return candidate
        if url.startswith("/static/"):
            candidate = os.path.join(root_path, url.lstrip("/").replace("/", os.sep))
            if os.path.exists(candidate):
                return candidate
        return None

    @classmethod
    def resolve_photo_path(cls, imovel, root_path, upload_root):
        fotos = [a for a in (getattr(imovel, "anexos", None) or []) if normalize_category(getattr(a, "categoria", "")) == "Foto"]
        for foto in fotos:
            absolute_path = cls.resolve_anexo_path(foto, root_path, upload_root)
            if absolute_path:
                return absolute_path
        return os.path.join(root_path, "static", "img", "placeholder-imovel.jpg")

    @classmethod
    def build_report_payload(cls, imovel, *, root_path, upload_root):
        codigo = imovel.codigo_interno or f"GND-{imovel.id:03d}"
        cidade = cls.sanitize_text(imovel.cidade or "--")
        estado = cls.sanitize_text(imovel.estado or "--")
        financeiro = getattr(imovel, "financeiro", None)
        snapshot = cls.build_financial_snapshot(imovel, financeiro)
        foto_path = cls.resolve_photo_path(imovel, root_path, upload_root)
        gerado_em = datetime.now()
        report_id = f"{codigo}-{gerado_em.strftime('%Y%m%d%H%M%S')}"

        analise_rows = [
            ("Preço de Venda", snapshot["normal"]["preco"], snapshot["rapida"]["preco"], "money", "primary"),
            ("Comissões de Venda", snapshot["normal"]["comissao_venda"], snapshot["rapida"]["comissao_venda"], "money", "negative"),
            ("Impostos Sobre Vendas", snapshot["normal"]["imposto_venda"], snapshot["rapida"]["imposto_venda"], "money", "negative"),
            ("Vendas Líquidas", snapshot["normal"]["venda_liquida"], snapshot["rapida"]["venda_liquida"], "money", "positive"),
            ("A. Arrematação", snapshot["common"]["sub_a"], snapshot["common"]["sub_a"], "money", "default"),
            ("B. Impostos e Taxas", snapshot["common"]["sub_b"], snapshot["common"]["sub_b"], "money", "default"),
            ("C. Custos Operacionais", snapshot["common"]["sub_c"], snapshot["common"]["sub_c"], "money", "warning"),
            ("D. Custo de Capital", snapshot["common"]["custo_capital"], snapshot["common"]["custo_capital"], "money", "primary"),
            ("Total (A+B+C+D)", snapshot["common"]["investimento_total"], snapshot["common"]["investimento_total"], "money", "total"),
            ("Resultado", snapshot["normal"]["resultado"], snapshot["rapida"]["resultado"], "money", "result"),
        ]

        leiloes = sorted(getattr(imovel, "leiloes", []) or [], key=lambda item: item.data_hora or datetime.max)
        leiloes_payload = [
            {
                "tipo": cls.sanitize_text(leilao.tipo_leilao or f"{index + 1}º Leilão"),
                "data": cls.format_datetime_br(leilao.data_hora),
                "valor": cls.format_currency(leilao.valor_minimo or 0),
            }
            for index, leilao in enumerate(leiloes[:3])
        ]

        return {
            "id": imovel.id,
            "codigo": cls.sanitize_text(codigo),
            "endereco": cls.sanitize_text(imovel.endereco or "--"),
            "status": cls.sanitize_text(imovel.status or "--"),
            "cidade_uf": f"{cidade} - {estado}" if cidade != "--" or estado != "--" else "--",
            "tipo": cls.sanitize_text(imovel.tipo_imovel or "--"),
            "area_privativa": cls.format_area(imovel.area_privativa),
            "ocupacao": "Ocupado" if bool(getattr(imovel, "ocupado", False)) else "Desocupado",
            "foto_path": foto_path,
            "gerado_em": cls.format_date_br(gerado_em),
            "report_id": report_id,
            "leiloes": leiloes_payload,
            "analise": {
                "lance_normal": snapshot["lance_maximo"]["normal"],
                "lance_rapida": snapshot["lance_maximo"]["rapida"],
                "lance_considerado": snapshot["common"]["valor_lance_considerado"],
                "comissao_corretor_percent": snapshot["common"]["comissao_corretor_percent"],
                "impostos_venda_percent": snapshot["common"]["impostos_venda_percent"],
                "rows": analise_rows,
            },
        }

    @classmethod
    def _draw_rounded_card(cls, pdf, x, y, width, height, fill_color=None, stroke_color=None, radius=18, stroke_width=1):
        pdf.saveState()
        pdf.setFillColor(fill_color or cls.COLOR_CARD)
        pdf.setStrokeColor(stroke_color or cls.COLOR_BORDER)
        pdf.setLineWidth(stroke_width)
        pdf.roundRect(x, y, width, height, radius, fill=1, stroke=1)
        pdf.restoreState()

    @classmethod
    def _draw_chip(cls, pdf, x, y, text, fill_color, text_color, border_color=None, height=18, padding_x=10, font_size=8.5):
        text = cls.sanitize_text(text)
        width = stringWidth(text, "Helvetica-Bold", font_size) + (padding_x * 2)
        pdf.saveState()
        pdf.setFillColor(fill_color)
        pdf.setStrokeColor(border_color or fill_color)
        pdf.roundRect(x, y, width, height, height / 2, fill=1, stroke=1)
        pdf.setFillColor(text_color)
        pdf.setFont("Helvetica-Bold", font_size)
        pdf.drawString(x + padding_x, y + 5.5, text)
        pdf.restoreState()
        return width

    @classmethod
    def _draw_image_cover(cls, pdf, image_path, x, y, width, height, radius=18):
        cls._draw_rounded_card(pdf, x, y, width, height, fill_color=cls.COLOR_GRAY_SOFT, stroke_color=cls.COLOR_BORDER, radius=radius)
        if not image_path or not os.path.exists(image_path):
            return

        try:
            with Image.open(image_path) as image:
                img_width, img_height = image.size
        except Exception:
            return

        if img_width <= 0 or img_height <= 0:
            return

        box_ratio = width / height
        img_ratio = img_width / img_height

        if img_ratio > box_ratio:
            draw_height = height
            draw_width = height * img_ratio
        else:
            draw_width = width
            draw_height = width / img_ratio

        draw_x = x + (width - draw_width) / 2
        draw_y = y + (height - draw_height) / 2

        pdf.saveState()
        clip_path = pdf.beginPath()
        clip_path.roundRect(x, y, width, height, radius)
        pdf.clipPath(clip_path, stroke=0, fill=0)
        pdf.drawImage(image_path, draw_x, draw_y, draw_width, draw_height, mask="auto")
        pdf.restoreState()

    @classmethod
    def _build_analysis_table(cls, payload, width, *, compact=False):
        analysis = payload["analise"]
        rows = [
            [
                "Sugestão de Lance Máximo",
                cls.format_currency(analysis["lance_normal"]),
                cls.format_currency(analysis["lance_rapida"]),
            ],
            [
                "Valor do lance considerado",
                cls.format_currency(analysis["lance_considerado"]),
                cls.format_currency(analysis["lance_considerado"]),
            ],
            [
                "Indicador",
                "Venda Normal",
                "Venda Rápida",
            ],
        ]

        for label, normal, rapida, kind, tone in analysis["rows"]:
            if kind == "money":
                normal_value = cls.format_currency(normal)
                rapida_value = cls.format_currency(rapida)
            else:
                normal_value = cls.sanitize_text(normal)
                rapida_value = cls.sanitize_text(rapida)
            rows.append([cls.sanitize_text(label), normal_value, rapida_value, tone])

        if compact:
            col_widths = [width * 0.45, width * 0.275, width * 0.275]
            base_font_size = 6.8
            base_leading = 8
            row_padding = 3.6
            highlight_font_size = 7.2
        else:
            col_widths = [width * 0.42, width * 0.29, width * 0.29]
            base_font_size = 9.2
            base_leading = 11
            row_padding = 6
            highlight_font_size = 10

        table_data = [row[:3] for row in rows]
        table = Table(table_data, colWidths=col_widths)
        style = TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), base_font_size),
            ("LEADING", (0, 0), (-1, -1), base_leading),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWPADDING", (0, 0), (-1, -1), row_padding),
            ("BOX", (0, 0), (-1, -1), 0.8, cls.COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, cls.COLOR_BORDER),
            ("BACKGROUND", (0, 0), (-1, 0), cls.COLOR_EMERALD_SOFT),
            ("TEXTCOLOR", (0, 0), (0, 0), cls.COLOR_EMERALD),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7.8 if compact else 10.2),
            ("BACKGROUND", (0, 1), (-1, 1), cls.COLOR_BLUE_SOFT),
            ("TEXTCOLOR", (0, 1), (0, 1), cls.COLOR_MUTED),
            ("FONTNAME", (1, 1), (2, 1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 2), (-1, 2), cls.COLOR_HEADER_SOFT),
            ("TEXTCOLOR", (0, 2), (-1, 2), colors.white),
            ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, 3), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 3), (0, -1), cls.COLOR_TEXT),
            ("TEXTCOLOR", (1, 0), (1, -1), cls.COLOR_BLUE),
            ("TEXTCOLOR", (2, 0), (2, -1), cls.COLOR_EMERALD),
        ])

        tone_map = {
            "negative": (cls.COLOR_RED_SOFT, cls.COLOR_RED),
            "positive": (cls.COLOR_EMERALD_SOFT, cls.COLOR_EMERALD),
            "warning": (cls.COLOR_AMBER_SOFT, cls.COLOR_AMBER),
            "primary": (cls.COLOR_BLUE_SOFT, cls.COLOR_BLUE),
            "total": (cls.COLOR_HEADER_SOFT, colors.white),
            "result": (colors.HexColor("#ECFDF5"), cls.COLOR_EMERALD),
        }

        row_index = 3
        for source_row in rows[3:]:
            tone = source_row[3] if len(source_row) > 3 else "default"
            if tone in tone_map:
                background, label_color = tone_map[tone]
                style.add("BACKGROUND", (0, row_index), (-1, row_index), background)
                style.add("TEXTCOLOR", (0, row_index), (0, row_index), label_color)
                if tone in {"total", "result"}:
                    style.add("FONTNAME", (0, row_index), (-1, row_index), "Helvetica-Bold")
                    style.add("FONTSIZE", (0, row_index), (-1, row_index), highlight_font_size)
            row_index += 1

        table.setStyle(style)
        return table


    @classmethod
    def render_mobile_pdf(cls, payload, *, output_path=None):
        """Renderiza uma versão vertical, compacta e legível em celulares."""
        buffer = BytesIO()
        page_w, page_h = cls.MOBILE_PAGE_SIZE
        margin = cls.MOBILE_MARGIN
        pdf = canvas.Canvas(buffer, pagesize=cls.MOBILE_PAGE_SIZE)
        pdf.setTitle(f"PDF Executivo Mobile - {payload['codigo']}")

        body_x = margin
        body_y = margin
        body_w = page_w - (margin * 2)

        pdf.setFillColor(cls.COLOR_BG)
        pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        header_h = 94
        header_y = page_h - margin - header_h
        cls._draw_rounded_card(pdf, body_x, header_y, body_w, header_h, fill_color=cls.COLOR_HEADER, stroke_color=cls.COLOR_HEADER, radius=18, stroke_width=0)

        title_width = body_w - 22
        title_lines = simpleSplit(payload["endereco"], "Helvetica-Bold", 18, title_width)[:2]
        title_style = ParagraphStyle(
            "executive_mobile_title",
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=20,
            textColor=colors.white,
        )
        title_paragraph = Paragraph("<br/>".join(title_lines), title_style)
        title_paragraph.wrapOn(pdf, title_width, 44)
        title_paragraph.drawOn(pdf, body_x + 12, header_y + 48)

        chip_y = header_y + 16
        status_fill, status_text = cls.status_theme(payload["status"])
        used = cls._draw_chip(pdf, body_x + 12, chip_y, payload["status"].upper(), status_fill, status_text, height=18, padding_x=8, font_size=7.6)
        cls._draw_chip(pdf, body_x + 20 + used, chip_y, payload["codigo"], colors.HexColor("#1E293B"), colors.white, border_color=colors.HexColor("#334155"), height=18, padding_x=8, font_size=7.6)
        pdf.setFont("Helvetica-Bold", 7.4)
        pdf.setFillColor(colors.HexColor("#CBD5E1"))
        pdf.drawRightString(body_x + body_w - 12, chip_y + 5.5, payload["cidade_uf"])

        content_y = header_y - 10
        photo_h = 150
        photo_y = content_y - photo_h
        cls._draw_image_cover(pdf, payload["foto_path"], body_x, photo_y, body_w, photo_h, radius=16)

        pdf.saveState()
        pdf.setFillColor(colors.Color(0, 0, 0, alpha=0.42))
        pdf.rect(body_x, photo_y, body_w, 28, fill=1, stroke=0)
        pdf.restoreState()
        pdf.setFont("Helvetica-Bold", 9.2)
        pdf.setFillColor(colors.white)
        pdf.drawString(body_x + 12, photo_y + 16.5, "Vista principal")
        pdf.setFont("Helvetica", 7)
        pdf.drawRightString(body_x + body_w - 12, photo_y + 16.5, "Registro fotografico")

        specs_y = photo_y - 58
        spec_gap = 6
        spec_w = (body_w - (spec_gap * 2)) / 3
        specs = [
            ("Tipo", payload["tipo"]),
            ("Area", payload["area_privativa"]),
            ("Ocupacao", payload["ocupacao"]),
        ]
        for index, (label, value) in enumerate(specs):
            box_x = body_x + (index * (spec_w + spec_gap))
            cls._draw_rounded_card(pdf, box_x, specs_y, spec_w, 48, fill_color=cls.COLOR_CARD, stroke_color=cls.COLOR_BORDER, radius=12)
            pdf.setFillColor(cls.COLOR_MUTED)
            pdf.setFont("Helvetica-Bold", 6.7)
            pdf.drawString(box_x + 8, specs_y + 32, cls.sanitize_text(label).upper())
            pdf.setFillColor(cls.COLOR_TEXT)
            value_text = cls.sanitize_text(value)
            font_size = 10.6
            value_lines = simpleSplit(value_text, "Helvetica-Bold", font_size, spec_w - 14)
            while len(value_lines) > 2 and font_size > 8:
                font_size -= 0.4
                value_lines = simpleSplit(value_text, "Helvetica-Bold", font_size, spec_w - 14)
            pdf.setFont("Helvetica-Bold", font_size)
            draw_y = specs_y + (18 if len(value_lines[:2]) > 1 else 16)
            for line in value_lines[:2]:
                pdf.drawString(box_x + 8, draw_y, line)
                draw_y -= font_size + 1

        leiloes = payload["leiloes"] or [{"tipo": "Sem pregoes", "data": "Sem dados", "valor": cls.format_currency(0)}]
        visible_leiloes = leiloes[:3]
        history_h = 92
        history_y = specs_y - history_h - 10
        cls._draw_rounded_card(pdf, body_x, history_y, body_w, history_h, fill_color=cls.COLOR_CARD, stroke_color=cls.COLOR_BORDER, radius=16)
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.setFillColor(cls.COLOR_TEXT)
        pdf.drawString(body_x + 12, history_y + history_h - 20, "Historico de Pregoes")
        row_top = history_y + history_h - 34
        for index, leilao in enumerate(visible_leiloes):
            row_y = row_top - 18 - (index * 19)
            cls._draw_rounded_card(pdf, body_x + 10, row_y, body_w - 20, 16, fill_color=cls.COLOR_GRAY_SOFT, stroke_color=cls.COLOR_BORDER, radius=7, stroke_width=0.4)
            pdf.setFont("Helvetica-Bold", 7.4)
            pdf.setFillColor(cls.COLOR_TEXT)
            pdf.drawString(body_x + 18, row_y + 5.3, cls.sanitize_text(leilao["tipo"]))
            pdf.setFont("Helvetica", 6.7)
            pdf.setFillColor(cls.COLOR_MUTED)
            pdf.drawString(body_x + 92, row_y + 5.3, cls.sanitize_text(leilao["data"]))
            pdf.setFont("Helvetica-Bold", 7.2)
            pdf.setFillColor(cls.COLOR_EMERALD)
            pdf.drawRightString(body_x + body_w - 18, row_y + 5.3, cls.sanitize_text(leilao["valor"]))

        analysis_y = margin + 24
        analysis_h = history_y - analysis_y - 10
        cls._draw_rounded_card(pdf, body_x, analysis_y, body_w, analysis_h, fill_color=cls.COLOR_CARD, stroke_color=cls.COLOR_BORDER, radius=16)
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.setFillColor(cls.COLOR_TEXT)
        pdf.drawString(body_x + 12, analysis_y + analysis_h - 19, "Analise do Negocio")
        pdf.setFont("Helvetica-Bold", 6.9)
        pdf.setFillColor(cls.COLOR_MUTED)
        pdf.drawRightString(body_x + body_w - 12, analysis_y + analysis_h - 18, "Normal x Rapida")

        table = cls._build_analysis_table(payload, body_w - 18, compact=True)
        _, table_h = table.wrap(body_w - 18, analysis_h - 42)
        table_y = max(analysis_y + 10, analysis_y + analysis_h - 34 - table_h)
        table.drawOn(pdf, body_x + 9, table_y)

        pdf.setFont("Helvetica-Bold", 6.8)
        pdf.setFillColor(cls.COLOR_MUTED)
        pdf.drawString(body_x + 2, margin + 5, "GanduInvest | PDF Executivo Mobile")
        pdf.drawRightString(body_x + body_w - 2, margin + 5, f"ID: {cls.sanitize_text(payload['report_id'])}")

        pdf.showPage()
        pdf.save()

        pdf_bytes = buffer.getvalue()
        buffer.close()

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as handler:
                handler.write(pdf_bytes)

        return pdf_bytes

    @classmethod
    def render_pdf(cls, payload, *, output_path=None):
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=cls.PAGE_SIZE)
        pdf.setTitle(f"PDF Executivo - {payload['codigo']}")

        page_w, page_h = cls.PAGE_WIDTH, cls.PAGE_HEIGHT
        margin = cls.PAGE_MARGIN
        body_x = margin
        body_y = margin
        body_w = page_w - (margin * 2)
        body_h = page_h - (margin * 2)

        pdf.setFillColor(cls.COLOR_BG)
        pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        header_h = 76
        header_y = page_h - margin - header_h
        cls._draw_rounded_card(pdf, body_x, header_y, body_w, header_h, fill_color=cls.COLOR_HEADER, stroke_color=cls.COLOR_HEADER, radius=22, stroke_width=0)

        address_width = body_w - 250
        title_lines = simpleSplit(payload["endereco"], "Helvetica-Bold", 23, address_width)
        title_lines = title_lines[:2]
        title_paragraph = Paragraph("<br/>".join(title_lines), cls.TITLE_STYLE)
        title_paragraph.wrapOn(pdf, address_width, header_h - 16)
        title_paragraph.drawOn(pdf, body_x + 18, header_y + 23)

        chips_y = header_y + 18
        chip_x = body_x + body_w - 225
        status_fill, status_text = cls.status_theme(payload["status"])
        used = cls._draw_chip(pdf, chip_x, chips_y + 28, payload["status"].upper(), status_fill, status_text, height=18, padding_x=9, font_size=8.2)
        cls._draw_chip(pdf, chip_x + used + 8, chips_y + 28, payload["codigo"], colors.HexColor("#1E293B"), colors.white, border_color=colors.HexColor("#334155"), height=18, padding_x=9, font_size=8.2)
        cls._draw_chip(pdf, chip_x, chips_y + 4, payload["cidade_uf"], cls.COLOR_BLUE_SOFT, cls.COLOR_BLUE, border_color=cls.COLOR_BLUE_SOFT, height=18, padding_x=9, font_size=8.2)
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.setFillColor(colors.HexColor("#CBD5E1"))
        pdf.drawRightString(body_x + body_w - 18, header_y + 14, f"Gerado em {payload['gerado_em']}")

        footer_h = 18
        content_top = header_y - 12
        content_bottom = body_y + footer_h + 8
        content_h = content_top - content_bottom
        gutter = 14
        left_w = 300
        right_w = body_w - left_w - gutter
        left_x = body_x
        right_x = left_x + left_w + gutter

        photo_h = 246
        photo_y = content_top - photo_h
        cls._draw_image_cover(pdf, payload["foto_path"], left_x, photo_y, left_w, photo_h, radius=18)

        overlay_h = 34
        pdf.saveState()
        pdf.setFillColor(colors.Color(0, 0, 0, alpha=0.38))
        overlay_path = pdf.beginPath()
        overlay_path.roundRect(left_x, photo_y, left_w, overlay_h, 18)
        pdf.clipPath(overlay_path, stroke=0, fill=0)
        pdf.rect(left_x, photo_y, left_w, overlay_h, fill=1, stroke=0)
        pdf.restoreState()
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.setFillColor(colors.white)
        pdf.drawString(left_x + 14, photo_y + 21, "Vista principal")
        pdf.setFont("Helvetica", 7.8)
        pdf.drawString(left_x + 14, photo_y + 9, "Registro fotográfico")

        specs_y = photo_y - 86
        spec_gap = 8
        spec_w = (left_w - (spec_gap * 2)) / 3
        specs = [
            ("Tipo", payload["tipo"]),
            ("Área Privativa", payload["area_privativa"]),
            ("Ocupação", payload["ocupacao"]),
        ]
        for index, (label, value) in enumerate(specs):
            box_x = left_x + (index * (spec_w + spec_gap))
            cls._draw_rounded_card(pdf, box_x, specs_y, spec_w, 72, fill_color=cls.COLOR_CARD, stroke_color=cls.COLOR_BORDER, radius=16)
            pdf.setFillColor(cls.COLOR_MUTED)
            pdf.setFont("Helvetica-Bold", 8.2)
            pdf.drawString(box_x + 12, specs_y + 51, cls.sanitize_text(label).upper())
            pdf.setFillColor(cls.COLOR_TEXT)
            value_text = cls.sanitize_text(value)
            font_size = 15.5
            value_lines = simpleSplit(value_text, "Helvetica-Bold", font_size, spec_w - 22)
            max_line_width = max((stringWidth(line, "Helvetica-Bold", font_size) for line in value_lines), default=0)
            while (len(value_lines) > 2 or max_line_width > (spec_w - 24)) and font_size > 11.0:
                font_size -= 0.5
                value_lines = simpleSplit(value_text, "Helvetica-Bold", font_size, spec_w - 22)
                max_line_width = max((stringWidth(line, "Helvetica-Bold", font_size) for line in value_lines), default=0)
            pdf.setFont("Helvetica-Bold", font_size)
            draw_y = specs_y + (30 if len(value_lines[:2]) > 1 else 27)
            for line in value_lines[:2]:
                pdf.drawString(box_x + 12, draw_y, line)
                draw_y -= (font_size + 1)

        leiloes = payload["leiloes"] or [{"tipo": "Sem pregões", "data": "Sem dados", "valor": cls.format_currency(0)}]
        visible_leiloes = leiloes[:3]
        history_title_block_h = 36
        history_row_h = 24
        history_row_gap = 6
        history_inner_padding = 14
        history_h = history_title_block_h + (history_inner_padding * 2) + (len(visible_leiloes) * history_row_h) + (max(0, len(visible_leiloes) - 1) * history_row_gap)
        history_y = content_top - history_h
        cls._draw_rounded_card(pdf, right_x, history_y, right_w, history_h, fill_color=cls.COLOR_CARD, stroke_color=cls.COLOR_BORDER, radius=18)
        pdf.setFillColor(cls.COLOR_TEXT)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(right_x + 16, history_y + history_h - 23, "Histórico de Pregões")

        history_inner_x = right_x + 16
        history_inner_w = right_w - 32
        history_rows_top = history_y + history_h - history_title_block_h - history_inner_padding
        for index, leilao in enumerate(visible_leiloes):
            row_y = history_rows_top - history_row_h - (index * (history_row_h + history_row_gap))
            cls._draw_rounded_card(pdf, history_inner_x, row_y, history_inner_w, history_row_h, fill_color=cls.COLOR_GRAY_SOFT, stroke_color=cls.COLOR_BORDER, radius=10, stroke_width=0.6)
            pdf.setFont("Helvetica-Bold", 8.8)
            pdf.setFillColor(cls.COLOR_TEXT)
            pdf.drawString(history_inner_x + 10, row_y + 14.2, cls.sanitize_text(leilao["tipo"]))
            pdf.setFont("Helvetica", 7.8)
            pdf.setFillColor(cls.COLOR_MUTED)
            pdf.drawString(history_inner_x + 120, row_y + 14.2, cls.sanitize_text(leilao["data"]))
            pdf.setFont("Helvetica-Bold", 8.8)
            pdf.setFillColor(cls.COLOR_EMERALD)
            pdf.drawRightString(history_inner_x + history_inner_w - 10, row_y + 14.2, cls.sanitize_text(leilao["valor"]))

        analysis_y = content_bottom
        analysis_h = history_y - analysis_y - 12
        cls._draw_rounded_card(pdf, right_x, analysis_y, right_w, analysis_h, fill_color=cls.COLOR_CARD, stroke_color=cls.COLOR_BORDER, radius=18)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.setFillColor(cls.COLOR_TEXT)
        pdf.drawString(right_x + 16, analysis_y + analysis_h - 22, "Análise do Negócio")
        pdf.setFont("Helvetica-Bold", 8.3)
        pdf.setFillColor(cls.COLOR_MUTED)
        pdf.drawRightString(right_x + right_w - 16, analysis_y + analysis_h - 22, "Venda Normal x Venda Rápida")

        analysis_table = cls._build_analysis_table(payload, right_w - 24)
        _, analysis_table_h = analysis_table.wrap(right_w - 24, analysis_h - 54)
        analysis_top_padding = 46
        analysis_bottom_padding = 12
        analysis_table_y = analysis_y + analysis_h - analysis_top_padding - analysis_table_h
        minimum_y = analysis_y + analysis_bottom_padding
        if analysis_table_y < minimum_y:
            analysis_table_y = minimum_y
        analysis_table.drawOn(pdf, right_x + 12, analysis_table_y)

        footer_y = body_y + 1
        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColor(cls.COLOR_MUTED)
        pdf.drawString(body_x + 2, footer_y + 5, "GanduInvest | PDF Executivo")
        pdf.drawRightString(body_x + body_w - 2, footer_y + 5, f"ID do relatório: {cls.sanitize_text(payload['report_id'])}")

        pdf.showPage()
        pdf.save()

        pdf_bytes = buffer.getvalue()
        buffer.close()

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as handler:
                handler.write(pdf_bytes)

        return pdf_bytes

    @classmethod
    def generate_for_imovel(cls, session, *, imovel_id, company_id, root_path, upload_root, output_root=None, layout="desktop"):
        imovel = session.query(Imovel).filter(
            Imovel.id == imovel_id,
            Imovel.company_id == company_id,
        ).first()

        if not imovel:
            raise ValueError("Imóvel não encontrado para o company_id informado.")

        payload = cls.build_report_payload(imovel, root_path=root_path, upload_root=upload_root)
        normalized_layout = (layout or "desktop").strip().lower()
        if normalized_layout not in {"desktop", "mobile"}:
            normalized_layout = "desktop"

        suffix = "mobile" if normalized_layout == "mobile" else "desktop"
        filename = f"pdf-executivo-{suffix}-{cls._slugify_filename(payload['codigo'])}.pdf"
        output_path = os.path.join(output_root, filename) if output_root else None
        renderer = cls.render_mobile_pdf if normalized_layout == "mobile" else cls.render_pdf
        pdf_bytes = renderer(payload, output_path=output_path)
        return filename, pdf_bytes, payload, output_path
