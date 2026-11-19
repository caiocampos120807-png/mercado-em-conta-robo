import csv,io,sys,tempfile,unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import avaliar_publicacao as g

TODAY=date(2026,11,18)

def feed(n):
    s=io.StringIO()
    w=csv.DictWriter(s,fieldnames=['produto','marca','tamanho','unidade','categoria','mercado','cidade','uf','preco','atualizado','link'])
    w.writeheader()
    for i in range(n):
        w.writerow({'produto':f'Arroz branco {i}','marca':'Camil','tamanho':5,'unidade':'kg','categoria':'Mercearia','mercado':'Pão de Açúcar','cidade':'São Paulo','uf':'SP','preco':'25.50','atualizado':TODAY.isoformat(),'link':f'https://www.paodeacucar.com/produto/{i}/arroz'})
    return s.getvalue()

class GateTests(unittest.TestCase):
    def test_zero_after_valid_data_is_blocked(self):
        ok,_=g.evaluate(feed(8),feed(0),TODAY)
        self.assertFalse(ok)

    def test_extreme_coverage_drop_is_blocked(self):
        ok,_=g.evaluate(feed(100),feed(12),TODAY)
        self.assertFalse(ok)

    def test_normal_drop_is_allowed(self):
        ok,_=g.evaluate(feed(100),feed(82),TODAY)
        self.assertTrue(ok)

    def test_expansion_allowed(self):
        ok,_=g.evaluate(feed(3),feed(30),TODAY)
        self.assertTrue(ok)

    def test_expired_old_prices_not_preserved_as_current(self):
        old=feed(12).replace('2026-11-18','2020-01-01')
        ok,_=g.evaluate(old,feed(0),TODAY)
        self.assertTrue(ok)

    def test_file_report_is_generated(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            (base/'precos.csv').write_text(feed(20),encoding='utf-8')
            self.assertTrue(g.run(base,previous_csv=feed(21),today=TODAY))
            self.assertIn('"pode_publicar": true',(base/'validacao_publicacao.json').read_text())

if __name__=='__main__':unittest.main()
