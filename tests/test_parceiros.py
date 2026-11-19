import csv
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import coletar_parceiros as p
from gerar_indicadores import authorized_hosts, audit_row

TODAY=date(2026,11,18)
URL='https://docs.google.com/spreadsheets/d/e/publicada/pub?output=csv'
MARKET='Mercado Local (online)'
HOST='mercadolocal.example'
PARTNER={'mercado':MARKET,'cidade':'São Paulo','uf':'SP','url_csv':URL,
         'dominios_produtos':[HOST], 'autorizado':True,'ativo':True}
ROW={'produto':'Arroz branco','marca':'Camil','tamanho':'5','unidade':'kg',
     'categoria':'Mercearia','mercado':MARKET,'cidade':'São Paulo','uf':'SP',
     'preco':'27.80','atualizado':TODAY.isoformat(),'link':f'https://{HOST}/produtos/arroz-5kg'}

def make_csv(rows):
    s=io.StringIO(); w=csv.DictWriter(s,fieldnames=p.COLUMNS);w.writeheader();w.writerows(rows);return s.getvalue()


class PartnerTests(unittest.TestCase):
    def test_only_authorized_enabled_partner(self):
        self.assertTrue(p.valid_partner(PARTNER))
        for k in ('autorizado','ativo'):
            a=dict(PARTNER);a[k]=False
            self.assertFalse(p.valid_partner(a))

    def test_url_rejects_unsafe_hosts_and_auth(self):
        for url in ('http://docs.google.com/a.csv', 'https://evil.example/catalog.csv',
                    'https://127.0.0.1/a.csv','https://user:pw@docs.google.com/a.csv',
                    'https://docs.google.com/a.csv#secret'):
            self.assertFalse(p.safe_url(url))
        self.assertTrue(p.safe_url(URL))

    def test_partner_valid_row(self):
        item,err=p.normalize_row(ROW,PARTNER,TODAY)
        self.assertEqual(err,'')
        self.assertEqual(item['preco'],27.8)

    def test_wrong_market_city_or_domain_rejected(self):
        for change in ({'mercado':'Outro mercado'},{'cidade':'Campinas'},{'link':'https://evil.example/item'}):
            row={**ROW,**change};result,reason=p.normalize_row(row,PARTNER,TODAY)
            self.assertIsNone(result); self.assertTrue(reason)

    def test_stale_and_injection_rejected(self):
        for change in ({'atualizado':'2026-11-10'}, {'produto':'=HYPERLINK("https://evil")'}):
            row={**ROW,**change};result,reason=p.normalize_row(row,PARTNER,TODAY)
            self.assertIsNone(result);self.assertTrue(reason)

    def test_csv_parser_rejects_missing_columns_and_garbage(self):
        with self.assertRaises(ValueError):p.parse_rows('produto,preco\na,12\n')
        with self.assertRaises(ValueError):p.parse_rows('')
        self.assertEqual(len(p.parse_rows(make_csv([ROW]))),1)

    def test_integration_with_real_base_and_auditor(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            (base/'parceiros-fontes.json').write_text(json.dumps({'parceiros':[PARTNER]}),encoding='utf-8')
            (base/'precos.csv').write_text(make_csv([]),encoding='utf-8')
            report=p.run(base,now=TODAY,download=lambda _:make_csv([ROW]))
            self.assertEqual(report['ofertas_validas_importadas'],1)
            self.assertEqual(len(p.parse_rows((base/'precos.csv').read_text())),1)
            self.assertIn(HOST,authorized_hosts(base))
            self.assertIsNotNone(audit_row(ROW,TODAY,authorized_hosts(base))[0])

    def test_fetch_failure_keeps_old_catalogue(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            (base/'parceiros-fontes.json').write_text(json.dumps({'parceiros':[PARTNER]}),encoding='utf-8')
            original=make_csv([ROW])
            (base/'precos.csv').write_text(original,encoding='utf-8')
            report=p.run(base,now=TODAY,download=lambda _:(_ for _ in ()).throw(ValueError('falha de rede')))
            self.assertEqual(report['ofertas_validas_importadas'],0)
            self.assertEqual((base/'precos.csv').read_text(),original.replace('\r\n','\n'))
            self.assertEqual(report['redes'][0]['status'],'falha')

    def test_feed_from_unapproved_partner_doesnt_call_network(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            (base/'parceiros-fontes.json').write_text(json.dumps({'parceiros':[{**PARTNER,'autorizado':False}]}))
            (base/'precos.csv').write_text(make_csv([]))
            report=p.run(base,now=TODAY,download=lambda _:self.fail('Não deveria buscar URL'))
            self.assertEqual(report['ofertas_validas_importadas'],0)

if __name__=='__main__':unittest.main()
