class PdfReaderService:
    @staticmethod
    def read(path: str) -> list[dict]:
        # Ensimmäisessä vaiheessa stub.
        # Myöhemmin tähän kytketään Azure Document Intelligence.
        return [
            {
                "source_sheet": "pdf_stub",
                "source_row_number": 1,
                "data": {
                    "pole_type": "Stub-PDF-Pole",
                    "support_height_m": 18,
                    "span_m": 120,
                    "guying": "yes",
                    "quantity": 1,
                },
            }
        ]