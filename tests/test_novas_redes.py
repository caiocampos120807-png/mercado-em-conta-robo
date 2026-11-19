import unittest
import integrar_redes as N

PAGUE='https://www.supermercadospaguemenos.com.br/mercearia/alimentos-basicos'
PAGUEPROD='https://www.supermercadospaguemenos.com.br/arroz-camil-tipo-1-selecao-especial-5kg-2004025019/p'
SAVE='https://www.savegnago.com.br/mercearia/graos-e-cereais'
SAVEPROD='https://www.savegnago.com.br/arroz-agulhinha-camil-5kg-tipo-1/p'

class TestRedesNovas(unittest.TestCase):
    def test_safe_url(self):
        self.assertEqual(N.safe_url(PAGUE,kind='listing'),PAGUE)
        self.assertEqual(N.safe_url(PAGUEPROD,kind='product'),PAGUEPROD)
        self.assertEqual(N.safe_url(SAVE,kind='listing'),SAVE)
        self.assertEqual(N.safe_url(SAVEPROD,kind='product'),SAVEPROD)
    def test_no_parameter_or_tokens(self):
        self.assertEqual(N.safe_url(PAGUE+'?senha=xyz',kind='listing'),None)
        self.assertEqual(N.safe_url(SAVEPROD+'?token=xyz',kind='product'),SAVEPROD)
    def test_sem_cep_nao_publica(self):
        net=dict(nome='Pague Menos',host='www.supermercadospaguemenos.com.br',localizacao_confirmada=False)
        with self.assertRaises(ValueError):N.record('Arroz Branco Camil 5kg',25,PAGUEPROD,net)
    def test_json_ld_com_link_e_preco_confirmado(self):
        net=dict(nome='Pague Menos',host='www.supermercadospaguemenos.com.br',localizacao_confirmada=True)
        page=N.HtmlProducts(PAGUE)
        page.feed(f'''<a href="{PAGUEPROD}">Arroz Branco Camil Tipo 1 5kg</a>
          <script type="application/ld+json">{{"@type":"Product","name":"Arroz Branco Camil Tipo 1 5kg",
          "url":"{PAGUEPROD}","offers":{{"@type":"Offer","price":"25.99","priceCurrency":"BRL",
          "availability":"https://schema.org/InStock"}}}}</script>''')
        page.close()
        result=N.listing_offers(page,net,'Campinas','SP')
        self.assertEqual(len(result),1)
        self.assertEqual(result[PAGUEPROD]['preco'],'25.99')
    def test_json_ld_sem_link_visivel_nao_publica(self):
        net=dict(nome='Pague Menos',host='www.supermercadospaguemenos.com.br',localizacao_confirmada=True)
        page=N.HtmlProducts(PAGUE)
        page.feed(f'<script type="application/ld+json">{{"@type":"Product","name":"Arroz Branco Camil Tipo 1 5kg","url":"{PAGUEPROD}","offers":{{"price":25.99}}}}</script>')
        page.close()
        self.assertEqual(N.listing_offers(page,net,'Campinas','SP'),{})
    def test_nao_confunde_preco_antigo_atual(self):
        self.assertIsNone(N.primary_price('R$ 29,99 R$ 25,99 14% OFF'))
    def test_price_jsonld_sem_cep_nao_publica(self):
        net=dict(nome='Pague Menos',host='www.supermercadospaguemenos.com.br',localizacao_confirmada=False)
        page=N.HtmlProducts(PAGUE)
        page.feed(f'<a href="{PAGUEPROD}">Arroz Branco Camil 5kg</a><script type="application/ld+json">{{"@type":"Product","name":"Arroz Branco Camil 5kg","url":"{PAGUEPROD}","offers":{{"price":20}}}}</script>')
        page.close()
        self.assertFalse(N.listing_offers(page,net,'São Paulo','SP'))

if __name__=='__main__':unittest.main()
