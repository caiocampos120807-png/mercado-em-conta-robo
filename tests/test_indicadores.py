import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from gerar_indicadores import audit_row, run, sku_key, as_float, quantity

TODAY=date(2026,11,18)

def offer(**changes):
    r={'produto':'Arroz branco','marca':'Camil','tamanho':'5','unidade':'kg','categoria':'Mercearia','mercado':'Sonda (online)', 'cidade':'São Paulo','uf':'SP','preco':'27.90','atualizado':TODAY.isoformat(),'link':'https://www.sondadelivery.com.br/delivery/produto/arroz-camil/123'}
    r.update(changes)
    return r

class IndicatorTests(unittest.TestCase):
    def test_price_parsers(self):
        self.assertEqual(as_float('R$ 1.234,56'),1234.56)
        self.assertIsNone(as_float('nan'))
        self.assertEqual(quantity('0,5','kg'),500)
    def test_equivalent_units_sku(self):
        self.assertEqual(sku_key(offer(tamanho='1',unidade='kg')),sku_key(offer(tamanho='1000',unidade='g')))
        self.assertNotEqual(sku_key(offer(marca='Outra')),sku_key(offer()))
    def test_source_guard(self):
        self.assertEqual(audit_row(offer(link='https://evil.example/item'),TODAY)[1], 'fonte não autorizada')
        self.assertEqual(audit_row(offer(atualizado='2024-01-01'),TODAY)[1], 'preço fora da validade')
        self.assertIsNotNone(audit_row(offer(),TODAY)[0])
    def test_history_and_comparability(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); rows=[offer(),offer(mercado='Pão de Açúcar (online)',preco='29.90',link='https://www.paodeacucar.com/produto/12/arroz-camil'),offer(atualizado=(TODAY-timedelta(days=4)).isoformat(),link='https://www.sondadelivery.com.br/delivery/produto/arroz/124')]
            with (p/'precos.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            result=run(p,TODAY)
            self.assertEqual(result['ofertas_ativas'],2)
            self.assertEqual(result['produtos_distintos'],1)
            self.assertEqual(result['produtos_em_2_ou_mais_mercados'],1)
            self.assertEqual(result['ofertas_rejeitadas'],1)
            self.assertEqual(run(p,TODAY)['observacoes_historicas'],2)
            saved=json.loads((p/'historico.json').read_text())
            self.assertEqual(len(saved['products']),1)
    def test_different_product_no_fuzzy_merge(self):
        self.assertNotEqual(sku_key(offer(produto='Arroz integral')),sku_key(offer(produto='Arroz branco')))
        self.assertNotEqual(sku_key(offer(tamanho='500',unidade='g')),sku_key(offer()))

if __name__ == '__main__': unittest.main()
