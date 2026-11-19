#!/usr/bin/env python3
"""Fail-safe para não publicar uma coleta catastrófica como se fosse normal.

A proteção compara ofertas recentes do commit anterior com as do CSV novo.
Não congela a data: o site rejeita preços com mais de 2 dias.
Em falha, o workflow termina vermelho, sem commit dos arquivos alterados.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from gerar_indicadores import audit_row, authorized_hosts

BASE = Path(__file__).resolve().parent


def checked_rows(csv_text, today=None, hosts=None):
    try:
        reader=csv.DictReader(io.StringIO(csv_text))
        if not reader.fieldnames or not {'produto','preco','atualizado','link'}.issubset(reader.fieldnames):
            return []
        found={}
        for item in reader:
            row,error=audit_row(item,today,hosts)
            if row: found[row['link']]=row
        return list(found.values())
    except (ValueError,TypeError,KeyError,csv.Error):
        return []


def evaluate(before,after, today=None, hosts=None):
    old=checked_rows(before,today,hosts)
    new=checked_rows(after,today,hosts)
    a,b=len(old),len(new)
    # Bloqueia apenas queda extrema. Quedas moderadas viram alertas na auditoria.
    if a>0 and b==0:
        return False, f'A coleta nova tem 0 ofertas válidas, contra {a} antes.'
    if a>=20 and b < max(3,int(a*.25)):
        return False, f'Queda extrema de cobertura: {a} -> {b} ofertas recentes.'
    if b==0:
        return True, 'Nenhuma oferta recente; dados antigos não poderão ser apresentados como atuais.'
    return True, f'Validação passou: {a} -> {b} ofertas recentes.'


def run(base=BASE, previous_csv=None, today=None):
    base=Path(base); today=today or date.today()
    new=(base/'precos.csv').read_text(encoding='utf-8-sig')
    if previous_csv is None:
        result=subprocess.run(['git','show','HEAD:precos.csv'], cwd=base, text=True,capture_output=True,check=False)
        previous_csv=result.stdout if result.returncode==0 else ''
    hosts=authorized_hosts(base)
    ok,message=evaluate(previous_csv,new,today,hosts)
    output={'schema':1,'validado_em_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'pode_publicar':ok,'resultado':message,'regra':'Bloqueia CSV vazio ou perda >=75% das ofertas recentes quando havia pelo menos 20 antes. Não mantém preços antigos como atuais.'}
    (base/'validacao_publicacao.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('GATE DE PUBLICAÇÃO:',message)
    return ok

if __name__=='__main__':
    if not run():
        raise SystemExit('Publicação bloqueada para proteger preços do site')
