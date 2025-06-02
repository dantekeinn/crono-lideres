# app.py
import os
from flask import Flask, render_template, request, send_file
import pandas as pd
from datetime import datetime
from calendar import monthrange

app = Flask(__name__)

# --- Auxiliar: fines de semana con nombre en español ---
def obtener_fines_de_semana(mes: int, anio: int):
    """
    Devuelve una lista de tuplas (fecha_str, nombre_dia) para
    todos los sábados y domingos del mes/año dados, en español.
    """
    total_dias = monthrange(anio, mes)[1]
    resultados = []
    for d in range(1, total_dias + 1):
        f = datetime(anio, mes, d)
        wd = f.weekday()  # 5 = sábado, 6 = domingo
        if wd == 5 or wd == 6:
            nombre = "Sábado" if wd == 5 else "Domingo"
            resultados.append((f.strftime("%d/%m/%Y"), nombre))
    return resultados

# --- Lógica de asignación con Facilitador, Refuerzo y bloques de 7h ---
def asignar_turnos(
    fechas: list[tuple[str,str]],
    equipo: dict[str,str],
    num_lideres: int,
    num_pushers: int,
    usar_pushers: bool,
    modo_pusher: str
) -> pd.DataFrame:
    turnos = ["06:00-13:00", "13:00-20:00", "17:00-00:00"]
    lideres       = [p for p,r in equipo.items() if r == 'lider']
    pushers       = [p for p,r in equipo.items() if r == 'pusher']
    facilitadores = [p for p,r in equipo.items() if r == 'facilitador']

    li = pi = fi = 0
    cronograma = []

    # Recorremos fines de semana en pares (sábado, domingo)
    for week_idx, i in enumerate(range(0, len(fechas), 2)):
        sab = fechas[i]
        dom = fechas[i+1] if i+1 < len(fechas) else None
        for fecha_str, dia_nombre in [sab, dom] if dom else [sab]:
            # Para cada uno de los tres turnos
            for turno in turnos:
                persona = "SIN ASIGNAR"
                rango   = "-"
                es_mediodia = (turno == "13:00-20:00")

                # Apertura/cierre -> solo líderes
                if not es_mediodia:
                    if lideres:
                        persona = lideres[li % len(lideres)]
                        rango   = 'lider'
                        li += 1

                else:
                    # Mediodía: facilitador alternante cada 2 fines
                    if facilitadores and week_idx % 2 == 0:
                        persona = facilitadores[fi % len(facilitadores)]
                        rango   = 'facilitador'
                        fi += 1
                    # Si no toca facilitador o es fin alterno, pusher
                    elif usar_pushers and pushers:
                        persona = pushers[pi % len(pushers)]
                        rango   = 'pusher'
                        pi += 1

                cronograma.append({
                    "Fecha":  fecha_str,
                    "Día":    dia_nombre,
                    "Turno":  turno,
                    "Persona":persona,
                    "Rango":  rango
                })

    # Convertir a DataFrame
    df = pd.DataFrame(cronograma)

    # ------------ Lógica de refuerzo ------------  
    counts = df['Persona'].value_counts()
    under = [p for p,c in counts.items() if p not in ('SIN ASIGNAR',) and c == 1]
    for person in under:
        mask = df['Persona'] == 'SIN ASIGNAR'
        if mask.any():
            idx = df[mask].index[0]
            df.at[idx, 'Persona'] = person
            df.at[idx, 'Rango']   = 'refuerzo'
    # ---------------------------------------------

    return df

# --- Rutas Flask ---
@app.route('/', methods=['GET','POST'])
def index():
    resultado = None
    archivo   = None
    error     = None

    if request.method == 'POST':
        # Validar mes/año
        try:
            mes  = int(request.form['mes'])
            anio = int(request.form['anio'])
        except:
            error = "Selecciona mes y año válidos."
            return render_template('index.html', error=error)

        # Parámetros
        num_lideres  = int(request.form.get('num_lideres', 2))
        num_pushers  = int(request.form.get('num_pushers', 1))
        usar_pushers = bool(request.form.get('usar_pushers'))
        modo_pusher  = request.form.get('modo_pusher', 'normal')
        filtro       = request.form.get('filtro', 'Todos').lower()

        # Leer y normalizar Excel
        file = request.files.get('file')
        if not file or file.filename == '':
            error = "Debes subir un Excel con 'nombre' y 'puesto'."
            return render_template('index.html', error=error)
        try:
            df_pers = pd.read_excel(file)
            df_pers.columns = df_pers.columns.str.strip().str.lower()
            if not {'nombre','puesto'}.issubset(df_pers.columns):
                raise KeyError("Faltan columnas 'nombre' o 'puesto'.")
            df_pers['nombre'] = df_pers['nombre'].astype(str).str.strip()
            df_pers['puesto'] = df_pers['puesto'].astype(str).str.strip().str.lower()
            equipo = dict(zip(df_pers['nombre'], df_pers['puesto']))
        except Exception as e:
            error = f"Error al leer Excel: {e}"
            return render_template('index.html', error=error)

        # Generar, filtrar y mostrar
        fechas = obtener_fines_de_semana(mes, anio)
        df     = asignar_turnos(fechas, equipo,
                                num_lideres, num_pushers,
                                usar_pushers, modo_pusher)
        if filtro != 'todos':
            df = df[df['Rango'] == filtro]

        archivo   = f'cronograma_{mes:02d}_{anio}.xlsx'
        df.to_excel(archivo, index=False)
        resultado = df.to_html(classes='table table-striped', index=False)

    return render_template('index.html',
                           resultado=resultado,
                           archivo=archivo,
                           error=error)

@app.route('/descargar/<path:nombre>')
def descargar(nombre):
    if os.path.exists(nombre):
        return send_file(nombre, as_attachment=True)
    return "Archivo no encontrado", 404

if __name__ == '__main__':
    app.run(debug=True)
