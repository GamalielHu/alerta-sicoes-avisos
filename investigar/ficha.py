"""Investigación: qué muestra el SICOES de un proceso (ficha, adjudicación, subasta)."""
import json, os, re, sys, time, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "servidor"))
from vigilar import Sicoes, BASE, TIPOS, limpiar

SAL = "/tmp/res"
os.makedirs(SAL, exist_ok=True)
s = Sicoes()
s.abrir()

def buscar_todos(entidad, tipos="OBSC"):
    datos = {"token": s.token, "entidad": entidad, "objetoContrato": "", "publicacionDesde": "", "publicacionHasta": "",
             "presentacionPropuestasDesde": "", "presentacionPropuestasHasta": "",
             "cuce1": "", "cuce2": "", "cuce3": "", "cuce4": "", "cuce5": "", "cuce6": "",
             "r1": "", "subasta": "", "tipo": "Simple", "operacion": "convNacional",
             "nroRegistros": "10", "draw": "1", "start": "0", "length": "10", "captcha": ""}
    for t in tipos:
        datos[TIPOS[t]] = t
    txt = s._pedir(BASE + "/portal/contrataciones/operacion.php", datos, {
        "X-Requested-With": "XMLHttpRequest", "Origin": BASE, "Referer": s.url_conv})
    return json.loads(txt)

js = buscar_todos("Servicio Departamental De Gestion Social - Potosi")
with open(f"{SAL}/busqueda_todos.json", "w") as f:
    json.dump({"columnas": s.columnas, "respuesta": js}, f, ensure_ascii=False, indent=1)
filas = js.get("data") or []
print("registros:", js.get("recordsTotal"), "filas:", len(filas))
cuces = []
for o in filas:
    col = lambda n: limpiar(o.get(s.columnas[n])) if n < len(s.columnas) else ""
    estado = [limpiar(o.get(c)) for c in s.columnas]
    print(" | ".join(x[:40] for x in estado))
    cuces.append(col(0))
cuces = [c for c in cuces if c][:4] + ["26-0905-01-1694495-2-1"]

# Token de index para la ficha
inicio = s._pedir(BASE + "/portal/index.php")
t1 = s._valor(inicio, r"""<input[^>]*id=["']token["'][^>]*>""")
for c in cuces:
    url = f"{BASE}/portal/contrataciones/ficha/fichaProceso.php?cp={c}&token={t1}"
    try:
        h = s._pedir(url)
    except Exception as e:
        h = f"ERROR {e}"
    with open(f"{SAL}/ficha_{c}.html", "w") as f:
        f.write(h)
    print(c, len(h), "turnstile" if "turnstile" in h.lower() else "", re.findall(r"""(?:href|action|src)=["']([^"']+\.php[^"']*)""", h)[:30])
    time.sleep(1)
