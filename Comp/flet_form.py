"""
Formulario de procesamiento de vídeo con Flet 1.x.

Requisitos:   pip install -U flet
Ejecutar:     python app_flet.py
Debe estar junto a davinci_render.py y upload_video.py (se reutilizan tal cual).

con internacionalizacion: $env:LANG='ca' ; python flet_form.py

Expresion regular para buscar string : comentado en start_form.bat
"""
import asyncio
import os
import sys
import json
from dataclasses import asdict
from pathlib import Path

# --- Bootstrap del API de scripts de Resolve ---------
_API_RESOLVE = Path(os.environ.get(
    "RESOLVE_SCRIPT_API",
    r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting",
))
_MODULOS_RESOLVE = _API_RESOLVE / "Modules"
if _MODULOS_RESOLVE.is_dir() and str(_MODULOS_RESOLVE) not in sys.path:
    sys.path.insert(0, str(_MODULOS_RESOLVE))
os.environ.setdefault("RESOLVE_SCRIPT_API", str(_API_RESOLVE))
os.environ.setdefault(
    "RESOLVE_SCRIPT_LIB",
    r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll",
)

import flet as ft

# davinci_render.py importa DaVinciResolveScript, que falla si Resolve no está instalado.
# El formulario debe abrirse igualmente, así que el import es opcional.
try:
    import davinci_render as resolve_api
except BaseException as _ex:
    resolve_api = None
    ERROR_RESOLVE = f"{type(_ex).__name__}: {_ex}"
else:
    ERROR_RESOLVE = ""

from upload_video import upload_video

import gettext

# Ruta absoluta: funciona tanto si lanzas el script desde Comp como desde la raíz.
DIR_SCRIPT = Path(__file__).resolve().parent
LOCALEDIR = DIR_SCRIPT / "locales"

# Conservamos el objeto del catalogo para poder cambiar de idioma en caliente.
# .install() mete builtins._; no hace falta escribir "_ = ..." en ningun sitio.
catalogo = gettext.translation("dialogs", localedir=str(LOCALEDIR), fallback=True)
catalogo.install()
IDIOMA_ACTUAL = None

PERSONAS = ["Laura", "Juan", "María", "Pedro"]
IDIOMAS = [("es", "Español"), ("ca", "Català"), ("en", "English")]


def idioma_activo() -> str:
    """Idioma del catalogo cargado, no el locale del sistema.

    gettext elige el catalogo con LANGUAGE > LC_ALL > LC_MESSAGES > LANG.
    locale.getlocale() consulta el locale de Windows, que no cambia con esas
    variables, por eso devolvia siempre el idioma del sistema.
    """
    if IDIOMA_ACTUAL:
        return IDIOMA_ACTUAL
    mofile = gettext.find("dialogs", localedir=str(LOCALEDIR))
    if mofile:
        # .../locales/<idioma>/LC_MESSAGES/dialogs.mo
        idioma = Path(mofile).parent.parent.name.split("_")[0].lower()
    else:
        # Sin catalogo, gettext devuelve los textos originales (ingles).
        idioma = "en"
    validos = {clave for clave, _ in IDIOMAS}
    return idioma if idioma in validos else "en"


def aplicar_idioma(lang: str):
    """Instala otro catalogo y devuelve (catalogo_anterior, catalogo_nuevo)."""
    global catalogo, IDIOMA_ACTUAL
    anterior = catalogo
    catalogo = gettext.translation(
        "dialogs", localedir=str(LOCALEDIR), languages=[lang], fallback=True)
    catalogo.install()          # vuelve a meter builtins._; sin "_ = ..."
    IDIOMA_ACTUAL = lang
    return anterior, catalogo


# Propiedades de los controles Flet que pueden contener texto traducible.
PROPIEDADES_TEXTO = (
    "value", "text", "label", "tooltip", "title", "content",
    "error_text", "hint_text", "helper_text", "prefix_text", "suffix_text",
    "caption",
)


def iterar_controles(control):
    """Recorre recursivamente el arbol de controles de Flet."""
    vistos = set()
    pendientes = [control]
    while pendientes:
        actual = pendientes.pop()
        if not isinstance(actual, ft.Control) or id(actual) in vistos:
            continue
        vistos.add(id(actual))
        yield actual
        for atributo in ("controls", "actions", "content", "title",
                         "leading", "trailing", "options"):
            hijo = getattr(actual, atributo, None)
            if isinstance(hijo, ft.Control):
                pendientes.append(hijo)
            elif isinstance(hijo, (list, tuple)):
                pendientes.extend(h for h in hijo if isinstance(h, ft.Control))


