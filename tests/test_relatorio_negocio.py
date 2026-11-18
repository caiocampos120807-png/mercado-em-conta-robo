import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from relatorio_negocio import construir

D=date(2026,11,18)
FIELDS=['produto','marca','tamanho','unidade','categoria','mercado','cidade','uf','preco','atualizado','link']

def row(prod,store,city,price,url_suffix):
    return dict(produto=prod,marca='Camil',tamanho='5',unidade='kg',categoria='Mercearia',mercado=store,cidade=city,uf='SP',preco=str(price),atualizado=D.isoformat(),link=f'https://www.paodeacucar.com/{url_suffix}')

class ReportTest(unittest.TestCase):
    def write(self,base,rows):
        with (Path(base)/'precos.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    def test_compare_only_same_city(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d,[row('Arroz','Loja A','São Paulo',19,'a'),row('Arroz','Loja B','São Paulo',18,'b'),row('Arroz','Loja C','Campinas',17,'c')])
            result=construir(d,D)
            self.assertEqual(result['comparacoes_possiveis_por_cidade'],1)
            self.assertEqual(result['cidades'][0]['produtos_comparaveis'],0)
            self.assertEqual(result['cidades'][1]['produtos_comparaveis'],1)
    def test_prices_not_invented_and_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            r=row('Arroz','Loja A','São Paulo',19,'a')
            self.write(d,[r,r])
            result=construir(d,D)
            self.assertEqual(result['ofertas_validadas'],1)
            self.assertEqual(result['mercados_com_precos'],1)
            saved=json.loads((Path(d)/'relatorio_negocio.json').read_text())
            self.assertEqual(saved['ofertas_validadas'],1)
    def test_reject_future_bad_and_old(self):
        with tempfile.TemporaryDirectory() as d:
            future=row('Arroz','Loja A','São Paulo',19,'future');future['atualizado']='2026-11-25'
            old=row('Arroz','Loja B','São Paulo',20,'old');old['atualizado']='2026-11-10'
            valid=row('Feijão','Loja C','Campinas',15,'new')
            self.write(d,[future,old,valid])
            result=construir(d,D)
            self.assertEqual(result['ofertas_validadas'],1)
            self.assertEqual(result['registros_rejeitados'],2)
    def test_conflict_same_url_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d,[row('Arroz','Loja A','São Paulo',18,'same'),row('Arroz','Loja A','São Paulo',19,'same')])
            result=construir(d,D)
            self.assertEqual(result['ofertas_validadas'],0)
            self.assertEqual(result['registros_rejeitados'],1)
    def test_missing_csv(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):construir(d,D)

if __name__=='__main__':unittest.main()
