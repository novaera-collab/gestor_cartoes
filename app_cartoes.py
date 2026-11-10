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

def obter_schema_tabela_existente(conn, cod_empresa, nome_tabela):
    """
    Testa se a tabela existe no schema da empresa (ex: xemp_0002).
    Se nao existir, recorre ao schema de compartilhamento xemp_0001.
    """
    schema_alvo = f"xemp_{str(cod_empresa).zfill(4)}"
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = %s AND table_name = %s
    """, (schema_alvo, nome_tabela))
    existe = cur.fetchone()
    if existe:
        return schema_alvo
    return "xemp_0001"

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
        cod_mov VARCHAR(50),
        tipo_rec VARCHAR(50),
        taxa_antecipacao_automatica NUMERIC(7,2) DEFAULT 0.00,
        taxa_antecipacao_pontual NUMERIC(7,2) DEFAULT 0.00
    );

    ALTER TABLE {schema}.cabecalho_cadastro_bandeiras ADD COLUMN IF NOT EXISTS cod_mov VARCHAR(50);
    ALTER TABLE {schema}.cabecalho_cadastro_bandeiras ADD COLUMN IF NOT EXISTS tipo_rec VARCHAR(50);

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
# MODAIS DE PESQUISA (LUPAS) E DUPLICAÇÃO
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
        try:
            conn = get_connection()
            schema_emp = obter_schema_tabela_existente(conn, self.cod_empresa, "gefil")
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
            messagebox.showerror("Erro", f"Erro na consulta de filiais:\n{err}", parent=self)

    def selecionar(self, cod_str, nome_str):
        self.callback(cod_str, nome_str)
        self.destroy()

class LupaGenericModal(ctk.CTkToplevel):
    def __init__(self, parent, cod_empresa, titulo, tabela, col_cod, col_desc, callback, filtro_extra=""):
        super().__init__(parent)
        self.cod_empresa = cod_empresa
        self.titulo = titulo
        self.tabela = tabela
        self.col_cod = col_cod
        self.col_desc = col_desc
        self.callback = callback
        self.filtro_extra = filtro_extra

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
        try:
            conn = get_connection()
            schema_emp = obter_schema_tabela_existente(conn, self.cod_empresa, self.tabela)
            cur = conn.cursor()
            
            condicoes = []
            params = []

            if self.filtro_extra:
                condicoes.append(f"({self.filtro_extra})")

            if termo:
                condicoes.append(f"(CAST({self.col_cod} AS TEXT) ILIKE %s OR {self.col_desc} ILIKE %s)")
                params.extend([f"%{termo}%", f"%{termo}%"])

            where_clause = ""
            if condicoes:
                where_clause = " WHERE " + " AND ".join(condicoes)

            query = f"SELECT {self.col_cod} AS codigo, {self.col_desc} AS descricao FROM {schema_emp}.{self.tabela} {where_clause} ORDER BY {self.col_cod} LIMIT 50;"

            cur.execute(query, tuple(params))
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
            messagebox.showerror("Erro", f"Erro na consulta de {self.titulo}:\n{err}", parent=self)

    def selecionar(self, cod_str, desc_str):
        self.callback(cod_str, desc_str)
        self.destroy()

class DuplicarBandeiraModal(ctk.CTkToplevel):
    def __init__(self, parent, cabecalho_id, callback_sucesso):
        super().__init__(parent)
        self.cabecalho_id = cabecalho_id
        self.callback_sucesso = callback_sucesso
        self.title("Duplicar Cadastro de Bandeira & Taxas")

        self.emp_dest = {"codigo": "", "nome": ""}
        self.fil_dest = {"codigo": "", "nome": ""}

        frame_info = ctk.CTkFrame(self)
        frame_info.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(frame_info, text="Selecione a Empresa e Filial de Destino:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        # Seleção Empresa
        frame_emp = ctk.CTkFrame(frame_info, fg_color="transparent")
        frame_emp.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(frame_emp, text="Empresa Destino:", width=120, anchor="w").pack(side="left")
        self.txt_emp = ctk.CTkEntry(frame_emp, width=240, placeholder_text="Selecione...")
        self.txt_emp.pack(side="left", padx=5)
        btn_lupa_emp = ctk.CTkButton(frame_emp, text="🔍", width=36, command=self.abrir_lupa_emp)
        btn_lupa_emp.pack(side="left")

        # Seleção Filial
        frame_fil = ctk.CTkFrame(frame_info, fg_color="transparent")
        frame_fil.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(frame_fil, text="Filial Destino:", width=120, anchor="w").pack(side="left")
        self.txt_fil = ctk.CTkEntry(frame_fil, width=240, placeholder_text="Selecione...")
        self.txt_fil.pack(side="left", padx=5)
        btn_lupa_fil = ctk.CTkButton(frame_fil, text="🔍", width=36, command=self.abrir_lupa_fil)
        btn_lupa_fil.pack(side="left")

        btn_confirmar = ctk.CTkButton(self, text="📋 Confirmar Duplicação", fg_color="#0288D1", hover_color="#0277BD", font=ctk.CTkFont(weight="bold"), command=self.executar_duplicacao)
        btn_confirmar.pack(fill="x", padx=15, pady=15)

        centralizar_modal(self, 480, 250)

    def abrir_lupa_emp(self):
        LupaEmpresaModal(self, callback=self.set_empresa)

    def set_empresa(self, cod, nome):
        self.emp_dest = {"codigo": cod, "nome": nome}
        self.txt_emp.delete(0, 'end')
        self.txt_emp.insert(0, f"[{cod}] {nome}")

    def abrir_lupa_fil(self):
        if not self.emp_dest["codigo"]:
            messagebox.showwarning("Atenção", "Selecione a Empresa de destino primeiro!", parent=self)
            return
        LupaFilialModal(self, cod_empresa=self.emp_dest["codigo"], callback=self.set_filial)

    def set_filial(self, cod, nome):
        self.fil_dest = {"codigo": cod, "nome": nome}
        self.txt_fil.delete(0, 'end')
        self.txt_fil.insert(0, f"[{cod}] {nome}")

    def executar_duplicacao(self):
        emp_d = self.emp_dest["codigo"]
        fil_d = self.fil_dest["codigo"]

        if not emp_d or not fil_d:
            messagebox.showwarning("Atenção", "Selecione a Empresa e Filial de destino!", parent=self)
            return

        schema = get_schema()
        try:
            conn = get_connection()
            cur = conn.cursor()

            # 1. Busca dados do cabeçalho de origem
            cur.execute(f"SELECT * FROM {schema}.cabecalho_cadastro_bandeiras WHERE id = %s", (self.cabecalho_id,))
            cab_origem = cur.fetchone()

            if not cab_origem:
                messagebox.showerror("Erro", "Cabeçalho de origem não encontrado!", parent=self)
                return

            # 2. Busca cadastro da bandeira correspondente de origem
            cur.execute(f"SELECT * FROM {schema}.bandeiras WHERE empresa_codigo=%s AND filial_codigo=%s AND codigo=%s",
                        (cab_origem['empresa_codigo'], cab_origem['filial_codigo'], cab_origem['bandeira_codigo']))
            band_origem = cur.fetchone()

            # 3. Garante/Grava cadastro da bandeira no destino
            if band_origem:
                cur.execute(f"""
                    INSERT INTO {schema}.bandeiras (codigo, empresa_codigo, filial_codigo, descricao, icone)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (empresa_codigo, filial_codigo, codigo) DO UPDATE SET descricao = EXCLUDED.descricao
                """, (band_origem['codigo'], emp_d, fil_d, band_origem['descricao'], band_origem['icone']))

            # 4. Insere novo cabeçalho no destino
            cur.execute(f"""
                INSERT INTO {schema}.cabecalho_cadastro_bandeiras 
                (empresa_codigo, filial_codigo, bandeira_codigo, conta_baixa, portador, tipo_cobranca, cod_mov, tipo_rec, taxa_antecipacao_automatica, taxa_antecipacao_pontual)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """, (
                emp_d, 
                fil_d, 
                cab_origem['bandeira_codigo'], 
                cab_origem['conta_baixa'], 
                cab_origem['portador'], 
                cab_origem['tipo_cobranca'], 
                cab_origem.get('cod_mov', ''),
                cab_origem.get('tipo_rec', ''),
                cab_origem['taxa_antecipacao_automatica'], 
                cab_origem['taxa_antecipacao_pontual']
            ))
            novo_cab_id = cur.fetchone()['id']

            # 5. Duplica itens (faixas de parcelas)
            cur.execute(f"""
                INSERT INTO {schema}.item_cabecalho_cadastro_bandeiras (cabecalho_id, parcela_inicial, parcela_final, sinal, dias, taxa)
                SELECT %s, parcela_inicial, parcela_final, sinal, dias, taxa
                FROM {schema}.item_cabecalho_cadastro_bandeiras
                WHERE cabecalho_id = %s;
            """, (novo_cab_id, self.cabecalho_id))

            conn.commit()
            conn.close()

            messagebox.showinfo("Sucesso", f"Bandeira [{cab_origem['bandeira_codigo']}] duplicada com sucesso para Empresa [{emp_d}] Filial [{fil_d}]!", parent=self)
            self.callback_sucesso()
            self.destroy()

        except Exception as err:
            messagebox.showerror("Erro ao Duplicar", f"Falha ao duplicar cadastro:\n{err}", parent=self)

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
        self.geometry("1150x760")

        self.empresa_sel = {"codigo": "", "nome": ""}
        self.filial_sel = {"codigo": "", "nome": ""}
        self.conta_sel = {"codigo": "", "nome": ""}
        self.portador_sel = {"codigo": "", "nome": ""}
        self.tipo_cobranca_sel = {"codigo": "", "nome": ""}
        self.cod_mov_sel = {"codigo": "", "nome": ""}
        self.tipo_rec_sel = {"codigo": "", "nome": ""}
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
        
        self.txt_conta = ctk.CTkEntry(frame_conta_box, width=450, placeholder_text="Selecione na Lupa...")
        self.txt_conta.pack(side="left", padx=(0, 5))
        btn_lupa_conta = ctk.CTkButton(frame_conta_box, text="🔍", width=36, command=self.abrir_lupa_conta)
        btn_lupa_conta.pack(side="left")

        # LINHA 2: PORTADOR E TIPO COBRANÇA
        ctk.CTkLabel(frame_form, text="Portador:").grid(row=2, column=0, padx=8, pady=5, sticky="w")
        
        frame_port_box = ctk.CTkFrame(frame_form, fg_color="transparent")
        frame_port_box.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        self.txt_portador = ctk.CTkEntry(frame_port_box, width=220, placeholder_text="Selecione na Lupa...")
        self.txt_portador.pack(side="left", padx=(0, 5))
        btn_lupa_port = ctk.CTkButton(frame_port_box, text="🔍", width=36, command=self.abrir_lupa_portador)
        btn_lupa_port.pack(side="left")

        ctk.CTkLabel(frame_form, text="Tipo Cobrança:").grid(row=2, column=2, padx=8, pady=5, sticky="w")
        
        frame_cobr_box = ctk.CTkFrame(frame_form, fg_color="transparent")
        frame_cobr_box.grid(row=2, column=3, columnspan=3, padx=5, pady=5, sticky="w")
        self.txt_tipo_cobranca = ctk.CTkEntry(frame_cobr_box, width=220, placeholder_text="Selecione na Lupa...")
        self.txt_tipo_cobranca.pack(side="left", padx=(0, 5))
        btn_lupa_cobr = ctk.CTkButton(frame_cobr_box, text="🔍", width=36, command=self.abrir_lupa_tipo_cobranca)
        btn_lupa_cobr.pack(side="left")

        # LINHA 3: COD. MOV BAIXA E TIPO REC. BAIXA
        ctk.CTkLabel(frame_form, text="Cod. Mov Baixa:").grid(row=3, column=0, padx=8, pady=5, sticky="w")
        
        frame_mov_box = ctk.CTkFrame(frame_form, fg_color="transparent")
        frame_mov_box.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        self.txt_cod_mov = ctk.CTkEntry(frame_mov_box, width=220, placeholder_text="Selecione na Lupa...")
        self.txt_cod_mov.pack(side="left", padx=(0, 5))
        btn_lupa_mov = ctk.CTkButton(frame_mov_box, text="🔍", width=36, command=self.abrir_lupa_cod_mov)
        btn_lupa_mov.pack(side="left")

        ctk.CTkLabel(frame_form, text="Tipo Rec.baixa:").grid(row=3, column=2, padx=8, pady=5, sticky="w")
        
        frame_rec_box = ctk.CTkFrame(frame_form, fg_color="transparent")
        frame_rec_box.grid(row=3, column=3, columnspan=3, padx=5, pady=5, sticky="w")
        self.txt_tipo_rec = ctk.CTkEntry(frame_rec_box, width=220, placeholder_text="Selecione na Lupa...")
        self.txt_tipo_rec.pack(side="left", padx=(0, 5))
        btn_lupa_rec = ctk.CTkButton(frame_rec_box, text="🔍", width=36, command=self.abrir_lupa_tipo_rec)
        btn_lupa_rec.pack(side="left")

        # LINHA 4: TAXAS DE ANTECIPAÇÃO
        ctk.CTkLabel(frame_form, text="% Antecip. Auto:").grid(row=4, column=0, padx=8, pady=5, sticky="w")
        self.txt_tx_auto = ctk.CTkEntry(frame_form, width=100, placeholder_text="0.00")
        self.txt_tx_auto.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(frame_form, text="% Antecip. Pontual:").grid(row=4, column=2, padx=8, pady=5, sticky="w")
        self.txt_tx_pontual = ctk.CTkEntry(frame_form, width=100, placeholder_text="0.00")
        self.txt_tx_pontual.grid(row=4, column=3, padx=5, pady=5, sticky="w")

        # FORMULÁRIO ITEM DA TAXA (PARCELAS)
        frame_item = ctk.CTkFrame(self.frame_form_bandeira)
        frame_item.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(frame_item, text="Parc. Ini:").grid(row=0, column=0, padx=4, pady=5)
        self.txt_p_ini = ctk.CTkEntry(frame_item, width=60)
        self.txt_p_ini.grid(row=0, column=1, padx=2, pady=5)

        ctk.CTkLabel(frame_item, text="Parc. Fim:").grid(row=0, column=2, padx=4, pady=5)
        self.txt_p_fim = ctk.CTkEntry(frame_item, width=60)
        self.txt_p_fim.grid(row=0, column=3, padx=2, pady=5)

        ctk.CTkLabel(frame_item, text="Sinal:").grid(row=0, column=4, padx=4, pady=5)
        self.cmb_sinal = ctk.CTkComboBox(frame_item, width=70, values=["=", ">="])
        self.cmb_sinal.grid(row=0, column=5, padx=2, pady=5)

        ctk.CTkLabel(frame_item, text="Dias:").grid(row=0, column=6, padx=4, pady=5)
        self.txt_dias = ctk.CTkEntry(frame_item, width=60)
        self.txt_dias.grid(row=0, column=7, padx=2, pady=5)

        ctk.CTkLabel(frame_item, text="% Taxa:").grid(row=0, column=8, padx=4, pady=5)
        self.txt_taxa = ctk.CTkEntry(frame_item, width=80)
        self.txt_taxa.grid(row=0, column=9, padx=2, pady=5)

        btn_add_item = ctk.CTkButton(frame_item, text="➕ Add Faixa", width=90, fg_color="#1976D2", hover_color="#0D47A1", command=self.adicionar_item_parcela)
        btn_add_item.grid(row=0, column=10, padx=8, pady=5)

        # TABELA DE PARCELAS/TAXAS
        self.frame_grid = ctk.CTkScrollableFrame(self.frame_form_bandeira, height=180)
        self.frame_grid.pack(fill="both", expand=True, padx=10, pady=5)

        # BOTÃO SALVAR
        frame_bot = ctk.CTkFrame(self.frame_form_bandeira, fg_color="transparent")
        frame_bot.pack(fill="x", padx=10, pady=10)

        btn_salvar = ctk.CTkButton(frame_bot, text="💾 Salvar Cadastro Completo", fg_color="#2E7D32", hover_color="#1B5E20", font=ctk.CTkFont(weight="bold"), height=36, command=self.salvar_tudo)
        btn_salvar.pack(side="right", padx=5)

        self.exibir_lista()

    def exibir_lista(self):
        self.frame_form_bandeira.pack_forget()
        self.frame_lista_bandeiras.pack(fill="both", expand=True)
        self.carregar_lista_bandeiras()

    def exibir_formulario(self):
        self.frame_lista_bandeiras.pack_forget()
        self.frame_form_bandeira.pack(fill="both", expand=True)

    def nova_bandeira(self):
        if not self.empresa_sel["codigo"] or not self.filial_sel["codigo"]:
            messagebox.showwarning("Atenção", "Selecione a Empresa e a Filial primeiro!", parent=self)
            return

        self.editando_id = None
        self.lbl_titulo_form.configure(text="Cadastro de Nova Bandeira & Taxas")
        self.limpar_formulario()
        self.exibir_formulario()

    def limpar_formulario(self):
        self.txt_band_cod.delete(0, 'end')
        self.txt_band_desc.delete(0, 'end')
        self.txt_conta.delete(0, 'end')
        self.txt_portador.delete(0, 'end')
        self.txt_tipo_cobranca.delete(0, 'end')
        self.txt_cod_mov.delete(0, 'end')
        self.txt_tipo_rec.delete(0, 'end')
        self.txt_tx_auto.delete(0, 'end')
        self.txt_tx_pontual.delete(0, 'end')

        self.conta_sel = {"codigo": "", "nome": ""}
        self.portador_sel = {"codigo": "", "nome": ""}
        self.tipo_cobranca_sel = {"codigo": "", "nome": ""}
        self.cod_mov_sel = {"codigo": "", "nome": ""}
        self.tipo_rec_sel = {"codigo": "", "nome": ""}
        self.itens_parcela.clear()
        self.atualizar_grid_items()

    def carregar_lista_bandeiras(self):
        for w in self.scroll_bandeiras.winfo_children():
            w.destroy()

        emp_cod = self.empresa_sel["codigo"]
        fil_cod = self.filial_sel["codigo"]

        if not emp_cod or not fil_cod:
            ctk.CTkLabel(self.scroll_bandeiras, text="Selecione uma Empresa e Filial acima para listar as bandeiras.", text_color="gray").pack(pady=30)
            return

        schema = get_schema()
        try:
            conn = get_connection()
            cur = conn.cursor()
            query = f"""
                SELECT c.id, c.bandeira_codigo, b.descricao 
                FROM {schema}.cabecalho_cadastro_bandeiras c
                LEFT JOIN {schema}.bandeiras b 
                       ON b.empresa_codigo = c.empresa_codigo 
                      AND b.filial_codigo = c.filial_codigo 
                      AND b.codigo = c.bandeira_codigo
                WHERE c.empresa_codigo = %s AND c.filial_codigo = %s
                ORDER BY c.bandeira_codigo;
            """
            cur.execute(query, (emp_cod, fil_cod))
            res = cur.fetchall()
            conn.close()

            if not res:
                ctk.CTkLabel(self.scroll_bandeiras, text="Nenhuma bandeira cadastrada para esta empresa/filial.", text_color="gray").pack(pady=30)
                return

            for item in res:
                row = ctk.CTkFrame(self.scroll_bandeiras)
                row.pack(fill="x", pady=4, padx=5)

                lbl_cod = f"[{item['bandeira_codigo']}]"
                lbl_desc = item['descricao'] or 'Sem Descrição'

                ctk.CTkLabel(row, text=lbl_cod, font=ctk.CTkFont(weight="bold"), width=80).pack(side="left", padx=10)
                ctk.CTkLabel(row, text=lbl_desc, font=ctk.CTkFont(size=14), anchor="w").pack(side="left", fill="x", expand=True, padx=10)

                btn_edt = ctk.CTkButton(row, text="✏️ Editar", width=80, fg_color="#F57C00", hover_color="#E65100", command=lambda cid=item['id']: self.editar_bandeira(cid))
                btn_edt.pack(side="right", padx=3)

                btn_dup = ctk.CTkButton(row, text="📋 Duplicar", width=85, fg_color="#0288D1", hover_color="#0277BD", command=lambda cid=item['id']: self.duplicar_bandeira(cid))
                btn_dup.pack(side="right", padx=3)

                btn_del = ctk.CTkButton(row, text="🗑️ Excluir", width=80, fg_color="#C62828", hover_color="#B71C1C", command=lambda cid=item['id']: self.excluir_bandeira(cid))
                btn_del.pack(side="right", padx=3)

        except Exception as err:
            messagebox.showerror("Erro ao Listar", f"Falha ao buscar bandeiras salvas:\n{err}", parent=self)

    def duplicar_bandeira(self, cabecalho_id):
        DuplicarBandeiraModal(self, cabecalho_id, callback_sucesso=self.carregar_lista_bandeiras)

    def editar_bandeira(self, cabecalho_id):
        schema = get_schema()
        emp_cod = self.empresa_sel['codigo']
        try:
            conn = get_connection()

            # Descobre schemas corretos das tabelas auxiliares (com fallback para xemp_0001)
            schema_bcconta = obter_schema_tabela_existente(conn, emp_cod, "bcconta")
            schema_rpport = obter_schema_tabela_existente(conn, emp_cod, "rpport")
            schema_rpcobr = obter_schema_tabela_existente(conn, emp_cod, "rpcobr")
            schema_bccmov = obter_schema_tabela_existente(conn, emp_cod, "bccmov")
            schema_rptiprp = obter_schema_tabela_existente(conn, emp_cod, "rptiprp")

            cur = conn.cursor()

            # 1. Carrega Cabeçalho
            cur.execute(f"SELECT * FROM {schema}.cabecalho_cadastro_bandeiras WHERE id = %s", (cabecalho_id,))
            cab = cur.fetchone()

            if not cab:
                messagebox.showerror("Erro", "Registro não encontrado!", parent=self)
                return

            self.editando_id = cabecalho_id
            self.limpar_formulario()
            self.lbl_titulo_form.configure(text=f"Editando Bandeira [{cab['bandeira_codigo']}]")

            # 2. Carrega Descrição da Bandeira
            cur.execute(f"SELECT descricao FROM {schema}.bandeiras WHERE empresa_codigo=%s AND filial_codigo=%s AND codigo=%s", 
                        (cab['empresa_codigo'], cab['filial_codigo'], cab['bandeira_codigo']))
            b_info = cur.fetchone()
            desc_b = b_info['descricao'] if b_info else ""

            self.txt_band_cod.insert(0, cab['bandeira_codigo'])
            self.txt_band_desc.insert(0, desc_b)
            self.txt_tx_auto.insert(0, str(cab['taxa_antecipacao_automatica'] or 0.0))
            self.txt_tx_pontual.insert(0, str(cab['taxa_antecipacao_pontual'] or 0.0))

            # 3. Descrições das tabelas auxiliares tratando compartilhamento
            if cab.get('conta_baixa'):
                cur.execute(f"SELECT fno AS desc FROM {schema_bcconta}.bcconta WHERE fco = %s", (cab['conta_baixa'],))
                r = cur.fetchone()
                desc = r['desc'] if r else ""
                self.set_conta(cab['conta_baixa'], desc)

            if cab.get('portador'):
                cur.execute(f"SELECT fde AS desc FROM {schema_rpport}.rpport WHERE fco = %s", (cab['portador'],))
                r = cur.fetchone()
                desc = r['desc'] if r else ""
                self.set_portador(cab['portador'], desc)

            if cab.get('tipo_cobranca'):
                cur.execute(f"SELECT fde AS desc FROM {schema_rpcobr}.rpcobr WHERE fco = %s", (cab['tipo_cobranca'],))
                r = cur.fetchone()
                desc = r['desc'] if r else ""
                self.set_tipo_cobranca(cab['tipo_cobranca