def traducir_arbol(page, anterior, nuevo):
    """Reevalua los textos ya creados usando el catalogo anterior como indice.

    Los controles guardan el resultado de _(), no el msgid. Para saber que
    msgid corresponde a cada texto usamos el catalogo que habia antes.
    """
    # NullTranslations (sin .mo) no tiene _catalog; en ese caso no hay
    # traducciones previas que invertir y los textos son los msgid originales.
    catalogo_anterior = getattr(anterior, "_catalog", {})
    inverso = {
        traduccion: origen
        for origen, traduccion in catalogo_anterior.items()
        if isinstance(origen, str) and isinstance(traduccion, str) and origen
    }

    def convertir(texto):
        return nuevo.gettext(inverso.get(texto, texto))

    if isinstance(page.title, str):
        page.title = convertir(page.title)

    for raiz in list(page.controls):
        for control in iterar_controles(raiz):
            for propiedad in PROPIEDADES_TEXTO:
                valor = getattr(control, propiedad, None)
                if isinstance(valor, str):
                    traducido = convertir(valor)
                    if traducido != valor:
                        setattr(control, propiedad, traducido)

PASOS = ["Notification", "Processing"]
ACENTO = "#1f6f8b"

# Tarjeta del formulario: tamaño fijo en ventanas grandes, se encoge en las pequeñas
ANCHO_TARJETA = 760
ALTO_TARJETA = 780
MARGEN = 24            # espacio entre la tarjeta y el borde de la ventana
VENTANA_COMPACTA = 600  # por debajo de este ancho la tarjeta ocupa toda la ventana

EXTENSIONES_IMG = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

PLANTILLA_CONFIG = DIR_SCRIPT / "settings_layout.json"

URL_DAVINCI = "https://www.blackmagicdesign.com/products/davinciresolve"
URL_API_RESOLVE = "https://wiki.dvresolve.com/developer-docs/scripting-api"


# ---------------------------------------------------------------------------
# Trabajo bloqueante (Resolve / YouTube). Se ejecuta con asyncio.to_thread,
# porque en Flet 1.x los handlers corren en el bucle de eventos y bloquearían la UI.
# ---------------------------------------------------------------------------
def ruta_render(carpeta, nombre):
    """Localiza el archivo renderizado (Resolve añade la extensión)."""
    base = Path(carpeta)
    if not base.is_dir():
        return None
    candidatos = [a for a in base.iterdir() if a.is_file() and a.stem == nombre]
    return max(candidatos, key=lambda a: a.stat().st_mtime) if candidatos else None


def estado_resolve() -> str:
    """Devuelve '' si Resolve Studio puede usarse, o el motivo por el que no."""
    if resolve_api is None:
        print(f"Could not import davinci_render.py: {ERROR_RESOLVE}")
        return "DaVinci Resolve Studio was not found on this computer."
    try:
        import DaVinciResolveScript as dvr
        resolve = dvr.scriptapp("Resolve")
    except BaseException as ex:
        print(f"Could not load the Resolve scripting API: {ex}")
        return "Could not load the DaVinci Resolve Studio scripting API."
    if resolve is None:
        return "DaVinci Resolve Studio is installed, but it is not running."
    try:
        gestor = resolve.GetProjectManager()
        proyecto = gestor.GetCurrentProject() if gestor else None
    except BaseException as ex:
        print(f"Could not connect to Resolve: {ex}")
        return "Could not connect to DaVinci Resolve Studio."
    if proyecto is None:
        return ("DaVinci Resolve Studio is open, but no project is "
                "loaded.")
    return ""


def leer_resolve() -> list[dict]:
    """Equivalente a la ruta GET / de Flask."""
    motivo = estado_resolve()
    if motivo:
        raise RuntimeError(motivo)
    resolve_api.init_davinci_project()
    resolve_api.delete_all_jobs()
    grupos = resolve_api.get_clips()
    resolve_api.show_render_prev(grupos)
    return [
        {
            **asdict(g),
            "thumbnail": b"",   # bytes de la imagen elegida
            "settings": {
                **resolve_api.settings,
                "MarkIn": g.start,
                "MarkOut": g.end,
                "CustomName": g.title,
            },
        }
        for g in grupos
    ]

def send_whatsapp(emisor, receptor, observacion, sesion_mia, idioma_msj, yt_ids):
    """Envio automatizado de mensajes de WhatsApp""" # TODO 
    pass

def trabajo_render( 
        emisor,
        receptor,
        observacion,
        sesion_mia,
        idioma_msj,
        a_renderizar,
        subir_youtube, apagar_pc
) -> str:
    """Renderiza, sube y (opcional) apaga. Devuelve un mensaje de error o ''."""
    mensaje = ""
    if resolve_api is None:
        return "DaVinci Resolve Studio is not available."
    try:
        jobs = resolve_api.create_render_jobs(a_renderizar)
        ok = bool(jobs) and resolve_api.render_jobs(jobs)  # BLOQUEA hasta terminar
        if not ok:
            return "The render did not finish successfully."
        if subir_youtube:
            yt_ids = []
            for c in a_renderizar:
                s = c["settings"]
                nombre = s.get("CustomName") or c["title"]
                ruta = ruta_render(s.get("TargetDir", ""), nombre)
                if ruta is None:
                    print(f"Could not find the rendered video for “{c['title']}”")
                    mensaje = "Some rendered videos could not be found for uploading."
                    continue
                yt_ids.append(upload_video(
                    str(ruta), c["title"], "", "UNLISTED",
                    miniatura=c["thumbnail"] or None,
                ))
            send_whatsapp(emisor, receptor, observacion, sesion_mia, idioma_msj, yt_ids)
        if apagar_pc:
            os.system("shutdown /s /t 60")  # cancelar con: shutdown /a
    except Exception as ex:
        mensaje = f"Error: {ex}"
    return mensaje


