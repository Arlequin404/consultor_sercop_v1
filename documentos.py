"""Lectura conservadora de enlaces publicados por el SERCOP."""
import html, http.cookiejar, os, re, tempfile, unicodedata, urllib.parse, urllib.request, zipfile, random, time
from html.parser import HTMLParser
from urllib.error import URLError

BASE='https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/'
DOMINIOS={'www.compraspublicas.gob.ec','compraspublicas.gob.ec','portal.compraspublicas.gob.ec'}
MAX_DOCUMENTO=30*1024*1024
MAX_TOTAL=150*1024*1024

def url_segura(value,base=BASE,detalle=False):
    if not isinstance(value,str): return None
    value=html.unescape(value).strip()
    if not value or re.search(r'[<>"\s]',value) or value.lower().startswith(('javascript:','data:','#','mailto:')):return None
    parsed=urllib.parse.urlsplit(urllib.parse.urljoin(base,value))
    try:port=parsed.port
    except ValueError:return None
    if parsed.scheme!='https' or parsed.hostname not in DOMINIOS or parsed.username or parsed.password or port not in (None,443):return None
    if detalle and not parsed.path.lower().endswith('/ncoregistrodetalle.cpe'):return None
    return urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,parsed.query,''))

class Anchors(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='a':
            a=dict(attrs);self.links.append(a.get('href',''))

def detalle_de_registro(row):
    for key in ('url','detalle','url_detalle','link','href'):
        value=row.get(key)
        if not isinstance(value,str):continue
        direct=url_segura(value,detalle=True)
        if direct:return direct
        parser=Anchors();parser.feed(value)
        for candidate in parser.links:
            target=url_segura(candidate,detalle=True)
            if target:return target
    return None

class SectionParser(HTMLParser):
    def __init__(self,base):super().__init__(convert_charrefs=True);self.base=base;self.in_section=False;self.done=False;self.current=None;self.items=[];self.text=''
    def handle_data(self,data):
        low=' '.join(data.lower().split())
        if 'documentos anexos' in low:self.in_section=True
        if self.in_section and low in ('proveedores','funcionario encargado','acciones del proceso'):self.done=True
        if self.current is not None:self.current['name']+=' '+data
    def handle_starttag(self,tag,attrs):
        if not self.in_section or self.done:return
        attrs=dict(attrs)
        if tag.lower()=='a':
            href=attrs.get('href','')
            # Solo enlaces explícitos o URL literal en window.open; no ejecuta JavaScript.
            if not href or href.lower().startswith('javascript:'):
                text=attrs.get('onclick','')+' '+href
                match=re.search(r"(?:open|location(?:\.href)?)\s*\(?\s*['\"]([^'\"]+)['\"]",text,re.I)
                href=match.group(1) if match else ''
            target=url_segura(href,self.base)
            if target:self.current={'url':target,'name':attrs.get('title','')}
    def handle_endtag(self,tag):
        if tag.lower()=='a' and self.current:
            self.current['name']=' '.join(self.current['name'].split()) or 'Documento';self.items.append(self.current);self.current=None

def es_navegacion(item):
    name=''.join(c for c in unicodedata.normalize('NFKD',item.get('name','').casefold()) if not unicodedata.combining(c))
    name=' '.join(name.split())
    path=urllib.parse.urlsplit(item['url']).path.casefold()
    # Enlaces de navegación del formulario, no anexos descargables.
    return name in {'regresar','atras','volver','enviar proforma','presentar proforma','inicio'} or path.endswith(('/frmncoformulario.cpe','/frmncoproformaingreso.cpe','/frmncolistado.cpe','/ncoregistrodetalle.cpe'))

def documentos_html(text,base):
    p=SectionParser(base);p.feed(text)
    return list({x['url']:x for x in p.items if not es_navegacion(x)}.values())

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not url_segura(newurl,req.full_url):raise URLError('El portal redirigió a un dominio no permitido.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def cliente():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),SafeRedirect())

def obtener_documentos(url):
    url=url_segura(url,detalle=True)
    if not url:raise ValueError('Usa una dirección HTTPS del detalle de una necesidad del SERCOP.')
    client=cliente();req=urllib.request.Request(url,headers={'User-Agent':'ConsultasSERCOP/1.0','Accept':'text/html'})
    with client.open(req,timeout=30) as resp:
        if 'html' not in resp.headers.get('Content-Type','').lower():raise ValueError('El portal no devolvió la página del proceso.')
        raw=resp.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError('La página del proceso es demasiado grande.')
        charset=resp.headers.get_content_charset() or 'utf-8';page=raw.decode(charset,errors='replace');base=resp.geturl()
    if re.search(r'captcha|iniciar sesi[oó]n|verificaci[oó]n de seguridad',page,re.I):raise ValueError('El portal solicita verificación o inicio de sesión. Abre el proceso en el navegador.')
    return client,documentos_html(page,base)

def download_zip(client,docs,path):
    if not docs:raise ValueError('No hay documentos para descargar.')
    temp=None;errors=[];count=0;total=0
    try:
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(os.path.abspath(path)),suffix='.tmp',delete=False) as f:temp=f.name
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as out:
            for index,doc in enumerate(docs,1):
                if index>1:time.sleep(random.uniform(0.5,1.2))
                try:
                    target=url_segura(doc['url'])
                    if not target:raise ValueError('Enlace no permitido')
                    with client.open(urllib.request.Request(target,headers={'User-Agent':'ConsultasSERCOP/1.0'}),timeout=30) as res:
                        kind=res.headers.get('Content-Type','').lower()
                        if 'html' in kind or 'json' in kind:raise ValueError('El portal respondió con una página, no un archivo')
                        data=res.read(MAX_DOCUMENTO+1)
                        if not data or len(data)>MAX_DOCUMENTO:raise ValueError('Archivo vacío o superior a 30 MB')
                        if data.lstrip()[:64].lower().startswith((b'<!doctype html',b'<html',b'<head')):raise ValueError('El portal devolvió una página HTML en lugar del archivo')
                        total+=len(data)
                        if total>MAX_TOTAL:raise ValueError('Se superó el límite total de 150 MB')
                        cd=res.headers.get('Content-Disposition','');name=re.search(r'filename\*?=(?:UTF-8\'\')?[\"]?([^\";]+)',cd,re.I)
                        name=urllib.parse.unquote(name.group(1)) if name else (doc['name'] or 'documento')
                        name=re.sub(r'[\\/:*?"<>|\x00-\x1f]+','_',name).strip(' .')[:130] or 'documento'
                        out.writestr(f'{index:02d}_{name}',data);count+=1
                except Exception as e:errors.append(f'{doc.get("name","Documento")}: {e}')
        if not count:raise ValueError('Ningún archivo se pudo descargar. '+('; '.join(errors[:2])))
        os.replace(temp,path);temp=None
        return count,errors
    finally:
        if temp and os.path.exists(temp):os.unlink(temp)

class FichaParser(HTMLParser):
    """Conserva el texto público de la ficha sin ejecutar scripts."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'):self.skip+=1
        elif not self.skip and tag in ('p','div','tr','li','br','h1','h2','h3','h4','td','th'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.skip:self.skip-=1
        elif not self.skip and tag in ('p','div','tr','li','h1','h2','h3','h4','td','th'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip and data.strip():self.parts.append(' '.join(data.split())+' ')
    def text(self):
        return '\n'.join(x.strip() for x in ''.join(self.parts).splitlines() if x.strip())[:120000]

def obtener_ficha(url):
    url=url_segura(url,detalle=True)
    if not url:raise ValueError('Usa la dirección HTTPS del detalle de una necesidad del SERCOP.')
    client=cliente()
    req=urllib.request.Request(url,headers={'User-Agent':'ConsultasSERCOP/1.0','Accept':'text/html'})
    with client.open(req,timeout=30) as resp:
        if 'html' not in resp.headers.get('Content-Type','').lower():raise ValueError('El portal no devolvió la ficha esperada.')
        raw=resp.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError('La ficha es demasiado grande.')
        page=raw.decode(resp.headers.get_content_charset() or 'utf-8',errors='replace');base=resp.geturl()
    parser=FichaParser();parser.feed(page);texto=parser.text()
    if not texto:raise ValueError('No se pudo leer el contenido de la ficha.')
    return texto,documentos_html(page,base)

def download_folder(client,docs,directory):
    """Descarga uno a uno y conserva el nombre del servidor cuando está disponible."""
    import random,time
    if not docs:raise ValueError('No hay documentos para descargar.')
    success=[];errors=[];total=0
    for i,doc in enumerate(docs):
        if i:time.sleep(random.uniform(0.5,1.2))
        try:
            target=url_segura(doc['url'])
            if not target:raise ValueError('Enlace no permitido')
            req=urllib.request.Request(target,headers={'User-Agent':'ConsultasSERCOP/1.0'})
            with client.open(req,timeout=30) as res:
                kind=res.headers.get('Content-Type','').lower()
                if 'html' in kind or 'json' in kind:raise ValueError('El portal devolvió una página en lugar de un archivo')
                data=res.read(MAX_DOCUMENTO+1)
                if not data or len(data)>MAX_DOCUMENTO:raise ValueError('Archivo vacío o superior a 30 MB')
                if data.lstrip()[:64].lower().startswith((b'<!doctype html',b'<html',b'<head')):raise ValueError('El portal devolvió una página HTML')
                if total+len(data)>MAX_TOTAL:raise ValueError('Se superó el límite total de 150 MB')
                cd=res.headers.get('Content-Disposition','')
                found=re.search(r'filename\*?=(?:UTF-8\'\')?[\"]?([^\";]+)',cd,re.I)
                source=urllib.parse.unquote(found.group(1).strip()) if found else os.path.basename(urllib.parse.urlsplit(res.geturl()).path)
                if not source or source.lower().endswith(('.cpe','.php','.aspx')):source=doc.get('name') or 'documento'
                name=re.sub(r'[\\/:*?"<>|\x00-\x1f]+','_',source).strip(' .')[:130] or 'documento'
                if not os.path.splitext(name)[1]:
                    ext={'application/pdf':'.pdf','application/zip':'.zip','application/msword':'.doc','application/vnd.openxmlformats-officedocument.wordprocessingml.document':'.docx'}.get(kind.split(';')[0],'')
                    name+=ext
                stem,ext=os.path.splitext(name);candidate=name;n=2
                while os.path.exists(os.path.join(directory,candidate)):
                    candidate=f'{stem} ({n}){ext}';n+=1
                # x evita sobrescribir si se crea un archivo con el mismo nombre.
                with open(os.path.join(directory,candidate),'xb') as out:out.write(data)
                total+=len(data);success.append(candidate)
        except Exception as e:errors.append(f'{doc.get("name","Documento")}: {e}')
    return success,errors
