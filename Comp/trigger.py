"""
Lanzador del servidor del formulario.

Se ejecuta DENTRO de DaVinci Resolve (Workspace > Scripts > Comp > trigger) y
arranca `flet_form.py` como proceso EXTERNO con el Python del .venv, que sí tiene
Flask, Playwright y acceso al API de Resolve.

Así el formulario corre fuera del entorno embebido de Resolve, pero se sigue
lanzando con una tecla desde dentro de Resolve.

Importante: este archivo solo usa la librería estándar, porque lo ejecuta el
Python embebido de Resolve (que no tiene Flask ni Playwright).
"""

import http.client
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
PORT = 5050
URL = f"http://{HOST}:{PORT}/"

# Rutas del API de scripts de Resolve (Windows, instalación por defecto).
# Se pueden sobreescribir con las variables de entorno del mismo nombre.
RESOLVE_SCRIPT_API = Path(os.environ.get(
    "RESOLVE_SCRIPT_API",
    r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting",
))
RESOLVE_SCRIPT_LIB = os.environ.get(
    "RESOLVE_SCRIPT_LIB",
    r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll",
)


def _carpeta_comp() -> Path:
    """Carpeta donde vive este trigger (Comp), aunque no exista __file__."""
    candidatos = []
    if "__file__" in globals():
        candidatos.append(globals()["__file__"])
    if sys.argv:
        candidatos.append(sys.argv[0])

    for candidato in candidatos:
        if not candidato:
            continue
        carpeta = Path(candidato).resolve().parent
        # Comprobamos que de verdad es la carpeta del proyecto.
        if (carpeta / "flet_form.py").is_file():
            return carpeta
        # Si trigger.py está en Utility/Edit/..., Comp es una carpeta hermana.
        hermana = carpeta.parent / "Comp"
        if (hermana / "flet_form.py").is_file():
            return hermana

    # Último recurso: ruta conocida del proyecto.
    return Path(os.path.expanduser(
        r"~\AppData\Roaming\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Comp"
    ))


COMP = _carpeta_comp()
RAIZ = COMP.parent
PYTHONW = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
FORM = COMP / "flet_form.py"
LOG = COMP / "form.log"


def servidor_activo(timeout: float = 0.25) -> bool:
    """True si ya hay un servidor HTTP escuchando en el puerto del formulario.

    Se consulta /health (una ruta trivial) para no ejecutar la ruta principal,
    que abre el proyecto de Resolve y recorre la timeline.
    """
    try:
        conexion = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
        try:
            conexion.request("GET", "/health")
            respuesta = conexion.getresponse()
            respuesta.read()
            # Solo cuenta como servidor nuestro si responde 200 en /health.
            # Un servidor antiguo (sin esa ruta) devuelve 404 y hay que reiniciarlo.
            return respuesta.status == 200
        finally:
            conexion.close()
    except OSError:
        return False


def puerto_en_uso() -> bool:
    """True si algo está escuchando en el puerto del formulario."""
    sonda = socket.socket()
    sonda.settimeout(0.25)
    try:
        sonda.connect((HOST, PORT))
        return True
    except OSError:
        return False
    finally:
        sonda.close()


def abrir_navegador() -> None:
    try:
        if webbrowser.open(URL, new=2):
            return
    except Exception:
        pass
    try:
        os.startfile(URL)  # type: ignore[attr-defined]
    except Exception:
        pass


def arrancar_servidor() -> None:
    """Lanza flet_form.py con el Python del .venv, desacoplado de Resolve."""
    entorno = os.environ.copy()
    entorno["RESOLVE_SCRIPT_API"] = str(RESOLVE_SCRIPT_API)
    entorno["RESOLVE_SCRIPT_LIB"] = str(RESOLVE_SCRIPT_LIB)
    modulos = str(RESOLVE_SCRIPT_API / "Modules")
    entorno["PYTHONPATH"] = modulos + os.pathsep + entorno.get("PYTHONPATH", "")
    # El navegador lo abre este trigger; flet_form.py no debe abrir otra pestaña.
    entorno["FORM_ABRIR_NAVEGADOR"] = "0"

    flags = 0
    if os.name == "nt":
        flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )

    with open(LOG, "a", encoding="utf-8") as log:
        subprocess.Popen(
            [str(PYTHONW), str(FORM)],
            cwd=str(COMP),
            env=entorno,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            close_fds=True,
        )


def main() -> None:
    # Si el servidor ya está en marcha, solo abrimos el formulario.
    if servidor_activo():
        print("El servidor ya estaba en marcha. Abriendo el formulario...")
        abrir_navegador()
        return

    if puerto_en_uso():
        raise RuntimeError(
            f"El puerto {PORT} está ocupado por un servidor antiguo. "
            "Ciérralo (pythonw.exe con flet_form.py en el Administrador de tareas) "
            "y vuelve a lanzar el trigger."
        )

    if not PYTHONW.is_file():
        raise FileNotFoundError(f"No existe el Python del entorno virtual: {PYTHONW}")
    if not FORM.is_file():
        raise FileNotFoundError(f"No existe flet_form.py: {FORM}")

    print("Arrancando el servidor del formulario...")
    arrancar_servidor()

    # Esperar a que Flask abra el puerto (máximo 20 s).
    for _ in range(200):
        if servidor_activo(0.2):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError(
            "El servidor no respondió en 20 s. Revisa el log: " + str(LOG)
        )

    abrir_navegador()


# Resolve ejecuta el script tal cual: llamamos a main() sin depender de __name__.
# (La variable TRIGGER_SOLO_DEFINICIONES permite importar el módulo para probarlo.)
if os.environ.get("TRIGGER_SOLO_DEFINICIONES") != "1":
    main()

