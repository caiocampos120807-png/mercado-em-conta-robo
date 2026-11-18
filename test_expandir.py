import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import expandir_catalogo as ex

PAO = 'https://www.paodeacucar.com/produto/1234/arroz-branco-camil-5kg'
SONDA = 'https://www.sondadelivery.com.br/delivery/produto/feijao-carioca-camil-1kg/10000'

class Tests(unittest.TestCase):
    def test_url_security(self):
        self.assertEqual(ex.safe_url(PAO, kind='product'), PAO)
        self.assertIsNone(ex.safe_url('https://malicioso.com/produto/12/arroz',kind='product'))
        self.assertIsNone(ex.safe_url('http://www.paodeacucar.com/produto/12/arroz',kind='product'))
        self.assertIsNone(ex.safe_url('https://www.paodeacucar.com/busca/arroz',kind='product'))
        self.assertIsNone(ex.safe_url('https://www.sondadelivery.com.br/checkout',kind='product'))
        self.assertIsNone(ex.safe_url('https://usuario:senha@www.paodeacucar.com/produto/12/arroz',kind='product'))

    def test_nested_category_urls(self):
        url='https://www.sondadelivery.com.br/delivery/categoria/Mercearia/Basica/Arroz'
        self.assertEqual(ex.safe_url(url,kind='listing'),url)

    def test_discover_listing(self):
        html = f'<a href="{PAO}">Arroz</a><a href="/sitemapProduto-2.sdex">Página 2</a><a href="/busca">Busca</a>'
        prods,pages = ex.discover(html,'https://www.paodeacucar.com/sitemapProduto.sdex')
        self.assertEqual(prods,{PAO})
        self.assertEqual(pages,{'https://www.paodeacucar.com/sitemapProduto-2.sdex'})

    def test_size_brand(self):
        p = ex.identify('Arroz agulhinha tipo 1 Camil pacote 5kg')
        self.assertEqual((p['produto'],p['marca'],p['tamanho'],p['unidade']),('Arroz branco','Camil',5,'kg'))
        self.assertEqual(ex.identify('Feijão Carioca Camil 1kg')['produto'],'Feijão carioca')
        self.assertEqual(ex.identify('Leite Integral Parmalat 1 Litro')['marca'],'Parmalat')

    def test_ambiguous(self):
        for item in ['Kit Arroz Camil 5kg e Feijão 1kg', 'Combo Leite Parmalat 1 Litro', 'Produtos sem tamanho']:
            with self.assertRaises(ValueError): ex.identify(item)

    def test_extract_product(self):
        html='<html><body><div>carrinho R$ 0,00</div><h1>Arroz branco Camil 5kg</h1><div>Cód: 2345 R$ 27,99</div><p>Preço por 1kg - R$ 5,60</p></body></html>'
        row=ex.extract_product(html,PAO,{'cidade_online':'São Paulo','uf_online':'SP'})
        self.assertEqual(row['preco'],'27.99')
        self.assertEqual(row['tamanho'],5)
        self.assertEqual(row['mercado'],'Pão de Açúcar (online)')

    def test_invalid_no_publish(self):
        with self.assertRaises(ValueError):
            ex.extract_product('<h1>Outro produto 1kg</h1>Preço R$ 12,00', PAO, {'cidade_online':'São Paulo','uf_online':'SP'})

    def test_pipeline_incremental_and_cleanup(self):
        listing='https://www.paodeacucar.com/sitemapProduto.sdex'
        html = '<a href="'+PAO+'">Arroz</a>'
        product = '<h1>Arroz branco Camil 5kg</h1> R$ 27,99'
        class Fake:
            def __init__(self): self.calls=[]
            def request(self,url):
                self.calls.append(url)
                return html if url.endswith('.sdex') else product
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            cfg={'max_paginas_descoberta_por_execucao':1,'max_produtos_consultados_por_execucao':4,
                 'cidade_online':'São Paulo','uf_online':'SP','intervalo_minimo_por_site_segundos':3}
            (path/'config-expansao.json').write_text(json.dumps(cfg))
            ex.write_csv(path/'precos.csv',[])
            report=ex.run(base=path,client=Fake())
            self.assertEqual(report['precos_coletados'],1)
            rows=ex.read_csv(path/'precos.csv')
            self.assertEqual(rows[0]['preco'],'27.99')
            self.assertEqual(report['urls_catalogo'],1)
            # Falha na próxima execução => sem reaproveitar registro vencido
            data=json.loads((path/'catalogo.json').read_text())
            data['produtos'][PAO]['ultima_consulta']='2020-01-01T00:00:00+00:00'
            data['paginas'][listing]['ultima_consulta']=ex.stamp()
            (path/'catalogo.json').write_text(json.dumps(data))
            class Broken:
                def request(self,url): raise ValueError('indisponível')
            report=ex.run(base=path,client=Broken())
            self.assertEqual(report['precos_coletados'],0)
            self.assertEqual(ex.read_csv(path/'precos.csv'),[])

    def test_disallow_old_price(self):
        r = {'preco':'10.00', 'atualizado':'2020-01-01'}
        self.assertFalse(ex.valid_recent(r, 2))

if __name__=='__main__':unittest.main()

class TestOfertasListagem(unittest.TestCase):
    def test_sonda_lista_com_preco_vinculado_ao_link(self):
        url='https://www.sondadelivery.com.br/delivery/categoria/Mercearia'
        html='<div><a href="/delivery/produto/arroz-branco-camil-5kg/123">Arroz branco Camil 5kg</a><p>Por R$ 23,90</p></div>'
        html+='<div><a href="/delivery/produto/feijao-carioca-camil-1kg/456">Feijão carioca Camil 1kg</a><p>Por R$ 9,40</p></div>'
        rows=ex.listing_offers(html,url,{'cidade_online':'São Paulo','uf_online':'SP'})
        self.assertEqual(len(rows),2)
        self.assertEqual(rows['https://www.sondadelivery.com.br/delivery/produto/arroz-branco-camil-5kg/123']['preco'],'23.90')

    def test_sonda_nao_inventa_preco(self):
        url='https://www.sondadelivery.com.br/delivery/categoria/Mercearia'
        h='<a href="/delivery/produto/arroz-branco-camil-5kg/123">Arroz branco Camil 5kg</a><p>Preço sob consulta</p>'
        self.assertEqual(ex.listing_offers(h,url,{'cidade_online':'São Paulo','uf_online':'SP'}),{})

    def test_preco_distante_nao_pertence_ao_produto(self):
        url='https://www.sondadelivery.com.br/delivery/categoria/Mercearia'
        h='<a href="/delivery/produto/arroz-branco-camil-5kg/123">Arroz branco Camil 5kg</a>'+'x'*350+'Por R$ 2,99'
        self.assertEqual(ex.listing_offers(h,url,{'cidade_online':'São Paulo','uf_online':'SP'}),{})
