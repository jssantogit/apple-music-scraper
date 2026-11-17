# Apple Music Scraper — auditoria inicial de catálogo (2026-11-17)

> Escopo: inventário estático dos contratos existentes, primeiro hardening do motor e verificações offline. **Não** é uma certificação de cobertura do Apple Music ao vivo, de paridade com a API oficial ou de permissão de uso.

## Superfície HTTP — 51 endpoints

As rotas vêm de `routes.ENDPOINTS` e são registradas com os dois prefixos: `/rota` e `/apple-music/rota`. `GET /health` e `GET /` são adicionais e não contam como endpoints de catálogo.

| Grupo | Qtde. | Rotas |
| --- | ---: | --- |
| Músicas | 2 | `/songs/details`, `/songs/batch` |
| Pesquisa | 10 | `/search/auto-complete`, `/search/all`, `/search/songs`, `/search/albums`, `/search/artists`, `/search/playlists`, `/search/music-videos`, `/search/stations`, `/search/curators`, `/search/labels` |
| Álbuns | 2 | `/albums/details`, `/albums/related` |
| Artistas | 6 | `/artists/details`, `/artists/top-songs`, `/artists/albums`, `/artists/music-videos`, `/artists/playlists`, `/artists/similar` |
| Playlists | 2 | `/playlists/details`, `/playlists/tracks` |
| Videoclipes | 1 | `/music-videos/details` |
| Rankings | 8 | `/charts/top-songs`, `/charts/top-albums`, `/charts/top-playlists`, `/charts/top-music-videos`, `/charts/daily-top-100`, `/charts/daily-top-100-list`, `/charts/city-top-25`, `/charts/city-charts-list` |
| Editorial / Explorar | 10 | `/browse`, `/browse/section`, `/browse/new-releases`, `/browse/recent-releases`, `/browse/best-new-songs`, `/browse/trending-songs`, `/browse/coming-soon`, `/browse/updated-playlists`, `/browse/popular`, `/browse/dj-mixes` |
| Rádio | 1 | `/radio` |
| Estações | 2 | `/stations/live`, `/stations/details` |
| Gêneros | 2 | `/genres`, `/genres/details` |
| Gravadoras | 2 | `/labels/details`, `/labels/releases` |
| Curadores | 2 | `/curators/details`, `/curators/playlists` |
| Países | 1 | `/countries` |
| **Total** | **51** | Contratos montados; teste `tests/test_api_contract.py` |

## O que cada domínio pode fornecer ao BitChord

- **Catálogo / identidade editorial:** pesquisa e detalhes de músicas, artistas, álbuns e playlists. ISRC em músicas, UPC em álbuns e storefront do link devem ser preservados como evidência, não como identidade canônica universal.
- **Imagens:** capas, retratos e artes editoriais vêm como campos de recursos, sem endpoint de imagem independente. Validar dimensões e conteúdo real antes de cachear.
- **Popularidade:** rankings da Apple, Daily Top 100 e City Top 25. Não converter posição em contagem de reproduções nem misturar com sinais de ListenBrainz/Last.fm sem proveniência.
- **Descoberta / editorial:** seções Browse, rádio, gêneros, playlists e curadores. Uma seção ausente pode retornar lista vazia com nota; distinguir indisponibilidade regional de erro de transporte.
- **Reprodução:** apenas metadados e previews disponíveis no catálogo público. Não tratar `audio_traits` como acesso ao stream integral.
- **Letras / conta:** letras completas, biblioteca pessoal e recomendações autenticadas não são capacidades fornecidas pelo scraper anônimo.

## Achados técnicos e correções deste primeiro corte

1. **HTTP 200 com JSON incompleto:** `api_get` validava só o primeiro caractere, depois uma falha no decode escapava da política de retry. Agora um payload inválido é tratado como resposta de upstream não JSON, com retries e erro tipado.
2. **Paginação sem progresso:** `follow_all` aceitava um `next` repetido ou retornos vazios e podia repetir requisições indefinidamente. Agora interrompe paginação sem progresso.
3. **Overfetch:** `follow_all` sempre solicitava `max_per_call` mesmo faltando um único item para `max_items`. Agora usa o orçamento restante.
4. **Bind público não intencional:** `run.py` anunciava `localhost` mas ouvia em `0.0.0.0`. Agora a interface padrão é `127.0.0.1`; para uso explícito na LAN, configurar `HOST=0.0.0.0`.

Testes reproduziram falhas antes das correções (RED). CI executa `python -m pytest -q tests/` em Python 3.11 e 3.12. Não há calls reais à Apple nos testes atuais.

## Checkpoint 2026-11-17 — qualidade editorial e sondagem real BR/US

