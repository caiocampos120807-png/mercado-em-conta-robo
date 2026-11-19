import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from preservar_precos import merge,run
from expandir_catalogo import write_csv,read_csv

def example(name,price,days=0,market='A'):
    return dict(produto=name,marca='Camil',tamanho='5',unidade='kg',categoria='Mercearia',mercado=market,
        cidade='São Paulo',uf='SP',preco=str(price),atualizado=(date.today()-timedelta(days=days)).isoformat(),
        link=f'https://example.com/{market}/{name}')

class TestArquivo(unittest.TestCase):
    def test_nao_perde_preco_atual_em_erro_de_coleta(self):
        old=[example('Arroz',25),example('Feijao',10)]
        current,history=merge(old,[],[])
        self.assertEqual(len(current),2);self.assertEqual(len(history),2)
    def test_nao_revalida_preco_vencido(self):
        old=[example('Arroz',25,8)]
        current,history=merge(old,[],[])
        self.assertEqual(len(current),0);self.assertEqual(len(history),1)
        self.assertEqual(history[0]['atualizado'],old[0]['atualizado'])
    def test_nao_perde_produto_antigo_quando_entra_novo(self):
        old=[example('Arroz',25,8)]
        newer=[example('Feijao',9)]
        current,history=merge(old,newer,[])
        self.assertEqual(len(current),1);self.assertEqual(len(history),2)
    def test_preco_novo_substitui_sem_duplicar(self):
        old=[example('Arroz',25,1)]
        newer=[example('Arroz',22)]
        current,history=merge(old,newer,[])
        self.assertEqual(len(current),1);self.assertEqual(len(history),1)
        self.assertEqual(current[0]['preco'],'22')
    def test_arquivo_nao_perde_ultimo_registro(self):
        old=[example('Arroz',25,6)]
        current,history=merge([],[],old)
        self.assertEqual(len(current),0);self.assertEqual(len(history),1)
    def test_salva_sem_precos_falsos(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            write_csv(base/'precos.csv',[example('Arroz',23)])
            st=run(base,previous=[example('Feijao',11)])
            self.assertEqual(st['ofertas_ativas'],2)
            self.assertEqual(len(read_csv(base/'catalogo_historico.csv')),2)
    def test_preco_futuro_nao_fica_atual(self):
        old=[example('Arroz',25,-3)]
        current,history=merge(old,[],[])
        self.assertEqual(len(current),0)
    def test_url_insegura_rejeitada(self):
        row=example('Arroz',25)
        row['link']='http://example.com/arroz'
        current,history=merge([row],[],[])
        self.assertEqual(current,[])
        self.assertEqual(history,[])

if __name__=='__main__':unittest.main()
