"""
app.py — Capa web: servidor + interfaz (el modelo de "las páginas").

Flujo en dos pasos:
  1) /api/inspeccionar : recibe la URL, devuelve metadatos (qué ha encontrado).
  2) /api/convertir    : descarga el audio, lo pasa a MP3 y lo envía al
                         navegador SIN dejar copia en disco (carpeta temporal).

Soporta YouTube y SoundCloud (yt-dlp resuelve ambos; el motor es el mismo).
"""

import io
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

from flask import Flask, request, jsonify, send_file, Response

import core

app = Flask(__name__)

BITRATES_VALIDOS = {"128", "192", "320"}

# Icono de la app, reutilizado como favicon (se sirve en /favicon.svg).
ICONO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
    '<defs><linearGradient id="fav" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#FF4B3E"/><stop offset="1" stop-color="#FF9A3D"/>'
    '</linearGradient></defs>'
    '<rect width="512" height="512" rx="112" fill="url(#fav)"/>'
    '<path d="M158 170 L158 342 L296 256 Z" fill="#fff" stroke="#fff" '
    'stroke-width="18" stroke-linejoin="round"/>'
    '<g fill="#fff"><rect x="320" y="206" width="26" height="100" rx="13"/>'
    '<rect x="358" y="171" width="26" height="170" rx="13"/>'
    '<rect x="396" y="191" width="26" height="130" rx="13"/></g></svg>'
)


