import queue
import threading
import time

import cv2

from QR_detection.QR_detector import QRCodeDetector

from . import config
from .brightness import BrightnessMonitor
from .camera import CameraWorker, apri_camera
from .interface import PalletInterface
from .storage import ExcelStorage


class QRReaderApp:
    def __init__(self):
        config.configura_esposizione(
            config.TEMPO_ESPOSIZIONE_US, config.DISPOSITIVO_CAMERA
        )
        config.configura_esposizione(
            config.TEMPO_ESPOSIZIONE_US_2, config.DISPOSITIVO_CAMERA_2
        )

        self.storage = ExcelStorage()
        self.camera_1 = None
        self.camera_2 = None
        self.camera_worker = None
        self.interface = None
        try:
            self.camera_1 = apri_camera(
                config.DISPOSITIVO_CAMERA,
                config.RISOLUZIONE_CAMERA,
                config.FPS_CAMERA,
            )
            self.camera_2 = apri_camera(
                config.DISPOSITIVO_CAMERA_2,
                config.RISOLUZIONE_CAMERA_2,
                config.FPS_CAMERA_2,
            )
            print("")
            self.detector_1 = QRCodeDetector(roi=config.REGIONE_INTERESSE)
            self.detector_2 = QRCodeDetector(roi=config.REGIONE_INTERESSE_2)
            self.interface = PalletInterface()
        except Exception:
            self._rilascia_risorse()
            raise

        self.statistiche_qr = {
            "Flaconi": {"totale": 0.0, "massimo": 0.0, "frame": 0},
            "Scatole": {"totale": 0.0, "massimo": 0.0, "frame": 0},
        }
        self.lock_statistiche_qr = threading.Lock()
        self.monitor_luminosita = BrightnessMonitor(
            self._registra_flacone_non_rilevato
        )

    def _registra_tempo_elaborazione(self, nome_camera, durata):
        with self.lock_statistiche_qr:
            statistiche = self.statistiche_qr[nome_camera]
            statistiche["totale"] += durata
            statistiche["massimo"] = max(statistiche["massimo"], durata)
            statistiche["frame"] += 1

    def _registra_flacone_non_rilevato(self):
        messaggio = self.storage.registra_flacone_non_rilevato(
            self.interface.dati_pallet
        )
        if messaggio is not None:
            print(messaggio)
            self.interface.aggiungi_log_qr(messaggio, errore=True)

    def _stampa_statistiche(self, inizio_intervallo):
        adesso = time.perf_counter()
        intervallo = adesso - inizio_intervallo
        if intervallo < 1:
            return inizio_intervallo

        with self.lock_statistiche_qr:
            statistiche_intervallo = {
                nome: valori.copy()
                for nome, valori in self.statistiche_qr.items()
            }
            for valori in self.statistiche_qr.values():
                valori.update(totale=0.0, massimo=0.0, frame=0)

        misure = []
        for nome_camera, statistiche in statistiche_intervallo.items():
            if statistiche["frame"]:
                media_ms = statistiche["totale"] / statistiche["frame"] * 1000
                massimo_ms = statistiche["massimo"] * 1000
                misure.append(
                    f"{nome_camera}: media {media_ms:.1f} ms, "
                    f"massimo {massimo_ms:.1f} ms "
                    f"({statistiche['frame']} frame)"
                )
        print(
            f"Elaborazione QR (ultimo {intervallo:.1f} s): "
            + " | ".join(misure)
        )
        return adesso

    def run(self):
        self.camera_worker = CameraWorker(
            self.camera_2,
            self.detector_2,
            self._registra_tempo_elaborazione,
        )
        self.camera_worker.start()
        frame_camera_2 = None
        inizio_intervallo_statistiche = time.perf_counter()

        try:
            while self.interface.aperta:
                self.interface.aggiorna()
                if not self.interface.aperta:
                    break

                try:
                    errore = self.camera_worker.errori.get_nowait()
                except queue.Empty:
                    pass
                else:
                    raise RuntimeError(
                        "Errore durante l'elaborazione della camera 2."
                    ) from errore

                ret, frame = self.camera_1.read()
                if not ret:
                    print("Impossibile leggere un frame dalla camera 1.")
                    break

                inizio_elaborazione = time.perf_counter()
                codice_flacone = self.detector_1.run_single(frame)
                self._registra_tempo_elaborazione(
                    "Flaconi", time.perf_counter() - inizio_elaborazione
                )
                if codice_flacone is not None:
                    messaggio = self.storage.salva_qr_flacone(
                        codice_flacone, self.interface.dati_pallet
                    )
                    if messaggio is not None:
                        print(messaggio)
                        self.interface.aggiungi_log_qr(messaggio)

                codice_flacone_rilevato = (
                    codice_flacone is not None
                    and str(codice_flacone).strip()[-9:].startswith("F")
                )
                self.monitor_luminosita.aggiorna(
                    frame,
                    codice_flacone_rilevato,
                    self.interface.dati_pallet is not None,
                )

                try:
                    while True:
                        frame_camera_2 = (
                            self.camera_worker.frame_pronto.get_nowait()
                        )
                except queue.Empty:
                    pass

                try:
                    while True:
                        codice_scatola = (
                            self.camera_worker.codici_pronti.get_nowait()
                        )
                        messaggio = self.storage.salva_qr_scatola(
                            codice_scatola, self.interface.dati_pallet
                        )
                        if messaggio is not None:
                            print(messaggio)
                            self.interface.aggiungi_log_qr(messaggio)
                except queue.Empty:
                    pass

                inizio_intervallo_statistiche = self._stampa_statistiche(
                    inizio_intervallo_statistiche
                )
                self.interface.aggiorna_anteprime(frame, frame_camera_2)
        finally:
            self.close()

    def _rilascia_risorse(self):
        if self.camera_worker is not None:
            self.camera_worker.arresta.set()
        if self.camera_1 is not None:
            self.camera_1.release()
        if self.camera_2 is not None:
            self.camera_2.release()
        if self.camera_worker is not None:
            self.camera_worker.stop()
        cv2.destroyAllWindows()
        if self.interface is not None:
            self.interface.distruggi()
        if hasattr(self, "storage"):
            self.storage.close()

    def close(self):
        self._rilascia_risorse()
        print("Programma terminato.")