5. **Fuso horário em datas editoriais:** `parsers.iso_datetime` convertia o relógio local em `Z` sem aplicar o deslocamento, corrompendo até o dia da atualização. Agora horários com offset são convertidos para UTC; horários sem offset não são rotulados como UTC sem prova.
6. **Busca combinada com listas explicitamente nulas:** `search.search_all` somava `None` e `list` quando uma categoria de curadores estava vazia; agora preserva as demais seções e retorna lista vazia para curadores.
7. **Sondagem ao vivo opt-in:** `python -m scripts.catalog_live_probe --countries br us` usa a pesquisa por "Daft Punk" (padrão), observa uma amostra de artista, álbum e música e emite somente contagens e presença de campos. Os testes de integração com Apple **não são executados no workflow unitário**; `catalog-live-probe.yml` é somente manual após estar no branch padrão.

Provas de regressão: os 5 casos adicionais de normalização falharam primeiro no run [#44099952657](https://github.com/jssantogit/apple-music-scraper/actions/runs/44099952657), e passaram depois no [#44100047405](https://github.com/jssantogit/apple-music-scraper/actions/runs/44100047405).

### Observação real — 17/11/2026, 14:12 UTC

Sondagem limitada de metadados executada na [CI #44100505439](https://github.com/jssantogit/apple-music-scraper/actions/runs/44100505439), no corte `17fb15bd`; os 23 testes unitários também passaram no mesmo run.

| Presença/contagem observada nos primeiros shelves ou detalhe | BR | US |
| --- | ---: | ---: |
| Artista selecionado por pesquisa | 5468295 | 5468295 |
| Músicas populares na seção inicial | 10 | 10 |
| Álbuns na seção inicial | 7 | 8 |
| Singles e EPs na seção inicial | 8 | 10 |
| Artistas semelhantes na seção inicial | 10 | 10 |
| Álbum selecionado por pesquisa | 1440871397 | 1440871397 |
| Faixas retornadas no detalhe do álbum | 18 | 18 |
| Imagem do artista e capa do álbum (URL presente) | Sim | Sim |
| UPC do álbum | Sim | Sim |
| ISRC e preview da música pesquisada | Sim | Sim |
| ID da música selecionada por busca | 617154366 | 697195462 |

**Interpretação limitada:** os mesmos IDs de artista/álbum expuseram contagens diferentes nos shelves de discografia entre BR e US. Isso apoia preservar storefront e país na chave de cache editorial, **não** afirmar discografia total ou paridade funcional com a Apple Music API oficial. As músicas selecionadas por relevância são diferentes; não usar seus IDs como comparação da mesma gravação. Presença de URL de imagem não prova resolução final/qualidade; `audio_traits` e preview não significam acesso ao stream integral.

O sucesso de uma única sondagem rápida não valida latência p50/p95, estabilidade de token/serviço ou 51 endpoints ao vivo. Nenhum token/JSON bruto foi publicado nos logs.

## Riscos e lacunas ainda abertas

- **Acesso não oficial:** `apple_music/fetch.py` usa token do player web e APIs não documentadas para integração de terceiros. Endpoints e credenciais podem mudar; licença MIT do scraper não concede direitos sobre dados/serviço da Apple.
- **Sem teste real de paridade:** falta comparar recursos e campos com a Apple Music API oficial e o app web, por storefront (ao menos BR e US), tipo de recurso e ausências.
- **Sem benchmark representativo:** não medimos latência p50/p95, carga, uso de banda, cache hit, limites de taxa ou comportamento sob 403/429 reais.
- **Validação de conteúdo:** investigar ordenação e paginação dos dois tipos de curadores, playlists longas, variantes clean/explicit, paginação de views de artistas, resolução de imagens e campos ausentes.
- **Falhas de upstream:** proteger a UI de dados parciais sem evidência; não marcar como completo um catálogo não verificado apenas porque chegou HTTP 200.
- **Antes da integração Android:** isolar provedor por capacidade, cancelamento/timeout, cache e proveniência; nenhuma alteração na interface da PR #212 ou no motor da PR #219 nesta fase.

## Próxima validação em campo (ainda não feita)

Montar fixtures datadas e privadas de dados públicos para: artista com vários EPs, álbum multi-disco e mais de 100 faixas, playlist longa, faixa com ISRC duplicado entre edições e resultados regionais BR/US; confrontar simultaneamente o mesmo ID na API oficial, quando o acesso for permitido. Registrar campo presente/ausente, diferenças de conteúdo e timestamps. Só então decidir portar o scraper para Kotlin ou executar como serviço pessoal.

## Checkpoint de rigor — paginação e busca (17/11/2026)

- A bancada passou de 42 para **67 testes offline** Python 3.11/3.12 após introduzir contratos de cobertura por par país × endpoint, limite `per_page` exato, total de itens, validação do cursor `next`, verificação de segunda página no modo deep, identidade e sobreposição em coleções estáveis.
- O resultado do benchmark inclui `covered_cases`/`total_cases_expected`, `followup_executed`, `followup_not_applicable` e `followup_shortfall`. A execução deep não será verde sem ao menos uma segunda página verificada em cada país selecionado.
- Um erro de duplicação de músicas no segundo bloco do Search foi reproduzido em catálogo real na Índia com o termo `Yo-Yo Ma`: `offset=2/5/10` produziu IDs repetidos, enquanto a cadeia `next` fornecida pela Apple usava `offset=9/12/17` e não repetiu os IDs. A [sondagem #44109197819](https://github.com/jssantogit/apple-music-scraper/actions/runs/44109197819) verificou seis pares brutos. O motor de busca agora respeita o cursor fornecido pela Apple, sujeito a validação estrita de domínio, caminho e ciclo. A [reprodução de produção #44110428583](https://github.com/jssantogit/apple-music-scraper/actions/runs/44110428583) confirmou seis pares sem duplicação após o conserto.
- A busca de curadores combinava recursos `apple-curators` e `curators` usando cálculo simples de offset e limite por tipo, situação que pode perder itens ou exceder o limite do pedido. Ela agora pagina cada tipo de forma independente, materializa o intervalo lógico pedido e detecta continuidade no limite entre os dois conjuntos. Os testes de fronteira e casos nulos foram incluídos. A [CI offline #44111142572](https://github.com/jssantogit/apple-music-scraper/actions/runs/44111142572) aprovou 67 testes em Python 3.11 e 3.12; a [bancada real deep #44111142703](https://github.com/jssantogit/apple-music-scraper/actions/runs/44111142703) aprovou 102/102 pares em JP+IN, 14 segundas páginas reais, 0 FAIL, 7 WARN.
- Ações de GitHub para a bancada passam a disparar em **toda atualização de PR**, não só quando uma lista restrita de caminhos é alterada. `scripts/catalog_page_probe.py` e seu workflow especializado ficam disponíveis para diagnósticos de páginas sem registrar respostas completas ou tokens.
- **Pendências sem falsa aprovação:** os falsos vazios dos atalhos Browse em BR/FR foram corrigidos e validados no checkpoint editorial abaixo. Permanecem a cobertura de outros idiomas/storefronts, campos de qualidade de imagem, rankings, playlists extensas, latência p95 e paridade com API oficial. Não promover para produção nem integrar ao BitChord nesta PR.


## Checkpoint editorial — Browse regional (17/11/2026)

- **Causa observada:** a Apple entrega os títulos das seções Browse no idioma do storefront, mesmo com `lang=en-US`. Em [diagnóstico regional #44113932585](https://github.com/jssantogit/apple-music-scraper/actions/runs/44113932585), BR devolveu 17 salas com conteúdo e apenas um dos oito atalhos em inglês funcionava; FR também devolveu 17 salas com conteúdo e apenas um atalho resolvido; US apresentava 18 salas, oito atalhos resolvidos.
- Os títulos correspondentes foram identificados pela resposta real de cada storefront, como `Novidades da semana` e `Nouveautés de la semaine` para `new-releases`. Nenhum ID numérico de sala foi codificado como constante: `refs.BROWSE_LOCALIZED_TITLES` guarda apenas aliases semânticos de títulos verificados para BR/FR; `browse.resolve_browse_room_id` resolve o ID atual na própria resposta regional, com normalização de acentos/pontuação, correspondência inequívoca e comportamento seguro se não houver sala.
- `shared.browse_room_ids` agora indexa IDs de salas presentes no grouping mesmo quando a prateleira inicial não pré-carrega itens; a antiga indexação via `P.grouping_sections` excluía esses casos.
- **Validação direta:** [CI regional #44115080163](https://github.com/jssantogit/apple-music-scraper/actions/runs/44115080163) consultou os atalhos HTTP reais em BR, FR, US, JP e IN. Resultado: **39 retornaram salas corretas com conteúdo, 1 reportou ausência legítima (DJ mixes não listado em JP), 0 falhas**. Brasil e França passaram de 1/8 para **8/8 atalhos resolvidos e com conteúdo**. O teste exige coincidência de ID de sala entre a página de Browse e seu atalho e falha se uma sala com itens de prévia retornar lista vazia.
- **Bancada geral:** [CI #44115079692](https://github.com/jssantogit/apple-music-scraper/actions/runs/44115079692) passou com **102/102 pares endpoint×país**, 16 segundas páginas reais, 0 FAIL e 8 WARN em IN+FR, relacionados a gravadoras, rankings, gêneros e curadores — não mais a `browse/*`. [CI unitária #44115079659](https://github.com/jssantogit/apple-music-scraper/actions/runs/44115079659) aprovou **95 testes** em Python 3.11/3.12.
- **Limites:** aliases localizados documentam apenas os idiomas observados. Não se deve atribuir automaticamente a mercados novos um título de outro idioma, nem fabricar uma sala quando a Apple não a lista. Continuar rastreando ausências reais e casos não cobertos separadamente de regressões.

