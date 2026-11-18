import csv
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

import integrar_redes as x

EXTRA='https://www.extramercado.com.br/produto/41329/arroz-agulhinha-tipo-1-camil-pacote-5kg'
EXTRA_FEIJAO='https://www.extramercado.com.br/produto/9461/feijao-carioca-tipo-1-camil-pacote-1kg'
EXTRA_CATEGORY='https://www.extramercado.com.br/categoria/alimentos/basico-da-despensa/graos-e-cereais/arroz'
CARREFOUR='https://mercado.carrefour.com.br/produto/arroz-branco-camil-tipo-kg-1970'
CARREFOUR_CAT='https://mercado.carrefour.com.br/categoria/mercearia/alimentos-basicos/arroz'
ATACADAO='https://www.atacadao.com.br/mercearia/graos'
MAMBO='https://www.mambo.com.br/camil'
EXTRA_NET={'id':'extra','nome':'Extra Mercado (online)','host':'www.extramercado.com.br','localizacao_confirmada':True}
CAR_NET={'id':'carrefour','nome':'Carrefour (online)','host':'mercado.carrefour.com.br','localizacao_confirmada':True}
ATACADAO_NET={'id':'atacadao','nome':'Atacadão (online)','host':'www.atacadao.com.br','localizacao_confirmada':False}


def parse(h,url):
    a=x.HtmlProducts(url)
    a.feed(h)
    a.close()
    return a

class TestUrlRules(unittest.TestCase):
    def test_known_urls(self):
        self.assertEqual(x.safe_url(EXTRA,kind='product'),EXTRA)
        self.assertEqual(x.safe_url(CARREFOUR,kind='product'),CARREFOUR)
        self.assertEqual(x.safe_url(ATACADAO,kind='listing'),ATACADAO)
        self.assertEqual(x.safe_url(MAMBO,kind='listing'),MAMBO)

    def test_block_bad_hosts(self):
        for raw in ('https://attacker.com/produto/123/arroz-5kg',
                    'http://www.extramercado.com.br/produto/123/arroz',
                    'https://evil@www.extramercado.com.br/produto/123/arroz',
                    'https://www.extramercado.com.br/checkout'):
            self.assertIsNone(x.safe_url(raw,kind='product'))

    def test_relative_link_restrict_host(self):
        self.assertEqual(x.safe_url('/produto/41329/arroz-camil-5kg',EXTRA_CATEGORY,'product'),
                         'https://www.extramercado.com.br/produto/41329/arroz-camil-5kg')
        self.assertIsNone(x.safe_url('//evil.xyz/produto/123/arroz',EXTRA_CATEGORY,'product'))

    def test_allow_only_safe_pagination(self):
        good=CARREFOUR_CAT+'?page=2'
        self.assertEqual(x.safe_url(good,kind='listing'),good)
        for bad in (CARREFOUR_CAT+'?page=999',CARREFOUR_CAT+'?sessionid=abc',CARREFOUR_CAT+'?page=2&cep=01000'):
            self.assertIsNone(x.safe_url(bad,kind='listing'))

    def test_strip_product_tracking(self):
        self.assertEqual(x.safe_url(EXTRA+'?utm_source=foo',kind='product'),EXTRA)


