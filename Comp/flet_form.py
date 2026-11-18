"""
Formulario de procesamiento de vídeo con Flet 1.x (equivalente a form.py + formulario.html).

Requisitos:   pip install -U flet
Ejecutar:     python app_flet.py
Debe estar junto a test.py y upload_video.py (se reutilizan tal cual).
"""
import asyncio
import os
import sys
from dataclasses import asdict
from pathlib import Path

# --- Bootstrap del API de scripts de Resolve (igual que en form.py) ---------
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
from test import (
    get_clips, create_render_jobs, render_jobs, settings,
    init_davinci_project, delete_all_jobs, show_render_prev,
)
from upload_video import upload_video

PERSONAS = ["Laura", "Juan", "María", "Pedro"]
IDIOMAS = [("es", "Español"), ("ca", "Català"), ("en", "English")]
PASOS = ["Notificación", "Procesamiento"]
ACENTO = "#1f6f8b"

# Tarjeta del formulario: tamaño fijo en ventanas grandes, se encoge en las pequeñas
ANCHO_TARJETA = 760
ALTO_TARJETA = 780
MARGEN = 24            # espacio entre la tarjeta y el borde de la ventana
VENTANA_COMPACTA = 600  # por debajo de este ancho la tarjeta ocupa toda la ventana

EXTENSIONES_IMG = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


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


def leer_resolve() -> list[dict]:
    """Equivalente a la ruta GET / de Flask."""
    init_davinci_project()
    delete_all_jobs()
    grupos = get_clips()
    show_render_prev(grupos)
    return [
        {
            **asdict(g),
            "thumbnail": b"",   # bytes de la imagen elegida
            "settings": {
                **settings,
                "MarkIn": g.start,
                "MarkOut": g.end,
                "CustomName": g.title,
            },
        }
        for g in grupos
    ]


def trabajo_render(a_renderizar, subir_youtube, apagar_pc) -> str:
    """Renderiza, sube y (opcional) apaga. Devuelve un mensaje de error o ''."""
    mensaje = ""
    try:
        jobs = create_render_jobs(a_renderizar)
        ok = bool(jobs) and render_jobs(jobs)  # BLOQUEA hasta terminar
        if not ok:
            return "El render no terminó correctamente."
        if subir_youtube:
            for c in a_renderizar:
                s = c["settings"]
                nombre = s.get("CustomName") or c["title"]
                ruta = ruta_render(s.get("TargetDir", ""), nombre)
                if ruta is None:
                    print(f"No encuentro el vídeo renderizado de «{c['title']}»")
                    mensaje = "Algún vídeo renderizado no se encontró para subirlo."
                    continue
                upload_video(
                    str(ruta), c["title"], "", "UNLISTED",
                    miniatura=c["thumbnail"] or None,
                )
        if apagar_pc:
            os.system("shutdown /s /t 60")  # cancelar con: shutdown /a
    except Exception as ex:
        mensaje = f"Error: {ex}"
    return mensaje


