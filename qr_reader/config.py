import os
import shutil
import subprocess

# File excel
FILE_EXCEL = os.path.join(os.path.expanduser("~"), "Desktop", "codici_qr.xlsx")
FOGLIO = "Letture"

# -------------- CAMERA 1 ----------------
# Impostazioni camera
DISPOSITIVO_CAMERA = "/dev/video0"
RISOLUZIONE_CAMERA = (1280, 720)
DIMENSIONE_ANTEPRIMA = (640, 360)
FPS_CAMERA = 90
TEMPO_ESPOSIZIONE = 1 / 500
TEMPO_ESPOSIZIONE_US = 1000 * TEMPO_ESPOSIZIONE * 1000

# Controllo codice mancato
CONTROLLO_LUMINOSITA_FLACONI = True
SOGLIA_LUMINOSITA_ALTA = 60
SOGLIA_LUMINOSITA_BASSA = 30
MIN_FRAME_ALTI = 3
MIN_FRAME_BASSI = 3
NUMERO_FRAME_MEDIA_LUMINOSITA = 5

# Zona di interesse della camera
_PERCENTUALE_BORDO_X = 35
_PERCENTUALE_BORDO_Y = 20
_BORDO_X = int(RISOLUZIONE_CAMERA[0] * _PERCENTUALE_BORDO_X / 100)
_BORDO_Y = int(RISOLUZIONE_CAMERA[1] * _PERCENTUALE_BORDO_Y / 100)
REGIONE_INTERESSE = (_BORDO_X, _BORDO_Y, RISOLUZIONE_CAMERA[0] - 2 * _BORDO_X, RISOLUZIONE_CAMERA[1] - 2 * _BORDO_Y)


# -------------- CAMERA 2 ----------------
# Impostazioni camera
DISPOSITIVO_CAMERA_2 = "/dev/video2"
RISOLUZIONE_CAMERA_2 = (1280, 720)
FPS_CAMERA_2 = 30
TEMPO_ESPOSIZIONE_2 = 0
TEMPO_ESPOSIZIONE_US_2 = 1000 * TEMPO_ESPOSIZIONE_2 * 1000

# Zona di interesse della camera
_PERCENTUALE_BORDO_X_2 = 35
_PERCENTUALE_BORDO_Y_2 = 20
_BORDO_X_2 = int(RISOLUZIONE_CAMERA_2[0] * _PERCENTUALE_BORDO_X_2 / 100)
_BORDO_Y_2 = int(RISOLUZIONE_CAMERA_2[1] * _PERCENTUALE_BORDO_Y_2 / 100)
REGIONE_INTERESSE_2 = (_BORDO_X_2, _BORDO_Y_2, RISOLUZIONE_CAMERA_2[0] - 2 * _BORDO_X_2, RISOLUZIONE_CAMERA_2[1] - 2 * _BORDO_Y_2)


def configura_esposizione(tempo_esposizione, camera):
    if tempo_esposizione == 0:
        return
    if tempo_esposizione <= 0 or tempo_esposizione % 100 != 0:
        raise ValueError("TEMPO_ESPOSIZIONE_US deve essere un multiplo positivo di 100.")
    v4l2_ctl = shutil.which("v4l2-ctl")
    if v4l2_ctl is None:
        raise RuntimeError("Il comando v4l2-ctl non è installato o non è disponibile nel PATH.")
    esposizione_v4l2 = tempo_esposizione // 100
    risultato = subprocess.run(
        [
            v4l2_ctl,
            "-d",
            camera,
            f"--set-ctrl=auto_exposure=1,exposure_time_absolute={esposizione_v4l2}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if risultato.returncode != 0:
        dettaglio = risultato.stderr.strip() or risultato.stdout.strip()
        raise RuntimeError(f"Impossibile impostare l'esposizione della camera: {dettaglio}")
    print(f"Esposizione: {tempo_esposizione / 1000:g} ms")
