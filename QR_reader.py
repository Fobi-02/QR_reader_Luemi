import cv2
import os
import queue
import shutil
import subprocess
import threading
import time
import base64
from datetime import datetime
import openpyxl
import sys
import tkinter as tk
from tkinter import messagebox
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "QR_detection"))
from QR_detector import QRCodeDetector

# -----------------------------
# CONFIGURAZIONE
# -----------------------------

FILE_EXCEL = "codici_qr.xlsx"
FOGLIO = "Letture"

# CAMERA 1 (flaconi)
DISPOSITIVO_CAMERA = "/dev/video0"
RISOLUZIONE_CAMERA = (1280, 720)  # larghezza, altezza
DIMENSIONE_ANTEPRIMA = (640, 360)
FPS_CAMERA = 90
TEMPO_ESPOSIZIONE = 1/500 # sintassi: 1/500 -> con 0 si imposta esposizione automatica
TEMPO_ESPOSIZIONE_US = 1000*TEMPO_ESPOSIZIONE*1000

# regione in cui cercare il qr code (bordo in % della dimensione)
perc_x = 35
perc_y = 20
bordo_x = int(RISOLUZIONE_CAMERA[0]*perc_x/100)
bordo_y = int(RISOLUZIONE_CAMERA[1]*perc_y/100)
REGIONE_INTERESSE = (bordo_x, bordo_y, RISOLUZIONE_CAMERA[0]-2*bordo_x, RISOLUZIONE_CAMERA[1]-2*bordo_y)


# CAMERA 2 (scatole)
DISPOSITIVO_CAMERA_2 = "/dev/video2"
RISOLUZIONE_CAMERA_2 = (1280, 720)  # larghezza, altezza
FPS_CAMERA_2 = 30
TEMPO_ESPOSIZIONE_2 = 1/50 # sintassi: 1/500 -> con 0 si imposta esposizione automatica
TEMPO_ESPOSIZIONE_US_2 = 1000*TEMPO_ESPOSIZIONE_2*1000

# regione in cui cercare il qr code (bordo in % della dimensione)
perc_x_2 = 35
perc_y_2 = 20
bordo_x_2 = int(RISOLUZIONE_CAMERA_2[0]*perc_x_2/100)
bordo_y_2 = int(RISOLUZIONE_CAMERA_2[1]*perc_y_2/100)
REGIONE_INTERESSE_2 = (bordo_x_2, bordo_y_2, RISOLUZIONE_CAMERA_2[0]-2*bordo_x_2, RISOLUZIONE_CAMERA_2[1]-2*bordo_y_2)




def configura_esposizione(tempo_esposizione, camera):
    if tempo_esposizione == 0:
        return
    if tempo_esposizione <= 0 or tempo_esposizione % 100 != 0:
        raise ValueError("TEMPO_ESPOSIZIONE_US deve essere un multiplo positivo di 100.")
    v4l2_ctl = shutil.which("v4l2-ctl")
    if v4l2_ctl is None:
        raise RuntimeError("Il comando v4l2-ctl non è installato o non è disponibile nel PATH.")
    esposizione_v4l2 = tempo_esposizione // 100
    risultato = subprocess.run([
            v4l2_ctl,
            "-d",
            camera,
            f"--set-ctrl=auto_exposure=1,exposure_time_absolute={esposizione_v4l2}",],
        capture_output=True,
        text=True,
        check=False,)
    if risultato.returncode != 0:
        dettaglio = risultato.stderr.strip() or risultato.stdout.strip()
        raise RuntimeError(f"Impossibile impostare l'esposizione della camera: {dettaglio}")
    print(f"Esposizione: {tempo_esposizione / 1000:g} ms")

configura_esposizione(TEMPO_ESPOSIZIONE_US, DISPOSITIVO_CAMERA)
configura_esposizione(TEMPO_ESPOSIZIONE_US_2, DISPOSITIVO_CAMERA_2)

# -----------------------------
# INIZIALIZZAZIONE EXCEL
# -----------------------------

