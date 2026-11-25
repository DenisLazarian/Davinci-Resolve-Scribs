"""
Subida automática de vídeos a YouTube con Playwright (YouTube Studio).

Uso:
    python upload_video.py

La primera vez se abrirá Chrome en la página de inicio de sesión de Google.
Inicia sesión a mano, vuelve a la terminal y pulsa ENTER. La sesión se guarda
en la carpeta "perfil_youtube", así que las siguientes ejecuciones ya no
pedirán login.

Si Google bloquea el inicio de sesión por ser un navegador automatizado,
cierra el script y abre Chrome con el mismo perfil:
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --user-data-dir="C:\\Users\\user1\\Desktop\\YT Scrippts\\perfil_youtube"
Inicia sesión ahí, cierra Chrome y vuelve a ejecutar el script.
"""

import os
import re
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DIR_SCRIPT = Path(__file__).resolve().parent
PERFIL_DIR = DIR_SCRIPT / "perfil_youtube"
STUDIO_URL = "https://studio.youtube.com"

# Evita UnicodeEncodeError con emojis en consolas Windows (cp1252/cp850).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Se prueba en orden: Chrome instalado, Edge, Chromium de Playwright.
CANALES_NAVEGADOR = ["chrome", "msedge", "chromium"]

VISIBILIDADES = {
    "PUBLIC": ['tp-yt-paper-radio-button[name="PUBLIC"]', "#public-radio-button"],
    "UNLISTED": ['tp-yt-paper-radio-button[name="UNLISTED"]', "#unlisted-radio-button"],
    "PRIVATE": ['tp-yt-paper-radio-button[name="PRIVATE"]', "#private-radio-button"],
}


def _log(mensaje):
    print(mensaje, flush=True)


def _primer_visible(page, selectores, timeout_ms=30000, descripcion="the element"):
    """Espera y devuelve el primer locator visible de una lista de selectores."""
    limite = time.time() + timeout_ms / 1000
    ultimo_error = None

    while time.time() < limite:
        for selector in selectores:
            try:
                locator = page.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    return locator.first
            except Exception as exc:  # la página puede estar navegando
                ultimo_error = exc
        page.wait_for_timeout(250)

    raise PlaywrightTimeoutError(
        f"Could not find {descripcion}. Selectors tried: " + ", ".join(selectores)
    ) from ultimo_error


def _clic_primer_visible(page, selectores, timeout_ms=30000, descripcion="the element"):
    locator = _primer_visible(page, selectores, timeout_ms, descripcion)
    locator.scroll_into_view_if_needed()
    locator.click()
    return locator


def _abrir_navegador(p):
    """Abre Chrome/Edge/Chromium con el perfil persistente (donde se guarda el login)."""
    PERFIL_DIR.mkdir(parents=True, exist_ok=True)
    errores = []

    for canal in CANALES_NAVEGADOR:
        try:
            contexto = p.chromium.launch_persistent_context(
                user_data_dir=str(PERFIL_DIR),
                channel=None if canal == "chromium" else canal,
                headless=False,
                viewport={"width": 1440, "height": 900},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--hide-crash-restore-bubble",
                ],
            )
            _log(f"Browser opened: {canal}")
            return contexto
        except Exception as exc:
            errores.append(f"{canal}: {exc}")

    raise RuntimeError(
        "Could not open any browser. Is Chrome already open using the "
        "'perfil_youtube' folder? Close it and try again.\n"
        + "\n".join(errores)
    )


