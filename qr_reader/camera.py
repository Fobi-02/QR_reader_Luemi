import queue
import threading
import time

import cv2


def apri_camera(dispositivo, risoluzione, fps):
    camera = cv2.VideoCapture(dispositivo, cv2.CAP_V4L2)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(f"Impossibile aprire la camera {dispositivo}.")

    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, risoluzione[0])
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, risoluzione[1])
    camera.set(cv2.CAP_PROP_FPS, fps)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    larghezza = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    altezza = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_effettivi = camera.get(cv2.CAP_PROP_FPS)
    print(f"Risoluzione: {larghezza}x{altezza} a {fps_effettivi:g} FPS")
    if (larghezza, altezza) != risoluzione:
        print(
            f"Avviso: la camera non ha applicato {risoluzione[0]}x{risoluzione[1]}; "
            "controllare i formati supportati dal driver."
        )
    return camera


class CameraWorker:
    def __init__(self, camera, detector, registra_tempo):
        self.camera = camera
        self.detector = detector
        self.registra_tempo = registra_tempo
        self.frame_pronto = queue.Queue(maxsize=1)
        self.codici_pronti = queue.Queue()
        self.errori = queue.Queue(maxsize=1)
        self.arresta = threading.Event()
        self.thread = threading.Thread(
            target=self._elabora,
            name="elaborazione-camera-2",
            daemon=True,
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.arresta.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def _elabora(self):
        ultimo_codice = None
        try:
            while not self.arresta.is_set():
                ret, frame = self.camera.read()
                if not ret:
                    if not self.arresta.is_set():
                        self.errori.put(
                            RuntimeError(
                                "Impossibile leggere un frame dalla camera 2."
                            )
                        )
                    return

                inizio_elaborazione = time.perf_counter()
                codice = self.detector.run_single(frame)
                self.registra_tempo("Scatole", time.perf_counter() - inizio_elaborazione)

                if codice is not None and codice != ultimo_codice:
                    self.codici_pronti.put(codice)
                ultimo_codice = codice
                self._aggiorna_frame(frame)
        except Exception as error:
            self.errori.put(error)

    def _aggiorna_frame(self, frame):
        try:
            self.frame_pronto.put_nowait(frame)
        except queue.Full:
            try:
                self.frame_pronto.get_nowait()
            except queue.Empty:
                pass
            try:
                self.frame_pronto.put_nowait(frame)
            except queue.Full:
                pass