# ---------------------------------------------------------------------------
async def main(page: ft.Page):
    page.title = "Procesamiento de video"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ACENTO)
    page.dark_theme = ft.Theme(color_scheme_seed=ACENTO)
    page.padding = 0
    page.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGHEST
    page.window.width = 1100
    page.window.height = 900

    clips: list[dict] = []
    estado = {"paso": 0}
    selector = ft.FilePicker()  # servicio: se mantiene la referencia

    # ------------------------------------------------------------------ Paso 1
    emisor = ft.Dropdown(label="Emisor", expand=True,
                         options=[ft.DropdownOption(key=p, text=p) for p in PERSONAS])
    receptor = ft.Dropdown(label="Receptor", expand=True,
                           options=[ft.DropdownOption(key=p, text=p) for p in PERSONAS])
    observacion = ft.TextField(label="Observación", multiline=True, min_lines=4, max_lines=6)
    sesion_mia = ft.Checkbox(label="La sesión me pertenece.")
    idioma_msj = ft.Dropdown(label="Idioma del mensaje", value="es",
                             options=[ft.DropdownOption(key=k, text=v) for k, v in IDIOMAS])

    paso1 = ft.Column(
        [
            ft.Text("Notificación", size=20, weight=ft.FontWeight.BOLD),
            ft.Text("Especifica tu nombre como emisor y a quién se dirige la notificación. "
                    "El mensaje se enviará a través de WhatsApp.",
                    color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row([emisor, receptor]),
            observacion,
            sesion_mia,
            idioma_msj,
        ],
        spacing=16,
    )

    # ------------------------------------------------------------------ Paso 2
    subir_yt = ft.Checkbox(label="Subir directo a YouTube")
    apagar_pc = ft.Checkbox(label="Apagar PC al terminar (60 s de margen)")
    lista = ft.Column(spacing=10)
    contador_clips = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT, size=13)
    lista_vacia = ft.Text("No queda ningún clip en la lista.", visible=False,
                          text_align=ft.TextAlign.CENTER)
    error_carga = ft.Text(color=ft.Colors.ERROR, visible=False)

    paso2 = ft.Column(
        [
            ft.Text("Procesamiento", size=20, weight=ft.FontWeight.BOLD),
            ft.Text("Aquí se muestran los clips que se procesarán y se pueden modificar "
                    "sus propiedades.", color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row([subir_yt, apagar_pc], wrap=True),
            ft.Row([ft.Text("Clips detectados", weight=ft.FontWeight.W_600), contador_clips],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            error_carga,
            lista,
            lista_vacia,
            ft.Text("Haz clic en la miniatura o en el título para cambiarlos. El lápiz abre "
                    "las propiedades del render y la ✕ descarta el grupo de clips.",
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

    async def cargar_clips():
        clips.clear()
        error_carga.visible = False
        try:
            clips.extend(await asyncio.to_thread(leer_resolve))
        except BaseException as ex:  # init_davinci_project puede llamar a exit(0)
            error_carga.value = f"No se pudo leer DaVinci Resolve: {ex or 'sin conexión'}"
            error_carga.visible = True
        pintar_clips()

    # ---------------------------------------------------------- Lista de clips
    def pintar_clips():
        lista.controls = [crear_item(c) for c in clips]
        total = sum(max(0, c["end"] - c["start"]) for c in clips)
        contador_clips.value = (f"{len(clips)} clip{'s' if len(clips) != 1 else ''} · {total} fotogramas"
                                if clips else "Sin clips")
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
            tooltip="Cambiar miniatura", ink=True, on_click=al_clic,
        )

    def crear_item(clip):
        s = clip["settings"]
        frames = max(0, clip["end"] - clip["start"])
        titulo = ft.TextButton(
            content=clip["title"], tooltip="Haz clic para cambiar el título",
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=4, vertical=0)),
        )
        meta = ft.Text(f"{clip['start']} – {clip['end']} · {frames} fotogramas · "
                       f"{s['FormatWidth']}×{s['FormatHeight']}",
                       size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        datos = ft.Column([titulo, meta], spacing=2, expand=True)
        titulo.on_click = lambda e, c=clip, col=datos: editar_titulo(c, col)

        return ft.Container(
            ft.Row(
                [
                    miniatura(clip),
                    datos,
                    ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip="Propiedades del render",
                                  on_click=lambda e, c=clip: abrir_ajustes(c)),
                    ft.IconButton(icon=ft.Icons.CLOSE, tooltip="Descartar el grupo de clips",
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

        aviso(f"«{clip['title']}» descartado del render.", "Deshacer", deshacer)

    # ----------------------------------------------------- Diálogo: miniatura
    async def abrir_miniatura(clip):
        elegida = {"bytes": b""}
        error = ft.Text(color=ft.Colors.ERROR, visible=False, size=12)
        nombre = ft.Text("Ningún archivo seleccionado", size=12,
                         color=ft.Colors.ON_SURFACE_VARIANT)

        def caja(contenido):
            return ft.Container(
                contenido, width=200, height=112, border_radius=8,
                alignment=ft.Alignment.CENTER,
                border=ft.Border.all(1.5, ft.Colors.OUTLINE_VARIANT),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )

        sin_imagen = lambda: ft.Text("Sin imagen", size=12)
        actual = caja(ft.Image(src=clip["thumbnail"], fit=ft.BoxFit.COVER, width=200, height=112)
                      if clip["thumbnail"] else sin_imagen())
        nueva = caja(sin_imagen())
        todos = ft.Checkbox(label=f"Aplicar a todos los clips ({len(clips)})")

        async def elegir(e):
            archivos = await selector.pick_files(
                file_type=ft.FilePickerFileType.IMAGE, allow_multiple=False)
            error.visible = False
            elegida["bytes"] = b""
            nueva.content = sin_imagen()
            if archivos:
                ruta = Path(archivos[0].path) if archivos[0].path else None
                if ruta is None or ruta.suffix.lower() not in EXTENSIONES_IMG:
                    error.value, error.visible = "El archivo debe ser una imagen.", True
                elif ruta.stat().st_size > 2 * 1024 * 1024:
                    error.value, error.visible = "La imagen es demasiado grande (máximo 2 MB).", True
                else:
                    elegida["bytes"] = ruta.read_bytes()
                    nombre.value = ruta.name
                    nueva.content = ft.Image(src=elegida["bytes"], fit=ft.BoxFit.COVER,
                                             width=200, height=112)
            page.update()

        def aplicar(e):
            if not elegida["bytes"]:
                error.value, error.visible = "Elige una imagen antes de aplicar los cambios.", True
                page.update()
                return
            destinos = list(clips) if todos.value else [clip]
            anteriores = [c["thumbnail"] for c in destinos]
            for c in destinos:
                c["thumbnail"] = elegida["bytes"]
            page.pop_dialog()
            pintar_clips()

            def deshacer():
                for c, t in zip(destinos, anteriores):
                    c["thumbnail"] = t
                pintar_clips()

            aviso(f"Miniatura aplicada a {len(destinos)} clips." if len(destinos) > 1
                  else "Miniatura actualizada.", "Deshacer", deshacer)

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Cambiar miniatura"),
            content=ft.Column(
                [
                    ft.Text(f"«{clip['title']}»", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Row([ft.Column([ft.Text("Actual", weight=ft.FontWeight.W_600), actual]),
                            ft.Column([ft.Text("Nueva", weight=ft.FontWeight.W_600), nueva])],
                           spacing=16),
                    ft.Row([ft.Button(content="Elegir imagen…", icon=ft.Icons.IMAGE_OUTLINED,
                                      on_click=elegir), nombre]),
                    ft.Text("YouTube exige al menos 1280×720 px y un máximo de 2 MB.",
                            size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    todos,
                    error,
                ],
                tight=True, spacing=12, width=440,
            ),
            actions=[ft.TextButton(content="Cancelar", on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton(content="Aplicar", on_click=aplicar)],
        ))

    # ------------------------------------------------ Diálogo: propiedades
    def abrir_ajustes(clip):
        s = clip["settings"]
        nombre = ft.TextField(label="Nombre del archivo", value=s.get("CustomName") or clip["title"],
                              max_length=120)
        ancho = ft.TextField(label="Anchura (px)", value=str(s["FormatWidth"]),
                             keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        alto = ft.TextField(label="Altura (px)", value=str(s["FormatHeight"]),
                            keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        carpeta = ft.TextField(label="Carpeta de destino", value=s.get("TargetDir", ""))
        todos = ft.Checkbox(label="Renderizar el clip completo", value=bool(s.get("SelectAllFrames")))
        f_in = ft.TextField(label="Fotograma inicial", value=str(s["MarkIn"]),
                            keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        f_out = ft.TextField(label="Fotograma final", value=str(s["MarkOut"]),
                             keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        video = ft.Checkbox(label="Exportar video", value=s.get("ExportVideo", True) is not False)
        audio = ft.Checkbox(label="Exportar audio", value=s.get("ExportAudio", True) is not False)
        duracion = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        def entero(campo, defecto):
            try:
                return int(float(campo.value))
            except (TypeError, ValueError):
                return defecto

        def refrescar(e=None):
            f_in.disabled = f_out.disabled = bool(todos.value)
            if todos.value:
                duracion.value = "Se renderizará el clip completo, sin marcas de entrada y salida."
            else:
                total = entero(f_out, 0) - entero(f_in, 0)
                duracion.value = (f"Duración: {total} fotogramas." if total > 0
                                  else "El fotograma final debe ser mayor que el inicial.")
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
                nombre.error_text, ok = "Obligatorio", False
            if w < 2:
                ancho.error_text, ok = "Mínimo 2", False
            if h < 2:
                alto.error_text, ok = "Mínimo 2", False
            if not todos.value and fin <= inicio:
                f_out.error_text, ok = "Debe ser mayor que el inicial", False
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
            page.pop_dialog()
            pintar_clips()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Column([ft.Text("Propiedades del render"),
                             ft.Text(f"«{clip['title']}» · {clip['start']} – {clip['end']} fotogramas",
                                     size=12, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=2),
            content=ft.Column(
                [nombre, ft.Row([ancho, alto]), carpeta, todos, ft.Row([f_in, f_out]),
                 duracion, video, audio],
                tight=True, spacing=12, width=480, scroll=ft.ScrollMode.AUTO,
            ),
            actions=[ft.TextButton(content="Cancelar", on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton(content="Guardar cambios", on_click=guardar)],
        ))
        refrescar()

    # ---------------------------------------------------------------- Render
    async def renderizar(e):
        if not validar_paso(0):
            mostrar_paso(0)
            return
        if not clips:
            aviso("No hay clips que renderizar.")
            return

        # Copia de lo que hay ahora mismo en pantalla
        a_renderizar = [dict(c, settings=dict(c["settings"])) for c in clips]
        print("Emisor:", emisor.value, "| Receptor:", receptor.value,
              "| Idioma:", idioma_msj.value, "| Mía:", sesion_mia.value)
        print("Observación:", observacion.value)

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Renderizando…"),
            content=ft.Row([ft.ProgressRing(), ft.Text("Esperando a DaVinci Resolve…")], spacing=16,
                           tight=True),
        ))
        page.update()  # que el diálogo se vea antes de empezar el trabajo bloqueante

        mensaje_error = await asyncio.to_thread(
            trabajo_render, a_renderizar, bool(subir_yt.value), bool(apagar_pc.value))

        page.pop_dialog()
        mostrar_resultado(mensaje_error)

    def mostrar_resultado(mensaje_error):
        async def otra(e):
            page.pop_dialog()
            emisor.value = receptor.value = None
            observacion.value = ""
            sesion_mia.value = subir_yt.value = apagar_pc.value = False
            idioma_msj.value = "es"
            mostrar_paso(0)
            await cargar_clips()

        async def cerrar(e):
            await page.window.destroy()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("¡Todo listo!" if not mensaje_error else "Terminado con avisos"),
            content=ft.Text(mensaje_error or "Los trabajos de renderizado han terminado en DaVinci Resolve.",
                            color=ft.Colors.ERROR if mensaje_error else None),
            actions=[ft.FilledButton(content="Cerrar aplicación", on_click=cerrar),
                     ft.OutlinedButton(content="Renderizar otro", on_click=otra)],
        ))

    # ------------------------------------------------------ Navegación pasos
    pasos_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=48)
    texto_contador = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT)
    btn_atras = ft.OutlinedButton(content="Atrás", on_click=lambda e: mostrar_paso(estado["paso"] - 1))
    btn_sig = ft.FilledButton(content="Siguiente", on_click=lambda e: siguiente())
    btn_enviar = ft.FilledButton(content="Renderizar", icon=ft.Icons.MOVIE_CREATION_OUTLINED,
                                 on_click=renderizar)

    def validar_paso(n):
        if n != 0:
            return True
        emisor.error_text = None if emisor.value else "Elige una opción"
        receptor.error_text = None if receptor.value else "Elige una opción"
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
        texto_contador.value = f"Paso {n + 1} de {len(PASOS)}"
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
                ft.Column([circulo, ft.Text(nombre, weight=ft.FontWeight.W_600 if activo else None)],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                padding=6, border_radius=10, ink=True, on_click=lambda e, i=i: ir_a(i)))
        pasos_row.controls = items
        page.update()

    # ----------------------------------------------------------- Cabecera/tema
    boton_tema = ft.IconButton(icon=ft.Icons.DARK_MODE_OUTLINED, icon_color=ft.Colors.WHITE,
                               tooltip="Cambiar a modo oscuro")

    def cambiar_tema(e):
        oscuro = page.theme_mode == ft.ThemeMode.DARK
        page.theme_mode = ft.ThemeMode.LIGHT if oscuro else ft.ThemeMode.DARK
        boton_tema.icon = ft.Icons.DARK_MODE_OUTLINED if oscuro else ft.Icons.LIGHT_MODE_OUTLINED
        boton_tema.tooltip = "Cambiar a modo oscuro" if oscuro else "Cambiar a modo claro"
        page.update()

    boton_tema.on_click = cambiar_tema

    cabecera = ft.Container(
        ft.Row(
            [
                ft.Column([
                    ft.Text("Procesamiento de video", size=28, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE),
                    ft.Text("Formulario para facilitar el procesamiento de videos.",
                            color=ft.Colors.WHITE_70),
                ], spacing=4, expand=True),
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

    # Tarjeta redondeada con tamaño fijo, como un formulario de login
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

    mostrar_paso(0)
    await cargar_clips()


if __name__ == "__main__":
    ft.run(main)