class TestContent(unittest.TestCase):
    def test_extra_product_visible_price(self):
        h='<header>Seu carrinho R$ 0,00</header><h1>Arroz Agulhinha Tipo 1 CAMIL Pacote 5kg</h1> Cód.: 0791595 R$ 26,99 Preço por 1kg - R$ 5,39'
        row=x.product_offer(parse(h,EXTRA),EXTRA,EXTRA_NET,'São Paulo','SP')
        self.assertEqual((row['produto'],row['marca'],row['tamanho'],row['preco']),('Arroz branco','Camil',5,'26.99'))

    def test_extra_no_confusing_unit_price(self):
        h='<h1>Arroz Agulhinha Tipo 1 CAMIL Pacote 5kg</h1>Preço por 1kg - R$ 5,39'
        with self.assertRaises(ValueError):x.product_offer(parse(h,EXTRA),EXTRA,EXTRA_NET,'São Paulo','SP')

    def test_extra_ambiguous_prices(self):
        h='<h1>Arroz Agulhinha Tipo 1 CAMIL Pacote 5kg</h1>R$ 35,99 R$ 28,50'
        with self.assertRaises(ValueError):x.product_offer(parse(h,EXTRA),EXTRA,EXTRA_NET,'São Paulo','SP')

    def test_explicit_por_price(self):
        self.assertEqual(x.primary_price('De R$ 29,90 Por R$ 24,90'),24.90)
        self.assertIsNone(x.primary_price('R$ 29,90 R$ 24,90'))

    def test_without_price(self):
        self.assertIsNone(x.primary_price('Produto indisponível'))

    def test_kit_disallowed(self):
        with self.assertRaises(ValueError):x.record('Kit arroz Camil 5kg',20,EXTRA,EXTRA_NET)

    def test_out_of_stock(self):
        h='<h1>Arroz Agulhinha Tipo 1 CAMIL Pacote 5kg</h1><p>Produto indisponível</p>R$ 26,99'
        with self.assertRaises(ValueError):x.product_offer(parse(h,EXTRA),EXTRA,EXTRA_NET,'São Paulo','SP')

    def test_no_unverified_location(self):
        with self.assertRaises(ValueError):x.record('Arroz Branco Camil 5kg',20,'https://www.atacadao.com.br/produto/arroz',ATACADAO_NET)

    def test_brands_different(self):
        h='''<h1>Arroz Branco Camil 5kg</h1><script type="application/ld+json">{"@type":"Product","name":"Arroz Branco Tio João 5kg","url":"'''+CARREFOUR+'''","offers":{"@type":"Offer","price":"22.00","priceCurrency":"BRL"}}</script>'''
        with self.assertRaises(ValueError):x.product_offer(parse(h,CARREFOUR),CARREFOUR,CAR_NET,'São Paulo','SP')

    def test_jsonld_valid(self):
        h='''<h1>Arroz Branco Camil 5kg</h1><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Arroz Branco Camil 5kg","url":"'''+CARREFOUR+'''","offers":{"@type":"Offer","price":"21.50","priceCurrency":"BRL","availability":"https://schema.org/InStock"}}</script>'''
        r=x.product_offer(parse(h,CARREFOUR),CARREFOUR,CAR_NET,'São Paulo','SP')
        self.assertEqual(r['preco'],'21.50')

    def test_jsonld_currency_rejected(self):
        h='''<h1>Arroz Branco Camil 5kg</h1><script type="application/ld+json">{"@type":"Product","name":"Arroz Branco Camil 5kg","offers":{"price":"20.00","priceCurrency":"USD"}}</script>'''
        with self.assertRaises(ValueError):x.product_offer(parse(h,CARREFOUR),CARREFOUR,CAR_NET,'São Paulo','SP')

    def test_jsonld_outofstock(self):
        h='''<h1>Arroz Branco Camil 5kg</h1><script type="application/ld+json">{"@type":"Product","name":"Arroz Branco Camil 5kg","offers":{"price":"20.00","priceCurrency":"BRL","availability":"https://schema.org/OutOfStock"}}</script>'''
        with self.assertRaises(ValueError):x.product_offer(parse(h,CARREFOUR),CARREFOUR,CAR_NET,'São Paulo','SP')

    def test_jsonld_not_from_other_product(self):
        h='''<h1>Arroz Branco Camil 5kg</h1><script type="application/ld+json">{"@type":"Product","name":"Arroz Branco Camil 5kg","url":"https://mercado.carrefour.com.br/produto/outra-coisa","offers":{"price":"20.00","priceCurrency":"BRL"}}</script>'''
        with self.assertRaises(ValueError):x.product_offer(parse(h,CARREFOUR),CARREFOUR,CAR_NET,'São Paulo','SP')

    def test_listing_single_product(self):
        html='''<div><a href="'''+CARREFOUR+'''">Arroz Branco Camil 5kg</a><span>R$ 24,90</span>Adicionar</div>'''
        p=parse(html,CARREFOUR_CAT)
        self.assertIn(CARREFOUR,p.links)
        offers=x.listing_offers(p,CAR_NET,'São Paulo','SP')
        self.assertEqual(offers[CARREFOUR]['preco'],'24.90')

    def test_listing_not_product_neighborhood(self):
        html='''<a href="'''+CARREFOUR+'''">Arroz Branco Camil 5kg</a>'''+('Sem desconto. '*20)+'''R$ 2,00'''
        self.assertEqual(x.listing_offers(parse(html,CARREFOUR_CAT),CAR_NET,'São Paulo','SP'),{})

    def test_listing_no_attribution(self):
        html='<a href="'+CARREFOUR+'">Veja nosso estoque</a> R$ 2,00'
        self.assertFalse(x.listing_offers(parse(html,CARREFOUR_CAT),CAR_NET,'São Paulo','SP'))

    def test_stale_not_allowed(self):
        self.assertFalse(x.exp.valid_recent({'preco':'30.00','atualizado':'2020-01-01'},2))

    def test_round_robin(self):
        x1='https://www.extramercado.com.br/produto/123/arroz';x2='https://www.extramercado.com.br/produto/456/feijao'
        y1='https://mercado.carrefour.com.br/produto/arroz-5kg'
        urls=x.fair_queue({x1:{'last':'2024-01-01'},x2:{'last':'2024-01-02'},y1:{'last':'2024-01-01'}})
        self.assertEqual(urls[0],y1)
        self.assertIn(x2,urls)


