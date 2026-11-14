import time
from tokenize import group

import DaVinciResolveScript as dvr_script 
from dataclasses import dataclass

# Conectarse a DaVinci Resolve
resolve, project_manager, project = None, None, None
fps = 0.0

from dataclasses import dataclass

@dataclass
class Clip:
    title: str = ""
    start: int = 0
    end: int = 0
    thumbnail: str = ""

# Configurar renderizado
settings = {
    "SelectAllFrames": False,
    "MarkIn": 0,
    "MarkOut": 0,
    "TargetDir": "C:\\Users\\denis\\Desktop\\videos pendientes",
    "CustomName": "Mi_video",
    "ExportVideo": True,
    "ExportAudio": True,
    "FormatWidth": 1920,
    "FormatHeight": 1080
}

allowed_time_separation, min_duration_frames = 5, 5  # segundos

# if resolve is None:
#     print("No se pudo conectar con DaVinci Resolve")
#     exit(0)
# else:
#     print("Conexión establecida correctamente")

def init_davinci_project():
    """Inicializar el proyecto de DaVinci Resolve"""
    global project, fps
    
    resolve = dvr_script.scriptapp("Resolve")
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject()
    fps = float(project.GetSetting("timelineFrameRate"))
    
    if resolve is None:
        print("No se pudo conectar con DaVinci Resolve")
        exit(0)
    if not project:
        raise RuntimeError("No hay ningún proyecto abierto en DaVinci Resolve.")


# def _log(s):
#     print('\n\n')
#     print("\n".join(s))

def delete_all_jobs():
    """Eliminar todas las tareas de renderizado"""
    project.DeleteAllRenderJobs();

def delete_render_job(job_id):
    """Eliminar una tarea de renderizado específica"""
    project.DeleteRenderJob(job_id)

def sec(frames):
    """Convert data in frames to Seconds"""
    seconds = (frames) / fps 
    return f"{seconds:.2f}"



# # Obtener el gestor de proyectos
# project_manager = resolve.GetProjectManager()

# # Obtener el proyecto actual
# project = project_manager.GetCurrentProject()



    # resu = []
    # for clip in clips:
    #     resu += "Clip de video: " + clip.GetName()
    #     resu += " - Duración: " + str(clip.GetDuration()) + " frames"
    #     resu += " - Start: " + str(clip.GetStart()) + " frames"
    #     resu += " - End: " + str(clip.GetEnd()) + " frames"

    # pr(resu)

def _nombre_dominante(miembros) -> str:
    """Nombre que da título al grupo.

    Se suma la duración de todos los clips que comparten el mismo nombre
    (un clip recortado en trozos conserva su nombre) y gana el nombre con
    más duración acumulada. Si hay empate, el que aparece antes."""
    totales, orden = {}, {}
    for i, clip in enumerate(miembros):
        nombre = clip.GetName()
        totales[nombre] = totales.get(nombre, 0) + (clip.GetEnd() - clip.GetStart())
        orden.setdefault(nombre, i)
    return max(totales, key=lambda n: (totales[n], -orden[n]))


def _grupo_desde_miembros(miembros) -> Clip:
    """Resume un grupo de clips contiguos en un solo Clip: abarca de la
    primera a la última y toma el nombre dominante del grupo."""
    return Clip(
        title=_nombre_dominante(miembros),
        start=min(c.GetStart() for c in miembros),
        end=max(c.GetEnd() for c in miembros),
    )


