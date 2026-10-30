"""Revisa el SICOES desde GitHub Actions y avisa las convocatorias nuevas por Firebase y ntfy.

Hace la misma consulta que la app (SicoesCliente.kt): abre la sesión, lee el token y el
orden de columnas (cambia en cada sesión) y pide las convocatorias vigentes de cada entidad.
El estado (lo que ya se avisó) se guarda en estado.json, que el workflow conserva en la rama
avisos-estado. La primera vez que aparece una entidad no se avisa nada: solo se registra.
"""
import html
import http.cookiejar
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

BASE = "https://www.sicoes.gob.bo"
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36"
CARPETA = os.path.dirname(os.path.abspath(__file__))
TIPOS = {"O": "obras", "B": "bienes", "S": "servicios", "C": "consultoria"}


def normalizar(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()


def limpiar(s):
    s = re.sub(r"<[^>]*>", " ", str(s or ""))
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


class Sicoes:
    def __init__(self):
        self.web = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.token = None
        self.columnas = []
        self.url_conv = ""

    def _pedir(self, url, datos=None, extra=None):
        cab = {"User-Agent": UA, "Accept-Language": "es-BO,es;q=0.9"}
        cab.update(extra or {})
        cuerpo = urllib.parse.urlencode(datos).encode() if datos is not None else None
        with self.web.open(urllib.request.Request(url, data=cuerpo, headers=cab), timeout=60) as r:
            return r.read().decode("utf-8", "replace")

    @staticmethod
    def _valor(pagina, patron):
        etiqueta = re.search(patron, pagina)
        if not etiqueta:
            return ""
        # El valor puede ir entre comillas dobles o simples (las columnas son JSON: van con simples)
        v = re.search(r"""value\s*=\s*(?:"([^"]*)"|'([^']*)')""", etiqueta.group(0))
        return html.unescape(v.group(1) if v.group(1) is not None else v.group(2)) if v else ""

    def abrir(self):
        inicio = self._pedir(BASE + "/portal/index.php")
        t1 = self._valor(inicio, r"""<input[^>]*id=["']token["'][^>]*>""")
        if not t1:
            raise RuntimeError("sin token en index.php")
        self.url_conv = BASE + "/portal/contrataciones/busqueda/convocatorias.php?tipo=convNacional&token=" + t1
        pag = self._pedir(self.url_conv)
        form = re.search(r"""<form[^>]*id=["']formSimple["'].*?</form>""", pag, re.S)
        self.token = self._valor(form.group(0) if form else pag, r"""<input[^>]*name=["']token["'][^>]*>""")
        if not self.token:
            self.token = self._valor(pag, r"""<input[^>]*name=["']token["'][^>]*>""")
        cols = self._valor(pag, r"""<input[^>]*id=["']colsConvocatoriasSimple["'][^>]*>""")
        if not self.token or not cols:
            i = pag.find("colsConvocatoriasSimple")
            raise RuntimeError("la página de convocatorias cambió (sin token o columnas): "
                               + repr(pag[max(0, i - 80):i + 120] if i >= 0 else pag[:200]))
        self.columnas = json.loads(cols)

    def buscar(self, entidad, tipos, max_paginas=30):
        if not self.token:
            self.abrir()
        filas, pagina = {}, 1
        while pagina <= max_paginas:
            datos = {
                "token": self.token, "entidad": entidad, "objetoContrato": "",
                "publicacionDesde": "", "publicacionHasta": "",
                "presentacionPropuestasDesde": "", "presentacionPropuestasHasta": "",
                "cuce1": "", "cuce2": "", "cuce3": "", "cuce4": "", "cuce5": "", "cuce6": "",
                "r1": "11", "subasta": "", "tipo": "Simple", "operacion": "convNacional",
                "nroRegistros": "10", "draw": str(pagina), "start": "0", "length": "10", "captcha": "",
            }
            for t in tipos:
                if t in TIPOS:
                    datos[TIPOS[t]] = t
            texto = self._pedir(BASE + "/portal/contrataciones/operacion.php", datos, {
                "X-Requested-With": "XMLHttpRequest", "Origin": BASE, "Referer": self.url_conv,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }).strip()
            if not texto.startswith("{"):
                raise RuntimeError("el SICOES rechazó la consulta (sesión vencida)")
            js = json.loads(texto)
            nuevas = 0
            for o in js.get("data") or []:
                col = lambda n: limpiar(o.get(self.columnas[n])) if n < len(self.columnas) else ""
                cuce = col(0)
                if cuce and cuce not in filas:
                    nuevas += 1
                    filas[cuce] = {"cuce": cuce, "entidad": col(1), "tipo": col(2), "modalidad": col(3),
                                   "objeto": col(4), "publicacion": col(6), "presentacion": col(7)}
            # Se corta cuando ya están todas o una página no trae nada nuevo
            if nuevas == 0 or len(filas) >= int(js.get("recordsTotal") or 0):
                break
            pagina += 1
            time.sleep(0.5)
        return list(filas.values())


class Firebase:
    """Avisos directos a la app por Firebase Cloud Messaging (tema = mismo nombre que en la app)."""

    def __init__(self, cuenta_json):
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
        info = json.loads(cuenta_json)
        self.proyecto = info["project_id"]
        self.cred = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
        self.cred.refresh(Request())

    def enviar(self, tema, titulo, cuerpo):
        mensaje = {"message": {
            "topic": tema,
            "notification": {"title": titulo, "body": cuerpo},
            "android": {"priority": "high", "notification": {
                "channel_id": "nuevas_convocatorias_v2", "sound": "default", "default_vibrate_timings": True}},
        }}
        req = urllib.request.Request(
            f"https://fcm.googleapis.com/v1/projects/{self.proyecto}/messages:send",
            data=json.dumps(mensaje).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.cred.token, "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()


def avisar(tema, c, firebase=None):
    titulo = f"Nueva convocatoria - {c['tipo']}"
    texto = (f"{c['objeto']}\n{c['entidad']}\nModalidad: {c['modalidad']}\n"
             f"Presentación: {c['presentacion']}\nCUCE: {c['cuce']}")
    if firebase:
        firebase.enviar(tema, titulo, texto)
    req = urllib.request.Request("https://ntfy.sh/" + tema, data=texto.encode("utf-8"), headers={
        "Title": titulo.encode("utf-8"), "Priority": "high", "Tags": "bell",
    })
    urllib.request.urlopen(req, timeout=30).read()


def entidades_de_la_app(tema):
    """Última lista enviada por la app. ntfy guarda los mensajes 12 h; por eso se copia al estado."""
    if not tema:
        return None
    try:
        with urllib.request.urlopen(f"https://ntfy.sh/{tema}-entidades/json?poll=1&since=all", timeout=30) as r:
            mensajes = [json.loads(l) for l in r.read().decode("utf-8").splitlines() if l.strip()]
        ultimos = [m for m in mensajes if m.get("event") == "message"]
        if not ultimos:
            return None
        lista = json.loads(ultimos[-1]["message"])
        return [e for e in lista if isinstance(e, dict) and e.get("entidad")]
    except Exception:
        return None


def main():
    tema = os.environ.get("NTFY_TEMA", "").strip()
    ruta_estado = os.path.join(CARPETA, "estado.json")
    try:
        with open(ruta_estado, encoding="utf-8") as f:
            estado = json.load(f)
    except (OSError, ValueError):
        estado = {}
    # Entidades: las que mandó la app (último mensaje del tema <tema>-entidades), si no las
    # últimas guardadas, y si no las de entidades.json
    entidades = entidades_de_la_app(tema) or estado.get("entidades")
    if entidades is None:
        with open(os.path.join(CARPETA, "entidades.json"), encoding="utf-8") as f:
            entidades = json.load(f)
    estado["entidades"] = entidades
    avisados = estado.setdefault("avisados", {})       # "entidad|CUCE" -> fecha en que se avisó
    iniciadas = set(estado.setdefault("iniciadas", []))
    ahora = time.strftime("%Y-%m-%d %H:%M", time.gmtime(time.time() - 4 * 3600))  # hora de Bolivia
    registro, nuevas = [], []

    sicoes = Sicoes()
    for e in entidades:
        nombre, tipos, exacta = e["entidad"], e.get("tipos", "O"), e.get("exacta", False)
        clave_ent = normalizar(nombre) + "|" + "".join(sorted(tipos)) + ("|exacta" if exacta else "")
        try:
            filas = sicoes.buscar(nombre, tipos)
        except Exception as err:  # una sesión vencida se reabre una vez
            try:
                sicoes.abrir()
                filas = sicoes.buscar(nombre, tipos)
            except Exception as err2:
                registro.append(f"ERROR {nombre}: {err2 or err}")
                continue
        if exacta:
            filas = [f for f in filas if normalizar(f["entidad"]) == normalizar(nombre)]
        primera = clave_ent not in iniciadas
        for f in filas:
            k = clave_ent + "|" + f["cuce"]
            if k not in avisados:
                avisados[k] = ahora
                if not primera:
                    nuevas.append(f)
        iniciadas.add(clave_ent)
        registro.append(f"{nombre}: {len(filas)} vigentes" + (" (primera carga, sin avisar)" if primera else ""))

    firebase = None
    if os.environ.get("FIREBASE_CUENTA", "").strip():
        try:
            firebase = Firebase(os.environ["FIREBASE_CUENTA"])
        except Exception as err:
            registro.append(f"ERROR Firebase: {err}")
    enviados = 0
    for c in nuevas[:15]:
        if not tema:
            break
        try:
            avisar(tema, c, firebase)
            enviados += 1
        except Exception as err:
            registro.append(f"ERROR ntfy: {err}")
    if os.environ.get("AVISO_PRUEBA") == "1" and tema:
        try:
            avisar(tema, {"objeto": "Avisos de Alerta SICOES activados" + (" (Firebase)" if firebase else ""),
                          "entidad": f"{len(entidades)} entidad(es) vigilada(s)",
                          "modalidad": "-", "presentacion": "-", "cuce": "-", "tipo": "prueba"}, firebase)
            registro.append("aviso de prueba enviado" + (" por Firebase y ntfy" if firebase else " por ntfy"))
        except Exception as err:
            registro.append(f"ERROR aviso de prueba: {err}")

    estado["iniciadas"] = sorted(iniciadas)
    estado["ultima_revision"] = ahora
    estado["registro"] = registro + [f"nuevas: {len(nuevas)}, avisadas: {enviados}"]
    with open(ruta_estado, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)
    print("\n".join(estado["registro"]))
    return 0  # los errores quedan en estado.json; fallar cada 15 min solo llenaría el correo de avisos


if __name__ == "__main__":
    sys.exit(main())
