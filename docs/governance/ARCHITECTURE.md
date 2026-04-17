# 🏗️ Arquitetura do Sistema: GanduInvest

O GanduInvest segue o padrão de arquitetura em camadas (Layered Architecture) para garantir separação de preocupações e testabilidade.

## 📁 Estrutura de Pastas

```text
/
├── app.py                   # Entry point (Flask App)
├── src/
│   ├── core/
│   │   ├── models/          # Layer 5: Tabelas PostgreSQL (SQLAlchemy)
│   │   ├── routes/          # Layer 2: Endpoints REST (Blueprints)
│   │   ├── services/        # Layer 3: Lógica de Negócio (ROI, Calculadora)
│   │   └── mcp_server.py    # Exposição de Tools para Agentes
│   └── intelligence/        # Layer 3.5: Fluxos LangGraph & RAG
├── static/                  # CSS (Tailwind), JS, Imagens
├── templates/               # Jinja2 Templates (HTML)
└── docs/
    └── governance/          # Documentação de Arquitetura e UI
```

## 🛡️ Camadas e Responsabilidades

### 1. Camada de Apresentação (Frontend)
- Utiliza **TailwindCSS** e **Jinja2**.
- Comunicação com backend via requisições fetch para rotas REST.
- Responsividade total (Desktop, Tablet, Mobile).

### 2. Camada de API (Blueprints)
- Responsável por receber dados, validar schemas (Pydantic) e rotear para o Service correspondente.
- **Regra:** Proibido código de lógica pesada ou acesso direto ao banco.

### 3. Camada de Serviço (Intelligence Body)
- Onde reside o "valor" do negócio. Cálculos financeiros, orquestração de leilões e mudanças de status.
- É a camada que pode ser exposta via Ferramentas MCP.

### 4. Camada de Inteligência (Brain)
- Automação de leitura de editais e extração de dados de links.
- Utiliza OpenAI + LangGraph.

### 5. Camada de Dados (PostgreSQL)
- Relacionamento 1:N entre Imóvel e Leilões.
- Multi-tenancy forçado via `company_id`.
