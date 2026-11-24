import csv, json, re, threading, unicodedata, urllib.request, webbrowser
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog
from documentos import detalle_de_registro, url_segura, obtener_documentos, download_zip, obtener_ficha, download_folder

URL='https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/NCORetornaRegistros.cpe?lot=1'
LISTADO='https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/NCO/FrmNCOListado.cpe'
EC=timezone(timedelta(hours=-5))
FUENTES=[
 ('Procesos','https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/SL/view/BusquedaDeProcesos.cpe'),
 ('Órdenes de compra',None),
 ('Emergencias','https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/SL/view/Emergencia/buscarResolucion.cpe'),
 ('Adquisiciones de ínfima cuantía','https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/IC/buscarInfima.cpe'),
 ('Régimen especial',None),('Procedimientos especiales',None),
 ('Necesidades y recepción de proformas',LISTADO),
 ('Convenio de pago u otro instrumento jurídico',None),('Reporte de adjudicaciones de obras',None)]
PORTAL='https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/' 
TIPOS_MONTO=(('presupuesto_referencial','Presupuesto referencial'), ('presupuestoReferencial','Presupuesto referencial'))

def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')) if not unicodedata.combining(c)).casefold()

def find_rows(value,depth=0):
    if depth>8: return []
    if isinstance(value,dict):
        if 'objeto_contratacion' in value: return [value]
        return [r for v in value.values() for r in find_rows(v,depth+1)]
    if isinstance(value,list): return [r for v in value for r in find_rows(v,depth+1)]
    return []

def deadline(value):
    try:
        date=datetime.fromisoformat(str(value).strip().replace('Z','+00:00'))
        return date.replace(tzinfo=EC) if date.tzinfo is None else date.astimezone(EC)
    except (ValueError,TypeError): return None

def active(r,now=None):
    end=deadline(r.get('fecha_limite_propuesta')); state=normalize(r.get('estado')).strip()
    return end is not None and end>(now or datetime.now(EC)) and state in ('en curso','vigente','publicada','publicado')

def amount(r):
    # Solo un campo expresamente identificado como presupuesto. Un valor unitario no es un presupuesto.
    for key,label in TIPOS_MONTO:
        raw=r.get(key)
        if raw is None or isinstance(raw,bool): continue
        try:
            text=str(raw).strip().replace('$','').replace(' ','')
            if not re.fullmatch(r'\d+(?:\.\d+)?',text): continue
            value=Decimal(text)
            if value>0 and value.is_finite(): return value,label
        except InvalidOperation: continue
    return None,None

def match(row,filters,now):
    query=normalize(filters['word']).strip(); mode=filters.get('mode','Todas las palabras')
    words=[v.strip() for v in query.split(',') if v.strip()] if mode=='Cualquiera (separar con comas)' else query.split()
    hay=normalize(' '.join(str(row.get(k) or '') for k in ('objeto_contratacion','codigo_contratacion','razon_social','email_encargado','funcionario_encargado','cpc','descripcion_cpc')))
    if mode=='Frase exacta' and query and query not in hay: return False
    if mode=='Todas las palabras' and not all(w in hay for w in words): return False
    if mode=='Cualquiera (separar con comas)' and words and not any(w in hay for w in words): return False
    if filters['only'] and not active(row,now): return False
    for field,key in [('province','provincia'),('kind','tipo_necesidad'),('state','estado')]:
        value=filters[field]
        if value and value!='Todos' and normalize(value)!=normalize(row.get(key) or ''): return False
    days=filters['days']
    if days is not None:
        end=deadline(row.get('fecha_limite_propuesta'))
        if end is None or not (timedelta(0)<end-now<=timedelta(days=days)): return False
    low,high=filters['low'],filters['high']
    if low is not None or high is not None:
        value,_=amount(row)
        if value is None: return filters['unknown']
        if (low is not None and value<low) or (high is not None and value>high):return False
    return True

def parse_decimal(text):
    text=text.strip().replace(',','.')
    if not text:return None
    try:
        v=Decimal(text)
        if not v.is_finite() or v<0: raise ValueError
        return v
    except (InvalidOperation,ValueError):raise ValueError('Ingresa montos válidos, por ejemplo 5000 o 1250.50.')

