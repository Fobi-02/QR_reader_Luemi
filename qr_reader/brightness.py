from collections import deque

import cv2

from . import config


class BrightnessMonitor:
    def __init__(self, registra_flacone_non_rilevato):
        self.registra_flacone_non_rilevato = registra_flacone_non_rilevato
        self.storico_luminosita = deque(
            maxlen=max(1, config.NUMERO_FRAME_MEDIA_LUMINOSITA)
        )
        self.stato = "basso"
        self.basso_confermato = False
        self.frame_alti = 0
        self.frame_bassi = 0
        self.codice_rilevato_nel_passaggio = False

    def aggiorna(self, frame, codice_rilevato, pallet_attivo):
        if not config.CONTROLLO_LUMINOSITA_FLACONI or not pallet_attivo:
            self._reset()
            return

        x, y, larghezza, altezza = config.REGIONE_INTERESSE
        roi = frame[
            max(0, y):min(frame.shape[0], y + altezza),
            max(0, x):min(frame.shape[1], x + larghezza),
        ]
        if roi.size == 0:
            return

        luminosita = cv2.mean(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY))[0]
        self.storico_luminosita.append(luminosita)
        luminosita_media = sum(self.storico_luminosita) / len(
            self.storico_luminosita
        )

        if self.stato == "basso":
            self._aggiorna_stato_basso(luminosita_media, codice_rilevato)
        elif self.stato == "alto":
            self._aggiorna_stato_alto(luminosita_media, codice_rilevato)

    def _aggiorna_stato_basso(self, luminosita_media, codice_rilevato):
        if luminosita_media < config.SOGLIA_LUMINOSITA_BASSA:
            self.frame_bassi += 1
            if self.frame_bassi >= config.MIN_FRAME_BASSI:
                self.basso_confermato = True
        else:
            self.frame_bassi = 0

        if (
            self.basso_confermato
            and luminosita_media >= config.SOGLIA_LUMINOSITA_ALTA
        ):
            self.frame_alti += 1
            if self.frame_alti >= config.MIN_FRAME_ALTI:
                self.stato = "alto"
                self.frame_alti = 0
                self.frame_bassi = 0
                self.codice_rilevato_nel_passaggio = bool(codice_rilevato)
        elif luminosita_media < config.SOGLIA_LUMINOSITA_ALTA:
            self.frame_alti = 0

    def _aggiorna_stato_alto(self, luminosita_media, codice_rilevato):
        if codice_rilevato:
            self.codice_rilevato_nel_passaggio = True

        if luminosita_media >= config.SOGLIA_LUMINOSITA_BASSA:
            self.frame_bassi = 0
            return

        self.frame_bassi += 1
        if self.frame_bassi >= config.MIN_FRAME_BASSI:
            if not self.codice_rilevato_nel_passaggio:
                self.registra_flacone_non_rilevato()

            self.stato = "basso"
            self.basso_confermato = True
            self.frame_alti = 0
            self.frame_bassi = 0
            self.codice_rilevato_nel_passaggio = False

    def _reset(self):
        self.stato = "basso"
        self.basso_confermato = False
        self.frame_alti = 0
        self.frame_bassi = 0
        self.codice_rilevato_nel_passaggio = False
        self.storico_luminosita.clear()
