# 🛒 Mercado em Conta — pronto e gratuito

Um comparador de preços de supermercado para ajudar sua família. Sem mensalidade obrigatória, sem conta para acessar o site, sem anúncios, sem bibliotecas externas e sem precisar instalar nada.

## 🚀 Comece em 30 segundos

1. Abra `index.html` no Chrome, Edge, Firefox ou Safari. Você verá uma **demonstração com preços inteiramente FICTÍCIOS**.
2. Clique em **Gerenciar → Meus dados** para sair da demonstração.
3. Cadastre alguns preços reais ou importe um arquivo `CSV` usando a aba **Gerenciar**.
4. Pesquise, adicione à lista e compare o total dos mercados.

**Importante:** dados digitados em “Gerenciar” são salvos SOMENTE no navegador atual. Exporte periodicamente seus preços em CSV para fazer backup; limpar o navegador pode apagar os cadastros. Em janelas anônimas ou alguns navegadores abrindo `file://`, os dados podem não persistir. Para mais confiabilidade, publique o site e use Google Sheets.

## 🌎 Publique GRATUITAMENTE na internet e compartilhe com seu pai

**Sugestão: Cloudflare Pages** (`https://pages.cloudflare.com/`).

1. Crie uma conta gratuita na Cloudflare.
2. Vá a **Workers & Pages** → **Create application** → **Pages** → **Direct Upload**.
3. Escolha um nome livre para o site (por exemplo, `mercado-em-conta-familia`).
4. Envie `index.html` (ou o ZIP com os arquivos na raiz do projeto). Você também pode arrastar a pasta do site. 
5. Clique em **Deploy** para obter seu link `*.pages.dev` e compartilhe com seu pai.

Observação: a plataforma muda os textos dos botões às vezes. Fonte oficial: https://developers.cloudflare.com/pages/get-started/direct-upload/ . A hospedagem está sujeita aos limites do plano gratuito; **você não precisa comprar domínio**.

## 🔄 Deixar os preços sincronizados entre os aparelhos, sem pagar

O recurso mais simples de manutenção coletiva é uma **planilha Google Sheets pública**. Ao editar a planilha, o site lê os novos preços na próxima abertura ou atualização automática de 15 em 15 minutos enquanto estiver aberto. Não é um robô que descobre preços sozinho: as linhas precisam ser atualizadas por uma pessoa ou fonte autorizada.

1. No Google Sheets, crie uma planilha e coloque **os mesmos cabeçalhos** do arquivo `modelo-precos.csv`.
2. Digite uma linha para cada produto + supermercado + cidade. Use somente informações destinadas a ser públicas.
3. Vá em **Arquivo → Compartilhar → Publicar na Web**. Selecione **a aba de preços** e o formato **CSV (valores separados por vírgula)**. Publique e copie o link, semelhante a `https://docs.google.com/spreadsheets/d/e/2PACX-.../pub?output=csv`.
4. Com o site já publicado, entre em **Gerenciar → Conectar planilha** e cole esse link.
5. Clique em **Link para a família** e mande o link gerado para seu pai. Ele abre o site e usa **os mesmos preços públicos**. Você não precisa criar conta para ele.

O Google pode demorar alguns minutos para refletir mudanças. Como o CSV é lido diretamente do navegador, o Google pode ocasionalmente bloqueá-lo por configurações de acesso/CORS. Se falhar, verifique as permissões/publicação ou importe CSV manualmente.

**Não publique documentos privados ou informações pessoais** em uma planilha destinada a ser pública.

## 📋 Formato da planilha

Colunas (nesta ordem, de preferência):

`produto,marca,tamanho,unidade,categoria,mercado,cidade,uf,preco,atualizado,link`

A coluna `preco` aceita números como `24.90` ou `24,90` (neste último caso, o CSV separado por vírgula deve colocar o valor entre aspas). Aceita CSV separado por vírgulas ou ponto e vírgula, com textos entre aspas.

- **produto:** Arroz branco
- **marca:** Marca da embalagem (use `Sem marca` quando não houver)
- **tamanho:** `5`
- **unidade:** `kg`, `g`, `l`, `ml` ou `un`
- **categoria:** `Mercearia`, `Laticínios`, `Hortifruti`, `Carnes`, `Bebidas`, `Limpeza`, `Higiene` ou `Outros`
- **mercado:** nome exato do supermercado
- **cidade:** município em que o preço vale
- **uf:** sigla de 2 letras, como SP
- **preco:** valor do pacote/embalagem, não valor por kg
- **atualizado:** data, preferencialmente `AAAA-MM-DD`
- **link:** URL da oferta (opcional)

Mesmo produto, mesma marca e mesma embalagem são comparados entre diferentes supermercados. Marcas e embalagens distintas aparecem separadas para não induzir a um resultado enganoso. A data da coleta é informativa e não confirma que o preço segue vigente.

## ✅ Recursos incluídos

- Busca por nome ou marca.
- Filtro de cidade e categoria; ordenação por preço e nome.
- Comparação por supermercado para **exatamente a mesma embalagem e marca**.
- Valor por kg, litro ou unidade.
- Lista de compras com quantidades e persistência no navegador.
- Cálculo do mercado com o menor custo **da lista inteira**.
- Identificação de supermercados com itens faltando.
- Possibilidade de comprar cada item no menor preço, com ressalva de deslocamento e frete.
- Cadastro, exclusão, importação e exportação CSV.
- Leitura de CSV público com atualização programada enquanto o site estiver aberto.
- Link para compartilhar a fonte de preços com familiares.
- Layout para celular e computador, sem rastreamento nem propaganda.

## ⚠️ Limitações intencionais e transparentes

- **Não coleta preços de redes de supermercados automaticamente** sem API ou outra fonte autorizada. Isso não tem como ser garantido de graça e para todas as lojas.
- Os dados digitados no cadastro são **locais** e não são enviados para um servidor.
- Dados importados de planilhas são públicos e podem estar desatualizados.
- Um site estático não oferece conta e senha de administrador nem banco online privado. Para edição colaborativa com autenticação seria necessário evoluir a arquitetura.
- Não inclui cálculo de frete, deslocamento, fidelidade, cupons ou preço em tempo real na boca do caixa.
- Os supermercados e preços iniciais são **fictícios e rotulados** como demonstração.
- Para preço confiável, confirme a loja, o tamanho, a forma de pagamento e a data da promoção.

## 💚 Projeto familiar

O objetivo é começar pequeno. Cadastre 15–30 produtos que seu pai compra sempre e 2–4 mercados da região. Você já terá uma comparação útil sem depender de um serviço pago.
