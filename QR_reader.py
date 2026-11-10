import cv2
import os
import shutil
import subprocess
from datetime import datetime
import openpyxl
import sys
import tkinter as tk
from tkinter import messagebox
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "QR_detection"))
from QR_detection import QRCodeDetector

# -----------------------------
# CONFIGURAZIONE
# -----------------------------

FILE_EXCEL = "codici_qr.xlsx"
FOGLIO = "Letture"

# Camera e tempo di esposizione
DISPOSITIVO_CAMERA = "/dev/video0"
RISOLUZIONE_CAMERA = (1280, 960)  # larghezza, altezza
FPS_CAMERA = 90
TEMPO_ESPOSIZIONE = 1/500 # sintassi: 1/500 -> con 0 si imposta esposizione automatica
TEMPO_ESPOSIZIONE_US = 1000*TEMPO_ESPOSIZIONE*1000

# regione in cui cercare il qr code (% della dimensione)
perc_x = 35
perc_y = 35
bordo_x = int(RISOLUZIONE_CAMERA[0]*perc_x/100)
bordo_y = int(RISOLUZIONE_CAMERA[1]*perc_y/100)
REGIONE_INTERESSE = (bordo_x, bordo_y, RISOLUZIONE_CAMERA[0]-2*bordo_x, RISOLUZIONE_CAMERA[1]-2*bordo_y)


def configura_esposizione():
    if TEMPO_ESPOSIZIONE_US==0:
        return
    if TEMPO_ESPOSIZIONE_US <= 0 or TEMPO_ESPOSIZIONE_US % 100 != 0:
        raise ValueError("TEMPO_ESPOSIZIONE_US deve essere un multiplo positivo di 100.")

    v4l2_ctl = shutil.which("v4l2-ctl")

    esposizione_v4l2 = TEMPO_ESPOSIZIONE_US // 100
    risultato = subprocess.run(
        [
            v4l2_ctl,
            "-d",
            DISPOSITIVO_CAMERA,
            f"--set-ctrl=auto_exposure=1,exposure_time_absolute={esposizione_v4l2}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if risultato.returncode != 0:
        dettaglio = risultato.stderr.strip() or risultato.stdout.strip()
        raise RuntimeError(f"Impossibile impostare l'esposizione della camera: {dettaglio}")

    print(f"Esposizione impostata: {TEMPO_ESPOSIZIONE_US / 1000:g} ms")

configura_esposizione()

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
    "QR Pallet",
    "Data flacone",
    "Ora flacone",
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

# Carica tutti i codici già registrati
codici_letti = set()
colonna_qr_flacone = colonne["QR flacone (KEY)"]
for cell in ws.iter_rows(min_row=2, min_col=colonna_qr_flacone, max_col=colonna_qr_flacone):
    if cell[0].value is not None:
        codici_letti.add(str(cell[0].value))

# -----------------------------
# QR reader
# -----------------------------

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
print(f"Risoluzione effettiva: {larghezza_effettiva}x{altezza_effettiva} a {fps_effettivi:g} FPS")
if (larghezza_effettiva, altezza_effettiva) != RISOLUZIONE_CAMERA:
    print(
        f"Avviso: la camera non ha applicato {RISOLUZIONE_CAMERA[0]}x{RISOLUZIONE_CAMERA[1]}; "
        "controllare i formati supportati dal driver."
    )

# -----------------------------
# FUNZIONE SALVATAGGIO
# -----------------------------

dati_pallet = None


def salva_qr_flacone(codice):
    global codici_letti
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
    nuova_riga = ws.max_row + 1
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
    print(f"QR: {codice} - Riga Excel: {nuova_riga}")


# -----------------------------
# INTERFACCIA DATI PALLET
# -----------------------------

finestra = tk.Tk()
finestra.title("Dati pallet")
finestra.resizable(False, False)

campi = (
    ("Ordine di acquisto", "Ordine di acquisto (KEY)"),
    ("Pos.Oda", "Pos.Oda (KEY)"),
    ("Partita/batch", "Partita/BATCH"),
    ("QR pallet", "QR Pallet"),
)
campi_testo = {}
for riga, (etichetta, nome_colonna) in enumerate(campi):
    tk.Label(finestra, text=etichetta).grid(row=riga, column=0, padx=10, pady=5, sticky="w")
    campo = tk.Entry(finestra, width=35)
    campo.grid(row=riga, column=1, padx=10, pady=5)
    campi_testo[nome_colonna] = campo

stato = tk.StringVar(value="Compila tutti i campi e premi Invio per registrare i QR.")
tk.Label(finestra, textvariable=stato).grid(
    row=len(campi), column=0, columnspan=2, padx=10, pady=5, sticky="w"
)


def invia_dati(event=None):
    global dati_pallet
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
    stato.set(f"Dati aggiornati alle {dati_pallet['Ora pallet']}.")
    return "break"


tk.Button(finestra, text="Invia", command=invia_dati).grid(
    row=len(campi) + 1, column=0, columnspan=2, pady=10
)
finestra.bind("<Return>", invia_dati)
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

try:
    while interfaccia_aperta:
        finestra.update()
        if not interfaccia_aperta:
            break
        ret, frame = cap.read()
        if not ret:
            break
        data = qr_detector.run_single(frame)
        if data is not None:
            salva_qr_flacone(data)
        cv2.imshow("Detect QR Code from Webcam", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Arresto programma")
            break
finally:
    cap.release()
    cv2.destroyAllWindows()
    finestra.destroy()
    wb.close()
    print("Programma terminato.")