# Mesa de trabalho de catálogo — 51 endpoints

## Objetivo

Executar verificações independentes, reproduzíveis e progressivamente variáveis para os 51 endpoints HTTP de catálogo do Apple Music Scraper. Não confundir compatibilidade do contrato, presença de conteúdo, permissão de acesso, integridade da informação e desempenho: são verificações diferentes. A API do player web não é um contrato oficial documentado para terceiros.

## Camadas e gatilhos

1. **Gate offline** — `Catalog unit tests`. Em cada push/PR, Python 3.11 e 3.12; regressões de transporte/paginação/metadados, esquemas Marshmallow, rotas com e sem prefixo `/apple-music`, parâmetros desconhecidos e parâmetros obrigatórios ausentes. Nenhum acesso à Apple. Um novo endpoint sem contrato registrado quebra o teste.
2. **Mesa ao vivo** — `Catalog workbench - all 51 endpoints`. Em PRs que alteram a própria bancada, percorre **51 rotas em dois storefronts** (perfil `deep`, total 102 casos). Agendada uma vez por semana (quarta-feira, 06:17 UTC, perfil `standard`, 51 casos e um storefront). Executável manualmente pelo GitHub Actions com inputs customizados de perfil, países, consulta, seed e modo estrito. **Agendamento e despacho manual só ficam disponíveis quando o workflow estiver na branch padrão**, isto é, depois do merge desta PR.
3. **Sondagem pontual** — `scripts/catalog_live_probe.py`, específica para um artista e os storefronts BR/US, não substitui a mesa de 51 endpoints.

Nenhum caso é pulado silenciosamente: um ID necessário não localizado produz `BLOCKED` e falha a rodada. Uma resposta HTTP não 200, JSON incorreto, campos obrigatórios ausentes, número de página inconsistente ou ID divergente produz `FAIL`. Um array válido mas vazio produz `WARN`; a rodada pode ser marcada FAIL também nesses casos com `strict_empty=true`. Um `PASS` indica somente que aquele caso foi respondido e passou os invariantes verificados.

## Rotação e edição dos casos

O arquivo `scripts/catalog_bench_cases.json` contém:
- `portfolios`: perfis musicais (Brasil, eletrônico, pop, rock, jazz, hip-hop, clássico, k-pop etc.), cada um com termo de busca. A seleção muda automaticamente conforme o número da execução do workflow. Editar/adicionar perfis muda as amostras sem modificar as funções de teste.
- `search_cases`: consultas próprias de categorias menos relacionadas ao artista, como estações, curadores e gravadoras; evita falsos vazios ao procurar um cantor em uma categoria editorial.
- `fallback_ids`: alguns IDs públicos documentados para catálogos com pesquisa escassa; a preferência é sempre descobrir IDs novos no storefront testado. Nunca inventar IDs ou tomar o fallback como verdade sem testar.
- Países padrão: BR, US, GB, JP, IN e FR, com rotação por seed. O perfil `standard` escolhe um país; o `deep` escolhe dois. O operador pode especificar outros países no despacho manual.

**Reprodução:** seed e parâmetros de perfil são registrados no relatório, junto com os IDs públicos selecionados, sua origem e o resultado de cada rota. A consulta ao catálogo é mutável: repetir o mesmo seed reproduz a seleção do portfólio, não congela o estado upstream. Use o relatório datado para uma comparação exata de IDs.

Para testar manualmente via Python, após instalar os requisitos:

    python -m scripts.catalog_bench --seed 8 --profile deep --storefronts br,us --query "Caetano Veloso" --output catalog-bench-report.json

Para ampliar a investigação para seções vazias, acrescente `--strict-empty`. O parâmetro `--delay` controla a pausa entre as chamadas (padrão de 0,4 s, workflow 0,5 s); não usar uma bancada de carga sem rate limit contra um serviço de terceiros.

## Como a mesa funciona

1. O script escolhe um perfil e os storefronts a partir do seed, sem dados pessoais e sem necessitar login Apple.
2. Consulta a busca geral e recursos de apoio para encontrar IDs reais de música, álbum, artista, playlist, videoclipe, estação, gravadora e curador. Para gênero, só escolhe um ID após confirmar que existe uma página editorial associada. Descobre também IDs de seções Browse, cidades e rankings por região.
3. Constrói parâmetros tipados por endpoint, checando o esquema antes de executar. O catálogo de casos inclui variantes de tipo de discografia, tipo de playlist de artista, tipo de lançamentos de gravadora, ranking geral/por gênero, ordenação e limites de página.
4. Invoca o aplicativo real Bottle via WSGI em memória (sem abrir uma porta HTTP), incluindo roteamento, validação Marshmallow, lógica de transformação, transporte para Apple e serialização. Verifica código HTTP e propriedades básicas de JSON, identidade, coleções e paginação.
5. Registra por endpoint: país, status PASS/WARN/FAIL/BLOCKED, código HTTP, latência, contagem observada, parâmetros públicos do caso e diagnóstico sintético. A saída não contém payload bruto, token, cookie, letra completa ou áudio integral.
6. Publica uma tabela no GitHub Step Summary e faz upload de `catalog-bench-report.json` como artefato por 30 dias, inclusive quando ocorre falha. O exit code vermelho só corresponde à verificação real, nunca a um resultado artificialmente recuperado.

## Interpretação e diagnóstico

- **PASS**: rota retornou HTTP 200, contrato estrutural válido e lista amostrada com conteúdo (quando aplicável).
- **WARN**: o endpoint funcionou estruturalmente, mas a categoria monitorada está vazia. Pode ser seleção de entidade/país, conteúdo temporário ausente ou problema semântico; investigação opcionalmente estrita.
- **FAIL**: HTTP 4xx/5xx na amostra escolhida, identidade equivocada, campos críticos ausentes, paginação malformada ou exceção. Não agrupar automaticamente um 404 regional com bug de código: auditar o caso e a origem do ID.
- **BLOCKED**: descoberta não encontrou fixture válida ou entrada planejada não passa no próprio esquema; não equivale a sucesso nem a falha comprovada da API.
- **Mudança de conteúdo não é necessariamente regressão**: playlists e rankings mudam; não fixar nomes, posições ou quantidade exata como assertions gerais. Em vez disso, verificar invariantes estáveis e registrar diferenças.

## Checkpoints observados em 17/11/2026

- [CI #44102475981](https://github.com/jssantogit/apple-music-scraper/actions/runs/44102475981): 51/51 rotas US testadas ao vivo; 46 PASS, 5 WARN, nenhum FAIL.
- [CI #44103129450](https://github.com/jssantogit/apple-music-scraper/actions/runs/44103129450): 51/51 rotas IN; um 404 para detalhes editoriais de gênero listado; a execução ficou corretamente vermelha. Melhoramos seleção da fixture, sem simplesmente converter 404 em verde.
- [CI #44103658629](https://github.com/jssantogit/apple-music-scraper/actions/runs/44103658629): 51/51 rotas US, 46 PASS, 5 WARN, 0 FAIL com seleção de gênero editorial verificada e identificação dos IDs públicos usados.

**Limite:** não prova completude dos 51 endpoints para todos os dados existentes, paridade campo a campo com a API oficial, qualidade visual real de imagens ou estabilidade prolongada do mecanismo de token. Testes com perfis e mercados diferentes aumentam a confiança e ajudam a encontrar casos de borda, mas não substituem auditoria do conteúdo real.
