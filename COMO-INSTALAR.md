# Mercado em Conta + Robô Automático (sem mensalidade)

## O que realmente faz

Este repositório traz um coletor de preços **já programado** para consultar 6 páginas de produtos reais (3 itens x 2 supermercados) uma vez ao dia. Ele não requer cadastrar números de preços; lê os valores das páginas públicas, **quando permitido e tecnicamente possível**.

O robô gera `precos.csv` no mesmo formato do site Mercado em Conta. O site **já publicado na Cloudflare** pode ler esse CSV por URL (Gerenciar → Atualização automática → Conectar planilha) e se atualiza ao abrir e a cada 15 minutos enquanto permanecer aberto. O robô trabalha mesmo quando o site estiver fechado.

ATENÇÃO: neste ambiente de preparação não foi possível executar requisições de rede aos mercados. **Os testes passaram com páginas HTML simuladas**, não com coleta real de 2026. É preciso executar o robô no GitHub para ver quais sites atualmente permitem acesso e quais preços ele consegue confirmar. Os preços de referência podem variar conforme CEP e loja. Se todos os mercados bloquearem as requisições, o CSV permanecerá vazio e o site NÃO terá ofertas — é mais seguro que inventar ou reaproveitar valores antigos.

## 1. Publicar o robô gratuitamente no GitHub

1. Crie sua conta gratuita em https://github.com/ (caso ainda não tenha).
2. Vá a https://github.com/new e crie um repositório **público**, chamado `mercado-em-conta-robo`. Confirme em **Create repository**.
3. Descompacte o arquivo `mercado-em-conta-robo-github.zip` no computador. **Não envie o ZIP diretamente ao GitHub:** ele precisa dos arquivos internos para executar o robô.
4. Na página do repositório GitHub, clique em **Add file → Upload files**; arraste os arquivos e pastas descompactados para a área de upload e confirme em **Commit changes**. O GitHub aceita soltar uma pasta e preserva o caminho dos arquivos; se `.github` estiver oculto no Finder do Mac, use **⌘ + Shift + .** para mostrar arquivos ocultos e inclua também essa pasta.
5. Verifique que existe este arquivo exatamente em: `.github/workflows/atualizar-precos.yml`. Se não aparecer, no GitHub use **Add file → Create new file**, digite esse caminho completo e cole o conteúdo do arquivo que veio no ZIP; depois clique em **Commit changes**.
6. Vá à aba **Actions** do repositório; se pedir, habilite Actions. Escolha **Atualizar preços de supermercado → Run workflow → Run workflow**.
7. Abra a execução e confira se os testes e o passo `Consultar páginas públicas` concluíram. Na raiz do repositório, abra `status.json`: o número `precos_coletados` informa quantas fontes responderam com um preço verificável; `avisos` mostra os bloqueios e falhas.

O agendamento está configurado para `17 9 * * *` (9h17 UTC, aproximadamente 6h17 no horário de Brasília). O GitHub não garante o minuto exato e pode atrasar ou pular execuções. Workflows agendados em repositórios públicos podem ser pausados depois de 60 dias sem atividade no repositório. Repositórios **públicos** têm execução gratuita dos runners padrão, segundo a documentação do GitHub (sujeito a alterações de políticas).

## 2. Conectar ao site que você já publicou

1. Copie este endereço, trocando `SEU_USUARIO` pelo seu nome de usuário **no GitHub**:

   `https://raw.githubusercontent.com/SEU_USUARIO/mercado-em-conta-robo/main/precos.csv`

2. Abra seu site `Mercado em Conta` (Cloudflare) → clique em **Gerenciar**.
3. Na caixa **Atualização automática por Google Sheets ou CSV público**, cole o endereço acima em **URL HTTPS do CSV publicado** e clique **Conectar planilha**.
4. Veja se aparecem preços reais na aba **Buscar preços**. Se `status.json` disser `precos_coletados: 0`, não há valores disponíveis; cheque os avisos e a execução na aba Actions, sem precisar inventar preços.
5. Use **Link para a família** no Gerenciar e mande o link gerado para seu pai. Ele receberá os dados públicos automaticamente.

**Importante:** a primeira versão do site publicada anteriormente pode manter ofertas antigas se uma coleta posterior produzir CSV vazio. Por segurança, publique a nova versão do site incluída no ZIP separado `mercado-em-conta-site-atualizado.zip`. Ela oculta ofertas com mais de 72 horas e limpa preços antigos se o CSV vier vazio ou a leitura falhar. A atualização pode ser feita na Cloudflare por **Workers & Pages → mercado-em-conta → New deployment**, enviando o ZIP do site atualizado. Sua URL existente pode continuar igual se atualizar o Worker atual.

## 3. Aumentar a lista de produtos (uma vez, não digitar preços)

Em `fontes.json`, há 6 URLs reais de produtos para começar, incluindo feijão, arroz e leite das redes Pão de Açúcar e Sonda. Para incluir outro item, adicione o endereço público da **página desse produto** e seus dados de identificação (nome, marca, embalagem, supermercado). O robô buscará o **preço sozinho todos os dias**. Não é uma busca ilimitada de todas as mercadorias de todos os supermercados: os produtos que deseja acompanhar precisam ser identificados ao menos uma vez. Se o site exigir login, seleção obrigatória de loja, CEP ou bloquear automação, será necessário fonte autorizada alternativa; **não tente contornar os bloqueios**.

Estrutura de cada item: `produto`, `marca`, `tamanho`, `unidade`, `categoria`, `mercado`, `cidade`, `uf`, `tipo`, `url`. `tipo` tem suporte inicial a `pao` (Pão de Açúcar) e `sonda` (Sonda). Não use nomes que induzam comparação incorreta de embalagem, modalidade ou região. O coletor valida marca, item e volume na própria página antes de publicar o preço.

## Limites e transparência

- Os exemplos de URLs foram encontrados em páginas públicas que exibiam produtos; **não há garantia de acesso automático a todos os sites**. Regras do `robots.txt` são consultadas antes de tentar buscar o produto, com falha fechada se indisponível. O robô não contorna captchas nem bloqueios.
- A disponibilidade e os preços podem depender da loja/CEP, modalidade de compra, estoque e fidelidade. **Não são promessas de preço na unidade física próxima da sua casa.** Confira no site do mercado antes de pagar.
- O robô grava o **dia real da coleta** em `atualizado` e nunca escreve preço calculado/fictício.
- Se uma fonte falhar, sua oferta **não** aparece no novo CSV. Se todas falharem, o CSV fica apenas com o cabeçalho. `status.json` informa o motivo.
- **Não é necessário** contratar Lovable, n8n, Supabase, API paga, domínio próprio ou servidor.
- O repositório precisa ser público para a execução gratuita indicada. Não coloque segredos, endereços residenciais, planilhas privadas ou dados pessoais no repositório.
- O site da Cloudflare não publica sozinho o GitHub: você precisa concluir a configuração acima na sua conta. Não há integração ativa até isso acontecer.

## Verificação técnica

Rode localmente `python -m unittest discover -s tests -v` para testar o extrator sem consultar sites. `python coletar.py` tenta fazer a coleta real; só execute quando tiver permissão e acesso à rede. O projeto depende apenas do Python 3.12 (sem bibliotecas pagas ou terceiros).