def _asegurar_sesion(page):
    """Entra en Studio y, si hace falta, pide al usuario que inicie sesión."""
    _log("Opening YouTube Studio...")
    page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(20000)

    for _ in range(3):
        if "accounts.google.com" not in page.url:
            try:
                page.wait_for_selector(
                    "ytcp-button.ytcpAppHeaderCreateIcon button, #create-icon, #upload-icon",
                    state="visible",
                    timeout=60000,
                )
                _log("Signed in successfully.")
                return
            except PlaywrightTimeoutError:
                # Puede que el botón tarde, pero si no hay botón de "Iniciar sesión"
                # damos la sesión por válida y seguimos (el flujo tiene plan B).
                if page.locator(
                    'a[href*="ServiceLogin"], ytcp-button#sign-in-button, '
                    'ytcp-button-shape#sign-in-button'
                ).count() == 0:
                    _log("Session detected.")
                    return

        _log("")
        _log("⚠️  You are not signed in to YouTube Studio.")
        _log("   Sign in with your Google account in the browser window.")
        _log("   Once you can see YouTube Studio, come back here and press ENTER.")
        input("👉 Press ENTER to continue...")

        page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(3000)

    raise RuntimeError("Could not sign in to YouTube Studio.")


def _abrir_dialogo_subida(page):
    """Abre el diálogo de subida desde el botón Crear (con plan B por /upload)."""
    _log("Opening the upload dialog...")

    try:
        _clic_primer_visible(
            page,
            [
                "ytcp-button.ytcpAppHeaderCreateIcon button",
                "button[aria-label*='Crear' i]",
                "button[aria-label*='Create' i]",
                "ytcp-button#create-icon",
                "#create-icon",
            ],
            timeout_ms=60000,
            descripcion="the 'Create' button",
        )
        _clic_primer_visible(
            page,
            [
                "tp-yt-paper-item#text-item-0",
                "#text-item-0",
                "tp-yt-paper-item:has-text('Subir')",
                "tp-yt-paper-item:has-text('Upload')",
            ],
            timeout_ms=30000,
            descripcion="the 'Upload videos' option",
        )
    except Exception as exc:
        # Plan B: esta URL abre Studio directamente con el diálogo de subida.
        _log(f"⚠️  Could not use the Create menu ({exc}). Trying youtube.com/upload...")
        page.goto("https://www.youtube.com/upload", wait_until="domcontentloaded", timeout=120000)

    page.wait_for_selector(
        'input[name="Filedata"], input[type="file"]',
        state="attached",
        timeout=120000,
    )


def _escribir_en_caja(page, locator, texto):
    """Escribe en una caja contenteditable de Studio respetando los saltos de línea."""
    locator.scroll_into_view_if_needed()
    locator.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")

    try:
        # insert_text no dispara atajos del navegador y conserva emojis/acentos.
        for indice, linea in enumerate(texto.split("\n")):
            if indice:
                page.keyboard.press("Enter")
            if linea:
                page.keyboard.insert_text(linea)
    except Exception:
        locator.fill(texto)


def _obtener_video_id(page, timeout_ms=120000):
    enlace = _primer_visible(
        page,
        [
            "a.ytcp-video-info",
            "ytcp-video-info a",
            'a[href*="youtu.be/"]',
        ],
        timeout_ms=timeout_ms,
        descripcion="the video link (ID)",
    )
    href = enlace.get_attribute("href") or ""
    coincidencia = re.search(r"(?:youtu\.be/|v=)([\w-]{11})", href)
    if not coincidencia:
        raise RuntimeError(f"Could not extract the video ID from the link: {href}")
    return coincidencia.group(1)


def _marcar_no_para_ninos(page):
    locator = _primer_visible(
        page,
        [
            'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
            "ytkc-made-for-kids-select tp-yt-paper-radio-button:nth-of-type(2)",
            "#audience tp-yt-paper-radio-button:nth-of-type(2)",
            "#audience tp-yt-paper-radio-button:has-text('No, no es contenido')",
            "#audience tp-yt-paper-radio-button:has-text('not made for kids')",
        ],
        timeout_ms=60000,
        descripcion="the 'No, it's not made for kids' option",
    )
    locator.scroll_into_view_if_needed()
    locator.click()