wb = openpyxl.load_workbook(FILE_EXCEL)
ws = wb[FOGLIO] if FOGLIO in wb.sheetnames else wb.create_sheet(FOGLIO)

colonne = {
    str(cella.value).strip(): cella.column
    for cella in ws[1]
    if cella.value is not None
}
colonne_richieste = (
    "Ordine di acquisto (KEY)",
    "Pos.Oda (KEY)",
    "QR flacone (KEY)",
    "Partita/BATCH",
    "QR scatola",
    "QR Pallet",
    "Data flacone",
    "Ora flacone",
    "Data scatola",
    "Ora scatola",
    "Data pallet",
    "Ora pallet",
)
colonne_mancanti = [nome for nome in colonne_richieste if nome not in colonne]
if colonne_mancanti:
    wb.close()
    raise ValueError(
        "Mancano queste intestazioni nel foglio Excel: "
        + ", ".join(colonne_mancanti)
    )

# Carica tutti i codici già registrati per flaconi e per scatole
codici_letti = set()
colonna_qr_flacone = colonne["QR flacone (KEY)"]
for cell in ws.iter_rows(min_row=2, min_col=colonna_qr_flacone, max_col=colonna_qr_flacone):
    if cell[0].value is not None:
        codici_letti.add(str(cell[0].value))

codici_letti_2 = set()
colonna_qr_scatola = colonne["QR scatola"]
for cell in ws.iter_rows(min_row=2, min_col=colonna_qr_scatola, max_col=colonna_qr_scatola):
    if cell[0].value is not None:
        codici_letti_2.add(str(cell[0].value))

# I flaconi occupano una riga ciascuno; ogni scatola occupa sei righe.
righe_flaconi_registrate = [
    riga
    for riga in range(2, ws.max_row + 1)
    if ws.cell(row=riga, column=colonna_qr_flacone).value is not None
]
contatore_flaconi = max(righe_flaconi_registrate, default=1) + 1

righe_scatole_registrate = [
    riga
    for riga in range(2, ws.max_row + 1)
    if ws.cell(row=riga, column=colonna_qr_scatola).value is not None
]
contatore_scatole = max(righe_scatole_registrate, default=1) + 1

# -----------------------------
# QR reader
# -----------------------------

# CAMERA 1
qr_detector = QRCodeDetector(roi=REGIONE_INTERESSE)
cap = cv2.VideoCapture(DISPOSITIVO_CAMERA, cv2.CAP_V4L2)
if not cap.isOpened():
    cap.release()
    wb.close()
    raise RuntimeError(f"Impossibile aprire la camera {DISPOSITIVO_CAMERA}.")

# Richiede MJPEG: consente modalità ad alta risoluzione e frequenza via USB.
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, RISOLUZIONE_CAMERA[0])
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RISOLUZIONE_CAMERA[1])
cap.set(cv2.CAP_PROP_FPS, FPS_CAMERA)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

larghezza_effettiva = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
altezza_effettiva = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps_effettivi = cap.get(cv2.CAP_PROP_FPS)
print(f"Risoluzione: {larghezza_effettiva}x{altezza_effettiva} a {fps_effettivi:g} FPS")
if (larghezza_effettiva, altezza_effettiva) != RISOLUZIONE_CAMERA:
    print(
        f"Avviso: la camera non ha applicato {RISOLUZIONE_CAMERA[0]}x{RISOLUZIONE_CAMERA[1]}; "
        "controllare i formati supportati dal driver."
    )

# CAMERA 2
qr_detector_2 = QRCodeDetector(roi=REGIONE_INTERESSE_2)
cap_2 = cv2.VideoCapture(DISPOSITIVO_CAMERA_2, cv2.CAP_V4L2)
if not cap_2.isOpened():
    cap_2.release()
    cap.release()
    wb.close()
    raise RuntimeError(f"Impossibile aprire la camera {DISPOSITIVO_CAMERA_2}.")

