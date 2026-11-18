import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coletar import parse_price, br_price, name_matches

P = {'produto':'Arroz branco', 'marca':'Camil', 'tamanho':5,'unidade':'kg','tipo':'pao'}
S = {'produto':'Feijão carioca', 'marca':'Camil','tamanho':1,'unidade':'kg','tipo':'sonda'}
L = {'produto':'Leite integral','marca':'Parmalat','tamanho':1,'unidade':'l','tipo':'sonda'}

class TestPreco(unittest.TestCase):
    def test_pao(self):
        html = '<html><body>R$ 0,00 carrinho<h1>Arroz Agulhinha Tipo 1 CAMIL Pacote 5kg</h1><p>Cód.: 0791595</p><p>R$ 23,99</p><p>Preço por 1kg - R$ 4,79</p></body></html>'
        self.assertEqual(parse_price(html, P), 23.99)
    def test_sonda(self):
        html = '<html><body><p>Subtotal R$ 0,00</p><h3>Feijão Carioca Camil 1kg</h3><p>Por R$ 10,55</p></body></html>'
        self.assertEqual(parse_price(html, S), 10.55)
    def test_leite(self):
        html = '<h3>Leite longa vida integral Parmalat 1 Litro</h3><p>Por R$ 7,03</p>'
        self.assertEqual(parse_price(html,L), 7.03)
    def test_no_price(self):
        with self.assertRaises(ValueError):
            parse_price('<h3>Feijão Carioca Camil 1kg</h3><p>Sem estoque</p>', S)
    def test_no_wrong_product(self):
        with self.assertRaises(ValueError):
            parse_price('<h1>Arroz Camil Integral 5kg</h1><p>Cód.: 123</p><p>R$ 16,99</p>', P)
    def test_no_wrong_size(self):
        with self.assertRaises(ValueError):
            parse_price('<h3>Feijão Carioca Camil 2kg</h3><p>Por R$ 10,55</p>', S)
    def test_currency(self):
        self.assertEqual(br_price('1.234,56'), 1234.56)
        self.assertIsNone(br_price('0,00'))
        self.assertTrue(name_matches('Arroz Agulhinha Tipo 1 CAMIL Pacote 5kg', P))

if __name__=='__main__':
    unittest.main()

class TestFluxo(unittest.TestCase):
    def test_workflow_writes_csv_with_real_price(self):
        import tempfile, json
        from unittest.mock import patch
        import coletar
        conf = {'fontes': [{'produto':'Feijão carioca', 'marca':'Camil', 'tamanho':1, 'unidade':'kg',
            'categoria':'Mercearia', 'mercado':'Sonda (online)', 'cidade':'São Paulo',
            'uf':'SP', 'tipo':'sonda', 'url':'https://www.sondadelivery.com.br/delivery/produto/teste'}]}
        fixture='<h3>Feijão Carioca Camil 1kg</h3><span>Por R$ 10,55</span>'
        with tempfile.TemporaryDirectory() as path:
            c = Path(path) / 'fontes.json'; c.write_text(json.dumps(conf), encoding='utf-8')
            with patch('coletar.allowed_by_robots', return_value=(True,'')), patch('coletar.get_text', return_value=fixture):
                report=coletar.run(config_path=c,base=path,pause=0)
            self.assertEqual(report['precos_coletados'],1)
            csvfile = (Path(path)/'precos.csv').read_text(encoding='utf-8')
            self.assertIn('10.55',csvfile)
            self.assertNotIn('23.99',csvfile)
            self.assertIn('status.json', [f.name for f in Path(path).iterdir()])

    def test_workflow_removes_old_prices_on_failure(self):
        import tempfile, json
        from unittest.mock import patch
        import coletar
        conf = {'fontes': [{'produto':'Feijão carioca', 'marca':'Camil', 'tamanho':1, 'unidade':'kg',
            'categoria':'Mercearia', 'mercado':'Sonda (online)', 'cidade':'São Paulo',
            'uf':'SP', 'tipo':'sonda', 'url':'https://www.sondadelivery.com.br/delivery/produto/teste'}]}
        with tempfile.TemporaryDirectory() as path:
            folder=Path(path)
            (folder/'precos.csv').write_text('R$ 19,99 PREÇO ANTIGO', encoding='utf-8')
            c=folder/'fontes.json';c.write_text(json.dumps(conf),encoding='utf-8')
            with patch('coletar.allowed_by_robots',return_value=(False,'Robots bloqueou')):
                report=coletar.run(config_path=c,base=path,pause=0)
            self.assertEqual(report['precos_coletados'],0)
            self.assertEqual(report['fontes_indisponiveis'],1)
            self.assertNotIn('PREÇO ANTIGO',(folder/'precos.csv').read_text(encoding='utf-8'))