def _ir_a_visibilidad(page):
    """Pulsa 'Siguiente' hasta que aparezcan las opciones de visibilidad."""
    for _ in range(8):
        if page.locator(
            'tp-yt-paper-radio-button[name="PUBLIC"], #public-radio-button'
        ).first.is_visible():
            return

        _clic_primer_visible(
            page,
            [
                "ytcp-button#next-button button",
                "#next-button",
                "button[aria-label*='Siguiente' i]",
                "button[aria-label*='Next' i]",
            ],
            timeout_ms=60000,
            descripcion="the 'Next' button",
        )
        page.wait_for_timeout(1200)

    raise RuntimeError("Did not reach the visibility tab.")


def _elegir_visibilidad(page, visibilidad):
    locator = _primer_visible(
        page,
        VISIBILIDADES[visibilidad],
        timeout_ms=60000,
        descripcion=f"the {visibilidad} visibility option",
    )
    locator.scroll_into_view_if_needed()
    locator.click()
    page.wait_for_timeout(800)


def _esperar_fin_subida(page, timeout_min=60):
    """Espera a que el archivo termine de subirse (la barra deja de mostrar %)."""
    _log("Waiting for the file upload to finish...")

    progreso_visto = False
    try:
        page.wait_for_selector("ytcp-video-upload-progress", state="attached", timeout=30000)
        progreso_visto = True
    except PlaywrightTimeoutError:
        _log("⚠️  Progress bar not found; the final button will be used instead.")

    limite = time.time() + timeout_min * 60
    while time.time() < limite:
        # Errores mostrados por Studio (límite diario, archivo rechazado, etc.)
        error = page.evaluate(
            """() => {
                const el = document.querySelector('.error-area.style-scope.ytcp-uploads-dialog');
                return el ? (el.innerText || '').trim() : '';
            }"""
        )
        if error:
            raise RuntimeError(f"YouTube rejected the upload: {error}")

        estado = page.evaluate(
            """() => {
                const progreso = document.querySelector('ytcp-video-upload-progress');
                if (!progreso) return null;
                const etiqueta = progreso.querySelector('.progress-label');
                return {
                    subiendo: progreso.hasAttribute('uploading'),
                    texto: (etiqueta ? etiqueta.textContent : '') || ''
                };
            }"""
        )

        if estado is not None:
            progreso_visto = True
            texto = estado["texto"]
            porcentaje = re.search(r"(\d+)\s*%", texto)
            llego_al_cien = porcentaje is not None and int(porcentaje.group(1)) >= 100
            if llego_al_cien or (not estado["subiendo"] and "%" not in texto):
                _log("Upload completed.")
                return
        else:
            # Si la barra existió y desapareció, la subida ya terminó.
            if progreso_visto:
                _log("Upload completed.")
                return

            # Sin barra de progreso: usar el botón final como referencia.
            boton = page.locator("#done-button button, #done-button").first
            try:
                if boton.count() > 0 and boton.is_visible() and not boton.is_disabled():
                    _log("Upload completed.")
                    return
            except Exception:
                pass

        page.wait_for_timeout(2000)

    raise TimeoutError(
        f"The upload did not finish within {timeout_min} minutes. "
        "You can increase the espera_subida_min parameter."
    )


def _esperar_boton_publicar(page, timeout_min=10):
    """Devuelve el botón final cuando YouTube lo habilita."""
    limite = time.time() + timeout_min * 60

    while time.time() < limite:
        for selector in (
            "ytcp-button#done-button button",
            "#done-button button",
            "#done-button",
        ):
            try:
                boton = page.locator(selector).first
                if boton.count() > 0 and boton.is_visible() and not boton.is_disabled():
                    return boton
            except Exception:
                continue
        page.wait_for_timeout(2000)

    raise TimeoutError("The publish button was not enabled in time.")