# --------------------------------------------------------------------------- #
#  Interfaz (una sola página; el navegador habla con la API por fetch).
# --------------------------------------------------------------------------- #
PAGINA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Onda · audio a MP3</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/favicon.svg">
<style>
  :root{
    --bg:#14110f; --bg2:#1b1714; --surface:#211c19; --surface-2:#2b2421;
    --line:#3a312c; --text:#f5efea; --muted:#a89c92;
    --g1:#ff4b3e; --g2:#ff9a3d; --accent:#ff7a41;
    --grad:linear-gradient(135deg,var(--g1),var(--g2));
    --mono:ui-monospace,SFMono-Regular,Menlo,"Roboto Mono",monospace;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  }
  *{box-sizing:border-box}
  body{
    margin:0;min-height:100dvh;background:
      radial-gradient(120% 60% at 50% -10%,rgba(255,122,65,.12),transparent 60%),var(--bg);
    color:var(--text);font-family:var(--sans);line-height:1.5;
    -webkit-font-smoothing:antialiased;
    padding:max(20px,env(safe-area-inset-top)) 18px 40px;
  }
  .wrap{max-width:540px;margin:0 auto}

  /* Cabecera */
  header{display:flex;align-items:center;gap:12px;padding:8px 0 26px}
  .logo{width:40px;height:40px;border-radius:11px;display:block;flex:none}
  .brand h1{font-size:21px;font-weight:800;letter-spacing:-.02em;margin:0;line-height:1}
  .brand p{margin:3px 0 0;font-size:12.5px;color:var(--muted)}

  /* Bloques / pasos */
  .step{margin-bottom:22px}
  .eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.14em;
    text-transform:uppercase;color:var(--muted);margin:0 0 9px;display:flex;gap:8px;align-items:center}
  .eyebrow .n{color:var(--accent)}
  .step.off{opacity:.4;pointer-events:none;filter:saturate(.4)}

  /* Input + botones */
  .field{display:flex;gap:8px}
  input[type=url]{
    flex:1;min-width:0;background:var(--surface);border:1px solid var(--line);
    color:var(--text);border-radius:13px;padding:14px 15px;font-size:15px;font-family:var(--sans);
    transition:border-color .15s,box-shadow .15s}
  input[type=url]::placeholder{color:#6f655d}
  input[type=url]:focus{outline:none;border-color:var(--accent);
    box-shadow:0 0 0 3px rgba(255,122,65,.18)}

  button{font-family:var(--sans);cursor:pointer;border:none}
  .btn{border-radius:13px;font-weight:700;font-size:15px;padding:14px 18px;
    transition:transform .08s,filter .15s,opacity .15s}
  .btn:active{transform:scale(.97)}
  .btn[disabled]{opacity:.55;cursor:default}
  .btn-primary{background:var(--grad);color:#241006}
  .btn-ghost{background:var(--surface);color:var(--text);border:1px solid var(--line)}
  .full{width:100%}

  /* Tarjeta de resultado */
  .card{background:var(--surface);border:1px solid var(--line);border-radius:16px;
    padding:13px;display:flex;gap:13px;align-items:center}
  .thumb{width:74px;height:74px;border-radius:11px;object-fit:cover;flex:none;background:var(--surface-2)}
  .thumb-fb{display:flex;align-items:center;justify-content:center;font-weight:800;
    font-size:26px;color:var(--accent)}
  .meta{min-width:0}
  .meta .t{font-weight:700;font-size:15px;margin:0 0 5px;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .meta .sub{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:13px}
  .dur{font-family:var(--mono)}
  .chip{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);
    border-radius:999px;padding:2px 9px;font-size:11.5px;color:var(--text)}
  .chip .dot{width:7px;height:7px;border-radius:50%}
  .dot-youtube{background:#ff4b3e}.dot-soundcloud{background:#ff8a3d}.dot-otra{background:var(--muted)}

  /* Calidad */
  .qgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}
  .q{background:var(--surface);border:1px solid var(--line);border-radius:14px;
    padding:14px 8px;text-align:center;color:var(--text);position:relative}
  .q .kb{font-family:var(--mono);font-size:20px;font-weight:700;line-height:1}
  .q .kb small{font-size:11px;color:var(--muted);font-weight:400}
  .q .lb{font-size:12px;color:var(--muted);margin-top:4px}
  .q[aria-pressed=true]{border-color:transparent;color:#241006;background:var(--grad)}
  .q[aria-pressed=true] .lb,.q[aria-pressed=true] .kb small{color:#5a2a08}

  /* Mensajes */
  .msg{font-size:13.5px;border-radius:12px;padding:11px 13px;margin-top:12px}
  .msg.err{background:rgba(255,75,62,.12);border:1px solid rgba(255,75,62,.35);color:#ffb3ab}
  .msg.ok{background:rgba(120,200,120,.1);border:1px solid rgba(120,200,120,.3);color:#bfe6bf}
  .hidden{display:none!important}

  /* Ecualizador animado (firma; el icono cobrando vida) */
  .eq{display:inline-flex;align-items:flex-end;gap:3px;height:15px}
  .eq i{width:3px;background:currentColor;border-radius:2px;animation:eq .9s ease-in-out infinite}
  .eq i:nth-child(1){animation-delay:-.6s}.eq i:nth-child(2){animation-delay:-.3s}
  .eq i:nth-child(3){animation-delay:-.9s}.eq i:nth-child(4){animation-delay:-.45s}
  @keyframes eq{0%,100%{height:4px}50%{height:15px}}
  .loading{display:inline-flex;align-items:center;gap:9px}
  @media (prefers-reduced-motion:reduce){.eq i{animation:none;height:10px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <svg class="logo" viewBox="0 0 512 512" aria-hidden="true">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#FF4B3E"/><stop offset="1" stop-color="#FF9A3D"/>
        </linearGradient>
      </defs>
      <rect width="512" height="512" rx="112" fill="url(#g)"/>
      <path d="M158 170 L158 342 L296 256 Z" fill="#fff" stroke="#fff" stroke-width="18" stroke-linejoin="round"/>
      <g fill="#fff">
        <rect x="320" y="206" width="26" height="100" rx="13"/>
        <rect x="358" y="171" width="26" height="170" rx="13"/>
        <rect x="396" y="191" width="26" height="130" rx="13"/>
      </g>
    </svg>
    <div class="brand">
      <h1>Onda</h1>
      <p>Extrae el audio de YouTube y SoundCloud</p>
    </div>
  </header>

  <!-- Paso 1: enlace -->
  <section class="step">
    <p class="eyebrow"><span class="n">01</span> Enlace</p>
    <div class="field">
      <input id="url" type="url" inputmode="url" autocomplete="off"
             placeholder="https://… de YouTube o SoundCloud">
      <button id="btnAnalizar" class="btn btn-ghost">Analizar</button>
    </div>
    <div id="errAnalizar" class="msg err hidden"></div>
  </section>

  <!-- Paso 2: resultado + calidad + descarga -->
  <section id="paso2" class="step off">
    <div id="resultado" class="card hidden"></div>

    <p class="eyebrow" style="margin-top:22px"><span class="n">02</span> Calidad</p>
    <div class="qgrid" id="qgrid">
      <button class="q" data-br="128" aria-pressed="false"><div class="kb">128<small> kbps</small></div><div class="lb">Ligero</div></button>
      <button class="q" data-br="192" aria-pressed="false"><div class="kb">192<small> kbps</small></div><div class="lb">Estándar</div></button>
      <button class="q" data-br="320" aria-pressed="true"><div class="kb">320<small> kbps</small></div><div class="lb">Máxima</div></button>
    </div>

    <button id="btnDescargar" class="btn btn-primary full" style="margin-top:16px">Descargar MP3</button>
    <div id="msgDescarga" class="msg hidden"></div>
  </section>
</div>

<script>
const $ = s => document.querySelector(s);
const eqHTML = '<span class="eq"><i></i><i></i><i></i><i></i></span>';
let datos = null;          // metadatos del análisis actual
let bitrate = "320";       // por defecto

const elUrl = $("#url"), btnA = $("#btnAnalizar"), btnD = $("#btnDescargar");
const paso2 = $("#paso2"), res = $("#resultado");
const errA = $("#errAnalizar"), msgD = $("#msgDescarga");

function show(el,txt,cls){el.className="msg "+cls;el.textContent=txt;el.classList.remove("hidden");}
function hide(el){el.classList.add("hidden");}

// --- Selección de calidad (tarjetas) ---
$("#qgrid").addEventListener("click", e => {
  const q = e.target.closest(".q"); if(!q) return;
  document.querySelectorAll(".q").forEach(b=>b.setAttribute("aria-pressed","false"));
  q.setAttribute("aria-pressed","true");
  bitrate = q.dataset.br;
});

// --- Paso 1: analizar ---
async function analizar(){
  const url = elUrl.value.trim();
  hide(errA); hide(msgD);
  if(!url){ show(errA,"Pega primero un enlace.","err"); return; }
  btnA.disabled = true; btnA.innerHTML = '<span class="loading">'+eqHTML+'Analizando…</span>';
  try{
    const r = await fetch("/api/inspeccionar",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({url})});
    const data = await r.json();
    if(!data.ok) throw new Error(data.error);
    datos = data;
    pintarResultado(data);
    paso2.classList.remove("off");
    res.classList.remove("hidden");
  }catch(err){
    show(errA, err.message || "No se pudo analizar el enlace.", "err");
    paso2.classList.add("off"); res.classList.add("hidden");
  }finally{
    btnA.disabled = false; btnA.textContent = "Analizar";
  }
}

function pintarResultado(d){
  const dot = "dot-" + (d.plataforma||"otra").toLowerCase();
  const inicial = (d.plataforma||"?").charAt(0);
  const thumb = d.miniatura
    ? '<img class="thumb" src="'+d.miniatura+'" alt="" onerror="this.outerHTML=fb">'
    : '<div class="thumb thumb-fb">'+inicial+'</div>';
  window.fb = '<div class="thumb thumb-fb">'+inicial+'</div>';
  res.innerHTML = thumb +
    '<div class="meta">'+
      '<p class="t">'+(d.titulo||"Sin título")+'</p>'+
      '<div class="sub">'+
        (d.autor?'<span>'+d.autor+'</span><span>·</span>':'')+
        '<span class="dur">'+(d.duracion_txt||"—")+'</span>'+
        '<span class="chip"><span class="dot '+dot+'"></span>'+(d.plataforma||"Otra")+'</span>'+
      '</div>'+
    '</div>';
}

// --- Paso 2: descargar ---
async function descargar(){
  if(!datos) return;
  hide(msgD);
  btnD.disabled = true; const txt = btnD.textContent;
  btnD.innerHTML = '<span class="loading">'+eqHTML+'Convirtiendo…</span>';
  try{
    const r = await fetch("/api/convertir",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({url:elUrl.value.trim(),bitrate})});
    if(!r.ok){
      const e = await r.json().catch(()=>({error:"Falló la conversión."}));
      throw new Error(e.error||"Falló la conversión.");
    }
    const blob = await r.blob();
    const nombre = decodeURIComponent(r.headers.get("X-Download-Name")||"audio.mp3");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = nombre;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(a.href);
    show(msgD,"Listo: "+nombre+". Revisa tus descargas.","ok");
  }catch(err){
    show(msgD, err.message || "No se pudo convertir.", "err");
  }finally{
    btnD.disabled = false; btnD.textContent = txt;
  }
}

btnA.addEventListener("click", analizar);
elUrl.addEventListener("keydown", e => { if(e.key==="Enter") analizar(); });
btnD.addEventListener("click", descargar);
</script>
</body>
</html>
"""


@app.route("/")
def inicio():
    return PAGINA


@app.route("/favicon.svg")
@app.route("/favicon.ico")
def favicon():
    return Response(ICONO_SVG, mimetype="image/svg+xml")


@app.route("/api/inspeccionar", methods=["POST"])
def api_inspeccionar():
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not url:
        return jsonify(ok=False, error="Pega primero un enlace."), 400
    try:
        info = core.inspeccionar(url)
    except Exception:
        # Mensaje en la voz de la interfaz: qué pasó y cómo arreglarlo.
        return jsonify(ok=False,
                       error="No reconozco ese enlace. Prueba con una URL de YouTube o SoundCloud."), 422
    info["ok"] = True
    return jsonify(info)


@app.route("/api/convertir", methods=["POST"])
def api_convertir():
    cuerpo = request.get_json(silent=True) or {}
    url = cuerpo.get("url", "").strip()
    bitrate = cuerpo.get("bitrate", "320")
    if bitrate not in BITRATES_VALIDOS:
        bitrate = "320"
    if not url:
        return jsonify(ok=False, error="Falta el enlace."), 400

    # Carpeta temporal: lo que se escribe aquí NO persiste en la Pi.
    tmpdir = tempfile.mkdtemp(prefix="onda_")
    try:
        ruta = core.descargar_mp3(url, bitrate=bitrate, carpeta=Path(tmpdir))
        datos = ruta.read_bytes()
        nombre = ruta.name
    except Exception:
        return jsonify(ok=False, error="No se pudo convertir el audio. Inténtalo de nuevo."), 502
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    resp = send_file(io.BytesIO(datos), as_attachment=True,
                     download_name=nombre, mimetype="audio/mpeg")
    # Nombre del fichero para que el front lo use al guardar (codificado por el acento/UTF-8).
    resp.headers["X-Download-Name"] = quote(nombre)
    return resp


if __name__ == "__main__":
    app.run(debug=True, port=5000)