# Richiede MJPEG: consente modalità ad alta risoluzione e frequenza via USB.
cap_2.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap_2.set(cv2.CAP_PROP_FRAME_WIDTH, RISOLUZIONE_CAMERA_2[0])
cap_2.set(cv2.CAP_PROP_FRAME_HEIGHT, RISOLUZIONE_CAMERA_2[1])
cap_2.set(cv2.CAP_PROP_FPS, FPS_CAMERA_2)
cap_2.set(cv2.CAP_PROP_BUFFERSIZE, 1)

larghezza_effettiva_2 = int(cap_2.get(cv2.CAP_PROP_FRAME_WIDTH))
altezza_effettiva_2 = int(cap_2.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps_effettivi_2 = cap_2.get(cv2.CAP_PROP_FPS)
print(f"Risoluzione: {larghezza_effettiva_2}x{altezza_effettiva_2} a {fps_effettivi_2:g} FPS")
if (larghezza_effettiva_2, altezza_effettiva_2) != RISOLUZIONE_CAMERA_2:
    print(
        f"Avviso: la camera non ha applicato {RISOLUZIONE_CAMERA_2[0]}x{RISOLUZIONE_CAMERA_2[1]}; "
        "controllare i formati supportati dal driver."
    )
print("")

# -----------------------------
# FUNZIONE SALVATAGGIO
# -----------------------------

dati_pallet = None

def salva_qr_flacone(codice):
    global contatore_flaconi
    codice = str(codice).strip()[-9:]
    if not codice:
        return
    if not codice[0] == "F":
        return
    if dati_pallet is None:
        return

    # Controlla se il codice è già stato letto
    if codice in codici_letti:
        return

    # Prima riga libera
    nuova_riga = contatore_flaconi
    for nome_colonna, valore in dati_pallet.items():
        ws.cell(row=nuova_riga, column=colonne[nome_colonna], value=valore)
    ws.cell(row=nuova_riga, column=colonna_qr_flacone, value=codice)
    adesso = datetime.now()
    ws.cell(row=nuova_riga, column=colonne["Data flacone"], value=adesso.strftime("%d/%m/%Y"))
    ws.cell(row=nuova_riga, column=colonne["Ora flacone"], value=adesso.strftime("%H:%M:%S"))
    # Salvataggio immediato
    wb.save(FILE_EXCEL)
    # Memorizza il codice per evitare duplicati
    codici_letti.add(codice)
    contatore_flaconi += 1
    messaggio = f"QR: {codice} - Riga Excel: {nuova_riga}"
    print(messaggio)
    aggiungi_log_qr(messaggio)


def salva_qr_scatola(codice):
    global contatore_scatole
    codice = str(codice).strip()[-9:]
    if not codice or codice in codici_letti_2:
        return
    # controlla che il QR code inizi con CB
    if not codice[0:2]=="CB":
        return
    if dati_pallet is None:
        return

    adesso = datetime.now()
    data_scatola = adesso.strftime("%d/%m/%Y")
    ora_scatola = adesso.strftime("%H:%M:%S")
    for nuova_riga in range(contatore_scatole, contatore_scatole + 6):
        ws.cell(row=nuova_riga, column=colonna_qr_scatola, value=codice)
        ws.cell(row=nuova_riga, column=colonne["Data scatola"], value=data_scatola)
        ws.cell(row=nuova_riga, column=colonne["Ora scatola"], value=ora_scatola)

    wb.save(FILE_EXCEL)
    codici_letti_2.add(codice)
    messaggio = f"QR scatola: {codice} - Righe Excel: {contatore_scatole}-{contatore_scatole + 5}"
    print(messaggio)
    aggiungi_log_qr(messaggio)
    contatore_scatole += 6


# -----------------------------
# INTERFACCIA DATI PALLET
# -----------------------------

finestra = tk.Tk()
finestra.title("QR Reader - Registrazione pallet")
finestra.geometry("1180x720")
finestra.minsize(960, 650)
finestra.resizable(True, True)
finestra.configure(bg="#F2F5F9")

# Palette moderna
COLORE_PRIMARIO = "#2563EB"
COLORE_PRIMARIO_SCuro = "#1D4ED8"
COLORE_TESTO = "#172033"
COLORE_SECONDARIO = "#64748B"
COLORE_BORDO = "#DCE4EF"
COLORE_CARTA = "#FFFFFF"
COLORE_SUCCESSO = "#16A34A"
COLORE_ERRORE = "#DC2626"

header = tk.Frame(finestra, bg="#FFFFFF", height=74)
header.grid(row=0, column=0, sticky="ew")
header.grid_propagate(False)
tk.Label(
    header,
    text="QR Reader",
    font=("Segoe UI", 20, "bold"),
    fg=COLORE_TESTO,
    bg="#FFFFFF",
).pack(side="left", padx=24)

badge_attivo = tk.Label(
    header,
    text="  SISTEMA DISATTIVATO  ",
    font=("Segoe UI", 9, "bold"),
    fg="#FFFFFF",
    bg=COLORE_ERRORE,
    padx=8,
    pady=5,
)
badge_attivo.pack(side="right", padx=24, pady=20)

contenuto = tk.Frame(finestra, bg="#F2F5F9")
contenuto.grid(row=1, column=0, sticky="nsew", padx=18, pady=18)
finestra.grid_rowconfigure(1, weight=1)
finestra.grid_columnconfigure(0, weight=1)
contenuto.grid_columnconfigure(0, weight=0)
contenuto.grid_columnconfigure(1, weight=1)
contenuto.grid_rowconfigure(0, weight=1)

# Pannello dati
pannello = tk.Frame(
    contenuto,
    bg=COLORE_CARTA,
    highlightbackground=COLORE_BORDO,
    highlightthickness=1,
)
pannello.grid(row=0, column=0, sticky="ns", padx=(0, 18))
pannello.grid_columnconfigure(0, weight=1)

tk.Label(
    pannello,
    text="Dati pallet",
    font=("Segoe UI", 15, "bold"),
    fg=COLORE_TESTO,
    bg=COLORE_CARTA,
).grid(row=0, column=0, sticky="w", padx=22, pady=(24, 10))
tk.Label(
    pannello,
    text="Inserisci i dati prima di avviare la lettura",
    font=("Segoe UI", 9),
    fg=COLORE_SECONDARIO,
    bg=COLORE_CARTA,
).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 22))

