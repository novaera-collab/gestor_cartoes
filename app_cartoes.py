# -*- coding: utf-8 -*-
import sys
import os
import json
import base64
import traceback
import customtkinter as ctk
from tkinter import messagebox, Toplevel, filedialog
import psycopg2
from psycopg2.extras import RealDictCursor

if sys.platform.startswith("win"):
    import ctypes
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

CONFIG_FILE = "app_cartao_conf_banco.json"

# ==========================================
# UTILITÁRIOS DE CRIPTOGRAFIA E CONFIGURAÇÃO
# ==========================================

def encriptar_texto(texto):
    if not texto:
        return ""
    try:
        return base64.b64encode(texto.encode('utf-8')).decode('utf-8')
    except Exception:
        return texto

def decriptar_texto(texto_cripto):
    if not texto_cripto:
        return ""
    try:
        return base64.b64decode(texto_cripto.encode('utf-8')).decode('utf-8')
    except Exception:
        return texto_cripto

def carregar_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if "password" in cfg:
                    cfg["password"] = decriptar_texto(cfg["password"])
                return cfg
        except Exception:
            pass
    return {
        "host": "localhost",
        "database": "seu_banco",
        "user": "postgres",
        "password": "",
        "port": "5432",
        "schema": "public"
    }

def salvar_config(cfg):
    cfg_copy = cfg.copy()
    if "password" in cfg_copy:
        cfg_copy["password"] = encriptar_texto(cfg_copy["password"])
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg_copy, f, indent=4)

def get_connection():
    cfg = carregar_config()
    conn = psycopg2.connect(
        host=cfg.get("host", "localhost"),
        database=cfg.get("database", "seu_banco"),
        user=cfg.get("user", "postgres"),
        password=cfg.get("password", ""),
        port=cfg.get("port", "5432"),
        cursor_factory=RealDictCursor
    )
    conn.set_client_encoding('LATIN1')
    return conn

def get_schema():
    cfg = carregar_config()
    schema = cfg.get("schema", "public").strip()
    return schema if schema else "public"

