"""Investigación 2: cómo abre el SICOES la ficha (irFicha) y qué pestañas tiene."""
import json, os, re, sys, time, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "servidor"))
from vigilar import Sicoes, BASE, TIPOS, limpiar

SAL = "/tmp/res"
os.makedirs(SAL, exist_ok=True)
s = Sicoes()
s.abrir()
conv = s._pedir(s.url_conv)
open(f"{SAL}/convocatorias.html", "w").write(conv)
srcs = re.findall(r"""<script[^>]*src=["']([^"']+)""", conv)
print("scripts:", srcs)
for src in srcs:
    url = src if src.startswith("http") else urllib.parse.urljoin(s.url_conv, src)
    if "sicoes" not in url:
        continue
    try:
        js = s._pedir(url)
    except Exception as e:
        print("ERR", url, e); continue
    nombre = re.sub(r"[^\w.]", "_", src.split("?")[0])[-80:]
    open(f"{SAL}/js_{nombre}", "w").write(js)
    for m in re.finditer(r"irFicha|fichaProceso|verFicha", js):
        print("==", src, m.group(0)); print(js[max(0, m.start()-300):m.start()+900]); print()
for m in re.finditer(r"irFicha", conv):
    print("== inline"); print(conv[max(0, m.start()-300):m.start()+900])

def buscar(entidad, start, r1=""):
    datos = {"token": s.token, "entidad": entidad, "objetoContrato": "", "publicacionDesde": "", "publicacionHasta": "",
             "presentacionPropuestasDesde": "", "presentacionPropuestasHasta": "",
             "cuce1": "", "cuce2": "", "cuce3": "", "cuce4": "", "cuce5": "", "cuce6": "",
             "r1": r1, "subasta": "", "tipo": "Simple", "operacion": "convNacional",
             "nroRegistros": "10", "draw": "1", "start": str(start), "length": "10", "captcha": ""}
    for t in "OBSC":
        datos[TIPOS[t]] = t
    return json.loads(s._pedir(BASE + "/portal/contrataciones/operacion.php", datos, {
        "X-Requested-With": "XMLHttpRequest", "Origin": BASE, "Referer": s.url_conv}))

estados = {}
for start in (60, 200, 400):
    js = buscar("Servicio Departamental De Gestion Social - Potosi", start)
    for o in js.get("data") or []:
        e = limpiar(o.get(s.columnas[8])); c = limpiar(o.get(s.columnas[0]))
        sub = limpiar(o.get(s.columnas[5]))
        estados.setdefault(e, []).append((c, sub))
    time.sleep(1)
print(json.dumps(estados, ensure_ascii=False, indent=1))
json.dump(estados, open(f"{SAL}/estados.json", "w"), ensure_ascii=False)
