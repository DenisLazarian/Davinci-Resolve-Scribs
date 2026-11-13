
from flask import Flask,render_template, request
import requests
from test import get_clips, create_render_jobs, render_jobs

# 1. Crear la instancia de la aplicación
app = Flask(__name__)

clips, groups, jobs_ids = [], [], []

# 2. Definir la ruta principal (página de inicio)
@app.route('/', methods=['GET', 'POST'])
def render_form():
    # person2 = {'name': 'John', 'age': 25}  # Example person data

    

    if request.method == 'POST':
        # Obtener los datos del formulario
        nombre = request.form.get('Emisor')
        apellidos = request.form.get('Receptor')
        sesion = request.form.getlist('sesion')  # Obtener todas las opciones seleccionadas

        # Aquí puedes procesar los datos según tus necesidades
        print("Nombre:", nombre)
        print("Apellidos:", apellidos)
        print("Opciones seleccionadas:", sesion)
        # Puedes redirigir a otra página o mostrar un mensaje de éxito


        jobs_ids = render_jobs(groups)
        return "Formulario enviado con éxito"

    clips = get_clips()
    groups = create_render_jobs(clips)

    return render_template('formulario.html')





# 3. Ejecutar el servidor si el archivo se corre directamente
if __name__ == "__main__":
    app.run(debug=True)
    requests.get("http://localhost:5000/")  # Abrir automáticamente en el navegador
