import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from destaques import build

TODAY=date(2026,11,18)
HEAD=['produto','marca','tamanho','unidade','categoria','mercado','cidade','uf','preco','atualizado','link']

def row(product='Arroz branco',market='A',city='São Paulo',price='20',suffix='a',**kw):
    r=dict(produto=product,marca='Camil',tamanho='5',unidade='kg',categoria='Mercearia',mercado=market,cidade=city,uf='SP',preco=price,atualizado='2026-11-18',link='https://www.paodeacucar.com/'+suffix)
    r.update(kw);return r

class HighlightsTest(unittest.TestCase):
    def build_rows(self,rows):
        with tempfile.TemporaryDirectory() as dirname:
            base=Path(dirname)
            with (base/'precos.csv').open('w',newline='',encoding='utf8') as file:
                writer=csv.DictWriter(file,fieldnames=HEAD);writer.writeheader();writer.writerows(rows)
            result=build(base,TODAY)
            self.assertEqual(result, json.loads((base/'destaques.json').read_text(encoding='utf8')))
            self.assertTrue((base/'boletim-compartilhavel.md').exists())
            return result

    def test_two_stores_same_city_and_sku(self):
        result=self.build_rows([row(),row(market='B',price='27',suffix='b')])
        self.assertEqual(len(result['comparacoes']),1)
        self.assertEqual(result['comparacoes'][0]['diferenca'],7)
        self.assertEqual(result['comparacoes'][0]['mercado_menor'],'A')

    def test_different_city_does_not_compare(self):
        result=self.build_rows([row(),row(market='B',city='Campinas',price='31',suffix='b')])
        self.assertEqual(len(result['comparacoes']),0)

    def test_different_sizes_do_not_compare(self):
        result=self.build_rows([row(),row(market='B',price='31',suffix='b',tamanho='1')])
        self.assertEqual(len(result['comparacoes']),0)

    def test_conflicting_url_discarded(self):
        result=self.build_rows([row(price='20'),row(price='90'),row(market='B',price='30',suffix='b')])
        self.assertEqual(len(result['comparacoes']),0)
        self.assertEqual(result['ofertas_rejeitadas'],1)

    def test_stale_and_future_rejected(self):
        result=self.build_rows([row(atualizado='2026-11-13'),row(market='B',suffix='b',atualizado='2026-12-01')])
        self.assertEqual(result['comparacoes'],[])
        self.assertEqual(result['ofertas_rejeitadas'],2)

    def test_same_market_twice_is_one_market(self):
        result=self.build_rows([row(),row(price='24',suffix='b')])
        self.assertEqual(result['comparacoes'],[])

    def test_no_positive_difference_no_highlight(self):
        result=self.build_rows([row(),row(market='B',price='20',suffix='b')])
        self.assertEqual(result['comparacoes'],[])

    def test_reject_unknown_host(self):
        result=self.build_rows([row(),row(market='B',price='30',suffix='b',link='https://unknown.example/p')])
        self.assertEqual(result['comparacoes'],[])

if __name__=='__main__': unittest.main()
