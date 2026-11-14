
from dataclasses import asdict
import json
from pathlib import Path

from flask import Flask,render_template, request
import webbrowser
from test import get_clips, create_render_jobs, render_jobs, settings, init_davinci_project, delete_all_jobs, delete_render_job, show_render_prev
from upload_video import upload_video
import DaVinciResolveScript as dvr_script 

# 1. Crear la instancia de la aplicación
app = Flask(__name__)

clips, groups, jobs_ids = [], [], []


def ruta_render(carpeta, nombre):
    """Localiza el archivo que DaVinci ha renderizado en `carpeta`.

    Resolve añade la extensión según el formato (.mp4, .mov...), así que
    buscamos por el nombre sin extensión en lugar de componer la ruta a mano.
    Si hay varios, devuelve el más reciente."""
    base = Path(carpeta)
    if not base.is_dir():
        return None
    candidatos = [
        archivo for archivo in base.iterdir()
        if archivo.is_file() and archivo.stem == nombre
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda a: a.stat().st_mtime)

@app.post('/submit')
def process_data():
    nombre = request.form.get('Emisor')
    apellidos = request.form.get('Receptor')
    sesion = request.form.getlist('sesion')  # Obtener todas las opciones seleccionadas


    # Aquí puedes procesar los datos según tus necesidades
    print("Nombre:", nombre)
    print("Apellidos:", apellidos)
    print("Opciones seleccionadas:", sesion)
    # Puedes redirigir a otra página o mostrar un mensaje de éxito

    clips = json.loads(request.form.get('clips_json') or "[]")
    jobs_ids = create_render_jobs(clips)

    # render_jobs ahora BLOQUEA hasta que todas las tareas terminan.
    # Solo subimos si de verdad acabaron bien: si no, el archivo no existe.
    render_ok = render_jobs(jobs_ids)

    if 'UploadYouTube' in sesion:
        if not render_ok:
            print("El render no terminó correctamente: no se sube nada a YouTube")
        else:
            for clip in clips:
                titulo = clip["title"]                    # el título nuevo
                s = clip["settings"]                      # CustomName, TargetDir, MarkIn...
                nombre = s.get("CustomName") or titulo

                ruta = ruta_render(s.get("TargetDir", ""), nombre)
                if ruta is None:
                    print(f"No encuentro el vídeo renderizado de «{titulo}» en {s.get('TargetDir')}")
                    continue

                upload_video(str(ruta), titulo, "", "UNLISTED")

    return "Formulario enviado con éxito"

# 2. Definir la ruta principal (página de inicio)
@app.get('/')
def render_form():
    # person2 = {'name': 'John', 'age': 25}  # Example person data

    init_davinci_project()  
    delete_all_jobs()  # Eliminar todas las tareas de renderizado antes de crear nuevas
    groups = get_clips()
    show_render_prev(groups)

    # Clips que se muestran (y se pueden editar) en el paso 2 del formulario
    clips_data = [
        {
            **asdict(group),
            "settings": {
                **settings,
                "MarkIn": group.start,
                "MarkOut": group.end,
                "CustomName": group.title,
            },
        }
        for group in groups
    ]
    return render_template('formulario.html', clips=clips_data)


# 3. Ejecutar el servidor si el archivo se corre directamente.
if __name__ == "__main__":
    # webbrowser.open("http://localhost:5000/")  # Abrir automáticamente en el navegador
    app.run(debug=True)