def centralizar_modal(modal, largura, altura):
    modal.update_idletasks()
    root = modal.winfo_toplevel()
    while root.master:
        root = root.master.winfo_toplevel()
    main_x = root.winfo_x()
    main_y = root.winfo_y()
    main_w = root.winfo_width()
    pos_x = main_x + max(0, (main_w - largura) // 2)
    pos_y = max(20, main_y + 30)
    modal.geometry(f"{largura}x{altura}+{pos_x}+{pos_y}")
    modal.transient(root)
    modal.grab_set()
    modal.focus_force()

# ==========================================
# CRIAÇÃO AUTOMÁTICA DE SCHEMA E TABELAS
# ==========================================

def criar_tabelas_banco():
    schema = get_schema()
    sql_script = f"""
    CREATE SCHEMA IF NOT EXISTS {schema};

    -- TABELA BANDEIRA
    CREATE TABLE IF NOT EXISTS {schema}.bandeiras (
        codigo VARCHAR(10) NOT NULL,
        empresa_codigo VARCHAR(10) NOT NULL,
        filial_codigo VARCHAR(10) NOT NULL,
        descricao VARCHAR(100) NOT NULL,
        icone VARCHAR(255),
        PRIMARY KEY (empresa_codigo, filial_codigo, codigo)
    );

    -- TABELA CABECALHO CADASTRO BANDEIRAS
    CREATE TABLE IF NOT EXISTS {schema}.cabecalho_cadastro_bandeiras (
        id SERIAL PRIMARY KEY,
        empresa_codigo VARCHAR(10) NOT NULL,
        filial_codigo VARCHAR(10) NOT NULL,
        bandeira_codigo VARCHAR(10) NOT NULL,
        conta_baixa VARCHAR(50),
        portador VARCHAR(50),
        tipo_cobranca VARCHAR(50),
        taxa_antecipacao_automatica NUMERIC(7,2) DEFAULT 0.00,
        taxa_antecipacao_pontual NUMERIC(7,2) DEFAULT 0.00
    );

    -- TABELA ITEM CABECALHO CADASTRO BANDEIRAS
    CREATE TABLE IF NOT EXISTS {schema}.item_cabecalho_cadastro_bandeiras (
        id SERIAL PRIMARY KEY,
        cabecalho_id INTEGER REFERENCES {schema}.cabecalho_cadastro_bandeiras(id) ON DELETE CASCADE,
        parcela_inicial INT NOT NULL,
        parcela_final INT NOT NULL,
        sinal VARCHAR(5) NOT NULL,
        dias INT NOT NULL,
        taxa NUMERIC(7,2) NOT NULL
    );
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql_script)
    conn.commit()
    conn.close()

# ==========================================
# MODAIS DE PESQUISA (LUPAS)
# ==========================================

class LupaEmpresaModal(ctk.CTkToplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.title("Consultar Empresa (geempre)")
        
        frame_top = ctk.CTkFrame(self)
        frame_top.pack(fill="x", padx=10, pady=10)
        
        self.txt_busca = ctk.CTkEntry(frame_top, width=300, placeholder_text="Buscar código ou nome...")
        self.txt_busca.pack(side="left", padx=5)
        self.txt_busca.bind("<Return>", lambda e: self.pesquisar())
        
        btn_busca = ctk.CTkButton(frame_top, text="🔍 Buscar", command=self.pesquisar)
        btn_busca.pack(side="left", padx=5)

        self.frame_lista = ctk.CTkScrollableFrame(self)
        self.frame_lista.pack(fill="both", expand=True, padx=10, pady=5)
        
        centralizar_modal(self, 500, 400)
        self.pesquisar()

    def pesquisar(self):
        for w in self.frame_lista.winfo_children():
            w.destroy()
            
        termo = self.txt_busca.get().strip()
        
        try:
            conn = get_connection()
            cur = conn.cursor()
            
            if not termo:
                query_xgeral = "SELECT fco AS codigo, fno AS nome FROM xgeral.geempre ORDER BY fco LIMIT 50;"
                query_params = ()
            else:
                query_xgeral = "SELECT fco AS codigo, fno AS nome FROM xgeral.geempre WHERE CAST(fco AS TEXT) ILIKE %s OR fno ILIKE %s ORDER BY fco LIMIT 50;"
                query_params = (f"%{termo}%", f"%{termo}%")

            cur.execute(query_xgeral, query_params)
            res = cur.fetchall()
            conn.close()

            if not res:
                ctk.CTkLabel(self.frame_lista, text="Nenhuma empresa encontrada.", text_color="gray").pack(pady=20)
                return

            for emp in res:
                row = ctk.CTkFrame(self.frame_lista)
                row.pack(fill="x", pady=2, padx=2)
                
                cod_str = str(emp['codigo']).strip().zfill(4)
                nome_str = str(emp['nome'] or '').strip()
                
                ctk.CTkLabel(row, text=f"[{cod_str}]", font=ctk.CTkFont(weight="bold"), width=60).pack(side="left", padx=5)
                ctk.CTkLabel(row, text=nome_str, anchor="w").pack(side="left", fill="x", expand=True, padx=5)
                
                btn_sel = ctk.CTkButton(row, text="✔", width=40, command=lambda c=cod_str, n=nome_str: self.selecionar(c, n))
                btn_sel.pack(side="right", padx=5)
                
        except Exception as err:
            messagebox.showerror("Erro na Consulta", f"Erro ao consultar empresas:\n{err}", parent=self)

    def selecionar(self, cod_str, nome_str):
        self.callback(cod_str, nome_str)
        self.destroy()

class LupaFilialModal(ctk.CTkToplevel):
    def __init__(self, parent, cod_empresa, callback):
        super().__init__(parent)
        self.cod_empresa = cod_empresa
        self.callback = callback
        self.title("Consultar Filial (gefil)")
        
        frame_top = ctk.CTkFrame(self)
        frame_top.pack(fill="x", padx=10, pady=10)
        
        self.txt_busca = ctk.CTkEntry(frame_top, width=300, placeholder_text="Buscar código ou nome...")
        self.txt_busca.pack(side="left", padx=5)
        self.txt_busca.bind("<Return>", lambda e: self.pesquisar())
        
        btn_busca = ctk.CTkButton(frame_top, text="🔍 Buscar", command=self.pesquisar)
        btn_busca.pack(side="left", padx=5)

        self.frame_lista = ctk.CTkScrollableFrame(self)
        self.frame_lista.pack(fill="both", expand=True, padx=10, pady=5)
        
        centralizar_modal(self, 500, 400)
        self.pesquisar()

    def pesquisar(self):
        for w in self.frame_lista.winfo_children():
            w.destroy()
        termo = self.txt_busca.get().strip()
        schema_emp = f"xemp_{str(self.cod_empresa).zfill(4)}"
        try:
            conn = get_connection()
            cur = conn.cursor()
            
            if not termo:
                query = f"SELECT fcodigo AS codigo, fnome AS nome FROM {schema_emp}.gefil ORDER BY fcodigo LIMIT 50;"
                params = ()
            else:
                query = f"SELECT fcodigo AS codigo, fnome AS nome FROM {schema_emp}.gefil WHERE CAST(fcodigo AS TEXT) ILIKE %s OR fnome ILIKE %s ORDER BY fcodigo LIMIT 50;"
                params = (f"%{termo}%", f"%{termo}%")
                
            cur.execute(query, params)
            res = cur.fetchall()
            conn.close()

            if not res:
                ctk.CTkLabel(self.frame_lista, text="Nenhuma filial encontrada.", text_color="gray").pack(pady=20)
                return

            for fil in res:
                row = ctk.CTkFrame(self.frame_lista)
                row.pack(fill="x", pady=2, padx=2)
                cod_str = str(fil['codigo']).strip().zfill(4)
                nome_str = str(fil['nome'] or '').strip()
                
                ctk.CTkLabel(row, text=f"[{cod_str}]", font=ctk.CTkFont(weight="bold"), width=60).pack(side="left", padx=5)
                ctk.CTkLabel(row, text=nome_str, anchor="w").pack(side="left", fill="x", expand=True, padx=5)
                btn_sel = ctk.CTkButton(row, text="✔", width=40, command=lambda c=cod_str, n=nome_str: self.selecionar(c, n))
                btn_sel.pack(side="right", padx=5)
        except Exception as err:
            messagebox.showerror("Erro", f"Erro na consulta de filiais em {schema_emp}:\n{err}", parent=self)

    def selecionar(self, cod_str, nome_str):
        self.callback(cod_str, nome_str)
        self.destroy()

class LupaGenericModal(ctk.CTkToplevel):
    def __init__(self, parent, cod_empresa, titulo, tabela, col_cod, col_desc, callback):
        super().__init__(parent)
        self.cod_empresa = cod_empresa
        self.titulo = titulo
        self.tabela = tabela
        self.col_cod = col_cod
        self.col_desc = col_desc
        self.callback = callback

        self.title(f"Consultar {self.titulo}")
        
        frame_top = ctk.CTkFrame(self)
        frame_top.pack(fill="x", padx=10, pady=10)
        
        self.txt_busca = ctk.CTkEntry(frame_top, width=300, placeholder_text="Buscar código ou descrição...")
        self.txt_busca.pack(side="left", padx=5)
        self.txt_busca.bind("<Return>", lambda e: self.pesquisar())
        
        btn_busca = ctk.CTkButton(frame_top, text="🔍 Buscar", command=self.pesquisar)
        btn_busca.pack(side="left", padx=5)

        self.frame_lista = ctk.CTkScrollableFrame(self)
        self.frame_lista.pack(fill="both", expand=True, padx=10, pady=5)
        
        centralizar_modal(self, 520, 420)
        self.pesquisar()

    def pesquisar(self):
        for w in self.frame_lista.winfo_children():
            w.destroy()
        termo = self.txt_busca.get().strip()
        schema_emp = f"xemp_{str(self.cod_empresa).zfill(4)}"
        try:
            conn = get_connection()
            cur = conn.cursor()
            
            if not termo:
                query = f"SELECT {self.col_cod} AS codigo, {self.col_desc} AS descricao FROM {schema_emp}.{self.tabela} ORDER BY {self.col_cod} LIMIT 50;"
                params = ()
            else:
                query = f"SELECT {self.col_cod} AS codigo, {self.col_desc} AS descricao FROM {schema_emp}.{self.tabela} WHERE CAST({self.col_cod} AS TEXT) ILIKE %s OR {self.col_desc} ILIKE %s ORDER BY {self.col_cod} LIMIT 50;"
                params = (f"%{termo}%", f"%{termo}%")
                
            cur.execute(query, params)
            res = cur.fetchall()
            conn.close()

            if not res:
                ctk.CTkLabel(self.frame_lista, text="Nenhum registro encontrado.", text_color="gray").pack(pady=20)
                return

            for item in res:
                row = ctk.CTkFrame(self.frame_lista)
                row.pack(fill="x", pady=2, padx=2)
                cod_str = str(item['codigo']).strip()
                desc_str = str(item['descricao'] or '').strip()
                
                ctk.CTkLabel(row, text=f"[{cod_str}]", font=ctk.CTkFont(weight="bold"), width=70).pack(side="left", padx=5)
                ctk.CTkLabel(row, text=desc_str, anchor="w").pack(side="left", fill="x", expand=True, padx=5)
                btn_sel = ctk.CTkButton(row, text="✔", width=40, command=lambda c=cod_str, d=desc_str: self.selecionar(c, d))
                btn_sel.pack(side="right", padx=5)
        except Exception as err:
            messagebox.showerror("Erro", f"Erro na consulta de {self.titulo} em {schema_emp}:\n{err}", parent=self)

    def selecionar(self, cod_str, desc_str):
        self.callback(cod_str, desc_str)
        self.destroy()

# ==========================================
# JANELA DE CONFIGURAÇÃO DO BANCO DE DADOS
# ==========================================

class ConfigBancoWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Configurações do Banco de Dados")
        cfg = carregar_config()

        fields = [("Host / IP:", "host"), ("Banco de Dados:", "database"), ("Schema:", "schema"), ("Usuário:", "user"), ("Senha:", "password"), ("Porta:", "port")]
        self.entries = {}

        for i, (label_text, key) in enumerate(fields):
            ctk.CTkLabel(self, text=label_text).grid(row=i, column=0, padx=15, pady=6, sticky="w")
            ent = ctk.CTkEntry(self, width=280, show="*" if key == "password" else "")
            ent.insert(0, cfg.get(key, ""))
            ent.grid(row=i, column=1, padx=15, pady=6)
            self.entries[key] = ent

        btn_gerar = ctk.CTkButton(self, text="🛠️ Gerar Schema e Tabelas", fg_color="#0288D1", hover_color="#0277BD", command=self.gerar_tabelas)
        btn_gerar.grid(row=len(fields), column=0, columnspan=2, pady=15, padx=15, sticky="ew")

        btn_salvar = ctk.CTkButton(self, text="💾 Salvar Configurações", fg_color="#2E7D32", hover_color="#1B5E20", command=self.salvar)
        btn_salvar.grid(row=len(fields)+1, column=0, columnspan=2, pady=(0, 15), padx=15, sticky="ew")

        centralizar_modal(self, 450, 360)

    def salvar(self):
        cfg = {k: ent.get().strip() for k, ent in self.entries.items()}
        salvar_config(cfg)
        messagebox.showinfo("Sucesso", "Configurações do banco salvas no arquivo app_cartao_conf_banco.json!", parent=self)
        self.destroy()

    def gerar_tabelas(self):
        self.salvar()
        try:
            criar_tabelas_banco()
            messagebox.showinfo("Sucesso", f"Schema e tabelas gerados/verificados com sucesso no schema '{get_schema()}'!", parent=self)
        except Exception as e:
            messagebox.showerror("Erro na Criação", f"Falha ao gerar tabelas:\n{e}", parent=self)

# ==========================================
# TELA PRINCIPAL E CADASTRO DE TAXAS
# ==========================================

class AppCartoesPrincipal(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Gestor de Taxas de Cartões de Crédito")
        self.geometry("1100x720")

        self.empresa_sel = {"codigo": "", "nome": ""}
        self.filial_sel = {"codigo": "", "nome": ""}
        self.conta_sel = {"codigo": "", "nome": ""}
        self.portador_sel = {"codigo": "", "nome": ""}
        self.tipo_cobranca_sel = {"codigo": "", "nome": ""}
        self.itens_parcela = []
        self.editando_id = None

        self.criar_layout()

    def criar_layout(self):
        # BANNER / TOPO
        frame_top = ctk.CTkFrame(self)
        frame_top.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(frame_top, text="💳 Gestão e Cadastro de Taxas de Cartão", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=15, pady=10)
        btn_config = ctk.CTkButton(frame_top, text="⚙️ Conf. Banco", fg_color="#455A64", hover_color="#37474F", command=self.abrir_config)
        btn_config.pack(side="right", padx=15)

        # PAINEL EMPRESA E FILIAL
        frame_emp_fil = ctk.CTkFrame(self)
        frame_emp_fil.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(frame_emp_fil, text="Empresa:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.txt_emp = ctk.CTkEntry(frame_emp_fil, width=250, placeholder_text="Selecione na Lupa...")
        self.txt_emp.grid(row=0, column=1, padx=5, pady=8)
        btn_lupa_emp = ctk.CTkButton(frame_emp_fil, text="🔍", width=36, command=self.abrir_lupa_emp)
        btn_lupa_emp.grid(row=0, column=2, padx=2, pady=8)

        ctk.CTkLabel(frame_emp_fil, text="Filial:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=3, padx=15, pady=8, sticky="w")
        self.txt_fil = ctk.CTkEntry(frame_emp_fil, width=250, placeholder_text="Selecione na Lupa...")
        self.txt_fil.grid(row=0, column=4, padx=5, pady=8)
        btn_lupa_fil = ctk.CTkButton(frame_emp_fil, text="🔍", width=36, command=self.abrir_lupa_fil)
        btn_lupa_fil.grid(row=0, column=5, padx=2, pady=8)

        # PAINEL PRINCIPAL DE CONTEÚDO (MUDANÇA DE TELAS)
        self.frame_conteudo = ctk.CTkFrame(self)
        self.frame_conteudo.pack(fill="both", expand=True, padx=15, pady=10)

        # 1. TELA DE LISTAGEM DE BANDEIRAS
        self.frame_lista_bandeiras = ctk.CTkFrame(self.frame_conteudo)
        
        frame_header_lista = ctk.CTkFrame(self.frame_lista_bandeiras, fg_color="transparent")
        frame_header_lista.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(frame_header_lista, text="Bandeiras Cadastradas", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        btn_add_band = ctk.CTkButton(frame_header_lista, text="➕ Cadastrar Nova Bandeira", fg_color="#1976D2", hover_color="#0D47A1", font=ctk.CTkFont(weight="bold"), command=self.nova_bandeira)
        btn_add_band.pack(side="right")

        self.scroll_bandeiras = ctk.CTkScrollableFrame(self.frame_lista_bandeiras)
        self.scroll_bandeiras.pack(fill="both", expand=True, padx=10, pady=5)

        # 2. TELA DE FORMULÁRIO DE CADASTRO / EDIÇÃO
        self.frame_form_bandeira = ctk.CTkFrame(self.frame_conteudo)

        frame_header_form = ctk.CTkFrame(self.frame_form_bandeira, fg_color="transparent")
        frame_header_form.pack(fill="x", padx=10, pady=5)

        btn_voltar = ctk.CTkButton(frame_header_form, text="⬅️ Voltar", width=90, fg_color="#455A64", hover_color="#37474F", command=self.exibir_lista)
        btn_voltar.pack(side="left")

        self.lbl_titulo_form = ctk.CTkLabel(frame_header_form, text="Cadastro de Bandeira & Taxas", font=ctk.CTkFont(size=15, weight="bold"))
        self.lbl_titulo_form.pack(side="left", padx=15)

        # FORMULÁRIO BANDEIRA E CABEÇALHO
        frame_form = ctk.CTkFrame(self.frame_form_bandeira)
        frame_form.pack(fill="x", padx=10, pady=5)

        # LINHA 0: BANDEIRA
        ctk.CTkLabel(frame_form, text="Cód. Bandeira:").grid(row=0, column=0, padx=8, pady=5, sticky="w")
        self.txt_band_cod = ctk.CTkEntry(frame_form, width=80, placeholder_text="001")
        self.txt_band_cod.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(frame_form, text="Descrição:").grid(row=0, column=2, padx=8, pady=5, sticky="w")
        self.txt_band_desc = ctk.CTkEntry(frame_form, width=300, placeholder_text="VISA / MASTERCARD...")
        self.txt_band_desc.grid(row=0, column=3, columnspan=3, padx=5, pady=5, sticky="w")

        # LINHA 1: CONTA BAIXA
        ctk.CTkLabel(frame_form, text="Conta Baixa:").grid(row=1, column=0, padx=8, pady=5, sticky="w")
        
        frame_conta_box = ctk.CTkFrame(frame_form, fg_color="transparent")
        frame_conta_box.grid(row=1, column=1, columnspan=5, padx=5, pady=5, sticky="w")
        
        self.txt_conta = ctk.CTk
