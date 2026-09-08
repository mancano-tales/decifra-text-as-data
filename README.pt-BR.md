<!-- 🇧🇷 Português — [🇺🇸 English version](README.md) -->

# decifra-text-as-data — Decifra

O **Decifra** é uma ferramenta local-first para transformar texto não estruturado (notícias, declarações políticas, relatórios de segurança pública) em dados categóricos usando um LLM orientado por um **codebook** explícito que você define — com uma etapa de validação contra rótulos codificados por humanos, porque LLMs não seguem a operacionalização específica de um codebook com fidelidade perfeita.

Não é uma ferramenta de codificação qualitativa manual (veja [Taguette](https://www.taguette.org/), [QualCoder](https://github.com/ccbogel/QualCoder) ou [QualiLab](https://github.com/LuizPF42/QualiLab) para isso). Você define um codebook, aponta para um corpus, e o Decifra chama o LLM sobre cada documento e preenche a tabela de output automaticamente.

**Status:** MVP funcional de variável única para um piloto acompanhado. A interface tem quatro abas (Corpus, Codebook, Execuções e Configurações); resultados e validação ficam dentro de Execuções. Estão implementados upload de documentos, estimativa aproximada de tokens, configuração persistente do provedor, consulta de evidências e servidor local único. Ainda não há instalador. Veja o [roteiro de teste](docs/MVP_TEST_GUIDE.md).

Destinado a pesquisadores, analistas de organizações, jornalistas de dados e ONGs que precisam classificar textos com regras explícitas e resultados verificáveis. O aplicativo e o banco são locais; ao usar um modelo remoto, o texto é enviado ao provedor escolhido.

Veja o [estado do MVP e as evidências da consolidação](docs/MVP_STATUS.md) para capacidades verificadas, pendências e limites dos testes.

---

## Por que o Decifra?

A classificação de texto por LLMs corre o risco de **violar a validade de construto**: o modelo aplica a *sua* operacionalização específica de um conceito, ou recai no conceito genérico aprendido durante o pré-treinamento (ex.: contando uma greve trabalhista como "protesto" mesmo quando o codebook exclui isso)? Ver Halterman & Keith, *"Codebook LLMs: Evaluating LLMs as Measurement Tools for Political Science Concepts"* (*Political Analysis*, 2025). O Decifra trata a validação do output do LLM contra codificação humana como uma etapa central do pipeline, não um detalhe secundário.

---

## O que está construído

- **Motor de codebook** (`text_as_data.codebook`): carrega um conceito e suas categorias (definições, exemplos positivos/negativos, notas de limite) de um arquivo YAML e deriva um schema Pydantic e um system prompt em tempo de execução.
- **Dois modos de provedor de LLM** (`text_as_data.providers`):
  - **Modo API-key**: output estruturado via `instructor` sobre os SDKs da Anthropic ou OpenAI — o caminho confiável.
  - **Modo CLI**: chama um CLI já instalado e autenticado (`claude -p`, `agy -p` ou similar) em vez de uma chave de API avulsa. Best-effort — o schema é solicitado no prompt e a resposta JSON é extraída com retentativa em caso de output malformado.
- **Backend FastAPI + SQLite** (`text_as_data.app`, `text_as_data.db`): faz cache de extração por (documento, hash do codebook, modelo) para não repetir chamadas de documentos já codificados; retenta um documento com falha até 3 vezes e registra o erro em vez de travar a run. Cada extração guarda o prompt e a resposta: stdout completo no modo CLI e JSON já interpretado no modo API (não a resposta completa original da API).
- **Validação** (`text_as_data.validation`): `agreement_report()` calcula acurácia e kappa de Cohen gerais, além de precisão, recall e F1 por categoria contra um conjunto gold codificado por humanos, e retorna a lista de discordâncias para inspeção manual.
- **Frontend** (`frontend/`, Vite + React + TypeScript): cinco etapas mais Configurações — Corpus (colar texto ou importar CSV/XLSX/TXT/Markdown/DOCX/PDF textual), Codebook (formulário estruturado + preview YAML), Runs (iniciar uma run, acompanhar progresso), Results (navegar, filtrar e editar resultados, exportar CSV/XLSX/JSON) e Validation (importar rótulos gold, ver métricas de concordância e discordâncias). Bilíngue PT-BR/EN.
- **Importações adicionais pelo backend**: importação de corpus/rótulos e exportação de resultados QualiLab continuam somente pela API. Documentos agora têm formulário na interface (sem OCR).
- **Configurações e estimativas**: chaves API no cofre do sistema, padrões de execução persistentes, contagem aproximada de tokens do prompt/esquema, cache, preços USD opcionais informados pelo usuário e uso de tokens reportado pelo SDK quando disponível. A estimativa não inclui possíveis custos de retentativas.
- **Evidência e repetibilidade**: a verificação da citação no texto é persistida nos resultados/exportações. `GET /runs/{id}/reproducibility?compare_to={id}` compara execuções; crie a repetição com `bypass_cache: true`. A interface exibe citações e sua verificação, permite consultar prompt/resposta e oferece a opção de ignorar o cache. O relatório de comparação entre execuções continua somente pela API.
- **Disclosure** (`text_as_data.disclosure`): estrutura inicial de relatório de métodos pelo backend. Há textos desatualizados e leitura do codebook/checkout atuais; não é um relatório histórico completo de validação ou repetibilidade.

**Ainda não construído:** Codebooks com múltiplas variáveis (apenas desenho). Cancelamento/retomada e recuperação de execuções interrompidas. Controles de exclusão. Instalador empacotado. Processamento paralelo de documentos (hoje é um documento por vez). Alpha de Krippendorff ou AC1 de Gwet (só o kappa de Cohen existe). Integrações diretas de API além de Anthropic e OpenAI (Gemini já foi usado via CLI externo; sem integração nativa Gemini ou local/Ollama).

---

## Instalação (desenvolvimento)

```bash
python -m venv .venv
# Ative .venv/bin/activate no Unix ou .venv/Scripts/Activate.ps1 no PowerShell.
python -m pip install -e ".[dev]"
cd frontend && npm ci && cd ..
```

Você também vai precisar de uma chave salva em Configurações ou de `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` como variável de ambiente (para modo API-key), ou de um CLI já instalado e autenticado como `claude` ou `agy` (para modo CLI).

> **Nota (ambientes com múltiplos worktrees):** A instalação editável aponta para um checkout dentro do ambiente Python usado na instalação. Compartilhar esse ambiente entre worktrees altera silenciosamente o destino dos imports. Use uma `.venv` por worktree. Se você tiver múltiplos worktrees, rode a suíte como `PYTHONPATH=src pytest` para contornar o editable install. Veja [`docs/MULTI_AGENT_WORKTREES.md`](docs/MULTI_AGENT_WORKTREES.md) para detalhes.

---

## Executando o MVP

Após instalar, compile a interface uma vez e inicie um único servidor:

```bash
npm --prefix frontend run build
python scripts/build_frontend.py
decifra serve
```

O navegador abre em `http://127.0.0.1:8765`. O banco fica no diretório de dados do usuário do sistema. `--data-dir CAMINHO` seleciona outro diretório; bancos anteriores não são movidos automaticamente. No Windows, `powershell -File scripts/start_pilot.ps1` mantém dados/configurações isolados deste piloto em `data/pilot`. [Roteiro sugerido](docs/MVP_TEST_GUIDE.md).

## Executando (desenvolvimento)

Para desenvolver a interface com recarga automática, inicie o backend FastAPI e o Vite juntos. `scripts/dev.sh` (macOS/Linux/Git Bash) e `scripts/dev.ps1` (PowerShell nativo) fazem isso com um comando em vez de dois terminais:

```bash
scripts/dev.sh              # backend em :8000, frontend em :5173
scripts/dev.sh 8010 5183    # opcional: sobrescrever as portas
```

```powershell
powershell -File scripts/dev.ps1
powershell -File scripts/dev.ps1 -BackendPort 8010 -FrontendPort 5183
```

Depois abra `http://localhost:5173`. Ctrl+C encerra os dois processos.

---

## Quickstart (API Python)

### 1. Definir um codebook em YAML

```yaml
concept: protest
description: Um evento público coletivo expressando uma demanda política ou social.
categories:
  - label: protest
    definition: Uma ocupação, marcha ou greve com demanda política declarada.
    positive_examples:
      - "Cerca de 200 estudantes marcharam até a prefeitura exigindo passe livre."
    negative_examples:
      - "Pessoas se reuniram para um festival de música."
    boundary_notes: Não inclui desfiles puramente cerimoniais.
  - label: not_protest
    definition: Qualquer evento que não atenda aos critérios acima.
```

### 2. Carregar e rodar uma extração

```python
import instructor
import pandas as pd
from anthropic import Anthropic

from text_as_data import Codebook, extract

codebook = Codebook.from_yaml_file("codebook.yaml")
client = instructor.from_anthropic(Anthropic())
texts = pd.DataFrame({"id": [1], "text": ["Cerca de 200 pessoas ocuparam a praça..."]})

predicted = extract(texts, codebook, client, model="claude-sonnet-5")
```

`extract()` é um helper Python para scripts avulsos; o backend usa `run_extraction()` para o fluxo persistente. Use o backend se quiser cache, retentativa e suporte ao modo CLI.

### 3. Ou pelo backend

```bash
scripts/dev.sh   # em um terminal

curl -X POST http://localhost:8000/codebooks -H "Content-Type: application/json" -d '{
  "concept": "protest",
  "description": "Um evento público coletivo expressando uma demanda política ou social.",
  "categories": [
    {"label": "protest", "definition": "Uma ocupação, marcha ou greve com demanda política declarada."},
    {"label": "not_protest", "definition": "Qualquer evento que não atenda aos critérios acima."}
  ]
}'
curl -X POST http://localhost:8000/corpora/paste -H "Content-Type: application/json" \
  -d '{"name": "demo", "text": "Cerca de 200 pessoas ocuparam a praça..."}'
curl -X POST http://localhost:8000/runs -H "Content-Type: application/json" \
  -d '{"codebook_id": 1, "corpus_id": "demo", "model": "claude-sonnet-5"}'
curl http://localhost:8000/runs/1/results
```

---

## Testes

```bash
PYTHONPATH=src pytest
```

Executa a suíte de testes do backend cobrindo o motor de codebook, os dois modos de provedor, os modelos SQLite, os endpoints FastAPI, a importação de corpus, o interop QualiLab, as métricas de validação e o módulo de disclosure.

---

## Empacotamento (não iniciado)

O plano (ver `AGENTS.md` § "Product trajectory") é um app desktop empacotado — o backend Python compilado em um único binário, rodando localmente, para que instalar o Decifra seja "baixar e abrir" em vez de "clonar o repositório e iniciar dois servidores de desenvolvimento". Esse trabalho ainda não começou. O `AGENTS.md` condiciona isso à validação do pipeline com uso real primeiro.