class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('Buscador de necesidades SERCOP - Etapa 2');self.geometry('1250x760');self.minsize(860,560)
        self.rows=[];self.filtered=[]; self.fetching=False; self.doc_counts={}; self.doc_cliente=None; self.docs=[]; self.doc_iid=None; self.doc_url=None
        self.dark=False;self.configure(bg='#f2f6f7');style=ttk.Style(self);self.ui_style=style
        try:style.theme_use('clam')
        except tk.TclError:pass
        style.configure('.',font=('Segoe UI',10),background='#f2f6f7',foreground='#18333d');style.configure('TFrame',background='#f2f6f7');style.configure('TLabel',background='#f2f6f7');style.configure('TLabelframe',background='#f2f6f7');style.configure('TLabelframe.Label',font=('Segoe UI',10,'bold'));style.configure('TButton',padding=(10,7));style.configure('Accent.TButton',background='#087c70',foreground='white',padding=(12,8));style.map('Accent.TButton',background=[('active','#09645b')]);style.configure('Treeview',rowheight=30,background='white',fieldbackground='white');style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),background='#deebea');style.map('Treeview',background=[('selected','#087c70')],foreground=[('selected','white')])
        self.source_flags={name:tk.BooleanVar(value=name=='Necesidades y recepción de proformas') for name,_ in FUENTES};self.word=tk.StringVar(value='correo');self.mode=tk.StringVar(value='Todas las palabras');self.only=tk.BooleanVar(value=True);self.unknown=tk.BooleanVar(value=True)
        self.province=tk.StringVar(value='Todos');self.kind=tk.StringVar(value='Todos');self.state=tk.StringVar(value='Todos');self.days=tk.StringVar();self.low=tk.StringVar();self.high=tk.StringVar()
        top=ttk.Frame(self,padding=12);top.pack(fill='x')
        header=ttk.Frame(top);header.pack(fill='x');ttk.Label(header,text='Consultor SERCOP',font=('Segoe UI',17,'bold')).pack(side='left');self.theme_btn=ttk.Button(header,text='Modo noche',command=self.toggle_theme);self.theme_btn.pack(side='right')
        ttk.Label(top,text='Consulta automática: solo necesidades · Otras secciones: acceso manual · Verifica los datos en SERCOP').pack(anchor='w',pady=3)
        self.source_toggle=ttk.Button(top,text='▸ Dónde buscar  ·  seleccionar secciones',command=lambda:self.toggle_panel('source'));self.source_toggle.pack(fill='x',pady=(5,0))
        sourcebox=ttk.LabelFrame(top,text='Secciones del SERCOP',padding=6);self.sourcebox=sourcebox
        for i,(name,url) in enumerate(FUENTES):
            note=' · integrado' if name=='Necesidades y recepción de proformas' else ' · portal manual'
            ttk.Checkbutton(sourcebox,text=name+note,variable=self.source_flags[name]).grid(row=i//3,column=i%3,sticky='w',padx=3)
        source_actions=ttk.Frame(sourcebox);source_actions.grid(row=3,column=0,columnspan=3,sticky='w')
        ttk.Button(source_actions,text='Seleccionar todas',command=lambda:self.select_sources(True)).pack(side='left');ttk.Button(source_actions,text='Deseleccionar',command=lambda:self.select_sources(False)).pack(side='left',padx=4);ttk.Button(source_actions,text='Abrir secciones manuales',command=self.open_selected_sources).pack(side='left')
        ttk.Label(sourcebox,text='Consulta automática: solo necesidades. Las demás se abren en el portal para búsqueda manual.').grid(row=4,column=0,columnspan=3,sticky='w')
        search=ttk.Frame(top);search.pack(fill='x',pady=4)
        ttk.Label(search,text='Palabras:').pack(side='left');entry=ttk.Entry(search,textvariable=self.word,width=28);entry.pack(side='left',padx=5);entry.bind('<Return>',lambda e:self.filter());ttk.Combobox(search,textvariable=self.mode,state='readonly',width=27,values=['Todas las palabras','Cualquiera (separar con comas)','Frase exacta']).pack(side='left',padx=3)
        self.btn=ttk.Button(search,text='Consultar SERCOP',command=self.fetch,style='Accent.TButton');self.btn.pack(side='left',padx=3)
        ttk.Button(search,text='Aplicar filtros',command=self.filter).pack(side='left',padx=3)
        ttk.Button(search,text='Limpiar filtros',command=self.clear).pack(side='left',padx=3)
        ttk.Checkbutton(search,text='Solo vigentes',variable=self.only).pack(side='left',padx=8)
        self.filter_toggle=ttk.Button(top,text='▸ Filtros avanzados  ·  provincia, tipo, estado y plazo',command=lambda:self.toggle_panel('filters'));self.filter_toggle.pack(fill='x',pady=(5,0))
        filters=ttk.LabelFrame(top,text='Filtros combinables',padding=8);self.filtersbox=filters
        ttk.Label(filters,text='Provincia / cantón').grid(row=0,column=0,sticky='w');ttk.Label(filters,text='Tipo de necesidad').grid(row=0,column=1,sticky='w');ttk.Label(filters,text='Estado').grid(row=0,column=2,sticky='w');ttk.Label(filters,text='Cierra en máximo (días)').grid(row=0,column=3,sticky='w')
        self.combo_p=ttk.Combobox(filters,textvariable=self.province,state='readonly',width=25);self.combo_p.grid(row=1,column=0,padx=(0,8),sticky='ew')
        self.combo_k=ttk.Combobox(filters,textvariable=self.kind,state='readonly',width=23);self.combo_k.grid(row=1,column=1,padx=(0,8),sticky='ew')
        self.combo_s=ttk.Combobox(filters,textvariable=self.state,state='readonly',width=18);self.combo_s.grid(row=1,column=2,padx=(0,8),sticky='ew')
        ttk.Entry(filters,textvariable=self.days,width=12).grid(row=1,column=3,sticky='w');self.set_options()
        ttk.Label(filters,text='El tipo de necesidad no indica si el procedimiento incluye puja.').grid(row=2,column=0,columnspan=4,sticky='w',pady=(8,0))
        actions=ttk.Frame(top);actions.pack(fill='x',pady=4)
        ttk.Button(actions,text='Ver detalle',command=self.show_detail).pack(side='left');ttk.Button(actions,text='Abrir listado SERCOP',command=lambda:webbrowser.open(LISTADO)).pack(side='left',padx=5)
        ttk.Button(actions,text='Ficha completa',command=self.open_full_detail).pack(side='left',padx=5);ttk.Button(actions,text='Abrir necesidad',command=self.open_need).pack(side='left',padx=5);ttk.Button(actions,text='Documentos',command=self.open_documents).pack(side='left',padx=5);ttk.Button(actions,text='Importar JSON',command=self.load).pack(side='left');ttk.Button(actions,text='Exportar CSV',command=self.export).pack(side='left',padx=5)
        self.status=tk.StringVar(value='Consulta el SERCOP. La búsqueda revisa únicamente el lote recibido; no está comprobado que incluya todas las necesidades.')
        ttk.Label(top,textvariable=self.status,wraplength=1180).pack(anchor='w',pady=4)
        frame=ttk.Frame(self,padding=(12,0,12,12));frame.pack(fill='both',expand=True)
        cols=('codigo','objeto','entidad','tipo','publicacion','limite','estado','restante','monto','archivos')
        self.tree=ttk.Treeview(frame,columns=cols,show='headings');names=['Código','Objeto publicado','Entidad','Tipo de necesidad','Publicado','Fecha límite','Estado','Tiempo restante','Presupuesto referencial','Archivos'];widths=[190,350,210,150,140,140,95,130,170,130]
        for key,name,width in zip(cols,names,widths):self.tree.heading(key,text=name);self.tree.column(key,width=width,minwidth=70)
        sy=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview);sx=ttk.Scrollbar(frame,orient='horizontal',command=self.tree.xview);self.tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set);self.tree.grid(row=0,column=0,sticky='nsew');sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew');frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        self.tree.bind('<Double-1>',lambda e:self.show_detail())
        self.tree.bind('<<TreeviewSelect>>',self.preview)
        preview=ttk.LabelFrame(self,text='Descripción publicada por la entidad',padding=8);preview.pack(fill='x',padx=12,pady=(0,10),before=frame)
        self.preview_text=tk.StringVar(value='Selecciona una fila para leer su descripción completa.');ttk.Label(preview,textvariable=self.preview_text,wraplength=1150,justify='left').pack(anchor='w')
    def toggle_panel(self,which):
        if which=='source':
            panel,button=self.sourcebox,self.source_toggle
            closed='▸ Dónde buscar  ·  seleccionar secciones';opened='▾ Dónde buscar  ·  seleccionar secciones'
        else:
            panel,button=self.filtersbox,self.filter_toggle
            closed='▸ Filtros avanzados  ·  provincia, tipo, estado y plazo';opened='▾ Filtros avanzados  ·  provincia, tipo, estado y plazo'
        if panel.winfo_manager():panel.pack_forget();button.configure(text=closed)
        else:panel.pack(fill='x',pady=3,after=button);button.configure(text=opened)
    def toggle_theme(self):
        self.dark=not self.dark
        if self.dark:
            bg,fg,field,border,accent,heading=('#142329','#edf6f5','#20363d','#38535a','#218d80','#29444a')
            self.theme_btn.configure(text='Modo claro')
        else:
            bg,fg,field,border,accent,heading=('#f2f6f7','#18333d','#ffffff','#c8dadd','#087c70','#deebea')
            self.theme_btn.configure(text='Modo noche')
        st=self.ui_style;self.configure(bg=bg);self.option_add('*TCombobox*Listbox.background',field);self.option_add('*TCombobox*Listbox.foreground',fg)
        st.configure('.',background=bg,foreground=fg,fieldbackground=field)
        for cls in ('TFrame','TLabel','TCheckbutton','TLabelframe','TLabelframe.Label'):st.configure(cls,background=bg,foreground=fg)
        st.configure('TButton',background=heading,foreground=fg,bordercolor=border);st.map('TButton',background=[('active',border)],foreground=[('disabled','#809395')])
        st.configure('Accent.TButton',background=accent,foreground='white');st.map('Accent.TButton',background=[('active',accent)])
        st.configure('TEntry',fieldbackground=field,foreground=fg,insertcolor=fg)
        st.configure('TCombobox',fieldbackground=field,foreground=fg,background=heading,arrowcolor=fg)
        st.map('TCombobox',fieldbackground=[('readonly',field)],foreground=[('readonly',fg)])
        st.configure('Treeview',background=field,fieldbackground=field,foreground=fg);st.configure('Treeview.Heading',background=heading,foreground=fg);st.map('Treeview',background=[('selected',accent)],foreground=[('selected','white')])
    def preview(self,event=None):
        selected=self.tree.selection()
        if selected:
            row=self.filtered[int(selected[0])];self.preview_text.set(str(row.get('objeto_contratacion') or 'Descripción no disponible'))
        else:self.preview_text.set('Selecciona una fila para leer su descripción completa.')
    def set_options(self):
        for combo,var,key in [(self.combo_p,self.province,'provincia'),(self.combo_k,self.kind,'tipo_necesidad'),(self.combo_s,self.state,'estado')]:
            vals=sorted({str(r.get(key)).strip() for r in self.rows if r.get(key)},key=normalize);combo['values']=['Todos']+vals
            if var.get() not in combo['values']:var.set('Todos')
    def select_sources(self,value):
        for var in self.source_flags.values():var.set(value)
    def open_selected_sources(self):
        chosen=[(name,url) for name,url in FUENTES if self.source_flags[name].get() and name!='Necesidades y recepción de proformas']
        if not chosen:messagebox.showinfo('Selecciona una sección','Selecciona al menos una sección con acceso manual.');return
        known=[(name,url) for name,url in chosen if url];unknown=[name for name,url in chosen if not url]
        for name,url in known:webbrowser.open_new_tab(url)
        if unknown:
            webbrowser.open_new_tab(PORTAL)
            messagebox.showinfo('Selecciona en el portal','Se abrió el menú principal. Allí selecciona manualmente: '+', '.join(unknown)+'.')
    def fetch(self):
        if not any(v.get() for v in self.source_flags.values()):messagebox.showinfo('Selecciona dónde buscar','Selecciona al menos una sección.');return
        if not self.source_flags['Necesidades y recepción de proformas'].get():messagebox.showinfo('Secciones de consulta manual','Estas secciones todavía no están integradas en la búsqueda. Usa Abrir secciones manuales.');return
        if any(v.get() for k,v in self.source_flags.items() if k!='Necesidades y recepción de proformas'):
            messagebox.showinfo('Búsqueda parcial','Se consultarán automáticamente solo las necesidades. Para las otras secciones usa Abrir secciones manuales; no se incluyen en los resultados.')
        if self.fetching:return
        self.fetching=True;self.btn.config(state='disabled');self.status.set('Consultando SERCOP; espera hasta 30 segundos...');threading.Thread(target=self._fetch,daemon=True).start()
    def _fetch(self):
        try:
            req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0 (compatible; ConsultasSERCOP/1.0)','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=30) as resp:
                payload=resp.read(25000001)
                if len(payload)>25000000: raise ValueError('El archivo supera 25 MB.')
            data=json.loads(payload.decode('utf-8-sig'));rows=find_rows(data)
            if not rows: raise ValueError('La respuesta no contiene registros reconocibles.')
            self.after(0,lambda:self.set_rows(rows))
        except Exception as exc:
            error=str(exc);self.after(0,lambda:self.fail_fetch(error))
    def fail_fetch(self,error):
        self.fetching=False;self.btn.config(state='normal');self.status.set('No se pudo consultar: '+error+'. Los resultados anteriores, si existen, no están actualizados.')
    def set_rows(self,rows):
        self.fetching=False;self.btn.config(state='normal');self.rows=rows;self.doc_counts={};self.set_options();self.filter()
    def get_filters(self):
        low=None;high=None;txt=self.days.get().strip()
        if low is not None and high is not None and low>high:raise ValueError('El monto mínimo no puede superar el máximo.')
        if txt and (not txt.isdigit() or not 1<=int(txt)<=3650):raise ValueError('Los días deben ser un número entero entre 1 y 3650.')
        return {'word':self.word.get().strip(),'mode':self.mode.get(),'only':self.only.get(),'province':self.province.get(),'kind':self.kind.get(),'state':self.state.get(),'days':int(txt) if txt else None,'low':low,'high':high,'unknown':self.unknown.get()}
    def filter(self):
        try:filters=self.get_filters()
        except ValueError as e:messagebox.showerror('Revisa los filtros',str(e));return
        now=datetime.now(EC);self.filtered=[r for r in self.rows if match(r,filters,now)]
        self.tree.delete(*self.tree.get_children())
        for index,r in enumerate(self.filtered):
            d=deadline(r.get('fecha_limite_propuesta'));seconds=int((d-now).total_seconds()) if d else None
            left='Sin fecha' if seconds is None else 'Vencido' if seconds<=0 else f'{seconds//86400} d {(seconds%86400)//3600} h'
            value,_=amount(r);val=f'${value:,.2f}' if value is not None else 'No disponible'
            self.tree.insert('','end',iid=str(index),values=(r.get('codigo_contratacion',''),r.get('objeto_contratacion',''),r.get('razon_social',''),r.get('tipo_necesidad') or 'No disponible',r.get('fecha_publicacion',''),r.get('fecha_limite_propuesta',''),r.get('estado',''),left,val,self.doc_counts.get(r.get('codigo_contratacion'),'Sin consultar'))) 
        self.preview();self.status.set(f'{len(self.filtered)} resultados de {len(self.rows)} registros recibidos. Solo se consulta el lote 1; cobertura completa no verificada.')
    def clear(self):
        self.word.set('');self.mode.set('Todas las palabras');self.only.set(True);self.unknown.set(True);self.province.set('Todos');self.kind.set('Todos');self.state.set('Todos');self.days.set('');self.low.set('');self.high.set('');self.filter()
    def show_detail(self):
        selected=self.tree.selection()
        if not selected:messagebox.showinfo('Selecciona una fila','Selecciona una necesidad para ver su detalle.');return
        r=self.filtered[int(selected[0])];value,label=amount(r);money=f'{label}: USD {value:,.2f}' if value is not None else 'Presupuesto referencial: No disponible'
        text='\n\n'.join(f'{label}: {r.get(key) or "No disponible"}' for label,key in [('Código','codigo_contratacion'),('Entidad','razon_social'),('Necesidad','objeto_contratacion'),('Tipo de necesidad','tipo_necesidad'),('Publicado','fecha_publicacion'),('Fecha límite de proformas','fecha_limite_propuesta'),('Estado','estado'),('Provincia / cantón','provincia')]);text+='\n\n'+money+'\n\nNúmero de archivos: '+str(self.doc_counts.get(r.get('codigo_contratacion'),'Sin consultar'))+'\n\nPuja o subasta: No determinado para este aviso. Verifica el tipo y condiciones en el SERCOP.'
        win=tk.Toplevel(self);win.title('Detalle de necesidad');win.geometry('700x540');area=scrolledtext.ScrolledText(win,wrap='word',font=('Segoe UI',10));area.pack(fill='both',expand=True,padx=12,pady=12);area.insert('1.0',text);area.configure(state='disabled');bar=ttk.Frame(win);bar.pack(fill='x',padx=12,pady=(0,12));ttk.Button(bar,text='Consultar ficha completa',command=lambda:self.open_full_detail(r)).pack(side='left');ttk.Button(bar,text='Ver y descargar archivos',command=lambda:self.open_documents(r)).pack(side='left',padx=6);ttk.Button(bar,text='Abrir en SERCOP',command=lambda:self.open_need(r)).pack(side='left',padx=6)
    def selected_record(self):
        selected=self.tree.selection()
        if not selected:
            messagebox.showinfo('Selecciona una necesidad','Selecciona una fila antes de continuar.');return None
        return self.filtered[int(selected[0])]
    def resolve_detail(self,row):
        found=detalle_de_registro(row)
        if found:return found
        answer=simpledialog.askstring('Enlace del proceso','El listado no incluye un enlace directo reconocible. Abre el listado oficial, entra en el detalle de la necesidad y pega aquí su dirección:',parent=self)
        if not answer:return None
        found=url_segura(answer,detalle=True)
        if not found:messagebox.showerror('Enlace no válido','Introduce la dirección HTTPS del detalle oficial de compraspublicas.gob.ec.');return None
        return found
    def open_full_detail(self,row=None):
        if row is None:row=self.selected_record()
        if row is None:return
        url=self.resolve_detail(row)
        if not url:return
        self.status.set('Leyendo la ficha oficial...')
        threading.Thread(target=self._fetch_full_detail,args=(url,),daemon=True).start()
    def _fetch_full_detail(self,url):
        try:
            text,docs=obtener_ficha(url)
            self.after(0,lambda:self._show_full_detail(text,len(docs)))
        except Exception as e:
            error=str(e);self.after(0,lambda:self._documents_error(error))
    def _show_full_detail(self,text,count):
        self.status.set(f'Ficha leída. Se detectaron {count} enlaces de documentos.')
        win=tk.Toplevel(self);win.title('Ficha pública de la necesidad');win.geometry('780x600')
        ttk.Label(win,text='Contenido de la ficha pública del SERCOP',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=12,pady=8)
        area=scrolledtext.ScrolledText(win,wrap='word',font=('Segoe UI',10));area.pack(fill='both',expand=True,padx=12,pady=12);area.insert('1.0',text);area.configure(state='disabled')
    def open_need(self,row=None):
        if row is None:row=self.selected_record()
        if row is None:return
        url=self.resolve_detail(row)
        if url:webbrowser.open(url)
    def open_documents(self,row=None):
        if row is None:row=self.selected_record()
        if row is None:return
        url=self.resolve_detail(row)
        if not url:return
        self.status.set('Buscando enlaces de documentos en el proceso oficial...')
        threading.Thread(target=self._find_documents,args=(url,row.get('codigo_contratacion')),daemon=True).start()
    def _find_documents(self,url,code):
        try:
            client,docs=obtener_documentos(url)
            self.after(0,lambda:self._documents_ready(client,docs,url,code))
        except Exception as e:
            error=str(e);self.after(0,lambda:self._documents_error(error))
    def _documents_error(self,error):
        self.status.set('No se pudieron consultar los documentos.');messagebox.showerror('No se pudieron consultar documentos',error+'\n\nPuedes abrir el proceso oficial y descargarlos manualmente.')
    def _documents_ready(self,client,docs,url,code):
        if code:self.doc_counts[code]=str(len(docs))+' detectados';self.filter()
        self.status.set(f'{len(docs)} enlaces de documentos detectados. Revisa la lista antes de descargar.')
        if not docs:
            messagebox.showinfo('Sin enlaces detectados','No se encontraron enlaces directos en la sección Documentos Anexos. El portal puede usar otro formato o una verificación. Abre el proceso y comprueba sus documentos.');return
        win=tk.Toplevel(self);win.title('Documentos de la necesidad');win.geometry('700x460');ttk.Label(win,text='Documentos detectados',font=('Segoe UI',14,'bold')).pack(anchor='w',padx=12,pady=10)
        ttk.Label(win,text='Selecciona uno o varios, o descarga todos en un ZIP.').pack(anchor='w',padx=12)
        box=tk.Listbox(win,selectmode='extended',font=('Segoe UI',10));box.pack(fill='both',expand=True,padx=12,pady=12)
        for d in docs:
            from urllib.parse import urlsplit, unquote
            import os
            suffix=os.path.splitext(unquote(urlsplit(d['url']).path))[1].lower() or os.path.splitext(d['name'])[1].lower()
            kind=suffix.lstrip('.').upper() if suffix and suffix.lower() not in ('.cpe','.php','.aspx') and len(suffix)<=6 else 'Tipo no identificado'
            box.insert('end',f"{d['name']}  —  {kind}")
        def save(which):
            chosen=docs if which=='all' else [docs[i] for i in box.curselection()]
            if not chosen:messagebox.showinfo('Selecciona documentos','Selecciona al menos un documento.',parent=win);return
            path=filedialog.asksaveasfilename(parent=win,title='Guardar documentos',initialfile='documentos_sercop.zip',defaultextension='.zip',filetypes=[('Archivo ZIP','*.zip')])
            if not path:return
            self.status.set('Descargando documentos...')
            threading.Thread(target=self._download_documents,args=(client,chosen,path),daemon=True).start()
        def save_folder():
            chosen=[docs[i] for i in box.curselection()] if box.curselection() else docs
            folder=filedialog.askdirectory(parent=win,title='Selecciona la carpeta de descarga')
            if not folder:return
            self.status.set('Descargando documentos en la carpeta...')
            threading.Thread(target=self._download_folder,args=(client,chosen,folder),daemon=True).start()
        buttons=ttk.Frame(win);buttons.pack(fill='x',padx=12,pady=(0,12));ttk.Button(buttons,text='Descargar seleccionados',command=lambda:save('selected')).pack(side='left');ttk.Button(buttons,text='Descargar todos en ZIP',style='Accent.TButton',command=lambda:save('all')).pack(side='left',padx=6);ttk.Button(buttons,text='Descargar en carpeta',command=lambda:save_folder()).pack(side='left',padx=6);ttk.Button(buttons,text='Abrir proceso oficial',command=lambda:webbrowser.open(url)).pack(side='left',padx=6)
    def _download_folder(self,client,docs,folder):
        try:
            names,errors=download_folder(client,docs,folder)
            msg=f'Se guardaron {len(names)} archivos en la carpeta.'
            if errors:msg+='\n\nNo se pudieron descargar:\n'+'\n'.join(errors)
            self.after(0,lambda:self._download_done(msg))
        except Exception as e:
            error=str(e);self.after(0,lambda:self._documents_error(error))
    def _download_documents(self,client,docs,path):
        try:
            count,errors=download_zip(client,docs,path)
            msg=f'Se guardaron {count} documentos en el ZIP.'
            if errors:msg+='\n\nNo se pudieron descargar:\n'+'\n'.join(errors)
            self.after(0,lambda:self._download_done(msg))
        except Exception as e:
            error=str(e);self.after(0,lambda:self._documents_error(error))
    def _download_done(self,msg):
        self.status.set('Descarga terminada.');messagebox.showinfo('Descarga de documentos',msg)
    def load(self):
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json'),('Todos','*.*')])
        if not path:return
        try:
            with open(path,encoding='utf-8-sig') as f:rows=find_rows(json.load(f))
            if not rows:raise ValueError('No se encontraron necesidades en el archivo.')
            self.set_rows(rows)
        except Exception as e:messagebox.showerror('No se pudo importar',str(e))
    def export(self):
        if not self.filtered:messagebox.showinfo('Sin resultados','Primero realiza una búsqueda.');return
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        cols=['codigo_contratacion','objeto_contratacion','razon_social','provincia','tipo_necesidad','fecha_publicacion','fecha_limite_propuesta','estado','presupuesto_referencial']
        try:
            with open(path,'w',encoding='utf-8-sig',newline='') as f:
                out=csv.DictWriter(f,fieldnames=cols);out.writeheader()
                for r in self.filtered:
                    value,_=amount(r);row={k:r.get(k,'') for k in cols};row['presupuesto_referencial']=str(value) if value is not None else ''
                    # Evita que Excel interprete contenido remoto como fórmula.
                    for k,v in row.items():
                        if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')):row[k]="'"+v
                    out.writerow(row)
            messagebox.showinfo('Exportado','Archivo guardado correctamente.')
        except OSError as e:messagebox.showerror('No se pudo exportar',str(e))

if __name__=='__main__':App().mainloop()
