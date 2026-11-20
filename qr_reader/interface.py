import base64
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import cv2


class PalletInterface:
    COLORE_PRIMARIO = "#2563EB"
    COLORE_PRIMARIO_SCuro = "#1D4ED8"
    COLORE_TESTO = "#172033"
    COLORE_SECONDARIO = "#64748B"
    COLORE_BORDO = "#DCE4EF"
    COLORE_CARTA = "#FFFFFF"
    COLORE_SUCCESSO = "#16A34A"
    COLORE_ERRORE = "#DC2626"

    CAMPI = (
        ("Ordine di acquisto", "Ordine di acquisto (KEY)"),
        ("Pos. Oda", "Pos.Oda (KEY)"),
        ("Partita / Batch", "Partita/BATCH"),
        ("QR pallet", "QR Pallet"),
    )

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("QR Reader - Registrazione pallet")
        self.root.geometry("1180x720")
        self.root.minsize(960, 650)
        self.root.resizable(True, True)
        self.root.configure(bg="#F2F5F9")
        self.dati_pallet = None
        self.interfaccia_aperta = True
        self.foto_camera_1 = None
        self.foto_camera_2 = None
        self.campi_testo = {}
        self._crea_interfaccia()
        self.root.protocol("WM_DELETE_WINDOW", self.chiudi)
        self.campi_testo[self.CAMPI[0][1]].focus_set()

    @property
    def aperta(self):
        return self.interfaccia_aperta

    def _crea_interfaccia(self):
        self._crea_header()
        contenuto = tk.Frame(self.root, bg="#F2F5F9")
        contenuto.grid(row=1, column=0, sticky="nsew", padx=18, pady=18)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        contenuto.grid_columnconfigure(0, weight=0)
        contenuto.grid_columnconfigure(1, weight=1)
        contenuto.grid_rowconfigure(0, weight=1)

        self._crea_pannello_dati(contenuto)
        self._crea_pannello_camere(contenuto)

    def _crea_header(self):
        header = tk.Frame(self.root, bg="#FFFFFF", height=74)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        tk.Label(
            header,
            text="QR Reader",
            font=("Segoe UI", 20, "bold"),
            fg=self.COLORE_TESTO,
            bg="#FFFFFF",
        ).pack(side="left", padx=24)

        self.badge_attivo = tk.Label(
            header,
            text="  SISTEMA DISATTIVATO  ",
            font=("Segoe UI", 9, "bold"),
            fg="#FFFFFF",
            bg=self.COLORE_ERRORE,
            padx=8,
            pady=5,
        )
        self.badge_attivo.pack(side="right", padx=24, pady=20)

    def _crea_pannello_dati(self, contenuto):
        pannello = tk.Frame(
            contenuto,
            bg=self.COLORE_CARTA,
            highlightbackground=self.COLORE_BORDO,
            highlightthickness=1,
        )
        pannello.grid(row=0, column=0, sticky="ns", padx=(0, 18))
        pannello.grid_columnconfigure(0, weight=1)

        tk.Label(
            pannello,
            text="Dati pallet",
            font=("Segoe UI", 15, "bold"),
            fg=self.COLORE_TESTO,
            bg=self.COLORE_CARTA,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(24, 10))
        tk.Label(
            pannello,
            text="Inserisci i dati prima di avviare la lettura",
            font=("Segoe UI", 9),
            fg=self.COLORE_SECONDARIO,
            bg=self.COLORE_CARTA,
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 22))

        for indice, (etichetta, nome_colonna) in enumerate(self.CAMPI):
            riga_etichetta = 2 + indice * 2
            tk.Label(
                pannello,
                text=etichetta,
                font=("Segoe UI", 10, "bold"),
                fg=self.COLORE_TESTO,
                bg=self.COLORE_CARTA,
            ).grid(
                row=riga_etichetta,
                column=0,
                sticky="w",
                padx=22,
                pady=(10, 6),
            )
            campo = tk.Entry(
                pannello,
                width=28,
                font=("Segoe UI", 11),
                relief="solid",
                borderwidth=1,
                highlightthickness=1,
                highlightbackground=self.COLORE_BORDO,
                highlightcolor=self.COLORE_PRIMARIO,
                bg="#FFFFFF",
                fg=self.COLORE_TESTO,
            )
            campo.grid(
                row=riga_etichetta + 1,
                column=0,
                sticky="ew",
                padx=22,
                pady=(0, 7),
                ipady=7,
            )
            self.campi_testo[nome_colonna] = campo

        self.stato = tk.StringVar(
            value="Sistema disattivato. Inserisci e conferma i dati del pallet."
        )
        self.stato_tela = tk.Label(
            pannello,
            textvariable=self.stato,
            font=("Segoe UI", 9),
            fg=self.COLORE_SECONDARIO,
            bg=self.COLORE_CARTA,
            wraplength=270,
            justify="left",
        )
        self.stato_tela.grid(
            row=11, column=0, sticky="ew", padx=22, pady=(14, 8)
        )

        self.bottone_invia = tk.Button(
            pannello,
            text="Conferma dati",
            command=self.invia_dati,
            font=("Segoe UI", 11, "bold"),
            fg="#FFFFFF",
            bg=self.COLORE_PRIMARIO,
            activebackground=self.COLORE_PRIMARIO_SCuro,
            activeforeground="#FFFFFF",
            relief="flat",
            cursor="hand2",
        )
        self.bottone_invia.grid(
            row=12, column=0, sticky="ew", padx=22, pady=(6, 22), ipady=9
        )
        self.bottone_disattiva = tk.Button(
            pannello,
            text="Disattiva sistema",
            command=self.disattiva_sistema,
            font=("Segoe UI", 10, "bold"),
            fg="#FFFFFF",
            bg=self.COLORE_ERRORE,
            activebackground="#B91C1C",
            activeforeground="#FFFFFF",
            disabledforeground="#FFFFFF",
            relief="flat",
            cursor="hand2",
            state="disabled",
        )
        self.bottone_disattiva.grid(
            row=13, column=0, sticky="ew", padx=22, pady=(0, 22), ipady=8
        )
        self.root.bind("<Return>", self.invia_dati)

    def _crea_pannello_camere(self, contenuto):
        camere = tk.Frame(contenuto, bg="#F2F5F9")
        camere.grid(row=0, column=1, sticky="nsew")
        camere.grid_columnconfigure(0, weight=1)
        camere.grid_columnconfigure(1, weight=1)
        camere.grid_rowconfigure(1, weight=1)
        camere.grid_rowconfigure(2, minsize=160)

        self.anteprima_camera_1 = self._crea_card_camera(camere, "Flaconi", 0)
        self.anteprima_camera_2 = self._crea_card_camera(camere, "Scatole", 1)

        terminale = tk.Frame(camere, bg=self.COLORE_BORDO)
        terminale.grid(
            row=2, column=0, columnspan=2, sticky="nsew", pady=(14, 0)
        )
        terminale.grid_rowconfigure(1, weight=1)
        terminale.grid_columnconfigure(0, weight=1)
        tk.Label(
            terminale,
            text="Registro letture QR",
            font=("Segoe UI", 10, "bold"),
            fg=self.COLORE_TESTO,
            bg=self.COLORE_BORDO,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(9, 5))

        scroll_log = tk.Scrollbar(terminale)
        scroll_log.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 8))
        self.log_qr = tk.Text(
            terminale,
            height=5,
            bg=self.COLORE_BORDO,
            fg="#000000",
            insertbackground="#E2E8F0",
            font=("DejaVu Sans Mono", 10),
            relief="flat",
            wrap="none",
            yscrollcommand=scroll_log.set,
            state="disabled",
        )
        self.log_qr.grid(
            row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 8)
        )
        scroll_log.configure(command=self.log_qr.yview)
        self.log_qr.tag_configure("rilevato", foreground="#000000")
        self.log_qr.tag_configure(
            "non_rilevato", foreground=self.COLORE_ERRORE
        )

    def _crea_card_camera(self, parent, titolo, colonna):
        card = tk.Frame(
            parent,
            bg=self.COLORE_CARTA,
            highlightbackground=self.COLORE_BORDO,
            highlightthickness=1,
        )
        card.grid(
            row=1,
            column=colonna,
            sticky="nsew",
            padx=(0, 9 if colonna == 0 else 0),
        )
        tk.Label(
            card,
            text=titolo,
            font=("Segoe UI", 12, "bold"),
            fg=self.COLORE_TESTO,
            bg=self.COLORE_CARTA,
        ).pack(anchor="w", padx=14, pady=(16, 12))
        anteprima = tk.Label(
            card,
            bg=self.COLORE_BORDO,
            text="In attesa della camera",
            fg="#94A3B8",
            font=("Segoe UI", 10),
        )
        anteprima.pack(fill="both", expand=True, padx=12, pady=(0, 16))
        return anteprima

    def invia_dati(self, event=None):
        campi_disabilitati = any(
            campo.cget("state") == "disabled"
            for campo in self.campi_testo.values()
        )
        if campi_disabilitati:
            self.dati_pallet = None
            for campo in self.campi_testo.values():
                campo.configure(state="normal")
            self.bottone_invia.configure(text="Conferma dati")
            self.badge_attivo.configure(
                text="  SISTEMA DISATTIVATO  ", bg=self.COLORE_ERRORE
            )
            self.bottone_disattiva.configure(state="disabled")
            self.stato.set("Modifica i dati del pallet e conferma")
            self.stato_tela.configure(fg=self.COLORE_SECONDARIO)
            self.campi_testo[self.CAMPI[0][1]].focus_set()
            return "break"

        valori = {
            nome: campo.get().strip()
            for nome, campo in self.campi_testo.items()
        }
        campo_vuoto = next(
            (nome for nome, valore in valori.items() if not valore), None
        )
        if campo_vuoto is not None:
            messagebox.showwarning(
                "Campo obbligatorio",
                "Compila tutti i campi prima di premere Invio.",
                parent=self.root,
            )
            self.campi_testo[campo_vuoto].focus_set()
            return "break"

        adesso = datetime.now()
        self.dati_pallet = {
            **valori,
            "Data pallet": adesso.strftime("%d/%m/%Y"),
            "Ora pallet": adesso.strftime("%H:%M:%S"),
        }
        self.stato.set(f"Pallet registrato alle {self.dati_pallet['Ora pallet']}")
        self.stato_tela.configure(fg=self.COLORE_SUCCESSO)
        self.badge_attivo.configure(
            text="  SISTEMA ATTIVO  ", bg=self.COLORE_SUCCESSO
        )
        for campo in self.campi_testo.values():
            campo.configure(state="disabled")
        self.bottone_invia.configure(text="Aggiorna dati")
        self.bottone_disattiva.configure(state="normal")
        return "break"

    def disattiva_sistema(self):
        self.dati_pallet = None
        self.badge_attivo.configure(
            text="  SISTEMA DISATTIVATO  ", bg=self.COLORE_ERRORE
        )
        self.stato.set(
            "Sistema disattivato. Conferma i dati per riprendere la lettura."
        )
        self.stato_tela.configure(fg=self.COLORE_ERRORE)
        for campo in self.campi_testo.values():
            campo.configure(state="normal")
        self.bottone_invia.configure(text="Conferma dati")
        self.bottone_disattiva.configure(state="disabled")
        self.campi_testo[self.CAMPI[0][1]].focus_set()

    def aggiungi_log_qr(self, messaggio, errore=False):
        self.log_qr.configure(state="normal")
        tag = "non_rilevato" if errore else "rilevato"
        self.log_qr.insert("end", messaggio + "\n", tag)
        righe_log = int(self.log_qr.index("end-1c").split(".")[0])
        if righe_log > 200:
            self.log_qr.delete("1.0", f"{righe_log - 200 + 1}.0")
        self.log_qr.see("end")
        self.log_qr.configure(state="disabled")

    def aggiorna_anteprime(self, frame_camera_1, frame_camera_2):
        self.foto_camera_1 = self._aggiorna_anteprima(
            self.anteprima_camera_1, frame_camera_1
        )
        self.foto_camera_2 = self._aggiorna_anteprima(
            self.anteprima_camera_2, frame_camera_2
        )

    @staticmethod
    def _aggiorna_anteprima(camera_label, frame):
        if frame is None:
            return None
        larghezza = max(280, camera_label.winfo_width() - 24)
        altezza = max(158, int(larghezza * 9 / 16))
        immagine = cv2.resize(
            frame, (larghezza, altezza), interpolation=cv2.INTER_AREA
        )
        codificata, png = cv2.imencode(".png", immagine)
        if not codificata:
            raise RuntimeError(
                "Impossibile codificare il frame della camera in PNG."
            )
        foto = tk.PhotoImage(
            data=base64.b64encode(png).decode("ascii"), format="png"
        )
        camera_label.configure(image=foto, text="")
        return foto

    def aggiorna(self):
        self.root.update()

    def chiudi(self):
        self.interfaccia_aperta = False
        self.root.withdraw()

    def distruggi(self):
        self.root.destroy()
