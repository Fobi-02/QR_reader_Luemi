from datetime import datetime

import openpyxl

from . import config


COLONNE_RICHIESTE = (
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


class ExcelStorage:
    def __init__(self):
        self.workbook = openpyxl.load_workbook(config.FILE_EXCEL)
        self.worksheet = (
            self.workbook[config.FOGLIO]
            if config.FOGLIO in self.workbook.sheetnames
            else self.workbook.create_sheet(config.FOGLIO)
        )
        self.columns = {
            str(cell.value).strip(): cell.column
            for cell in self.worksheet[1]
            if cell.value is not None
        }
        colonne_mancanti = [
            nome for nome in COLONNE_RICHIESTE if nome not in self.columns
        ]
        if colonne_mancanti:
            self.close()
            raise ValueError(
                "Mancano queste intestazioni nel foglio Excel: "
                + ", ".join(colonne_mancanti)
            )

        self.colonna_qr_flacone = self.columns["QR flacone (KEY)"]
        self.colonna_qr_scatola = self.columns["QR scatola"]
        self.codici_flaconi = self._carica_codici(self.colonna_qr_flacone)
        self.codici_scatole = self._carica_codici(self.colonna_qr_scatola)
        self.contatore_flaconi = self._prossima_riga(self.colonna_qr_flacone)
        self.contatore_scatole = self._prossima_riga(self.colonna_qr_scatola)

    def _carica_codici(self, colonna):
        return {
            str(celle[0].value)
            for celle in self.worksheet.iter_rows(
                min_row=2, min_col=colonna, max_col=colonna
            )
            if celle[0].value is not None
        }

    def _prossima_riga(self, colonna):
        righe_registrate = [
            riga
            for riga in range(2, self.worksheet.max_row + 1)
            if self.worksheet.cell(row=riga, column=colonna).value is not None
        ]
        return max(righe_registrate, default=1) + 1

    def _scrivi_dati_pallet(self, riga, dati_pallet):
        for nome_colonna, valore in dati_pallet.items():
            self.worksheet.cell(
                row=riga, column=self.columns[nome_colonna], value=valore
            )

    def salva_qr_flacone(self, codice, dati_pallet):
        codice = str(codice).strip()[-9:]
        if not codice or codice[0] != "F" or dati_pallet is None:
            return None
        if codice in self.codici_flaconi:
            return None

        nuova_riga = self.contatore_flaconi
        self._scrivi_dati_pallet(nuova_riga, dati_pallet)
        self.worksheet.cell(
            row=nuova_riga, column=self.colonna_qr_flacone, value=codice
        )
        adesso = datetime.now()
        self.worksheet.cell(
            row=nuova_riga,
            column=self.columns["Data flacone"],
            value=adesso.strftime("%d/%m/%Y"),
        )
        self.worksheet.cell(
            row=nuova_riga,
            column=self.columns["Ora flacone"],
            value=adesso.strftime("%H:%M:%S"),
        )
        self.workbook.save(config.FILE_EXCEL)
        self.codici_flaconi.add(codice)
        self.contatore_flaconi += 1
        return f"QR: {codice} - Riga Excel: {nuova_riga}"

    def registra_flacone_non_rilevato(self, dati_pallet):
        if dati_pallet is None:
            return None

        nuova_riga = self.contatore_flaconi
        self._scrivi_dati_pallet(nuova_riga, dati_pallet)
        self.worksheet.cell(
            row=nuova_riga, column=self.colonna_qr_flacone, value=None
        )
        adesso = datetime.now()
        self.worksheet.cell(
            row=nuova_riga,
            column=self.columns["Data flacone"],
            value=adesso.strftime("%d/%m/%Y"),
        )
        self.worksheet.cell(
            row=nuova_riga,
            column=self.columns["Ora flacone"],
            value=adesso.strftime("%H:%M:%S"),
        )
        self.workbook.save(config.FILE_EXCEL)
        self.contatore_flaconi += 1
        return f"Errore, codice non rilevato - Riga Excel: {nuova_riga}"

    def salva_qr_scatola(self, codice, dati_pallet):
        codice = str(codice).strip()[-9:]
        if not codice or codice in self.codici_scatole:
            return None
        if not codice.startswith("CB") or dati_pallet is None:
            return None

        adesso = datetime.now()
        data_scatola = adesso.strftime("%d/%m/%Y")
        ora_scatola = adesso.strftime("%H:%M:%S")
        ultima_riga = self.contatore_scatole + 5
        for nuova_riga in range(self.contatore_scatole, ultima_riga + 1):
            self.worksheet.cell(
                row=nuova_riga, column=self.colonna_qr_scatola, value=codice
            )
            self.worksheet.cell(
                row=nuova_riga,
                column=self.columns["Data scatola"],
                value=data_scatola,
            )
            self.worksheet.cell(
                row=nuova_riga,
                column=self.columns["Ora scatola"],
                value=ora_scatola,
            )

        self.workbook.save(config.FILE_EXCEL)
        self.codici_scatole.add(codice)
        messaggio = (
            f"QR scatola: {codice} - Righe Excel: "
            f"{self.contatore_scatole}-{ultima_riga}"
        )
        self.contatore_scatole += 6
        return messaggio

    def close(self):
        self.workbook.close()
