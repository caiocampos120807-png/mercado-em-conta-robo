#!/usr/bin/env python3
"""Integra feeds CSV AUTORIZADOS pelos respectivos supermercados (sem custos de API).

A configuração começa vazia. Nenhuma loja é contada até fornecer consentimento,
CSV com link público e produtos válidos. Sem login, scraping nem anúncios falsos.
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from gerar_indicadores import audit_row, authorized_hosts
from expandir_catalogo import read_csv, write_csv

HERE = Path(__file__).resolve().parent
MAX_BYTES = 3_000_000
MAX_ROWS = 5000
MAX_FEEDS = 20
FEED_HOSTS = {'docs.google.com', 'raw.githubusercontent.com', 'github.com'}
# Redirecionamentos do Google Sheets para arquivos CSV públicos.
GOOGLE_FEED_SUFFIX = '.googleusercontent.com'
COLUMNS = ['produto','marca','tamanho','unidade','categoria','mercado','cidade','uf','preco','atualizado','link']


def host_valid(host, allow_google_redirect=False):
    h=(host or '').lower().rstrip('.')
    return h in FEED_HOSTS or (allow_google_redirect and h.endswith(GOOGLE_FEED_SUFFIX) and h != GOOGLE_FEED_SUFFIX[1:])


def safe_url(url, feed=True, extra_hosts=()):
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or p.username or p.password or p.port or not p.hostname or p.fragment:
            return False
        if len(url)>1800 or len(p.path)>1100:
            return False
        if feed:
            return host_valid(p.hostname,True)
        return p.hostname.lower().rstrip('.') in extra_hosts
    except (ValueError,TypeError,AttributeError):
        return False


class RestrictedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl,True):
            raise ValueError('redirecionamento do CSV para host não permitido')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_csv(url, opener=None):
    if not safe_url(url,True):
        raise ValueError('URL do feed não autorizada')
    opener=opener or build_opener(RestrictedRedirect())
    req=Request(url,headers={'User-Agent':'MercadoEmConta-Parceiros/1.0 (feed autorizado)', 'Accept':'text/csv,text/plain;q=0.8'})
    with opener.open(req, timeout=20) as resp:
        if not safe_url(resp.url,True):
            raise ValueError('URL final do feed não autorizada')
        raw=resp.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise ValueError('CSV do parceiro acima de 3 MB')
        mime=resp.headers.get('Content-Type','')
        if mime and not any(t in mime.lower() for t in ('csv','text/plain','octet-stream')):
            raise ValueError('resposta não é CSV')
        return raw.decode('utf-8-sig')


def parse_rows(text):
    if len(text.encode('utf-8'))>MAX_BYTES:
        raise ValueError('CSV maior que o limite')
    if not text.strip():
        raise ValueError('CSV vazio')
    first=text.splitlines()[0]
    delim=';' if first.count(';')>first.count(',') else ','
    reader=csv.DictReader(io.StringIO(text),delimiter=delim)
    if not reader.fieldnames or set(COLUMNS)-set(reader.fieldnames):
        raise ValueError('CSV sem todas as colunas exigidas')
    result=[]
    for row in reader:
        if len(result)>=MAX_ROWS: raise ValueError('CSV acima do limite de 5.000 produtos')
        if None in row or any(x is None for x in row.values()):
            raise ValueError('CSV com campos extras ou quebrados')
        result.append({k:str(row.get(k,'')).strip() for k in COLUMNS})
    return result


def valid_partner(item):
    if not isinstance(item,dict) or item.get('autorizado') is not True or item.get('ativo') is not True:
        return False
    hosts=item.get('dominios_produtos')
    if (not isinstance(hosts,list) or not hosts or len(hosts)>5 or
            any(not isinstance(h,str) or not h or h!=h.lower() or '/' in h or ':' in h or h.startswith('.') for h in hosts)):
        return False
    return (safe_url(item.get('url_csv'),True) and
            all(isinstance(item.get(k),str) and 1<=len(item[k])<=110 for k in ('mercado','cidade','uf')) and
            len(item['uf'])==2)


def normalize_row(row,item,today):
    if any(row[k].strip() != item[k].strip() for k in ('mercado','cidade','uf')):
        return None, 'loja ou cidade divergente'
    # Garante que produtos levam ao domínio OFICIAL especificado pelo proprietário.
    if not safe_url(row['link'],False,set(item['dominios_produtos'])):
        return None, 'link fora do domínio autorizado'
    # Evita CSV formula injection ao exportar ofertas para planilhas de terceiros.
    for k in ('produto','marca','categoria','mercado','cidade'):
        if row[k].lstrip().startswith(('=','+','-','@','\t','\r','\n')):
            return None, 'texto que pode ser executado em planilhas'
    allowed=authorized_hosts(None, extra=item['dominios_produtos'])
    out,reason=audit_row(row,today,allowed)
    return out,reason


def run(base=HERE, now=None, download=fetch_csv):
    base=Path(base)
    today=now or date.today()
    path=base/'parceiros-fontes.json'
    config=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'parceiros': []}
    feeds=config.get('parceiros',[])
    if not isinstance(feeds,list) or len(feeds)>MAX_FEEDS:
        raise ValueError('Configuração de parceiros inválida ou acima do limite')
    current=read_csv(base/'precos.csv')
    merged={r['link']:r for r in current if r.get('link')}
    seen=set();status=[];collected=0
    for item in feeds:
        name=str(item.get('mercado','?'))[:110] if isinstance(item,dict) else '?'
        rec={'mercado':name,'status':'inativo','ofertas':0,'motivo':''}
        if not valid_partner(item):
            rec['motivo']='configuração incompleta ou ainda sem autorização comprovada'
            status.append(rec)
            continue
        if item['url_csv'] in seen:
            rec['motivo']='feed duplicado'
            status.append(rec)
            continue
        seen.add(item['url_csv'])
        try:
            rows=parse_rows(download(item['url_csv']))
            rejects=Counter();count=0
            for row in rows:
                v,err=normalize_row(row,item,today)
                if not v:
                    rejects[err]+=1;continue
                # Fonte explicitamente autorizada pode atualizar uma oferta existente.
                merged[v['link']]=v
                count+=1
            rec['status']='ok' if count else 'sem_ofertas_validas'
            rec['ofertas']=count
            rec['rejeitados']=sum(rejects.values())
            rec['motivo']='; '.join(f'{k}: {n}' for k,n in rejects.most_common(3))
            collected+=count
        except (ValueError,TypeError,OSError,HTTPError,URLError,UnicodeError,csv.Error) as e:
            rec['status']='falha'
            rec['motivo']=str(e)[:150]
        status.append(rec)
    # Conector não altera a base quando não há novos preços válidos.
    if collected:
        write_csv(base/'precos.csv',list(merged.values()))
    output={'data':today.isoformat(),'parceiros_configurados':len(feeds),
            'ofertas_validas_importadas':collected,'redes':status,
            'aviso':'Só incluir feeds de mercados que deram autorização. Uma fonte configurada não significa parceria contratada.'}
    (base/'parceiros-status.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PARCEIROS: {len(feeds)} feeds configurados; {collected} ofertas válidas confirmadas.')
    return output


if __name__=='__main__':
    run()
