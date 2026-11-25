import tempfile
from pathlib import Path
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from report_web import publish, start_server
from station import simulate


class ReportDownloadTests(unittest.TestCase):
    def test_published_token_downloads_pdf_and_unknown_token_is_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"reports.db"
            server=start_server(db,0)
            base=f"http://127.0.0.1:{server.server_port}"
            try:
                url=publish(db,simulate("RC-42","Prüflampe"),base)
                with urlopen(url,timeout=3) as response:
                    self.assertEqual(response.headers["Content-Type"],"application/pdf")
                    self.assertEqual(response.headers["Cache-Control"],"no-store")
                    pdf=response.read()
                    self.assertTrue(pdf.startswith(b"%PDF-"))
                    self.assertIn(b"%%EOF",pdf)
                with self.assertRaises(HTTPError) as missing:
                    urlopen(base+"/r/not-a-token",timeout=3)
                self.assertEqual(missing.exception.code,404)
            finally:
                server.shutdown()
                server.server_close()


if __name__=="__main__":
    unittest.main()
