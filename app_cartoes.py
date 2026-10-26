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

    -- TABELA EMPRESA
    CREATE TABLE IF NOT EXISTS {schema}.empresa (
        codigo VARCHAR(10) PRIMARY KEY,
        nome VARCHAR(100) NOT NULL
    );

    -- TABELA FILIAL
    CREATE TABLE IF NOT EXISTS {schema}.filial (
        codigo VARCHAR(10) NOT NULL,
        nome VARCHAR(100) NOT NULL,
        empresa_codigo VARCHAR(10) NOT NULL,
        PRIMARY KEY (empresa_codigo, codigo),
        CONSTRAINT fk_filial_empresa FOREIGN KEY (empresa_codigo) REFERENCES {schema}.empresa(codigo) ON DELETE CASCADE
    );

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
        schema = get_schema()
        try:
            conn = get_connection()
            cur = conn.cursor()
            # Tenta buscar do xgeral.geempre ou da tabela importada
            query = f"SELECT fco AS codigo, fnu AS nome FROM xgeral.geempre WHERE CAST(fco AS TEXT) ILIKE %s OR fnu ILIKE %s LIMIT 30"
            try:
                cur.execute(query, (f"%{termo}%", f"%{termo}%"))
                res = cur.fetchall()
            except Exception:
                conn.rollback()
                cur.execute(f"SELECT codigo, nome FROM {schema}.empresa WHERE codigo ILIKE %s OR nome ILIKE %s LIMIT 30", (f"%{termo}%", f"%{termo}%"))
                res = cur.fetchall()
            conn.close()

            for emp in res:
                row = ctk.CTkFrame(self.frame_lista)
                row.pack(fill="x", pady=2, padx=2)
                ctk.CTkLabel(row, text=f"[{emp['codigo']}]", font=ctk.CTkFont(weight="bold"), width=60).pack(side="left", padx=5)
                ctk.CTkLabel(row, text=emp['nome'], anchor="w").pack(side="left", fill="x", expand=True, padx=5)
                btn_sel = ctk.CTkButton(row, text="✔", width=40, command=lambda e=emp: self.selecionar(e))
                btn_sel.pack(side="right", padx=5)
        except Exception as err:
            messagebox.showerror("Erro", f"Erro na consulta de empresas:\n{err}", parent=self)

    def selecionar(self, emp):
        # Salva a empresa localmente na tabela de cache se necessário
        schema = get_schema()
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(f"INSERT INTO {schema}.empresa (codigo, nome) VALUES (%s, %s) ON CONFLICT (codigo) DO UPDATE SET nome = EXCLUDED.nome", (str(emp['codigo']), str(emp['nome'])))
            conn.commit()
            conn.close()
        except Exception:
            pass
        self.callback(str(emp['codigo']), str(emp['nome']))
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
        schema = get_schema()
        try:
            conn = get_connection()
            cur = conn.cursor()
            query = "SELECT fcodigo AS codigo, fnome AS nome FROM xemp_0001.gefil WHERE CAST(fcodigo AS TEXT) ILIKE %s OR fnome ILIKE %s LIMIT 30"
            try:
                cur.execute(query, (f"%{termo}%", f"%{termo}%"))
                res = cur.fetchall()
            except Exception:
                conn.rollback()
                cur.execute(f"SELECT codigo, nome FROM {schema}.filial WHERE empresa_codigo = %s AND (codigo ILIKE %s OR nome ILIKE %s) LIMIT 30", (self.cod_empresa, f"%{termo}%", f"%{termo}%"))
                res = cur.fetchall()
            conn.close()

            for fil in res:
                row = ctk.CTkFrame(self.frame_lista)
                row.pack(fill="x", pady=2, padx=2)
                ctk.CTkLabel(row, text=f"[{fil['codigo']}]", font=ctk.CTkFont(weight="bold"), width=60).pack(side="left", padx=5)
                ctk.CTkLabel(row, text=fil['nome'], anchor="w").pack(side="left", fill="x", expand=True, padx=5)
                btn_sel = ctk.CTkButton(row, text="✔", width=40, command=lambda f=fil: self.selecionar(f))
                btn_sel.pack(side="right", padx=5)
        except Exception as err:
            messagebox.showerror("Erro", f"Erro na consulta de filiais:\n{err}", parent=self)

    def selecionar(self, fil):
        schema = get_schema()
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(f"INSERT INTO {schema}.filial (codigo, nome, empresa_codigo) VALUES (%s, %s, %s) ON CONFLICT (empresa_codigo, codigo) DO UPDATE SET nome = EXCLUDED.nome", (str(fil['codigo']), str(fil['nome']), self.cod_empresa))
            conn.commit()
            conn.close()
        except Exception:
            pass
        self.callback(str(fil['codigo']), str(fil['nome']))
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
        self.geometry("1100x700")

        self.empresa_sel = {"codigo": "", "nome": ""}
        self.filial_sel = {"codigo": "", "nome": ""}
        self.itens_parcela = []

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
        self.txt_emp = ctk.CTkEntry(frame_emp_fil, width=220, placeholder_text="Selecione na Lupa...")
        self.txt_emp.grid(row=0, column=1, padx=5, pady=8)
        btn_lupa_emp = ctk.CTkButton(frame_emp_fil, text="🔍", width=36, command=self.abrir_lupa_emp)
        btn_lupa_emp.grid(row=0, column=2, padx=2, pady=8)

        ctk.CTkLabel(frame_emp_fil, text="Filial:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=3, padx=15, pady=8, sticky="w")
        self.txt_fil = ctk.CTkEntry(frame_emp_fil, width=220, placeholder_text="Selecione na Lupa...")
        self.txt_fil.grid(row=0, column=4, padx=5, pady=8)
        btn_lupa_fil = ctk.CTkButton(frame_emp_fil, text="🔍", width=36, command=self.abrir_lupa_fil)
        btn_lupa_fil.grid(row=0, column=5, padx=2, pady=8)

        # SEÇÃO BANDEIRA E PARÂMETROS
        tabview = ctk.CTkTabview(self)
        tabview.pack(fill="both", expand=True, padx=15, pady=10)

        tab_bandeira = tabview.add("Cadastro de Bandeira & Taxas")

        # FORMULÁRIO BANDEIRA E CABEÇALHO
        frame_form = ctk.CTkFrame(tab_bandeira)
        frame_form.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(frame_form, text="Cód. Bandeira:").grid(row=0, column=0, padx=8, pady=5, sticky="w")
        self.txt_band_cod = ctk.CTkEntry(frame_form, width=80, placeholder_text="001")
        self.txt_band_cod.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(frame_form, text="Descrição:").grid(row=0, column=2, padx=8, pady=5, sticky="w")
        self.txt_band_desc = ctk.CTkEntry(frame_form, width=220, placeholder_text="VISA / MASTERCARD...")
        self.txt_band_desc.grid(row=0, column=3, padx=5, pady=5)

        ctk.CTkLabel(frame_form, text="Conta Baixa:").grid(row=1, column=0, padx=8, pady=5, sticky="w")
        self.txt_conta = ctk.CTkEntry(frame_form, width=150)
        self.txt_conta.grid(row=1, column=1, padx=5, pady=5)

        ctk.CTkLabel(frame_form, text="Portador:").grid(row=1, column=2, padx=8, pady=5, sticky="w")
        self.txt_portador = ctk.CTkEntry(frame_form, width=150)
        self.txt_portador.grid(row=1, column=3, padx=5, pady=5)

        ctk.CTkLabel(frame_form, text="% Antecip. Auto:").grid(row=2, column=0, padx=8, pady=5, sticky="w")
        self.txt_tx_auto = ctk.CTkEntry(frame_form, width=100, placeholder_text="0.00")
        self.txt_tx_auto.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(frame_form, text="% Antecip. Pontual:").grid(row=2, column=2, padx=8, pady=5, sticky="w")
        self.txt_tx_pontual = ctk.CTkEntry(frame_form, width=100, placeholder_text="0.00")
        self.txt_tx_pontual.grid(row=2, column=3, padx=5, pady=5, sticky="w")

        # FORMULÁRIO ITEM DA TAXA (PARCELAS)
        frame_item = ctk.CTkFrame(tab_bandeira)
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
        self.frame_grid = ctk.CTkScrollableFrame(tab_bandeira, height=180)
        self.frame_grid.pack(fill="both", expand=True, padx=10, pady=5)

        # BOTOES DE AÇÃO
        frame_bot = ctk.CTkFrame(self, fg_color="transparent")
        frame_bot.pack(fill="x", padx=15, pady=10)

        btn_salvar = ctk.CTkButton(frame_bot, text="💾 Salvar Cadastro Completo", fg_color="#2E7D32", hover_color="#1B5E20", font=ctk.CTkFont(weight="bold"), height=36, command=self.salvar_tudo)
        btn_salvar.pack(side="right", padx=5)

    def abrir_config(self):
        ConfigBancoWindow(self)

    def abrir_lupa_emp(self):
        LupaEmpresaModal(self, callback=self.set_empresa)

    def set_empresa(self, cod, nome):
        self.empresa_sel = {"codigo": cod, "nome": nome}
        self.txt_emp.delete(0, 'end')
        self.txt_emp.insert(0, f"[{cod}] {nome}")

    def abrir_lupa_fil(self):
        if not self.empresa_sel["codigo"]:
            messagebox.showwarning("Atenção", "Selecione uma Empresa primeiro!", parent=self)
            return
        LupaFilialModal(self, cod_empresa=self.empresa_sel["codigo"], callback=self.set_filial)

    def set_filial(self, cod, nome):
        self.filial_sel = {"codigo": cod, "nome": nome}
        self.txt_fil.delete(0, 'end')
        self.txt_fil.insert(0, f"[{cod}] {nome}")

    def adicionar_item_parcela(self):
        try:
            p_ini = int(self.txt_p_ini.get().strip())
            p_fim = int(self.txt_p_fim.get().strip())
            sinal = self.cmb_sinal.get()
            dias = int(self.txt_dias.get().strip())
            taxa = float(self.txt_taxa.get().strip().replace(',', '.'))
        except ValueError:
            messagebox.showerror("Erro", "Valores de parcelas, dias e taxas devem ser válidos!", parent=self)
            return

        self.itens_parcela.append({"p_ini": p_ini, "p_fim": p_fim, "sinal": sinal, "dias": dias, "taxa": taxa})
        self.atualizar_grid_items()

        self.txt_p_ini.delete(0, 'end')
        self.txt_p_fim.delete(0, 'end')
        self.txt_dias.delete(0, 'end')
        self.txt_taxa.delete(0, 'end')

    def atualizar_grid_items(self):
        for w in self.frame_grid.winfo_children():
            w.destroy()

        for idx, item in enumerate(self.itens_parcela):
            row = ctk.CTkFrame(self.frame_grid)
            row.pack(fill="x", pady=2, padx=2)
            lbl = f"Parcelas: {item['p_ini']} até {item['p_fim']} | Sinal: {item['sinal']} | Dias: {item['dias']} | Taxa: {item['taxa']:.2f}%"
            ctk.CTkLabel(row, text=lbl, anchor="w").pack(side="left", padx=10, expand=True)
            btn_del = ctk.CTkButton(row, text="🗑️", width=32, fg_color="#C62828", hover_color="#B71C1C", command=lambda i=idx: self.remover_item(i))
            btn_del.pack(side="right", padx=5)

    def remover_item(self, idx):
        self.itens_parcela.pop(idx)
        self.atualizar_grid_items()

    def salvar_tudo(self):
        schema = get_schema()
        emp_cod = self.empresa_sel["codigo"]
        fil_cod = self.filial_sel["codigo"]
        band_cod = self.txt_band_cod.get().strip()
        band_desc = self.txt_band_desc.get().strip()

        if not emp_cod or not fil_cod or not band_cod or not band_desc:
            messagebox.showwarning("Atenção", "Selecione Empresa, Filial e preencha Código e Descrição da Bandeira!", parent=self)
            return

        try:
            conn = get_connection()
            cur = conn.cursor()

            # 1. Salva Bandeira
            cur.execute(f"""
                INSERT INTO {schema}.bandeiras (codigo, empresa_codigo, filial_codigo, descricao)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (empresa_codigo, filial_codigo, codigo) DO UPDATE SET descricao = EXCLUDED.descricao
            """, (band_cod, emp_cod, fil_cod, band_desc))

            # 2. Salva Cabeçalho Cadastro Bandeira
            tx_auto = float(self.txt_tx_auto.get().strip().replace(',', '.') or 0)
            tx_pontual = float(self.txt_tx_pontual.get().strip().replace(',', '.') or 0)

            cur.execute(f"""
                INSERT INTO {schema}.cabecalho_cadastro_bandeiras 
                (empresa_codigo, filial_codigo, bandeira_codigo, conta_baixa, portador, taxa_antecipacao_automatica, taxa_antecipacao_pontual)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """, (emp_cod, fil_cod, band_cod, self.txt_conta.get().strip(), self.txt_portador.get().strip(), tx_auto, tx_pontual))

            cabecalho_id = cur.fetchone()['id']

            # 3. Salva Itens das Parcelas
            for item in self.itens_parcela:
                cur.execute(f"""
                    INSERT INTO {schema}.item_cabecalho_cadastro_bandeiras
                    (cabecalho_id, parcela_inicial, parcela_final, sinal, dias, taxa)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (cabecalho_id, item['p_ini'], item['p_fim'], item['sinal'], item['dias'], item['taxa']))

            conn.commit()
            conn.close()

            messagebox.showinfo("Sucesso", "Cadastro e Taxas gravados com sucesso!", parent=self)
            self.itens_parcela.clear()
            self.atualizar_grid_items()

        except Exception as err:
            messagebox.showerror("Erro ao Salvar", f"Falha ao gravar registros no banco:\n{err}", parent=self)

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = AppCartoesPrincipal()
    app.mainloop()
