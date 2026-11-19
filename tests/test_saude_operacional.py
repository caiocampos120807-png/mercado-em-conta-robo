import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from saude_operacional import montar

HEADER = ['produto','marca','tamanho','unidade','categoria','mercado','cidade','uf','preco','atualizado','link']


def offer(price='12.40', market='Sonda', city='São Paulo', item='Arroz branco', url='https://www.sondadelivery.com.br/arroz-camil-5kg'):
    return {'produto': item, 'marca':'Camil', 'tamanho':'5', 'unidade':'kg', 'categoria':'Mercearia',
            'mercado':market,'cidade':city,'uf':'SP','preco':price,'atualizado':date.today().isoformat(), 'link':url}


def write(path, offers):
    with (path / 'precos.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(offers)


class TestMonitor(unittest.TestCase):
    def test_sem_ofertas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write(base, [])
            result = montar(base)
            self.assertEqual(result['estado'], 'sem_ofertas')
            self.assertEqual(result['ofertas_validas'], 0)
            self.assertTrue((base / 'saude_operacional.json').exists())

    def test_comparacao_apenas_na_mesma_cidade(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write(base, [offer(), offer('14.40', 'Pão de Açúcar', 'São Paulo', url='https://www.paodeacucar.com/arroz-camil-5kg'),
                         offer('13.20', 'Pão de Açúcar', 'Campinas', url='https://www.paodeacucar.com/arroz-camil-5kg-camp')])
            result = montar(base)
            self.assertEqual(result['ofertas_validas'], 3)
            self.assertEqual(result['redes_ativas'], 2)
            self.assertEqual(result['produtos_comparaveis_mesma_cidade'], 1)
            self.assertEqual(result['comparacoes_por_cidade']['Campinas / SP'], 0)

    def test_url_contraditoria_descartada(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write(base, [offer(), offer(price='99.90')])
            result = montar(base)
            self.assertEqual(result['ofertas_validas'], 0)
            self.assertEqual(result['ofertas_rejeitadas'], 1)
            self.assertIn('URL contraditória', result['motivos_rejeicao'])

    def test_nao_publica_preco_velho(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            p = offer()
            p['atualizado'] = (date.today() - timedelta(days=6)).isoformat()
            write(base, [p])
            result = montar(base)
            self.assertEqual(result['ofertas_validas'], 0)
            self.assertEqual(result['estado'], 'sem_ofertas')

    def test_queda_alertada(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write(base, [offer()])
            (base / 'saude_operacional.json').write_text(json.dumps({'ofertas_validas': 8}), encoding='utf-8')
            result = montar(base)
            self.assertEqual(result['queda_vs_anterior_percentual'], 87.5)
            self.assertTrue(any('caiu' in aviso for aviso in result['avisos']))


if __name__ == '__main__':
    unittest.main()