campi = (
    ("Ordine di acquisto", "Ordine di acquisto (KEY)"),
    ("Pos. Oda", "Pos.Oda (KEY)"),
    ("Partita / Batch", "Partita/BATCH"),
    ("QR pallet", "QR Pallet"),
)
campi_testo = {}
for indice, (etichetta, nome_colonna) in enumerate(campi):
    riga_etichetta = 2 + indice * 2
    tk.Label(
        pannello,
        text=etichetta,
        font=("Segoe UI", 10, "bold"),
        fg="#475569",
        bg=COLORE_CARTA,
    ).grid(row=riga_etichetta, column=0, sticky="w", padx=22, pady=(10, 6))
    campo = tk.Entry(
        pannello,
        width=28,
        font=("Segoe UI", 11),
        relief="solid",
        borderwidth=1,
        highlightthickness=1,
        highlightbackground=COLORE_BORDO,
        highlightcolor=COLORE_PRIMARIO,
        bg="#FFFFFF",
        fg=COLORE_TESTO,
    )
    campo.grid(row=riga_etichetta + 1, column=0, sticky="ew", padx=22, pady=(0, 7), ipady=7)
    campi_testo[nome_colonna] = campo

stato = tk.StringVar(value="Sistema disattivato. Inserisci e conferma i dati del pallet.")
stato_tela = tk.Label(
    pannello,
    textvariable=stato,
    font=("Segoe UI", 9),
    fg=COLORE_SECONDARIO,
    bg=COLORE_CARTA,
    wraplength=270,
    justify="left",
)
stato_tela.grid(row=11, column=0, sticky="ew", padx=22, pady=(14, 8))

