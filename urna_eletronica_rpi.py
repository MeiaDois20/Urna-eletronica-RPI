"""
Urna Eletrônica (Raspberry Pi) - Tkinter + SQLite + Pygame (som)
Arquitetura: MVC simples em um arquivo para facilitar execução no Raspberry Pi.

Requisitos:
 - Python 3
 - bibliotecas: pillow, pygame
   pip3 install pillow pygame
 - Banco SQLite: votos.db com tabelas 'candidatos' e 'votos'.
 - Fotos dos candidatos em ./images/candidate_<id>.png (id = candidato.id)
 - Som de confirmação em ./sounds/puc.wav

Como rodar:
 - Coloque esse arquivo no Raspberry Pi, crie a pasta images e sounds
 - Ajuste caminhos se necessário
 - python3 urna_eletronica_rpi.py

Notas:
 - O código tenta ser resiliente: se uma foto não existir, mostra um placeholder.
 - A animação da tela final é feita com um efeito simples (fade-out por camada).
 - Relatório de votos pode ser salvo em CSV.

"""

import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk, ImageOps
import sqlite3
import os
import csv
import pygame
import threading
import time

# ----------------- CONFIGURAÇÕES -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "votos.db")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")

PUC_SOUND = os.path.join(SOUNDS_DIR, "confirma-urna.mp3")
PHOTO_PLACEHOLDER = os.path.join(IMAGES_DIR, "placeholder.png")
MAX_DIGITS = 2  # ajuste conforme necessidade


