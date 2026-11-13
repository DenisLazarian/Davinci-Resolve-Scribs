import time

import DaVinciResolveScript as dvr_script 
# from DaVinciResolveScript import RenderSettings
from dataclasses import dataclass

# Conectarse a DaVinci Resolve
resolve = dvr_script.scriptapp("Resolve")

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

if resolve is None:
    print("No se pudo conectar con DaVinci Resolve")
    exit(0)
else:
    print("Conexión establecida correctamente")


# def _log(s):
#     print('\n\n')
#     print("\n".join(s))

def sec(frames):
    """Convert data in frames to Seconds"""
    fps = float(project.GetSetting("timelineFrameRate"))
    seconds = (frames) / fps 
    return f"{seconds:.2f}"



# Obtener el gestor de proyectos
project_manager = resolve.GetProjectManager()

# Obtener el proyecto actual
project = project_manager.GetCurrentProject()



    # resu = []
    # for clip in clips:
    #     resu += "Clip de video: " + clip.GetName()
    #     resu += " - Duración: " + str(clip.GetDuration()) + " frames"
    #     resu += " - Start: " + str(clip.GetStart()) + " frames"
    #     resu += " - End: " + str(clip.GetEnd()) + " frames"

    # pr(resu)
fps = float(project.GetSetting("timelineFrameRate"))

def get_clips() -> list:
    timeline = project.GetCurrentTimeline()
    clips = timeline.GetItemListInTrack("video", 1)

    allowed_frames = allowed_time_separation * fps

    clips = timeline.GetItemListInTrack("video", 1)

    # Ordenar cronológicamente
    clips = sorted(clips, key=lambda c: c.GetStart())

    # Primer grupo
    main_clip = Clip(
        title=clips[0].GetName(),
        start=clips[0].GetStart(),
        end=clips[0].GetEnd()
    )

    groups = []

    for clip in clips[1:]:

        gap = clip.GetStart() - main_clip.end

        if gap <= allowed_frames:
            # Pertenece al mismo grupo
            main_clip.end = max(main_clip.end, clip.GetEnd())

        else:
            # Guardar grupo anterior
            groups.append(main_clip)

            # Crear nuevo grupo
            main_clip = Clip(
                title=clip.GetName(),
                start=clip.GetStart(),
                end=clip.GetEnd()
            )

    # Guardar el último grupo
    groups.append(main_clip)
    return groups

# Crear tareas de renderizado

def create_render_jobs(groups) -> list:
    job_ids = []

    for group in groups:

        duration = group.end - group.start
        print(sec(duration));

        # Ignorar grupos de 5 segundos o menos
        if float(sec(duration)) < min_duration_frames:
            print(f"Ignorado: {group.title} ({duration / fps:.2f} segundos)")
            continue

        settings["MarkIn"] = group.start
        settings["MarkOut"] = group.end
        settings["CustomName"] = group.title

        if project.SetRenderSettings(settings):

            job_id = project.AddRenderJob()
            job_ids.append(job_id)
            print(
                f"Tarea añadida: {job_id} | "
                f"{group.title} | "
                f"{(group.end - group.start) / fps:.2f} segundos"
            )

        else:
            print("Error configurando el renderizado")
            return

    return job_ids
            

def render_jobs(job_ids) -> None:
    project.StartRendering()

    # Esperar a que terminen todas las tareas
    while True:

        completed = True

        for job_id in job_ids:
            status = project.GetRenderJobStatus(job_id)

            if status["JobStatus"] not in ["Complete", "Failed", "Cancelled"]:
                completed = False
                return

        if completed:
            print("finalizado")
            return

        time.sleep(2)



    # clips = timeline.GetItemListInTrack("audio", 1)

    # if project:
    #     print("Proyecto actual:", project.GetName())
    # else:
    #     print("No hay ningún proyecto abierto")

