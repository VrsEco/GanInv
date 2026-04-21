class FinanceService:
    @staticmethod
    def calculate_full_sheet(f: dict):
        """
        Recebe um dicionário com os dados da FichaFinanceira e retorna os KPIs calculados.
        Baseado na planilha Gandu.
        """
        # 1. Fluxo de Venda
        venda_bruta = f.get('valor_venda_projetado', 0)
        comissao_vlr = venda_bruta * (f.get('comissao_corretor_percent', 0) / 100)
        venda_liquida_01 = venda_bruta - comissao_vlr
        impostos_vlr = venda_liquida_01 * (f.get('impostos_venda_percent', 0) / 100)
        venda_liquida_02 = venda_liquida_01 - impostos_vlr
        
        # 2. Custos de Aquisição e Operação
        lance = f.get('valor_arrematacao', 0)
        comissao_leiloeiro = lance * (f.get('comissao_leiloeiro_percent', 5) / 100)
        outros_custos_arrematacao = f.get('outros_custos_arrematacao', 0)
        
        # ITIV e Registro podem ser valor fixo ou percentual (prioriza valor fixo se existir)
        itiv = f.get('itiv_vlr', 0) or (lance * (f.get('itiv_percent', 0) / 100))
        registro = f.get('registro_cartorio', 0) or (lance * (f.get('registro_cartorio_percent', 0) / 100))
        
        custos_operacao = [
            comissao_leiloeiro,
            outros_custos_arrematacao,
            itiv,
            registro,
            f.get('iptu_atrasado', 0),
            f.get('condominio_atrasado', 0),
            f.get('condominio_futuro', 0),
            f.get('desocupacao', 0),
            f.get('reforma_prevista', 0),
            f.get('honorarios_advogado', 0),
            f.get('despesas_operacionais', 0),
            f.get('contingencia', 0)
        ]
        
        investimento_total = lance + sum([x or 0 for x in custos_operacao])
        
        # 3. KPIs
        lucro_bruto = venda_liquida_02 - investimento_total
        roi = (lucro_bruto / investimento_total * 100) if investimento_total > 0 else 0
        margem_venda = (lucro_bruto / venda_bruta * 100) if venda_bruta > 0 else 0
        
        return {
            "venda_bruta": venda_bruta,
            "comissao_vlr": comissao_vlr,
            "venda_liquida_01": venda_liquida_01,
            "impostos_vlr": impostos_vlr,
            "venda_liquida_02": venda_liquida_02,
            "investimento_total": investimento_total,
            "lucro_bruto": lucro_bruto,
            "roi": round(roi, 2),
            "margem_venda": round(margem_venda, 2),
            "custos_detalhe": {
                "lance": lance,
                "comissao_leiloeiro": comissao_leiloeiro,
                "outros_custos_arrematacao": outros_custos_arrematacao,
                "itiv": itiv,
                "registro": registro
            }
        }

    @staticmethod
    def calculate_max_bid(valor_venda_estimado, custos_adicionais, margem_lucro_desejada_percent=0.20):
        # ... (keep existing or update)
        pass