class TestPipeline(unittest.TestCase):
    def test_merge_keeps_old_and_adds_new(self):
        class Fake:
            disabled=set()
            def get(self,url):
                if url==EXTRA_CATEGORY:
                    return '<a href="'+EXTRA+'">Arroz Agulhinha Tipo 1 Camil Pacote 5kg</a><span>R$ 26,99</span>'
                if url==CARREFOUR_CAT:
                    return '<a href="'+CARREFOUR+'">Arroz Branco Camil 5kg</a><span>R$ 20,99</span>'
                if url==MAMBO:
                    return '<a href="/arroz-camil-5kg/p">Produto Indisponível</a>'
                if url==ATACADAO:
                    return '<h1>Escolha uma loja ou informe seu CEP</h1>'
                if url==EXTRA:
                    return '<h1>Arroz Agulhinha Tipo 1 Camil Pacote 5kg</h1> R$ 26,99'
                if url==CARREFOUR:
                    return '<h1>Arroz Branco Camil 5kg</h1> R$ 20,99'
                raise ValueError('Página não encontrada')
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            old=dict(produto='Arroz branco',marca='Camil',tamanho='5',unidade='kg',categoria='Mercearia',
                     mercado='Pão de Açúcar (online)',cidade='São Paulo',uf='SP',preco='27.99',
                     atualizado=x.date.today().isoformat(),link='https://www.paodeacucar.com/produto/11/arroz')
            x.exp.write_csv(folder/'precos.csv',[old])
            cfg={'cidade_online':'São Paulo','uf_online':'SP','limites':{
                'paginas_listagem_por_execucao':5,'paginas_produto_por_execucao':6},'redes':[
                {**EXTRA_NET,'listagens':[EXTRA_CATEGORY],'produtos_iniciais':[EXTRA]},
                {**CAR_NET,'listagens':[CARREFOUR_CAT],'produtos_iniciais':[CARREFOUR]},
                {**ATACADAO_NET,'listagens':[ATACADAO]},
                {'id':'mambo','nome':'Mambo (online)','host':'www.mambo.com.br','localizacao_confirmada':True,'listagens':[MAMBO]}
                ]}
            (folder/'redes-fontes.json').write_text(json.dumps(cfg),encoding='utf8')
            result=x.run(base=folder,client=Fake())
            rows=x.exp.read_csv(folder/'precos.csv')
            self.assertEqual(len(rows),3)
            self.assertEqual(len({r['mercado'] for r in rows}),3)
            self.assertEqual(result['redes']['extra']['precos_validos'],1)
            self.assertEqual(result['redes']['carrefour']['precos_validos'],1)
            self.assertEqual(result['redes']['atacadao']['precos_validos'],0)
            self.assertTrue((folder/'catalogo_redes.json').exists())
            self.assertEqual(x.load_json(folder/'redes-status.json',{})['redes_candidatas'],4)

    def test_new_network_failure_keeps_old(self):
        class Blocked:
            disabled=set()
            def get(self,url):raise ValueError('robots.txt indisponível')
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            old=dict(produto='Arroz branco',marca='Camil',tamanho='5',unidade='kg',categoria='Mercearia',
                     mercado='Pão de Açúcar (online)',cidade='São Paulo',uf='SP',preco='27.99',
                     atualizado=x.date.today().isoformat(),link='https://www.paodeacucar.com/produto/11/arroz')
            x.exp.write_csv(folder/'precos.csv',[old])
            cfg={'redes':[{**EXTRA_NET,'listagens':[EXTRA_CATEGORY]}]}
            (folder/'redes-fontes.json').write_text(json.dumps(cfg))
            x.run(base=folder,client=Blocked())
            self.assertEqual(len(x.exp.read_csv(folder/'precos.csv')),1)

if __name__=='__main__':unittest.main()