# Al elegir PUBLIC o UNLISTED, YouTube muestra un aviso que recomienda dejar el
# vídeo en privado y guarda el vídeo como borrador si no se confirma.
_BOTONES_CONFIRMAR_AVISO = [
    "ytcp-confirmation-dialog #confirm-button button",
    "ytcp-confirmation-dialog #confirm-button",
    "ytcp-dialog #confirm-button button",
    "ytcp-dialog #confirm-button",
    "tp-yt-paper-dialog #confirm-button button",
    "tp-yt-paper-dialog #confirm-button",
    "button:has-text('Publicar de todas formas')",
    "button:has-text('Publicar de todos modos')",
    "button:has-text('Publicar igualmente')",
    "button:has-text('Publish anyway')",
    "button:has-text('Publicar ahora')",
    "button:has-text('Publish now')",
]

_CLAVES_CONFIRMAR = (
    "de todas formas",
    "de todos modos",
    "igualmente",
    "anyway",
    "publicar",
    "publish",
    "continuar",
    "continue",
)

_CLAVES_CANCELAR = ("descartar", "discard", "cancelar", "cancel", "volver", "revisar")


def _boton_habilitado(boton):
    """True si el botón (o el <button> que contiene) se puede pulsar."""
    try:
        deshabilitado = boton.evaluate(
            """el => {
                const objetivo = el.matches('button') ? el : el.querySelector('button');
                if (!objetivo) {
                    return el.hasAttribute('disabled') ||
                        el.getAttribute('aria-disabled') === 'true';
                }
                return objetivo.disabled ||
                    objetivo.getAttribute('aria-disabled') === 'true';
            }"""
        )
        return not deshabilitado
    except Exception:
        return True


def _buscar_boton_confirmar(page):
    """Devuelve el botón 'Publicar de todas formas' del aviso, si está visible."""
    for selector in _BOTONES_CONFIRMAR_AVISO:
        try:
            locator = page.locator(selector)
            total = min(locator.count(), 5)
        except Exception:
            continue

        for indice in range(total):
            boton = locator.nth(indice)
            try:
                if not boton.is_visible():
                    continue
                texto = (boton.inner_text() or "").strip().lower()
                if any(clave in texto for clave in _CLAVES_CANCELAR):
                    continue
                if not any(clave in texto for clave in _CLAVES_CONFIRMAR):
                    continue
                if not _boton_habilitado(boton):
                    continue
                return boton
            except Exception:
                continue

    return None


def _confirmar_aviso_publicacion(page, timeout_ms=20000):
    """Acepta el aviso que recomienda publicar en privado ('Publicar de todas formas').

    Devuelve True si se llegó a pulsar alguna confirmación.
    """
    limite = time.time() + timeout_ms / 1000
    pulsado = False

    while time.time() < limite:
        # Si ya apareció el diálogo final, no hay aviso pendiente.
        try:
            if page.locator("ytcp-video-share-dialog").first.is_visible():
                return pulsado
        except Exception:
            pass

        boton = _buscar_boton_confirmar(page)
        if boton is None:
            page.wait_for_timeout(500)
            continue

        try:
            boton.scroll_into_view_if_needed()
            boton.click()
            pulsado = True
            _log(
                "⚠️  YouTube recommended publishing as private; "
                "clicking 'Publish anyway'."
            )
            page.wait_for_timeout(1000)
        except Exception:
            page.wait_for_timeout(500)

    return pulsado


def _publicar(page):
    _log("Publishing the video...")
    boton = _esperar_boton_publicar(page)
    boton.scroll_into_view_if_needed()
    boton.click()

    _confirmar_aviso_publicacion(page)

    video_id = None
    try:
        page.wait_for_selector("ytcp-video-share-dialog", state="visible", timeout=60000)
        page.wait_for_timeout(1500)

        enlace = page.locator("ytcp-video-share-dialog a[href*='youtu.be/']").first
        if enlace.count() > 0:
            href = enlace.get_attribute("href") or ""
            coincidencia = re.search(r"(?:youtu\.be/|v=)([\w-]{11})", href)
            if coincidencia:
                video_id = coincidencia.group(1)

        try:
            page.locator("ytcp-video-share-dialog #close-button").first.click(timeout=10000)
        except Exception:
            page.keyboard.press("Escape")
    except PlaywrightTimeoutError:
        _log("⚠️  The confirmation dialog did not appear, but the video was already submitted.")

    return video_id