def invia_dati(event=None):
    global dati_pallet
    campi_disabilitati = any(campo.cget("state") == "disabled" for campo in campi_testo.values())
    if campi_disabilitati:
        dati_pallet = None
        for campo in campi_testo.values():
            campo.configure(state="normal")
        bottone_invia.configure(text="Conferma dati")
        badge_attivo.configure(text="  SISTEMA DISATTIVATO  ", bg=COLORE_ERRORE)
        bottone_disattiva.configure(state="disabled")
        stato.set("Modifica i dati del pallet e conferma")
        stato_tela.configure(fg=COLORE_SECONDARIO)
        campi_testo[campi[0][1]].focus_set()
        return "break"

    valori = {nome: campo.get().strip() for nome, campo in campi_testo.items()}
    campo_vuoto = next((nome for nome, valore in valori.items() if not valore), None)
    if campo_vuoto is not None:
        messagebox.showwarning(
            "Campo obbligatorio",
            "Compila tutti i campi prima di premere Invio.",
            parent=finestra,
        )
        campi_testo[campo_vuoto].focus_set()
        return "break"

    adesso = datetime.now()
    dati_pallet = {
        **valori,
        "Data pallet": adesso.strftime("%d/%m/%Y"),
        "Ora pallet": adesso.strftime("%H:%M:%S"),
    }
    stato.set(f"Pallet registrato alle {dati_pallet['Ora pallet']}")
    stato_tela.configure(fg=COLORE_SUCCESSO)
    badge_attivo.configure(text="  SISTEMA ATTIVO  ", bg=COLORE_SUCCESSO)
    for campo in campi_testo.values():
        campo.configure(state="disabled")
    bottone_invia.configure(text="Aggiorna dati")
    bottone_disattiva.configure(state="normal")
    return "break"


def disattiva_sistema():
    global dati_pallet
    dati_pallet = None
    badge_attivo.configure(text="  SISTEMA DISATTIVATO  ", bg=COLORE_ERRORE)
    stato.set("Sistema disattivato. Conferma i dati per riprendere la lettura.")
    stato_tela.configure(fg=COLORE_ERRORE)
    for campo in campi_testo.values():
        campo.configure(state="normal")
    bottone_invia.configure(text="Conferma dati")
    bottone_disattiva.configure(state="disabled")
    campi_testo[campi[0][1]].focus_set()

bottone_invia = tk.Button(
    pannello,
    text="Conferma dati",
    command=invia_dati,
    font=("Segoe UI", 11, "bold"),
    fg="#FFFFFF",
    bg=COLORE_PRIMARIO,
    activebackground=COLORE_PRIMARIO_SCuro,
    activeforeground="#FFFFFF",
    relief="flat",
    cursor="hand2",
)
bottone_invia.grid(row=12, column=0, sticky="ew", padx=22, pady=(6, 22), ipady=9)
bottone_disattiva = tk.Button(
    pannello,
    text="Disattiva sistema",
    command=disattiva_sistema,
    font=("Segoe UI", 10, "bold"),
    fg="#FFFFFF",
    bg=COLORE_ERRORE,
    activebackground="#B91C1C",
    activeforeground="#FFFFFF",
    disabledforeground="#FFFFFF",
    relief="flat",
    cursor="hand2",
    state="disabled",
)
bottone_disattiva.grid(row=13, column=0, sticky="ew", padx=22, pady=(0, 22), ipady=8)
finestra.bind("<Return>", invia_dati)

# Pannello camere
camere = tk.Frame(contenuto, bg="#F2F5F9")
camere.grid(row=0, column=1, sticky="nsew")
camere.grid_columnconfigure(0, weight=1)
camere.grid_columnconfigure(1, weight=1)
camere.grid_rowconfigure(1, weight=1)
camere.grid_rowconfigure(2, minsize=160)

