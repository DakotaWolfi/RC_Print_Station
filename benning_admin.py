"""Optional, token-authenticated import form for the loopback admin server."""
import base64
import binascii
from email import policy
from email.parser import BytesParser
from html import escape
import secrets
import sqlite3

from benning_csv import ImportErrorDetail, MAX_BYTES
from benning_store import Measurements
from i18n import error_text, tr
from station_config import load


class ImportPage:
    def __init__(self,db,token):
        token=token.strip()
        if len(token)<24 or not token.isascii():
            raise ValueError("BENNING-Import benötigt einen ASCII-Token mit mindestens 24 Zeichen.")
        self.credential=b"benning:"+token.encode("ascii")
        self.csrf=secrets.token_urlsafe(32)
        self.store=Measurements(db)

    def serve(self,handler,submit=False):
        auth=handler.headers.get("Authorization","")
        try:
            if not auth.startswith("Basic ") or len(auth)>1024:
                raise ValueError()
            credential=base64.b64decode(auth[6:],validate=True)
        except (ValueError,binascii.Error):
            credential=b""
        if not secrets.compare_digest(credential,self.credential):
            handler.send_response(401)
            handler.send_header("WWW-Authenticate",'Basic realm="FMI BENNING Import"')
            handler.send_header("Cache-Control","no-store")
            handler.end_headers()
            return
        language=load()["language"]
        t=lambda key:escape(tr(language,key))
        message=""
        status=200
        if submit:
            try:
                size=int(handler.headers.get("Content-Length","0"))
                kind=handler.headers.get("Content-Type","")
                if not 0<size<=MAX_BYTES+8192 or not kind.startswith("multipart/form-data;"):
                    raise ImportErrorDetail("CSV/TXT-Datei oder Dateigrösse prüfen.")
                body=handler.rfile.read(size)
                if len(body)!=size:
                    raise ImportErrorDetail("Upload unvollständig.")
                mime=BytesParser(policy=policy.default).parsebytes(
                    b"Content-Type: "+kind.encode("ascii")+b"\r\n\r\n"+body)
                fields={}
                for part in mime.iter_parts():
                    name=part.get_param("name",header="content-disposition")
                    if name not in ("csrf","format","data") or name in fields:
                        raise ImportErrorDetail("Unerwartetes Upload-Feld.")
                    fields[name]=part.get_payload(decode=True)
                if mime.defects or not secrets.compare_digest(fields.get("csrf",b""),self.csrf.encode()):
                    handler.send_error(403)
                    return
                kind=fields.get("format")
                if kind not in (b"csv",b"txt"):
                    raise ImportErrorDetail("Dateiformat wählen.")
                result=self.store.import_bytes(fields.get("data",b""),"file-"+kind.decode())
                message=tr(language,"{count} Messungen importiert. Quelle Datei am Host wählen.",count=result.count)
            except (ImportErrorDetail,ValueError,TypeError,sqlite3.Error) as error:
                message=error_text(language,str(error) if isinstance(error,ImportErrorDetail) else "Dateiimport fehlgeschlagen.")
                status=400
        page=f"""<!DOCTYPE html><html lang="{language}"><meta charset="utf-8"><title>BENNING Import</title>
<h1>{t('BENNING ST 725 importieren')}</h1><p>{escape(message)}</p>
<form method="post" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{self.csrf}">
<label>Format <select name="format"><option value="csv">USB-CSV</option>
<option value="txt">{t('Druckbericht (experimentell)')}</option></select></label>
<label>{t('Datei')} <input type="file" name="data" required></label>
<button type="submit">{t('Validieren und importieren')}</button></form>
<p><a href="/">{t('Stationsverwaltung')}</a></p></html>""".encode()
        handler.send_response(status)
        handler.send_header("Content-Type","text/html; charset=utf-8")
        handler.send_header("Cache-Control","no-store")
        handler.send_header("X-Frame-Options","DENY")
        handler.send_header("Content-Length",str(len(page)))
        handler.end_headers()
        handler.wfile.write(page)