def _preparar_miniatura(miniatura):
    """Acepta bytes, str o Path y devuelve (ruta, es_temporal).

    Los bytes (como los que guarda el formulario de Flet) se escriben en un
    archivo temporal para poder pasárselos al input de YouTube Studio.
    """
    if not miniatura:
        return None, False

    if isinstance(miniatura, (bytes, bytearray)):
        datos = bytes(miniatura)
        if datos.startswith(b"\x89PNG"):
            sufijo = ".png"
        elif datos.startswith(b"\xff\xd8"):
            sufijo = ".jpg"
        elif datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
            sufijo = ".webp"
        elif datos.startswith(b"GIF8"):
            sufijo = ".gif"
        elif datos.startswith(b"BM"):
            sufijo = ".bmp"
        else:
            sufijo = ".png"

        descriptor, nombre = tempfile.mkstemp(prefix="miniatura_", suffix=sufijo)
        os.close(descriptor)
        archivo = Path(nombre)
        archivo.write_bytes(datos)
        return archivo, True

    ruta = Path(miniatura)
    if not ruta.is_absolute():
        ruta = (DIR_SCRIPT / ruta).resolve()
    if not ruta.is_file():
        raise FileNotFoundError(f"The thumbnail file does not exist: {ruta}")
    return ruta, False


def _subir_miniatura(page, ruta, timeout_ms=120000):
    """Sube la miniatura en la pestaña de detalles y comprueba que se aplicó."""
    _log(f"Uploading thumbnail: {ruta.name}")

    selectores = [
        "ytcp-thumbnail-uploader input#file-loader",
        "ytcp-thumbnail-uploader input[type='file']",
        "input#file-loader[type='file']",
    ]

    entrada = None
    limite = time.time() + timeout_ms / 1000
    while time.time() < limite and entrada is None:
        for selector in selectores:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    entrada = locator
                    break
            except Exception:
                continue
        if entrada is None:
            page.wait_for_timeout(500)

    if entrada is None:
        _log("⚠️  Thumbnail selector not found; publishing without it.")
        return False

    try:
        entrada.set_input_files(str(ruta))
    except Exception as exc:
        _log(f"⚠️  Could not upload the thumbnail ({exc}); publishing without it.")
        return False

    # YouTube tarda unos segundos en procesar la imagen; si la rechaza,
    # muestra el motivo dentro del propio cargador de miniaturas.
    limite = time.time() + 30
    while time.time() < limite:
        try:
            estado = page.evaluate(
                """() => {
                    const caja = document.querySelector('ytcp-thumbnail-uploader');
                    if (!caja) return { error: '', aplicada: false };
                    const error = caja.querySelector('.error, .thumbnail-error, #error');
                    const img = caja.querySelector('img#image, img.thumbnail-image');
                    const src = img ? (img.getAttribute('src') || '') : '';
                    return {
                        error: error ? (error.innerText || '').trim() : '',
                        aplicada: !!src && !/^data:image\\/gif/.test(src)
                    };
                }"""
            )
        except Exception:
            estado = {"error": "", "aplicada": False}

        if estado["error"]:
            _log(f"⚠️  YouTube rejected the thumbnail: {estado['error']}")
            return False

        if estado["aplicada"]:
            _log("Thumbnail applied.")
            return True

        page.wait_for_timeout(500)

    _log("⚠️  Could not confirm the thumbnail; publishing anyway.")
    return False


