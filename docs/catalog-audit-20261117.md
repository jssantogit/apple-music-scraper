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

## Riscos e lacunas ainda abertas

- **Acesso não oficial:** `apple_music/fetch.py` usa token do player web e APIs não documentadas para integração de terceiros. Endpoints e credenciais podem mudar; licença MIT do scraper não concede direitos sobre dados/serviço da Apple.
- **Sem teste real de paridade:** falta comparar recursos e campos com a Apple Music API oficial e o app web, por storefront (ao menos BR e US), tipo de recurso e ausências.
- **Sem benchmark representativo:** não medimos latência p50/p95, carga, uso de banda, cache hit, limites de taxa ou comportamento sob 403/429 reais.
- **Validação de conteúdo:** investigar ordenação e paginação dos dois tipos de curadores, playlists longas, variantes clean/explicit, paginação de views de artistas, resolução de imagens e campos ausentes.
- **Falhas de upstream:** proteger a UI de dados parciais sem evidência; não marcar como completo um catálogo não verificado apenas porque chegou HTTP 200.
- **Antes da integração Android:** isolar provedor por capacidade, cancelamento/timeout, cache e proveniência; nenhuma alteração na interface da PR #212 ou no motor da PR #219 nesta fase.

## Próxima validação em campo (ainda não feita)

Montar fixtures datadas e privadas de dados públicos para: artista com vários EPs, álbum multi-disco e mais de 100 faixas, playlist longa, faixa com ISRC duplicado entre edições e resultados regionais BR/US; confrontar simultaneamente o mesmo ID na API oficial, quando o acesso for permitido. Registrar campo presente/ausente, diferenças de conteúdo e timestamps. Só então decidir portar o scraper para Kotlin ou executar como serviço pessoal.