def crea_card_camera(parent, titolo, colonna):
    card = tk.Frame(
        parent,
        bg=COLORE_CARTA,
        highlightbackground=COLORE_BORDO,
        highlightthickness=1,
    )
    card.grid(row=1, column=colonna, sticky="nsew", padx=(0, 9 if colonna == 0 else 0))
    tk.Label(
        card,
        text=titolo,
        font=("Segoe UI", 12, "bold"),
        fg=COLORE_TESTO,
        bg=COLORE_CARTA,
    ).pack(anchor="w", padx=14, pady=(16, 12))
    anteprima = tk.Label(
        card,
        bg="#101827",
        text="In attesa della camera",
        fg="#94A3B8",
        font=("Segoe UI", 10),
    )
    anteprima.pack(fill="both", expand=True, padx=12, pady=(0, 16))
    return anteprima

foto_camera_1 = None
foto_camera_2 = None
anteprima_camera_1 = crea_card_camera(camere, "Flaconi", 0)
anteprima_camera_2 = crea_card_camera(camere, "Scatole", 1)

terminale = tk.Frame(camere, bg="#111827")
terminale.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(14, 0))
terminale.grid_rowconfigure(1, weight=1)
terminale.grid_columnconfigure(0, weight=1)
tk.Label(
    terminale,
    text="Registro letture QR",
    font=("Segoe UI", 10, "bold"),
    fg="#E2E8F0",
    bg="#111827",
).grid(row=0, column=0, sticky="w", padx=12, pady=(9, 5))

scroll_log = tk.Scrollbar(terminale)
scroll_log.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 8))
log_qr = tk.Text(
    terminale,
    height=5,
    bg="#0B1220",
    fg="#86EFAC",
    insertbackground="#E2E8F0",
    font=("DejaVu Sans Mono", 10),
    relief="flat",
    wrap="none",
    yscrollcommand=scroll_log.set,
    state="disabled",
)
log_qr.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 8))
scroll_log.configure(command=log_qr.yview)

def aggiungi_log_qr(messaggio):
    log_qr.configure(state="normal")
    log_qr.insert("end", messaggio + "\n")
    righe_log = int(log_qr.index("end-1c").split(".")[0])
    if righe_log > 200:
        log_qr.delete("1.0", f"{righe_log - 200 + 1}.0")
    log_qr.see("end")
    log_qr.configure(state="disabled")

interfaccia_aperta = True


def chiudi_interfaccia():
    global interfaccia_aperta
    interfaccia_aperta = False
    finestra.withdraw()


finestra.protocol("WM_DELETE_WINDOW", chiudi_interfaccia)
campi_testo[campi[0][1]].focus_set()


# -----------------------------
# CICLO PRINCIPALE
# -----------------------------

statistiche_qr = {
    "Flaconi": {"totale": 0.0, "massimo": 0.0, "frame": 0},
    "Scatole": {"totale": 0.0, "massimo": 0.0, "frame": 0},
}
lock_statistiche_qr = threading.Lock()
frame_scatole_pronto = queue.Queue(maxsize=1)
codici_scatole_pronti = queue.Queue()
errori_camera_2 = queue.Queue(maxsize=1)
arresta_camera_2 = threading.Event()
thread_camera_2 = None
inizio_intervallo_statistiche = time.perf_counter()


def elabora_camera_2():
    ultimo_codice = None
    try:
        while not arresta_camera_2.is_set():
            ret, frame_2 = cap_2.read()
            if not ret:
                if not arresta_camera_2.is_set():
                    errori_camera_2.put(RuntimeError("Impossibile leggere un frame dalla camera 2."))
                return

            inizio_elaborazione = time.perf_counter()
            data_2 = qr_detector_2.run_single(frame_2)
            durata_elaborazione = time.perf_counter() - inizio_elaborazione
            with lock_statistiche_qr:
                statistiche_qr["Scatole"]["totale"] += durata_elaborazione
                statistiche_qr["Scatole"]["massimo"] = max(
                    statistiche_qr["Scatole"]["massimo"], durata_elaborazione
                )
                statistiche_qr["Scatole"]["frame"] += 1

            if data_2 is not None and data_2 != ultimo_codice:
                codici_scatole_pronti.put(data_2)
            ultimo_codice = data_2

            try:
                frame_scatole_pronto.put_nowait(frame_2)
            except queue.Full:
                try:
                    frame_scatole_pronto.get_nowait()
                except queue.Empty:
                    pass
                try:
                    frame_scatole_pronto.put_nowait(frame_2)
                except queue.Full:
                    pass
    except Exception as error:
        errori_camera_2.put(error)


