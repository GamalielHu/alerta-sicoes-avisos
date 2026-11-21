"""Investigación 3: abrir la ficha como irFicha (token #id de convocatorias) y ver pestañas."""
import json, os, re, sys, time, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "servidor"))
from vigilar import Sicoes, BASE, TIPOS, limpiar

SAL = "/tmp/res"
os.makedirs(SAL, exist_ok=True)

def buscar(s, entidad, start):
    datos = {"token": s.token, "entidad": entidad, "objetoContrato": "", "publicacionDesde": "", "publicacionHasta": "",
             "presentacionPropuestasDesde": "", "presentacionPropuestasHasta": "",
             "cuce1": "", "cuce2": "", "cuce3": "", "cuce4": "", "cuce5": "", "cuce6": "",
             "r1": "", "subasta": "", "tipo": "Simple", "operacion": "convNacional",
             "nroRegistros": "10", "draw": "1", "start": str(start), "length": "10", "captcha": ""}
    for t in "OBSC":
        datos[TIPOS[t]] = t
    return json.loads(s._pedir(BASE + "/portal/contrataciones/operacion.php", datos, {
        "X-Requested-With": "XMLHttpRequest", "Origin": BASE, "Referer": s.url_conv}))

s = Sicoes(); s.abrir()
estados = {}
for start in (100, 300, 600):
    try:
        js = buscar(s, "Servicio Departamental De Gestion Social - Potosi", start)
    except Exception as e:
        print("busqueda", start, e); continue
    for o in js.get("data") or []:
        estados.setdefault(limpiar(o.get(s.columnas[8])), []).append((limpiar(o.get(s.columnas[0])), limpiar(o.get(s.columnas[5]))))
    time.sleep(1)
print(json.dumps(estados, ensure_ascii=False, indent=1))
cuces = []
for e, l in estados.items():
    if e != "Vigente":
        cuces += [c for c, _ in l[:2]]
cuces = cuces[:5] or ["26-0905-01-1712525-1-1"]

for c in cuces:
    s2 = Sicoes(); s2.abrir()
    conv = s2._pedir(s2.url_conv)
    tid = s2._valor(conv, r"""<input[^>]*id=["']token["'][^>]*>""")
    url = f"{BASE}/portal/contrataciones/ficha/fichaProceso.php?cp={c}&token={tid}"
    try:
        h = s2._pedir(url, None, {"Referer": s2.url_conv})
    except Exception as e:
        h = f"ERROR {e}"
    open(f"{SAL}/ficha_{c}.html", "w").write(h)
    t = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<script.*?</script>|<style.*?</style>", "", h))
    t = re.sub(r"\s+", " ", t)
    print("\n#####", c, len(h), "turnstile" if "turnstile" in h.lower() else "", "login" if "captcha8" in h else "")
    print(t[:3000])
    print("links:", sorted(set(re.findall(r"""(?:href|action|src|url)\s*[=:]\s*["']([^"']+\.php[^"']*)""", h)))[:40])
    print("tabs:", re.findall(r"""data-toggle=["']tab["'][^>]*>([^<]+)""", h))
    time.sleep(1)