def upload_video(
    ruta_video,
    titulo,
    descripcion="",
    visibilidad="PRIVATE",
    espera_subida_min=60,
    miniatura=None,
):
    print("uploading video")
    ruta = Path(ruta_video)
    if not ruta.is_absolute():
        ruta = (DIR_SCRIPT / ruta).resolve()
    if not ruta.is_file():
        raise FileNotFoundError(f"The video file does not exist: {ruta}")

    visibilidad = visibilidad.upper().strip()
    if visibilidad not in VISIBILIDADES:
        raise ValueError("visibilidad must be PUBLIC, UNLISTED or PRIVATE")

    titulo = titulo.strip()
    descripcion = descripcion.strip()
    if not titulo:
        raise ValueError("The title cannot be empty.")
    if len(titulo) > 100:
        raise ValueError("The title exceeds the 100 characters allowed by YouTube.")
    if len(descripcion) > 5000:
        raise ValueError("The description exceeds the 5000 characters allowed by YouTube.")
    if "<" in titulo or ">" in titulo or "<" in descripcion or ">" in descripcion:
        raise ValueError("YouTube does not allow the characters '<' or '>' in the title/description.")

    ruta_miniatura, miniatura_temporal = _preparar_miniatura(miniatura)
    if ruta_miniatura is not None and ruta_miniatura.stat().st_size > 2 * 1024 * 1024:
        _log("⚠️  The thumbnail exceeds the 2 MB limit supported by YouTube; it may be rejected.")

    video_id = None

    with sync_playwright() as p:
        contexto = _abrir_navegador(p)
        contexto.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        page = contexto.pages[0] if contexto.pages else contexto.new_page()
        page.set_default_timeout(60000)

        try:
            _asegurar_sesion(page)
            _abrir_dialogo_subida(page)

            _log(f"Uploading file: {ruta}")
            time.sleep(2)
            page.locator('input[name="Filedata"], input[type="file"]').first.set_input_files(str(ruta))

            # Esperar el formulario de detalles del vídeo.
            titulo_box = _primer_visible(
                page,
                ["#title-textarea #textbox", "#title-wrapper #textbox", "#textbox"],
                timeout_ms=120000,
                descripcion="the title box",
            )

            _log("Filling in title and description...")
            _escribir_en_caja(page, titulo_box, titulo)

            descripcion_box = page.locator("#description-textarea #textbox").first
            if descripcion_box.count() == 0 or not descripcion_box.is_visible():
                descripcion_box = page.locator("#textbox").nth(1)
            _escribir_en_caja(page, descripcion_box, descripcion)

            if ruta_miniatura is not None:
                _subir_miniatura(page, ruta_miniatura)

            # El ID aparece en el panel derecho en cuanto arranca la subida.
            try:
                video_id = _obtener_video_id(page, timeout_ms=60000)
                _log(f"Video ID: {video_id}")
            except PlaywrightTimeoutError:
                _log("⚠️  Could not read the ID yet; will try again when publishing.")

            _log("Setting audience...")
            _marcar_no_para_ninos(page)

            _log("Moving on to the visibility screen...")
            _ir_a_visibilidad(page)

            _log(f"Selecting visibility: {visibilidad}")
            _elegir_visibilidad(page, visibilidad)

            _esperar_fin_subida(page, timeout_min=espera_subida_min)
            video_id = _publicar(page) or video_id

            _log("✅ Process finished successfully!")
        finally:
            contexto.close()
            if miniatura_temporal and ruta_miniatura is not None:
                try:
                    ruta_miniatura.unlink()
                except OSError:
                    pass

    return video_id


if __name__ == "__main__":
    try:
        id_subido = upload_video(
            ruta_video="..\\prueba2.mp4",
            titulo="Título de prueba desde Python 1",
            descripcion="Descripción de prueba.\n\nSegunda línea de la descripción.",
            visibilidad="UNLISTED",
        )
        # id_subido = upload_video(
        #     ruta_video="..\\prueba2.mp4",
        #     titulo="Título de prueba desde Python 2",
        #     descripcion="Descripción de prueba.\n\nSegunda línea de la descripción.",
        #     visibilidad="PRIVATE",
        # )
        print(f"\nYou can use this ID in the rest of your program: {id_subido}")
        print(f"Link: https://youtu.be/{id_subido}")
    except Exception as exc:
        print(f"\n❌ Error: {exc}")
        sys.exit(1)