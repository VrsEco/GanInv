"""
Auto-migração idempotente: garante que colunas/tabelas esperadas pelos modelos
existam no banco. Usa ALTER TABLE ... ADD COLUMN IF NOT EXISTS do PostgreSQL.
"""
import os
from sqlalchemy import create_engine, text


EXPECTED_COLUMNS = {
    "leiloes": [
        ("leiloeiro", "VARCHAR(100)"),
    ],
    "fichas_financeiras": [
        ("valor_arrematacao", "FLOAT DEFAULT 0"),
        ("comissao_leiloeiro_percent", "FLOAT DEFAULT 5"),
        ("outros_custos_arrematacao", "FLOAT DEFAULT 0"),
        ("itiv_percent", "FLOAT DEFAULT 0"),
        ("itiv_vlr", "FLOAT DEFAULT 0"),
        ("registro_cartorio_percent", "FLOAT DEFAULT 0"),
        ("registro_cartorio", "FLOAT DEFAULT 0"),
        ("desocupacao", "FLOAT DEFAULT 0"),
        ("reforma_prevista", "FLOAT DEFAULT 0"),
        ("iptu_atrasado", "FLOAT DEFAULT 0"),
        ("iptu_futuro", "FLOAT DEFAULT 0"),
        ("condominio_atrasado", "FLOAT DEFAULT 0"),
        ("condominio_futuro", "FLOAT DEFAULT 0"),
        ("honorarios_advogado", "FLOAT DEFAULT 0"),
        ("valor_venda_projetado", "FLOAT DEFAULT 0"),
        ("comissao_corretor_percent", "FLOAT DEFAULT 5"),
        ("comissao_corretor_vlr", "FLOAT DEFAULT 0"),
        ("impostos_venda_percent", "FLOAT DEFAULT 0"),
        ("impostos_venda_vlr", "FLOAT DEFAULT 0"),
        ("despesas_operacionais", "FLOAT DEFAULT 0"),
        ("contingencia", "FLOAT DEFAULT 0"),
        ("desocupacao_obs", "TEXT"),
        ("reforma_obs", "TEXT"),
        ("limpeza", "FLOAT DEFAULT 0"),
        ("limpeza_obs", "TEXT"),
        ("iptu_atrasado_ate", "VARCHAR(7)"),
        ("iptu_atrasado_obs", "TEXT"),
        ("iptu_futuro_meses", "INTEGER DEFAULT 0"),
        ("condo_atrasado_ate", "VARCHAR(7)"),
        ("condo_atrasado_obs", "TEXT"),
        ("condo_futuro_meses", "INTEGER DEFAULT 0"),
        ("contingencia_obs", "TEXT"),
        ("custo_capital_meses", "INTEGER DEFAULT 0"),
        ("custo_capital_percent", "FLOAT DEFAULT 0"),
        ("lucro_minimo_percent", "FLOAT DEFAULT 0"),
        ("lucro_minimo_vlr", "FLOAT DEFAULT 0"),
    ],
    "imoveis": [
        ("descartado", "BOOLEAN DEFAULT FALSE"),
        ("motivo_descarte", "VARCHAR(100)"),
        ("data_descarte", "TIMESTAMP"),
        ("obs_descarte", "TEXT"),
        ("triagem_status", "VARCHAR(20) DEFAULT 'Pendente'"),
        ("triagem_motivo_codigo", "VARCHAR(50)"),
        ("triagem_motivo_label", "VARCHAR(120)"),
        ("triagem_observacao", "TEXT"),
        ("triagem_decidido_em", "TIMESTAMP"),
        ("triagem_decidido_por", "VARCHAR(255)"),
        ("valor_condominio", "FLOAT DEFAULT 0"),
        ("idade_predio", "INTEGER"),
        ("descritivo_predio", "TEXT"),
        ("descritivo_imovel", "TEXT"),
        ("valor_m2_regiao", "FLOAT DEFAULT 0"),
        ("contato_morador", "BOOLEAN DEFAULT FALSE"),
        ("relato_morador", "TEXT"),
        ("contato_sindico", "BOOLEAN DEFAULT FALSE"),
        ("relato_sindico", "TEXT"),
        ("outros_debitos", "FLOAT DEFAULT 0"),
        ("observacoes_internas", "TEXT"),
        ("valor_venda_normal", "FLOAT"),
        ("data_disponibilizacao", "TIMESTAMP"),
        ("data_venda", "TIMESTAMP"),
    ],
    "anexos": [
        ("company_id", "INTEGER"),
        ("nome_original", "VARCHAR(255)"),
        ("nome_arquivo", "VARCHAR(255)"),
        ("storage_path", "VARCHAR(1024)"),
        ("mime_type", "VARCHAR(255)"),
        ("tamanho_bytes", "INTEGER DEFAULT 0"),
        ("updated_at", "TIMESTAMP"),
    ],
}


def sync_schema():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return
    engine = create_engine(db_url)
    with engine.begin() as conn:
        for table, cols in EXPECTED_COLUMNS.items():
            for col, coltype in cols:
                conn.execute(text(
                    f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}'
                ))

        conn.execute(text("""
            UPDATE anexos AS a
               SET company_id = i.company_id
              FROM imoveis AS i
             WHERE a.imovel_id = i.id
               AND a.company_id IS NULL
        """))
