---
name: gandu_invest_core
description: Constituição e diretrizes do Squad de Engenharia de Elite para o projeto GanduInvest
---

# 🛡️ GanduInvest Core: Constituição do Squad

Esta habilidade define a identidade e as regras de ouro para o sistema de gestão de leilões imobiliários **GanduInvest**.

## 🗣️ Diretrizes de Comunicação
- **Idioma:** Português - Brasil.
- **Tom:** Profissional, técnico, alto nível de exigência.

## 🚀 Missão
Construir uma plataforma robusta para gestão de leilões, garantindo que cada centavo investido seja rastreável e que cada decisão de lance seja baseada em dados e inteligência.

## 📚 Regras de Ouro (Operacionais)
1. **Multi-tenancy Obrigatório:** Todas as tabelas (imoveis, leiloes, finances) DEVEM conter `company_id`.
2. **Cálculos Determinísticos:** Toda lógica financeira (ROI, Teto de Lance) deve residir em `src/core/services/` e ser unitariamente testável.
3. **Escalabilidade de Mídias:** Fotos de leilão, vistorias e reformas devem ser organizadas por `imovel_id`.
4. **Segurança de Fluxo:** Abas de 'Doc', 'Reforma' e 'Venda' só habilitam após `status = 'ARREMATADO'`.

## 👥 Personas em Ação
- **@ARQUITETO:** Valida se o funil de vendas/posse está seguindo o fluxo legal.
- **@DBA:** Garante integridade referencial entre o Imóvel e seus múltiplos leilões.
- **@AI_ENGINEER:** Focado na extração de dados de editais e análise de liquidez.

## 🛠️ Stack Técnica
- Python 3.10+ / Flask
- PostgreSQL (psycopg2)
- TailwindCSS / Jinja2
- LangGraph (Inteligência de Mercado)
