# Instalação rápida — não apague seus preços!

- Suba `gerar_indicadores.py` no diretório principal do seu GitHub, **não** o ZIP.
- Suba `tests/test_indicadores.py` **dentro da pasta tests**; opcional, mas recomendado.
- Abra `.github/workflows/atualizar-precos.yml` no GitHub e cole no editor o conteúdo do arquivo `atualizar-precos.yml` deste pacote. Salve com Commit changes.
- Vá a Actions, execute o workflow e confira os novos arquivos `historico.json` e `indicadores.json`.
- NÃO envie `precos.csv` nem `catalogo.json` vazios ou de demonstração. Preserve os existentes.

O histórico começa na primeira execução bem-sucedida.