# ----------------- MODELO (Banco) -----------------
class Model:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._ensure_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _ensure_db(self):
        # Cria tabelas básicas se não existirem
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS candidatos (
                id INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                partido TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS votos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidato_id INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def get_candidato(self, id_):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT id, nome, partido FROM candidatos WHERE id = ?", (id_,))
        row = cur.fetchone()
        conn.close()
        return row

    
    def gravar_voto(self, candidato_id):
        conn = self._conn()  # conexão aberta dentro do método
        cur = conn.cursor()

        # candidato_id pode ser None para BRANCO ou NULO
        if candidato_id is None:
            voto_tipo = "BRANCO"
            candidato_val = None
        else:
            voto_tipo = "VALIDO"
            candidato_val = candidato_id

        cur.execute(
            "INSERT INTO votos (candidato_id, voto_tipo) VALUES (?, ?)",
            (candidato_val, voto_tipo)
        )
        conn.commit()
        conn.close()


    def contar_votos(self):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT candidato_id, COUNT(*) FROM votos GROUP BY candidato_id")
        rows = cur.fetchall()
        conn.close()
        # transformar em dict {id: count}
        return {r[0]: r[1] for r in rows}

    def listar_candidatos(self):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT id, nome, partido FROM candidatos ORDER BY id")
        rows = cur.fetchall()
        conn.close()
        return rows

# ----------------- SOM (pygame) -----------------
class SoundPlayer:
    def __init__(self, puc_path=PUC_SOUND):
        self.puc_path = puc_path
        pygame.mixer.init()

    def play_puc(self):
        if not os.path.exists(self.puc_path):
            return
        # tocar em thread para não bloquear UI
        threading.Thread(target=self._play_file, args=(self.puc_path,), daemon=True).start()

    def _play_file(self, path):
        try:
            snd = pygame.mixer.Sound(path)
            snd.play()
            # esperar até terminar (breve)
            time.sleep(snd.get_length())
        except Exception as e:
            print("Erro ao tocar som:", e)

# ----------------- VIEW (Tkinter) -----------------
class UrnaView(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.title("Urna Eletrônica")
        self.attributes("-fullscreen", True)
        self.configure(bg="#111")

        # top frame: display candidato
        self.top_frame = tk.Frame(self, bg="#222", pady=20)
        self.top_frame.pack(fill="x")

        # foto
        self.photo_label = tk.Label(self.top_frame, bg="#222")
        self.photo_label.pack(side="left", padx=40)

        # info (numero, nome, partido)
        self.info_frame = tk.Frame(self.top_frame, bg="#222")
        self.info_frame.pack(side="left", padx=20)

        self.numero_label = tk.Label(self.info_frame, text="", font=("Helvetica", 72), bg="#222", fg="#fff")
        self.numero_label.pack(anchor="w")

        self.nome_label = tk.Label(self.info_frame, text="", font=("Helvetica", 36), bg="#222", fg="#fff")
        self.nome_label.pack(anchor="w", pady=(10,0))

        self.partido_label = tk.Label(self.info_frame, text="", font=("Helvetica", 24), bg="#222", fg="#ddd")
        self.partido_label.pack(anchor="w")

        # teclado
        self.keypad_frame = tk.Frame(self, bg="#333", pady=30)
        self.keypad_frame.pack()

        btn_font = ("Helvetica", 28)
        keys = [["1","2","3"], ["4","5","6"], ["7","8","9"], ["0"]]
        for row in keys:
            row_frame = tk.Frame(self.keypad_frame, bg="#333")
            row_frame.pack()
            for k in row:
                b = tk.Button(row_frame, text=k, font=btn_font, width=4, height=2,
                              command=lambda val=k: self.controller.on_digit(val))
                b.pack(side="left", padx=8, pady=6)

        # botoes especiais
        self.special_frame = tk.Frame(self, bg="#333", pady=20)
        self.special_frame.pack()

        self.btn_branco = tk.Button(self.special_frame, text="BRANCO", font=("Helvetica",20), width=10,
                                    command=self.controller.on_branco)
        self.btn_branco.pack(side="left", padx=12)

        self.btn_corrige = tk.Button(self.special_frame, text="CORRIGE", font=("Helvetica",20), width=10,
                                     command=self.controller.on_corrige)
        self.btn_corrige.pack(side="left", padx=12)

        self.btn_confirma = tk.Button(self.special_frame, text="CONFIRMA", font=("Helvetica",20), width=10,
                                      command=self.controller.on_confirma)
        self.btn_confirma.pack(side="left", padx=12)

        # rodapé com ações administrativas (não visível para eleitor)
        self.footer_frame = tk.Frame(self, bg="#111")
        self.footer_frame.pack(side="bottom", fill="x", pady=10)

        self.btn_relatorio = tk.Button(self.footer_frame, text="Relatório (admin)", command=self.controller.on_relatorio)
        self.btn_relatorio.pack(side="left", padx=8)

        self.btn_sair = tk.Button(self.footer_frame, text="Sair", command=self.controller.on_exit)
        self.btn_sair.pack(side="right", padx=8)

        # variáveis de interface
        self.current_photo = None

    def atualizar_numero(self, numero_text):
        self.numero_label.config(text=numero_text)

    def atualizar_candidato(self, candidato):
        # candidato: (id, nome, partido) ou None
        if candidato is None:
            self.nome_label.config(text="")
            self.partido_label.config(text="")
            self._set_photo_by_id(None)
            return
        _id, nome, partido = candidato
        self.nome_label.config(text=nome)
        self.partido_label.config(text=partido or "")
        self._set_photo_by_id(_id)

    def _set_photo_by_id(self, id_):
        # carrega imagem do candidato se existir, senão placeholder
        img_path = None
        if id_ is None:
            img_path = PHOTO_PLACEHOLDER if os.path.exists(PHOTO_PLACEHOLDER) else None
        else:
            candidate_img = os.path.join(IMAGES_DIR, f"candidate_{id_}.png")
            if os.path.exists(candidate_img):
                img_path = candidate_img
            else:
                img_path = PHOTO_PLACEHOLDER if os.path.exists(PHOTO_PLACEHOLDER) else None

        if img_path:
            try:
                img = Image.open(img_path)
                img = ImageOps.contain(img, (240, 240))
                photo = ImageTk.PhotoImage(img)
                self.current_photo = photo
                self.photo_label.config(image=photo)
            except Exception as e:
                print("Erro ao carregar foto:", e)
                self.photo_label.config(image="")
        else:
            self.photo_label.config(image="")

    def animacao_fim(self, callback=None):
        # mostrará um overlay branco que aumenta a opacidade (simples)
        overlay = tk.Toplevel(self)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-topmost", True)
        overlay.config(bg="#000")
        overlay.lift()

        canvas = tk.Canvas(overlay, bg="#000", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        steps = 20
        for i in range(steps):
            alpha = int(255 * (i+1)/steps)
            # criar retângulo com cor rgba não é trivial; usar imagem transparente é complexo
            # simplificamos mudando a cor do canvas gradualmente para branco
            grey = int(255 * (i+1)/steps)
            color = '#%02x%02x%02x' % (grey, grey, grey)
            canvas.configure(bg=color)
            overlay.update()
            time.sleep(0.03)

        # mensagem FIM
        canvas.create_text(self.winfo_screenwidth()/2, self.winfo_screenheight()/2,
                           text="FIM", font=("Helvetica", 96), fill="#000")
        overlay.update()
        if callback:
            self.after(1200, lambda: (overlay.destroy(), callback()))
        else:
            self.after(1200, overlay.destroy)

    def perguntar_salvar_relatorio(self):
        f = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files","*.csv")])
        return f

# ----------------- CONTROLLER -----------------
class Controller:
    def __init__(self):
        self.model = Model()
        self.sound = SoundPlayer()
        self.view = UrnaView(self)
        self.numero = ""
        self.view.atualizar_numero("")
        self.view.atualizar_candidato(None)

    # eventos UI
    def on_digit(self, digit):
        if len(self.numero) >= MAX_DIGITS:
            return
        self.numero += digit
        self.view.atualizar_numero(self.numero)
        # tentar mostrar candidato se número completo
        try:
            if len(self.numero) == MAX_DIGITS:
                cid = int(self.numero)
                candidato = self.model.get_candidato(cid)
                if candidato:
                    self.view.atualizar_candidato(candidato)
                else:
                    self.view.atualizar_candidato(None)
        except Exception as e:
            print("Erro ao buscar candidato:", e)

    def on_corrige(self):
        self.numero = ""
        self.view.atualizar_numero("")
        self.view.atualizar_candidato(None)

    def on_branco(self):
        self.numero = "BRANCO"
        self.view.atualizar_numero("BRANCO")
        self.view.atualizar_candidato(None)

    def on_confirma(self):
        # lógica de confirmação
        if self.numero == "":
            messagebox.showwarning("Erro", "Nenhum número digitado.")
            return

        # tocar som e gravar voto com pequena animação
        # tocar som em thread
        self.sound.play_puc()

        if self.numero == "BRANCO":
            self.model.gravar_voto(None)
            messagebox.showinfo("Voto", "Voto em BRANCO confirmado!")
            # animação fim e reset
            self.view.animacao_fim(callback=self._reset_after_vote)
            return

        if self.numero.isdigit():
            cid = int(self.numero)
            candidato = self.model.get_candidato(cid)
            if candidato:
                self.model.gravar_voto(cid)
                messagebox.showinfo("Voto", f"Voto confirmado para {candidato[1]}")
                self.view.animacao_fim(callback=self._reset_after_vote)
            else:
                # voto nulo
                resp = messagebox.askyesno("Confirmar", "Candidato não encontrado. Confirma voto NULO?")
                if resp:
                    self.model.gravar_voto(None)
                    self.sound.play_puc()
                    self.view.animacao_fim(callback=self._reset_after_vote)
        else:
            messagebox.showerror("Erro", "Número inválido.")

    def _reset_after_vote(self):
        # limpa tela e prepara próximo eleitor
        self.numero = ""
        self.view.atualizar_numero("")
        self.view.atualizar_candidato(None)

    def on_relatorio(self):
        # gerar relatório e mostrar em janela
        votos = self.model.contar_votos()  # dict {id: count}
        candidatos = {c[0]: (c[1], c[2]) for c in self.model.listar_candidatos()}

        # criar janela relatório
        win = tk.Toplevel(self.view)
        win.title("Relatório de Votos")
        txt = tk.Text(win, width=60, height=20)
        txt.pack()

        total = 0
        for cid, count in votos.items():
            total += count
            if cid is None:
                txt.insert("end", f"BRANCOS: {count}\n")
            else:
                nome, partido = candidatos.get(cid, ("<desconhecido>", ""))
                txt.insert("end", f"{cid} - {nome} ({partido}) : {count}\n")

        # mostrar candidatos sem votos
        for cid, (nome, partido) in candidatos.items():
            if cid not in votos:
                txt.insert("end", f"{cid} - {nome} ({partido}) : 0\n")

        txt.insert("end", f"\nTotal votos registrados: {total}\n")

        def salvar():
            path = self.view.perguntar_salvar_relatorio()
            if not path:
                return
            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["candidato_id","nome","partido","votos"])
                    for cid, count in votos.items():
                        if cid is None:
                            writer.writerow(["BRANCO","BRANCO","",count])
                        else:
                            nome, partido = candidatos.get(cid, ("<desconhecido>", ""))
                            writer.writerow([cid, nome, partido, count])
                messagebox.showinfo("Salvo", f"Relatório salvo em {path}")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao salvar: {e}")

        btn_save = tk.Button(win, text="Salvar CSV", command=salvar)
        btn_save.pack(pady=8)

    def on_exit(self):
        if messagebox.askyesno("Sair", "Deseja realmente sair?"):
            try:
                pygame.mixer.quit()
            except:
                pass
            self.view.destroy()

    def run(self):
        self.view.mainloop()

# ----------------- EXECUÇÃO -----------------
if __name__ == '__main__':
    # criar pastas se necessário
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(SOUNDS_DIR, exist_ok=True)

    # se não existir placeholder, cria um básico
    if not os.path.exists(PHOTO_PLACEHOLDER):
        try:
            img = Image.new('RGB', (240,240), color=(200,200,200))
            img.save(PHOTO_PLACEHOLDER)
        except Exception:
            pass
    
    # Inserir candidatos automaticamente (execute só 1 vez)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    candidatos = [
        (13, "Lula", "PT"),
        (22, "Bolsonaro", "PL"),
    ]

    for c in candidatos:
        try:
            cur.execute("INSERT INTO candidatos (id, nome, partido) VALUES (?, ?, ?)", c)
        except:
            pass  # ignora se já existe

    conn.commit()
    conn.close()

    controller = Controller()
    controller.run()