try:
    thread_camera_2 = threading.Thread(
        target=elabora_camera_2,
        name="elaborazione-camera-2",
        daemon=True,
    )
    thread_camera_2.start()
    frame_2 = None

    def aggiorna_anteprima(camera_label, frame):
        if frame is None:
            return None
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        larghezza = max(280, camera_label.winfo_width() - 24)
        altezza = max(158, int(larghezza * 9 / 16))
        immagine = cv2.resize(frame, (larghezza, altezza), interpolation=cv2.INTER_AREA)
        codificata, png = cv2.imencode(".png", immagine)
        if not codificata:
            raise RuntimeError("Impossibile codificare il frame della camera in PNG.")
        foto = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"), format="png")
        camera_label.configure(image=foto, text="")
        return foto

    while interfaccia_aperta:
        finestra.update()
        if not interfaccia_aperta:
            break
        try:
            errore = errori_camera_2.get_nowait()
        except queue.Empty:
            pass
        else:
            raise RuntimeError("Errore durante l'elaborazione della camera 2.") from errore

        ret, frame = cap.read()
        if not ret:
            print("Impossibile leggere un frame dalla camera 1.")
            break

        inizio_elaborazione = time.perf_counter()
        data = qr_detector.run_single(frame)
        durata_elaborazione = time.perf_counter() - inizio_elaborazione
        with lock_statistiche_qr:
            statistiche_qr["Flaconi"]["totale"] += durata_elaborazione
            statistiche_qr["Flaconi"]["massimo"] = max(
                statistiche_qr["Flaconi"]["massimo"], durata_elaborazione
            )
            statistiche_qr["Flaconi"]["frame"] += 1
        if data is not None:
            salva_qr_flacone(data)

        try:
            while True:
                frame_2 = frame_scatole_pronto.get_nowait()
        except queue.Empty:
            pass
        try:
            while True:
                salva_qr_scatola(codici_scatole_pronti.get_nowait())
        except queue.Empty:
            pass

        adesso = time.perf_counter()
        intervallo = adesso - inizio_intervallo_statistiche
        if intervallo >= 1:
            misure = []
            with lock_statistiche_qr:
                statistiche_intervallo = {
                    nome: valori.copy() for nome, valori in statistiche_qr.items()
                }
                for valori in statistiche_qr.values():
                    valori.update(totale=0.0, massimo=0.0, frame=0)
            for nome_camera, statistiche in statistiche_intervallo.items():
                if statistiche["frame"]:
                    media_ms = statistiche["totale"] / statistiche["frame"] * 1000
                    massimo_ms = statistiche["massimo"] * 1000
                    misure.append(
                        f"{nome_camera}: media {media_ms:.1f} ms, "
                        f"massimo {massimo_ms:.1f} ms "
                        f"({statistiche['frame']} frame)"
                    )
            print(f"Elaborazione QR (ultimo {intervallo:.1f} s): " + " | ".join(misure))
            inizio_intervallo_statistiche = adesso
        foto_camera_1 = aggiorna_anteprima(anteprima_camera_1, frame)
        foto_camera_2 = aggiorna_anteprima(anteprima_camera_2, frame_2)
finally:
    arresta_camera_2.set()
    cap.release()
    cap_2.release()
    if thread_camera_2 is not None:
        thread_camera_2.join(timeout=2)
    cv2.destroyAllWindows()
    finestra.destroy()
    wb.close()
    print("Programma terminato.")