def get_clips() -> list:
    timeline = project.GetCurrentTimeline()
    clips = timeline.GetItemListInTrack("video", 1)

    if not clips:
        return []

    # Ordenar cronológicamente
    clips = sorted(clips, key=lambda c: c.GetStart())

    allowed_frames = allowed_time_separation * fps

    # Agrupar clips separados por menos de `allowed_time_separation` segundos
    grupos, actual = [], [clips[0]]
    fin = clips[0].GetEnd()

    for clip in clips[1:]:
        if clip.GetStart() - fin <= allowed_frames:
            # Pertenece al mismo grupo
            actual.append(clip)
            fin = max(fin, clip.GetEnd())
        else:
            # Guardar el grupo anterior y empezar uno nuevo
            grupos.append(actual)
            actual, fin = [clip], clip.GetEnd()

    # Guardar el último grupo
    grupos.append(actual)

    return [_grupo_desde_miembros(miembros) for miembros in grupos]

# Crear tareas de renderizado

def show_render_prev(groups) -> list:
    usados = {}  # nombres finales ya asignados, para no sobreescribir renders

    for group in groups:

        duration = group.end - group.start
        print(sec(duration));

        # Ignorar grupos de 5 segundos o menos
        if float(sec(duration)) < min_duration_frames:
            print(f"Ignorado: {group.title} ({duration / fps:.2f} segundos)")
            groups.remove(group)
            continue

        group.title = establish_title(group.title)

        # Nombres únicos: si dos grupos acaban con el mismo nombre, el segundo
        # render sobreescribiría al primero. Se añade un sufijo.
        usados[group.title] = usados.get(group.title, 0) + 1
        if usados[group.title] > 1:
            group.title = f"{group.title} ({usados[group.title]})"


def create_render_jobs(clips) -> list:
    job_ids = []

    for clip in clips:
        if project.SetRenderSettings(clip["settings"]):

            job_id = project.AddRenderJob()
            job_ids.append(job_id)
            print(
                f"Tarea añadida: {job_id} | "
                f"{clip['title']} | "
                f"{(clip['end'] - clip['start']) / fps:.2f} segundos"
            )
        else:
            print("Error configurando el renderizado")
            return

    return job_ids
            

def render_jobs(job_ids) -> bool:
    """Inicia el render y espera a que terminen TODAS las tareas.

    Devuelve True solo si todas acabaron en 'Complete'. Hay que esperar aquí
    antes de subir los vídeos, porque si no el archivo aún no existe."""
    if not job_ids:
        print("No hay tareas de renderizado")
        return False

    if not project.StartRendering():
        print("No se pudo iniciar el renderizado")
        return False

    finalizados = {"Complete", "Failed", "Cancelled"}

    while True:
        estados = {}
        for job_id in job_ids:
            info = project.GetRenderJobStatus(job_id) or {}
            estados[job_id] = info.get("JobStatus", "Unknown")

        # Seguimos esperando mientras quede alguna tarea en marcha
        if all(estado in finalizados for estado in estados.values()):
            fallidos = {j: e for j, e in estados.items() if e != "Complete"}
            if fallidos:
                print(f"Tareas no completadas: {fallidos}")
                return False
            print("finalizado")
            return True

        time.sleep(2)

def establish_title(title) -> str:
    """Establecer titulo con formato A&ODDMMYYYY{AM/PM}"""
    import re 

    # Expresión regular estricta: valida meses (01-12), días (01-31), horas (00-23), minutos y segundos (00-59)
    patron = re.compile(
        r"^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])([01]\d|2[0-3])[0-5]\d[0-5]\d\.[A-Za-z0-9]+$"
    )
    if patron.fullmatch(title) is None:
        print(f"El título '{title}' no cumple con el formato esperado.")
        return title
    
    year = title[:4]
    month = title[4:6]
    day = title[6:8]

    hour = title[8:10]

    day_moment = "" 
    if int(hour) < 17:
        day_moment = "AM"
    else:
        day_moment = "PM"

    return f"A&O{day}{month}{year}{day_moment}"


    # clips = timeline.GetItemListInTrack("audio", 1)

    # if project:
    #     print("Proyecto actual:", project.GetName())
    # else:
    #     print("No hay ningún proyecto abierto")

if __name__ == "__main__":
    groups = get_clips()
    job_ids = create_render_jobs(groups)
    render_jobs(job_ids)
