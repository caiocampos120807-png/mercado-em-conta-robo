import unittest
import cesta_familia as fam

class TestCestaFamilia(unittest.TestCase):
    def test_basicos_prioritarios(self):
        for item in ['Arroz Branco Camil 5kg','Feijão Carioca Camil 1kg','Leite Integral Parmalat 1L',
                     'Óleo de Soja Liza 900ml','Café Pilão 500g','Detergente Ypê 500ml']:
            self.assertGreaterEqual(fam.priority(item),85,item)
    def test_itens_sem_relevancia(self):
        for item in ['Salsicha 500g','Azeite Especial 500ml','Sorvete Premium 2L',
                     'Cobertura para bolo 1kg','Relógio de pulso']:
            self.assertEqual(fam.priority(item),0,item)
    def test_leite_condensado_nao_e_leite_uht(self):
        self.assertEqual(fam.priority('Leite Condensado Moça 395g'),0)
    def test_item_e_mercado_com_a_mesma_sku(self):
        row={'produto':'Arroz branco','marca':'Camil','tamanho':5,'unidade':'kg','mercado':'Pão de Açúcar'}
        state={'row':{'produto':'Arroz branco','marca':'Camil','tamanho':5,'unidade':'kg','mercado':'Extra'}}
        value=fam.score_product('https://www.extramercado.com.br/produto/22/arroz-branco-camil-5kg',state,[row])
        self.assertGreaterEqual(value,180)
    def test_compra_prioridade_mais_alta(self):
        rows={
            'https://www.extramercado.com.br/produto/10/arroz-camil-5kg':{'last':'','row':None},
            'https://www.extramercado.com.br/produto/15/sorvete-2l':{'last':'','row':None},
        }
        order=fam.prioritize_queue(rows,rows)
        self.assertIn('arroz',order[0])
    def test_relatorio_sem_dobrar_preco(self):
        data=[{'produto':'Arroz branco','mercado':'Pão de Açúcar'}, {'produto':'Arroz branco','mercado':'Sonda'},
              {'produto':'Shampoo','mercado':'Sonda'}]
        r=fam.report(data)
        self.assertEqual(next(a for a in r if a['item']=='Arroz')['mercados'],2)
        self.assertEqual(next(a for a in r if a['item']=='Shampoo')['ofertas'],1)

if __name__=='__main__':unittest.main()