# ---------------------------------------------------------------------------
async def main(page: ft.Page):
    ruta_datos = os.getenv("FLET_APP_STORAGE_DATA", ".")
    os.makedirs(ruta_datos, exist_ok=True)

    archivo_config = os.path.join(ruta_datos, "settings.json")

    def guardar_json(datos: dict):
        with open(archivo_config, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)

    def leer_json() -> dict:
        if os.path.exists(archivo_config):
            with open(archivo_config, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def leer_plantilla() -> dict:
        with open(PLANTILLA_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)

    def combinar(plantilla, datos):
        """Rellena la plantilla con los datos guardados, sin añadir claves nuevas."""
        if isinstance(plantilla, dict):
            guardados = datos if isinstance(datos, dict) else {}
            return {clave: combinar(valor, guardados.get(clave))
                    for clave, valor in plantilla.items()}
        if isinstance(plantilla, bool):
            return bool(datos)
        if isinstance(plantilla, str):
            return datos if isinstance(datos, str) else plantilla
        return plantilla

    def cargar_config() -> dict:
        """Lee settings.json; si no existe lo crea a partir de settings_layout.json."""
        try:
            plantilla = leer_plantilla()
        except (OSError, json.JSONDecodeError) as ex:
            print(f"Could not read the template {PLANTILLA_CONFIG}: {ex}")
            return {}

        if not os.path.exists(archivo_config):
            try:
                guardar_json(plantilla)
            except OSError as ex:
                print(f"Could not create {archivo_config}: {ex}")
            return plantilla

        try:
            return combinar(plantilla, leer_json())
        except (OSError, json.JSONDecodeError) as ex:
            print(f"settings.json is not valid ({ex}); using the template.")
            return plantilla

    page.title = _(("Video processing"))
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ACENTO)
    page.dark_theme = ft.Theme(color_scheme_seed=ACENTO)
    page.padding = 0
    page.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGHEST
    page.window.width = 1100
    page.window.height = 900

    clips: list[dict] = []
    estado = {"paso": 0}
    # Preferencias de vídeo que no se editan en un campo del formulario.
    prefs = {"thumbnail_path": "", "destiny_dir": ""}
    selector = ft.FilePicker()  # servicio: se mantiene la referencia
    lanzador = ft.UrlLauncher()  # servicio para abrir los enlaces de ayuda

    # ------------------------------------------------------------------ Paso 1
    emisor = ft.Dropdown(label=_("Sender"), expand=True,
                         options=[ft.DropdownOption(key=p, text=p) for p in PERSONAS])
    receptor = ft.Dropdown(label=_("Recipient"), expand=True,
                           options=[ft.DropdownOption(key=p, text=p) for p in PERSONAS])
    observacion = ft.TextField(label=_("Notes"), multiline=True, min_lines=4, max_lines=6)
    sesion_mia = ft.Checkbox(label=_("This session belongs to me."))
    idioma_msj = ft.Dropdown(label=_("Message language"), value="es",
                             options=[ft.DropdownOption(key=k, text=v) for k, v in IDIOMAS])
    guardar_prefs = ft.Checkbox(label=_("Save preferences for the next form"))

    paso1 = ft.Column(
        [
            ft.Text(_("Notification"), size=20, weight=ft.FontWeight.BOLD),
            ft.Text(_("Specify your name as the sender and who the notification is addressed to. "
                    "The message will be sent via WhatsApp."),
                    color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row([emisor, receptor]),
            observacion,
            sesion_mia,
            idioma_msj,
            guardar_prefs,
        ],
        spacing=16,
    )

    # ------------------------------------------------------------------ Paso 2
    subir_yt = ft.Checkbox(label=_("Upload directly to YouTube"))
    apagar_pc = ft.Checkbox(label=_("Shut down PC when finished (60 s delay)"))
    lista = ft.Column(spacing=10)
    contador_clips = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT, size=13)
    lista_vacia = ft.Text(_("No clips left in the list."), visible=False,
                          text_align=ft.TextAlign.CENTER)
    error_carga = ft.Text(color=ft.Colors.ERROR, visible=False)

    paso2 = ft.Column(
        [
            ft.Text(_("Processing"), size=20, weight=ft.FontWeight.BOLD),
            ft.Text(_("The clips that will be processed are listed here, and their "
                    "properties can be edited."), color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row([subir_yt, apagar_pc], wrap=True),
            ft.Row([ft.Text(_("Detected clips"), weight=ft.FontWeight.W_600), contador_clips],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            error_carga,
            lista,
            lista_vacia,
            ft.Text(_("Click a thumbnail or a title to change it. The pencil opens the "
                    "render properties and the {} discards the clip group.".format("✕")),
                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ],
        spacing=14,
        visible=False,
    )

    # ------------------------------------------------------------- Utilidades
    def aviso(texto, accion=None, callback=None):
        page.show_dialog(ft.SnackBar(
            content=ft.Text(texto),
            action=accion,
            on_action=(lambda e: callback()) if callback else None,
            duration=8000,
        ))

    def boton_enlace(texto, url, icono):
        async def abrir(e):
            try:
                await lanzador.launch_url(url)
            except BaseException as ex:
                aviso(f"Could not open the link: {ex}")
        return ft.TextButton(content=texto, icon=icono, on_click=abrir)

    def mostrar_requisitos_resolve(motivo):
        page.show_dialog(ft.AlertDialog(
            modal=True,
            icon=ft.Icon(icon=ft.Icons.ERROR_OUTLINE),
            icon_color=ft.Colors.ERROR,
            title=ft.Text(_("DaVinci Resolve Studio is required")),
            content=ft.Column(
                [
                    ft.Text(motivo),
                    ft.Text(_("This form renders videos with DaVinci Resolve Studio. "
                            "Install it, open it with a project loaded and press "
                            "Render again.")),
                    ft.Text(_("If you already have it installed, check Preferences > System > "
                            "General to allow access from external applications."),
                            color=ft.Colors.ON_SURFACE_VARIANT, size=12),
                    ft.Column(
                        [
                            boton_enlace(_("Scripting API documentation"),
                                         URL_API_RESOLVE, ft.Icons.MENU_BOOK_OUTLINED),
                            boton_enlace(_("Official DaVinci Resolve website"),
                                         URL_DAVINCI, ft.Icons.OPEN_IN_NEW),
                        ],
                        spacing=0,
                    ),
                ],
                tight=True, spacing=14, width=460,
            ),
            actions=[ft.FilledButton(content=_("Got it"),
                                     on_click=lambda e: page.pop_dialog())],
        ))

    def persona_valida(valor):
        return valor if valor in PERSONAS else None

    def idioma_valido(valor):
        return valor if valor in {clave for clave, _ in IDIOMAS} else "es"

    def aplicar_config(datos: dict):
        """Vuelca settings.json sobre los campos del formulario."""
        emisor.value = persona_valida(datos.get("Emiter"))
        receptor.value = persona_valida(datos.get("Receiver"))
        sesion_mia.value = bool(datos.get("sesions_belonging"))
        subir_yt.value = bool(datos.get("upload_youtube"))
        idioma_msj.value = idioma_valido(datos.get("message_language"))
        video = datos.get("video_config")
        video = video if isinstance(video, dict) else {}
        prefs["thumbnail_path"] = str(video.get("thumbnail") or "")
        prefs["destiny_dir"] = str(video.get("destiny_dir") or "")
        page.update()

    def preferencias_actuales() -> dict:
        """Construye el JSON con los mismos campos que settings_layout.json."""
        destino = prefs.get("destiny_dir") or ""
        if not destino and clips:
            destino = clips[0]["settings"].get("TargetDir", "")
        return {
            "Emiter": emisor.value or "",
            "Receiver": receptor.value or "",
            "upload_youtube": bool(subir_yt.value),
            "sesions_belonging": bool(sesion_mia.value),
            "message_language": idioma_msj.value or "",
            "video_config": {
                "thumbnail": prefs.get("thumbnail_path", ""),
                "destiny_dir": destino or "",
            },
        }

    def aplicar_config_video():
        """Aplica carpeta de destino y miniatura guardadas a los clips cargados."""
        destino = prefs.get("destiny_dir") or ""
        if destino:
            for clip in clips:
                clip["settings"]["TargetDir"] = destino

        ruta_miniatura = prefs.get("thumbnail_path") or ""
        if ruta_miniatura:
            try:
                datos = Path(ruta_miniatura).read_bytes()
            except OSError:
                datos = b""
            if datos:
                for clip in clips:
                    clip["thumbnail"] = datos

    async def cargar_clips():
        clips.clear()
        error_carga.visible = False
        try:
            clips.extend(await asyncio.to_thread(leer_resolve))
            aplicar_config_video()
        except BaseException as ex:  # init_davinci_project puede llamar a exit(0)
            error_carga.value = _("Could not read DaVinci Resolve: %s") % {ex or _('no connection')}
            error_carga.visible = True
        pintar_clips()

    # ---------------------------------------------------------- Lista de clips
    def pintar_clips():
        lista.controls = [crear_item(c) for c in clips]
        total = sum(max(0, c["end"] - c["start"]) for c in clips)
        contador_clips.value = ((f"{len(clips)} clip{'s' if len(clips) != 1 else ''} · {total} " + _("frames")) 
                                if clips else _("No clips"))
        lista_vacia.visible = not clips
        page.update()

    def miniatura(clip):
        if clip["thumbnail"]:
            contenido = ft.Image(src=clip["thumbnail"], fit=ft.BoxFit.COVER, width=132, height=74)
        else:
            contenido = ft.Icon(icon=ft.Icons.PLAY_CIRCLE_OUTLINE, size=32, color=ACENTO)

        async def al_clic(e):
            await abrir_miniatura(clip)

        return ft.Container(
            contenido, width=132, height=74, alignment=ft.Alignment.CENTER,
            border_radius=8, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border=ft.Border.all(1.5, ft.Colors.OUTLINE_VARIANT),
            tooltip=_("Change thumbnail"), ink=True, on_click=al_clic,
        )

    def crear_item(clip):
        s = clip["settings"]
        frames = max(0, clip["end"] - clip["start"])
        titulo = ft.TextButton(
            content=clip["title"], tooltip=_("Click to change the title"),
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=4, vertical=0)),
        )
        meta = ft.Text(f"{clip['start']} – {clip['end']} · {frames} " + _("frames") +" · "
                       f"{s['FormatWidth']}×{s['FormatHeight']}",
                       size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        datos = ft.Column([titulo, meta], spacing=2, expand=True)
        titulo.on_click = lambda e, c=clip, col=datos: editar_titulo(c, col)

        return ft.Container(
            ft.Row(
                [
                    miniatura(clip),
                    datos,
                    ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip=_("Render properties"),
                                  on_click=lambda e, c=clip: abrir_ajustes(c)),
                    ft.IconButton(icon=ft.Icons.CLOSE, tooltip=_("Discard this clip group"),
                                  icon_color=ft.Colors.ERROR,
                                  on_click=lambda e, c=clip: descartar(c)),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=10, border_radius=10,
            border=ft.Border.all(1.5, ft.Colors.OUTLINE_VARIANT),
        )

    def editar_titulo(clip, columna):
        hecho = {"v": False}
        campo = ft.TextField(value=clip["title"], dense=True, autofocus=True, max_length=120)

        def terminar(e):
            if hecho["v"]:
                return
            hecho["v"] = True
            nuevo = (campo.value or "").strip()
            if nuevo:
                clip["title"] = nuevo
                clip["settings"]["CustomName"] = nuevo  # título y nombre de archivo sincronizados
            pintar_clips()

        campo.on_submit = terminar
        campo.on_blur = terminar
        columna.controls[0] = campo
        page.update()

    def descartar(clip):
        if clip not in clips:
            return
        indice = clips.index(clip)
        clips.remove(clip)
        pintar_clips()

        def deshacer():
            clips.insert(min(indice, len(clips)), clip)
            pintar_clips()

        aviso(_("%s removed from the render.") % (f"“{clip['title']}”"), _("Undo"), deshacer)

    # ----------------------------------------------------- Diálogo: miniatura
    async def abrir_miniatura(clip):
        elegida = {"bytes": b"", "ruta": ""}
        error = ft.Text(color=ft.Colors.ERROR, visible=False, size=12)
        nombre = ft.Text(_("No file selected"), size=12,
                         color=ft.Colors.ON_SURFACE_VARIANT)

        def caja(contenido):
            return ft.Container(
                contenido, width=200, height=112, border_radius=8,
                alignment=ft.Alignment.CENTER,
                border=ft.Border.all(1.5, ft.Colors.OUTLINE_VARIANT),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )

        sin_imagen = lambda: ft.Text(_("No image"), size=12)
        actual = caja(ft.Image(src=clip["thumbnail"], fit=ft.BoxFit.COVER, width=200, height=112)
                      if clip["thumbnail"] else sin_imagen())
        nueva = caja(sin_imagen())
        todos = ft.Checkbox(label=_("Apply to all clips (%s)") % len(clips))

        async def elegir(e):
            archivos = await selector.pick_files(
                file_type=ft.FilePickerFileType.IMAGE, allow_multiple=False)
            error.visible = False
            elegida["bytes"] = b""
            elegida["ruta"] = ""
            nueva.content = sin_imagen()
            if archivos:
                ruta = Path(archivos[0].path) if archivos[0].path else None
                if ruta is None or ruta.suffix.lower() not in EXTENSIONES_IMG:
                    error.value, error.visible = _("The file must be an image."), True
                elif ruta.stat().st_size > 2 * 1024 * 1024:
                    error.value, error.visible = _("The image is too large (2 MB maximum)."), True
                else:
                    elegida["bytes"] = ruta.read_bytes()
                    elegida["ruta"] = str(ruta)
                    nombre.value = ruta.name
                    nueva.content = ft.Image(src=elegida["bytes"], fit=ft.BoxFit.COVER,
                                             width=200, height=112)
            page.update()

        def aplicar(e):
            if not elegida["bytes"]:
                error.value, error.visible = _("Choose an image before applying the changes."), True
                page.update()
                return
            destinos = list(clips) if todos.value else [clip]
            anteriores = [c["thumbnail"] for c in destinos]
            ruta_anterior = prefs.get("thumbnail_path", "")
            for c in destinos:
                c["thumbnail"] = elegida["bytes"]
            if elegida["ruta"]:
                prefs["thumbnail_path"] = elegida["ruta"]
            page.pop_dialog()
            pintar_clips()

            def deshacer():
                for c, t in zip(destinos, anteriores):
                    c["thumbnail"] = t
                prefs["thumbnail_path"] = ruta_anterior
                pintar_clips()

            aviso(_("Thumbnail applied to %(count)d clips.") % {"count": len(destinos)}
                  if len(destinos) > 1 else _("Thumbnail updated."),
                  _("Undo"), deshacer)

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(_("Change thumbnail")),
            content=ft.Column(
                [
                    ft.Text(f"“{clip['title']}”", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Row([ft.Column([ft.Text(_("Current"), weight=ft.FontWeight.W_600), actual]),
                            ft.Column([ft.Text(_("New"), weight=ft.FontWeight.W_600), nueva])],
                           spacing=16),
                    ft.Row([ft.Button(content=_("Choose image…"), icon=ft.Icons.IMAGE_OUTLINED,
                                      on_click=elegir), nombre]),
                    ft.Text(_("YouTube requires at least 1280×720 px and a maximum of 2 MB."),
                            size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    todos,
                    error,
                ],
                tight=True, spacing=12, width=440,
            ),
            actions=[ft.TextButton(content=_("Cancel"), on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton(content=_("Apply"), on_click=aplicar)],
        ))

    # ------------------------------------------------ Diálogo: propiedades
    def abrir_ajustes(clip):
        s = clip["settings"]
        nombre = ft.TextField(label=_("File name"), value=s.get("CustomName") or clip["title"],
                              max_length=120)
        ancho = ft.TextField(label=_("Width (px)"), value=str(s["FormatWidth"]),
                             keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        alto = ft.TextField(label=_("Height (px)"), value=str(s["FormatHeight"]),
                             keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        carpeta = ft.TextField(label=_("Destination folder"), value=s.get("TargetDir", ""))
        todos = ft.Checkbox(label=_("Render the entire clip"), value=bool(s.get("SelectAllFrames")))
        f_in = ft.TextField(label=_("Start frame"), value=str(s["MarkIn"]),
                            keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        f_out = ft.TextField(label=_("End frame"), value=str(s["MarkOut"]),
                             keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        video = ft.Checkbox(label=_("Export video"), value=s.get("ExportVideo", True) is not False)
        audio = ft.Checkbox(label=_("Export audio"), value=s.get("ExportAudio", True) is not False)
        duracion = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        def entero(campo, defecto):
            try:
                return int(float(campo.value))
            except (TypeError, ValueError):
                return defecto

        def refrescar(e=None):
            f_in.disabled = f_out.disabled = bool(todos.value)
            if todos.value:
                duracion.value = _("The entire clip will be rendered, without in/out marks.")
            else:
                total = entero(f_out, 0) - entero(f_in, 0)
                duracion.value = (_("Duration: %(frames)d %(unit)s") % {
                                      "frames": total, "unit": _("frames")
                                  } if total > 0
                                  else _("The end frame must be greater than the start frame."))
            page.update()

        todos.on_change = refrescar
        f_in.on_change = refrescar
        f_out.on_change = refrescar

        def guardar(e):
            inicio = max(0, entero(f_in, clip["start"]))
            fin = max(0, entero(f_out, clip["end"]))
            w, h = entero(ancho, 0), entero(alto, 0)
            for campo in (nombre, ancho, alto, f_out):
                campo.error_text = None
            ok = True
            if not (nombre.value or "").strip():
                nombre.error_text, ok = _("Required"), False
            if w < 2:
                ancho.error_text, ok = _("Minimum 2"), False
            if h < 2:
                alto.error_text, ok = _("Minimum 2"), False
            if not todos.value and fin <= inicio:
                f_out.error_text, ok = _("Must be greater than the start frame"), False
            if not ok:
                page.update()
                return

            clip["title"] = nombre.value.strip()
            s.update({
                "CustomName": clip["title"], "FormatWidth": w, "FormatHeight": h,
                "TargetDir": (carpeta.value or "").strip(), "SelectAllFrames": bool(todos.value),
                "MarkIn": inicio, "MarkOut": fin,
                "ExportVideo": bool(video.value), "ExportAudio": bool(audio.value),
            })
            clip["start"], clip["end"] = inicio, fin
            prefs["destiny_dir"] = s.get("TargetDir", "")
            page.pop_dialog()
            pintar_clips()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Column([ft.Text(_("Render properties")),
                             ft.Text("“{}” · {} – {} {}".format(clip['title'], clip['start'], clip['end'], _("frames")),
                                     size=12, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=2),
            content=ft.Column(
                [nombre, ft.Row([ancho, alto]), carpeta, todos, ft.Row([f_in, f_out]),
                 duracion, video, audio],
                tight=True, spacing=12, width=480, scroll=ft.ScrollMode.AUTO,
            ),
            actions=[ft.TextButton(content=_("Cancel"), on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton(content=_("Save changes"), on_click=guardar)],
        ))
        refrescar()

    # ---------------------------------------------------------------- Render
    async def renderizar(e):
        motivo = await asyncio.to_thread(estado_resolve)
        if motivo:
            mostrar_requisitos_resolve(motivo)
            return
        if not validar_paso(0):
            mostrar_paso(0)
            return
        if not clips:
            aviso(_("There are no clips to render."))
            return

        if guardar_prefs.value:
            try:
                datos = preferencias_actuales()
                guardar_json(datos)
                prefs["thumbnail_path"] = datos["video_config"]["thumbnail"]
                prefs["destiny_dir"] = datos["video_config"]["destiny_dir"]
            except OSError as ex:
                aviso(_("Could not save preferences: %s") % ex)

        # Copia de lo que hay ahora mismo en pantalla
        a_renderizar = [dict(c, settings=dict(c["settings"])) for c in clips]
        print(_("Sender"),":", emisor.value, "|", _("Recipient"),":", receptor.value,
              "|", _("Language"),":", idioma_msj.value, "|", _("Own session"),":", sesion_mia.value)
        print(_("Notes:"), observacion.value)

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(_("Rendering…")),
            content=ft.Row([ft.ProgressRing(), ft.Text(_("Waiting for DaVinci Resolve…"))], spacing=16,
                           tight=True),
        ))
        page.update()  # que el diálogo se vea antes de empezar el trabajo bloqueante

        mensaje_error = await asyncio.to_thread(
            trabajo_render,
            emisor.value,
            receptor.value,
            observacion.value,
            sesion_mia.value,
            idioma_msj.value, 
            a_renderizar, 
            bool(subir_yt.value), 
            bool(apagar_pc.value))

        page.pop_dialog()
        mostrar_resultado(mensaje_error)

    def mostrar_resultado(mensaje_error):
        async def otra(e):
            page.pop_dialog()
            aplicar_config(cargar_config())
            observacion.value = ""
            apagar_pc.value = False
            mostrar_paso(0)
            await cargar_clips()

        async def cerrar(e):
            await page.window.destroy()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(_("All done!") if not mensaje_error else _("Finished with warnings")),
            content=ft.Text(mensaje_error or _("The render jobs have finished in DaVinci Resolve."),
                            color=ft.Colors.ERROR if mensaje_error else None),
            actions=[ft.FilledButton(content=_("Close app"), on_click=cerrar),
                     ft.OutlinedButton(content=_("Render another"), on_click=otra)],
        ))

    # ------------------------------------------------------ Navegación pasos
    pasos_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=48)
    texto_contador = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT)
    btn_atras = ft.OutlinedButton(content=_("Back"), on_click=lambda e: mostrar_paso(estado["paso"] - 1))
    btn_sig = ft.FilledButton(content=_("Next"), on_click=lambda e: siguiente())
    btn_enviar = ft.FilledButton(content=_("Render"), icon=ft.Icons.MOVIE_CREATION_OUTLINED,
                                 on_click=renderizar)

    def validar_paso(n):
        if n != 0:
            return True
        emisor.error_text = None if emisor.value else _("Choose an option")
        receptor.error_text = None if receptor.value else _("Choose an option")
        page.update()
        return bool(emisor.value and receptor.value)

    def siguiente():
        if validar_paso(estado["paso"]):
            mostrar_paso(estado["paso"] + 1)

    def ir_a(destino):
        if destino > estado["paso"]:
            for i in range(estado["paso"], destino):
                if not validar_paso(i):
                    mostrar_paso(i)
                    return
        mostrar_paso(destino)

    def mostrar_paso(n):
        estado["paso"] = n
        paso1.visible, paso2.visible = n == 0, n == 1
        btn_atras.visible = n > 0
        btn_sig.visible = n < len(PASOS) - 1
        btn_enviar.visible = n == len(PASOS) - 1
        texto_contador.value = _("Step %d of %d") % (n + 1, len(PASOS))
        items = []
        for i, nombre in enumerate(PASOS):
            activo, hecho = i == n, i < n
            circulo = ft.Container(
                ft.Icon(icon=ft.Icons.CHECK, size=18, color=ACENTO) if hecho
                else ft.Text(str(i + 1), weight=ft.FontWeight.BOLD,
                             color=ft.Colors.WHITE if activo else ft.Colors.ON_SURFACE_VARIANT),
                width=36, height=36, border_radius=18, alignment=ft.Alignment.CENTER,
                bgcolor=ACENTO if activo else None,
                border=ft.Border.all(2, ACENTO if (activo or hecho) else ft.Colors.OUTLINE_VARIANT),
            )
            items.append(ft.Container(
                ft.Column([circulo, ft.Text(_(nombre), weight=ft.FontWeight.W_600 if activo else None)],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                padding=6, border_radius=10, ink=True, on_click=lambda e, i=i: ir_a(i)))
        pasos_row.controls = items
        page.update()

    # ----------------------------------------------------------- Cabecera/tema
    boton_tema = ft.IconButton(icon=ft.Icons.DARK_MODE_OUTLINED, icon_color=ft.Colors.WHITE,
                               tooltip=_("Switch to dark mode"))

    def cambiar_tema(e):
        oscuro = page.theme_mode == ft.ThemeMode.DARK
        page.theme_mode = ft.ThemeMode.LIGHT if oscuro else ft.ThemeMode.DARK
        boton_tema.icon = ft.Icons.DARK_MODE_OUTLINED if oscuro else ft.Icons.LIGHT_MODE_OUTLINED
        boton_tema.tooltip = _("Switch to dark mode") if oscuro else _("Switch to light mode")
        page.update()

    boton_tema.on_click = cambiar_tema

    # ----------------------------------------------------------- Cebecera/idioma
    idioma = idioma_activo()
    print(idioma)
    select_lang = ft.Dropdown(value=idioma,
                             options=[ft.DropdownOption(key=k, text=v) for k, v in IDIOMAS],
                             color=ft.Colors.WHITE,
                             border_color=ft.Colors.WHITE,
                             bgcolor=ft.Colors.WHITE,
                             fill_color=ft.Colors.WHITE
                            #  border=ft.BorderSide(color=ft.Colors.WHITE)
                             )

    titulo_principal = ft.Text(_("Video processing"), size=28,
                               weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
    subtitulo_principal = ft.Text(_("Form to simplify %s.") % _("Video processing").lower(),
                                  color=ft.Colors.WHITE_70)

    async def change_language(e: ft.ControlEvent):
        """Cambia el catalogo y actualiza los textos ya creados."""
        anterior, nuevo = aplicar_idioma(e.control.value)
        traducir_arbol(page, anterior, nuevo)

        # Estos dos llevan formato, asi que el arbol no puede reconstruirlos.
        titulo_principal.value = _("Video processing")
        subtitulo_principal.value = _("Form to simplify %s.") % _("Video processing").lower()

        # Reconstruye contadores, nombres de paso y metadatos de clips.
        pintar_clips()
        mostrar_paso(estado["paso"])
        page.update()

    select_lang.on_select = change_language

    

    cabecera = ft.Container(
        ft.Row(
            [
                ft.Column([
                    titulo_principal,
                    subtitulo_principal,
                ], spacing=4, expand=True),
                select_lang,
                boton_tema,
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        bgcolor=ACENTO, padding=ft.Padding.symmetric(horizontal=32, vertical=28),
    )

    pie = ft.Container(
        ft.Row([texto_contador, ft.Row([btn_atras, btn_sig, btn_enviar])],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=ft.Padding.symmetric(horizontal=32, vertical=16),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )

    # Tarjeta redondeada con tamaño fijo.
    tarjeta = ft.Container(
        content=ft.Column(
            [
                cabecera,
                ft.Container(pasos_row, padding=ft.Padding.symmetric(vertical=18)),
                ft.Divider(height=1),
                ft.Container(ft.Column([paso1, paso2], scroll=ft.ScrollMode.AUTO),
                             padding=ft.Padding.symmetric(horizontal=32, vertical=20), expand=True),
                pie,
            ],
            spacing=0, expand=True,
        ),
        width=ANCHO_TARJETA,
        height=ALTO_TARJETA,
        bgcolor=ft.Colors.SURFACE,
        border_radius=16,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        shadow=ft.BoxShadow(blur_radius=40, color=ft.Colors.BLACK_26, offset=ft.Offset(0, 12)),
    )
    marco = ft.Container(tarjeta, alignment=ft.Alignment.CENTER, expand=True,
                         padding=MARGEN)

    def adaptar(e=None):
        """Tarjeta de tamaño fijo si cabe; si la ventana es pequeña, se encoge con ella."""
        ancho_v = page.width or page.window.width or ANCHO_TARJETA + 2 * MARGEN
        alto_v = page.height or page.window.height or ALTO_TARJETA + 2 * MARGEN
        compacta = ancho_v < VENTANA_COMPACTA
        margen = 0 if compacta else MARGEN
        marco.padding = margen
        tarjeta.width = max(280, min(ANCHO_TARJETA, ancho_v - 2 * margen))
        tarjeta.height = max(360, min(ALTO_TARJETA, alto_v - 2 * margen))
        tarjeta.border_radius = 0 if compacta else 16
        page.update()

    page.on_resize = adaptar
    page.add(marco)
    adaptar()

    aplicar_config(cargar_config())
    mostrar_paso(0)
    await cargar_clips()


if __name__ == "__main__":
    ft.run(main)