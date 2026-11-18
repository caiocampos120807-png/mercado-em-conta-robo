# Mercado em Conta — atualização de coleta para até 6 redes (R$ 0)

## O que realmente existe nesta entrega

- Mantém **Pão de Açúcar e Sonda**, que já tinham ofertas coletadas no seu robô.
- Acrescenta um **coletor novo** (`integrar_redes.py`) com quatro redes candidatas: **Extra Mercado, Carrefour, Atacadão e Mambo**.
- O **Extra Mercado** começa com URLs verificadas de arroz Camil 5 kg, feijão Camil 1 kg, leite Parmalat 1 L e café Pilão 500 g, além de páginas de categoria. O **Carrefour** começa com produtos e categorias verificadas de arroz, feijão, leite, bebidas e hortifruti.
- O **Atacadão** exige loja/CEP em várias páginas: seu conector **não publica preços sem local definido**. O **Mambo** pode mostrar itens indisponíveis: essas ofertas são ignoradas.
- O robô procura páginas de produto, JSON-LD com ofertas BRL e cartões de listagem com preço explícito. Só insere um valor quando a marca, embalagem, preço e link foram identificados.
- Tudo é **incremental**: até 12 listagens e até 65 páginas individuais por execução no coletor adicional, com intervalo mínimo de 4 segundos por domínio. A descoberta guarda até 6 mil links por nova rede. Limites editáveis em `redes-fontes.json` sem necessidade de assinatura. Não aumente a frequência se um site bloquear.
- Os arquivos `catalogo_redes.json` e `redes-status.json` são criados automaticamente no primeiro teste. O `redes-status.json` mostra separadamente **redes configuradas** e **redes com preços confirmados**.
- Mantém `precos.csv` do robô antigo e incorpora as novas ofertas, sem apagar registros existentes que ainda estejam dentro da validade.
- Atualiza `gerar_indicadores.py` para aceitar os novos domínios no histórico e no painel de qualidade.
- Atualização opcional do site inclui quadro **“Outras redes: resultado real da coleta”** na aba **Dados**.

**Este pacote NÃO contém ofertas fictícias e NÃO contém valores reais pré-coletados das novas redes.** Os testes são locais e simulam HTML público; a primeira coleta real será executada na sua conta GitHub. Ter 6 conectores não significa ter preços de 6 supermercados. Pode haver 0 preços novos se os sites bloquearem ou omitirem informações.

## PASSO A — Atualizar o robô no GitHub

1. Baixe `mercado-em-conta-robo-6-redes-upgrade.zip` e abra (descompacte) no Mac.
2. Abra https://github.com/caiocampos120807-png/mercado-em-conta-robo e clique em **Code → Add file → Upload files**.
3. Da pasta extraída, envie `integrar_redes.py`, `redes-fontes.json`, `gerar_indicadores.py` e `tests/test_integrar_redes.py` (o arquivo de teste dentro da pasta `tests`). Clique em **Commit changes**. Se o GitHub reclamar de arquivos iguais, substitua os existentes; **não** apague o CSV atual.
4. Abra https://github.com/caiocampos120807-png/mercado-em-conta-robo/blob/main/.github/workflows/atualizar-precos.yml → ícone do lápis. Substitua o **conteúdo** pelo arquivo `.github/workflows/atualizar-precos.yml` que veio no ZIP. **Commit changes**.
5. Abra https://github.com/caiocampos120807-png/mercado-em-conta-robo/actions → **Atualizar preços de supermercado → Run workflow → Run workflow**.
6. Quando terminar, vá a **Code** e abra `redes-status.json`. Ele mostra os resultados por mercado. Abra também `precos.csv`: só redes com valores confirmados aparecerão na busca.

**Não envie nem exclua `precos.csv`, `catalogo.json`, `status.json`, `coletar.py`, `expandir_catalogo.py` e `fontes.json`.** Esses arquivos já estão no seu repositório e devem ser preservados. O ZIP de atualização **não inclui** seus dados.

## PASSO B — Atualização opcional do visual da Cloudflare

O site atual já lê `precos.csv`: **não é obrigatório atualizar a Cloudflare para que novos mercados apareçam**. Assim que o GitHub publicar novos preços válidos, clique em **Atualizar** no site.

Para ter o novo quadro de estado por rede:

1. Baixe `mercado-em-conta-site-6-redes.zip`.
2. Abra https://dash.cloudflare.com/ → **Workers & Pages → mercado-em-conta → New deployment**.
3. Envie o ZIP do site e clique em **Deploy**. Não crie outro site nem compre domínio.
4. Abra o endereço atual do Mercado em Conta e clique em **Dados**. Confira a seção **Outras redes: resultado real da coleta**.

## Onde ver erros

GitHub Actions: clique na execução → **coletar** → **Buscar preços em redes adicionais**. Um robô verde pode ter 0 ofertas novas: isso não é sucesso de extração. Confira `redes-status.json` e, se houver, os avisos de acesso/robots.txt.

## Custos, ética e limites

- Projeto apenas com Python stdlib + GitHub Actions (runner padrão, repositório **público**) + Cloudflare com arquivos estáticos.
- Evita login, CAPTCHA, proxies, APIs privadas, identificação falsa, cookies pessoais e contorno de `robots.txt`. Quando o site proíbe ou bloqueia, o coletor interrompe para aquela rede.
- Não requer cartão de crédito, assinatura paga ou APIs pagas para executar o pacote dentro das condições gratuitas atuais.
- Preços podem depender do CEP, da loja, do estoque, do cartão de fidelidade ou do horário. Não são garantia de preço físico.
- O GitHub pode suspender agendamentos automáticos após 60 dias sem atividade; nesse caso, reative em Actions.
- O limite superior é o acesso a dados confiáveis, não apenas a quantidade de URLs que cabem no código.

## Testes locais realizados

`python -m unittest discover -s tests -v` — 51 testes Python passaram. `node --test tests.js` — 8 testes de regras de interface passaram. `node --check app.js` passou. **Não foi possível consultar os supermercados na máquina onde este pacote foi gerado.** Os totais reais só serão conhecidos após a execução do GitHub. Nenhuma atualização foi aplicada diretamente à sua conta nesta conversa.
