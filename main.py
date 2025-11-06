from fastapi import FastAPI, UploadFile, File , Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
import bcrypt
from datetime import datetime
import io
from garbage_classifier import classify_image_from_stream

#mongodb://localhost:27017/
#Jaco:505
# main.py - Inserta esto después de las importaciones
# ...
from datetime import datetime
import io
from garbage_classifier import classify_image_from_stream

# ================== Diccionario de Mapeo de Reciclaje ===================
# main.py - REEMPLAZAR tu RECYCLING_MAP actual con este
# main.py - INSERTA ESTO AL INICIO DEL ARCHIVO, antes de la conexión a Mongo
RECYCLING_MAP = {
    # ------------------ CLASES RECICLABLES (Contenedor Azul/Verde) ------------------
    # Plástico
    "plastic": {
        "material": "Plástico Genérico", 
        "categoria": "Plástico", 
        "color": "Azul", 
        "puntos": 10, 
        "instrucciones": "Lavar, retirar tapas y etiquetas. Compactar la botella para ahorrar espacio."
    },
    "plastic bottle": { # <-- CLASE ESPECÍFICA DE LA IA
        "material": "Botella de Plástico", 
        "categoria": "Plástico", 
        "color": "Azul", 
        "puntos": 10, 
        "instrucciones": "Lavar, retirar tapas y etiquetas. Compactar la botella para ahorrar espacio."
    },
    
    # Metal
    "metal": {
        "material": "Metal (Lata)", 
        "categoria": "Metal", 
        "color": "Azul", 
        "puntos": 15, 
        "instrucciones": "Lavar y aplastar para ahorrar espacio. No reciclar aerosoles presurizados."
    },
    "can": { # <-- CLASE ESPECÍFICA DE LA IA
        "material": "Lata de Bebida/Comida", 
        "categoria": "Metal", 
        "color": "Azul", 
        "puntos": 15, 
        "instrucciones": "Lavar y aplastar para ahorrar espacio. No reciclar aerosoles presurizados."
    },
    
    # Vidrio
    "glass": {
        "material": "Vidrio", 
        "categoria": "Vidrio", 
        "color": "Verde", 
        "puntos": 5, 
        "instrucciones": "Lavar. No reciclar cerámica, bombillas, ni vidrios rotos de ventanas."
    },
    
    # Papel/Cartón
    "cardboard": {
        "material": "Cartón", 
        "categoria": "Papel/Cartón", 
        "color": "Azul", 
        "puntos": 5, 
        "instrucciones": "Doblar y compactar. Debe estar limpio y seco."
    },
    "paper": {
        "material": "Papel", 
        "categoria": "Papel/Cartón", 
        "color": "Azul", 
        "puntos": 5, 
        "instrucciones": "No arrugar demasiado. Evita papel mojado o sucio."
    },

    # ------------------ CLASES NO RECICLABLES/ESPECIALES (Contenedor Gris/Marrón) ------------------
    "organic": { 
        "material": "Residuo Orgánico", 
        "categoria": "Orgánico", 
        "color": "Marrón", 
        "puntos": 0, 
        "instrucciones": "Compostar o desechar en el contenedor de orgánicos (Marrón), nunca en reciclables."
    },
    "trash": {
        "material": "Residuo Genérico", 
        "categoria": "No Reciclable", 
        "color": "Gris/Negro", 
        "puntos": 0, 
        "instrucciones": "Desechar como residuo ordinario. No debe ir en botes de reciclaje."
    },
    "other": { # Fallback
        "material": "Elemento Desconocido", 
        "categoria": "No Reciclable", 
        "color": "Gris/Negro", 
        "puntos": 0, 
        "instrucciones": "Reintentar el escaneo o desechar como ordinario."
    }
}
# ===================================================================================

# ================== Conexión a Mongo ===================
client = MongoClient(
    # "mongodb://localhost:27017/"  # Cambia esto si tu MongoDB está en otro host/puerto
    "mongodb+srv://Jaco:505@reciclajedb.tvx4n5b.mongodb.net/?appName=ReciclajeDB"
    # "mongodb+srv://dr8007942_db_user:53Nw0jv4qqkvEOil@greenscanner.qqwcxk9.mongodb.net/?retryWrites=true&w=majority&appName=greenscanner"
)
db = client["reciclaje"]

# ================== App & CORS =========================
app = FastAPI(title="EcoRecycle API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://192.168.20.23:5500",
        "http://10.0.2.2:5500",
        "https://green-scanner.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================== Modelos ============================
class User(BaseModel):
    nombre: str
    correo: str
    password: str

class Login(BaseModel):
    correo: str
    password: str

class Puntos(BaseModel):
    correo: str
    puntos: int

class Canje(BaseModel):
    correo: str
    premio: str

class ClasificacionRequest(BaseModel):
    correo: str


# ================== Utils ==============================
def get_user(correo: str):
    return db.usuarios.find_one({"correo": correo})

def int_or_0(x, key: str):
    try:
        return int(x.get(key, 0))
    except Exception:
        return 0


# ================== Rutas ==============================
@app.get("/")
def root():
    return {"status": "ok", "service": "EcoRecycle API"}


# -------- Puntos (saldo actual) ------------------------
@app.get("/usuarios/{correo}/puntos")
def puntos_usuario(correo: str):
    u = get_user(correo)
    if not u:
        return {"error": "Usuario no encontrado"}
    return {"correo": correo, "puntos": int_or_0(u, "puntos")}


# -------- Puntos acumulados (de por vida) --------------
@app.get("/usuarios/{correo}/puntos-acumulados")
def puntos_acumulados_usuario(correo: str):
    u = get_user(correo)
    if not u:
        return {"error": "Usuario no encontrado"}
    return {"correo": correo, "puntos_acumulados": int_or_0(u, "puntos_acumulados")}

# -------- Login ----------------------------------------
@app.post("/login")
def login(user: Login):
    db_user = get_user(user.correo)

    if not db_user:
        return {"error": "Credenciales incorrectas"}

    # Convertir el hash de la base de datos a bytes
    # El hash de la base de datos ya está en bytes
    stored_password = db_user["password"]

    if user.password != stored_password:
        return {"error": "Credenciales incorrectas"}

    return {
        "mensaje": "Login exitoso",
        "puntos": int_or_0(db_user, "puntos"),
        "puntos_acumulados": int_or_0(db_user, "puntos_acumulados"),
    }

# -------- Registro -------------------------------------
# -------- Registro -------------------------------------
@app.post("/register")
def register(user: User):
    if get_user(user.correo):
        return {"error": "Usuario ya registrado"}
    
    # --- ¡ESTO SÍ VA! ---
    # Codificamos la contraseña a bytes, la hasheamos, y guardamos el hash (que son bytes)
    hashed = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    
    db.usuarios.insert_one(
        {
            "nombre": user.nombre,
            "correo": user.correo,
            "password": hashed, # <-- Guardamos el HASH (bytes)
            "puntos": 0,
            "puntos_acumulados": 0,
        }
    )
    return {"mensaje": "Usuario registrado"}


# -------- Sumar puntos (escáner / voz) -----------------
@app.post("/puntos/agregar")
def agregar_puntos(puntos: Puntos):

    # --- CORRECCIÓN ---
    # 1. Verificar que el usuario existe
    usuario_existente = get_user(puntos.correo)
    if not usuario_existente:
        return {"error": "Usuario no encontrado, no se pueden sumar puntos"}
    # --- FIN DE LA CORRECCIÓN ---

    # 2. Suma al saldo y al acumulado (ahora sabemos que existe)
    db.usuarios.update_one(
        {"correo": puntos.correo},
        {"$inc": {"puntos": puntos.puntos, "puntos_acumulados": puntos.puntos}},
        # upsert=False (está bien dejarlo, aunque ya no es crítico)
    )

    # 3. Guardar historial
    db.historial.insert_one(
        {
            "usuario": puntos.correo,
            "accion": "escaneo",
            "detalle": f"+{puntos.puntos} puntos por reciclaje",
            "fecha": datetime.utcnow(),
        }
    )

    # 4. Devolver los nuevos totales (re-usamos la variable)
    #    OJO: get_user() es otra llamada a la DB. Es mejor usar los datos que ya tenemos
    #    y sumarles los puntos, o simplemente llamar a get_user() de nuevo.
    #    Llamar de nuevo es más simple y asegura consistencia:
    
    nuevo = get_user(puntos.correo) # Llamamos de nuevo para obtener los datos frescos
    
    return {
        "mensaje": "Puntos agregados",
        "puntos": int_or_0(nuevo, "puntos"),
        "puntos_acumulados": int_or_0(nuevo, "puntos_acumulados"),
    }


# -------- Listar premios -------------------------------
@app.get("/premios")
def listar_premios():
    # quita _id en la proyección
    return list(db.premios.find({}, {"_id": 0}))


# -------- Canjear premio -------------------------------
@app.post("/puntos/canjear")
def canjear_premio(data: Canje):
    user = get_user(data.correo)
    if not user:
        return {"error": "Usuario no encontrado"}

    premio = db.premios.find_one({"nombre": data.premio})
    if not premio:
        return {"error": "Premio no encontrado"}

    pts_necesarios = int(premio.get("puntos_necesarios", 0))
    stock_actual = int(premio.get("stock", 0))
    saldo_actual = int_or_0(user, "puntos")

    if stock_actual <= 0:
        return {"error": "Premio sin stock"}
    if saldo_actual < pts_necesarios:
        return {"error": "No tienes suficientes puntos"}

    db.usuarios.update_one(
        {"correo": data.correo},
        {"$inc": {"puntos": -pts_necesarios}},  # ¡sólo saldo actual!
    )
    db.premios.update_one({"nombre": data.premio}, {"$inc": {"stock": -1}})
    db.historial.insert_one(
        {
            "usuario": data.correo,
            "accion": "canje",
            "detalle": f"Gastó {pts_necesarios} pts por: {data.premio}",
            "fecha": datetime.utcnow(),
        }
    )
    nuevo = get_user(data.correo)
    return {
        "mensaje": f"Canjeaste {data.premio}",
        "puntos": int_or_0(nuevo, "puntos"),
        "puntos_acumulados": int_or_0(nuevo, "puntos_acumulados"),
    }


# -------- Historial ------------------------------------
@app.get("/historial/{correo}")
def ver_historial(correo: str):
    historial = list(db.historial.find({"usuario": correo}, {"_id": 0}))

    # --- CORRECCIÓN ---
    # Usamos una función de ordenamiento más segura
    # para evitar errores si una 'fecha' es None o no es un datetime.
    def get_safe_date(item):
        fecha_item = item.get("fecha")
        if isinstance(fecha_item, datetime):
            return fecha_item
        # Si 'fecha' es None, o un string, o cualquier otra cosa,
        # lo tratamos como el más antiguo (datetime.min).
        return datetime.min

    historial.sort(key=get_safe_date, reverse=True)
    # --- FIN DE LA CORRECCIÓN ---

    return historial


# -------- Garbage Classification -----------------------
# main.py - REEMPLAZA tu función @app.post("/classify") existente con esta
# ...

# ----------------- Clasificación de Imagen ---------------------
class ClasificacionResponse(BaseModel):
    mensaje: str
    resultado: dict
    puntos_ganados: int
    filename: str
    fecha: str


@app.post("/classify", response_model=ClasificacionResponse)
def classify_image_endpoint(
    file: UploadFile = File(...),
    correo: str = Form(...)
):
    try:
        # 1. Leer el contenido del archivo
        file_content = file.file.read()

        # 2. Clasificar la imagen con el modelo de IA
        result = classify_image_from_stream(io.BytesIO(file_content))
        
        # 3. Manejar errores del clasificador de IA
        if "error" in result:
            # Si el error está aquí, el modelo falló. Usamos el mapeo 'other'
            predicted_class = "other"
        else:
            # Obtener la clase predicha y asegurarla en MINÚSCULAS
            # Esto es VITAL para que coincida con las claves del diccionario
            predicted_class = result.get("predicted_class", "other").lower()

        # 4. APLICAR EL MAPEO DE RECICLAJE
        # Si la clase predicha no está en nuestro mapa, se usará la info de "other"
        recycling_info = RECYCLING_MAP.get(predicted_class, RECYCLING_MAP["other"])
        
        puntos_ganados = recycling_info["puntos"]
        mensaje_puntos = f"+{puntos_ganados} puntos por reciclaje de {recycling_info['material']}"
        
        # 5. Actualizar puntos del usuario en MongoDB
        if puntos_ganados > 0:
            db.usuarios.update_one(
                {"correo": correo},
                {"$inc": {"puntos": puntos_ganados}}
            )

        # 6. Preparar y guardar el registro para el historial
        clasificacion_data = {
            "correo": correo,
            "fecha": datetime.now().isoformat(),
            "puntos_ganados": puntos_ganados,
            "accion": "escaneo",
            "detalle": mensaje_puntos,
            "resultado": recycling_info
        }
        
        db.clasificaciones.insert_one(clasificacion_data)

        # 7. Devolver la respuesta completa al frontend
        return {
            "mensaje": "Clasificación exitosa",
            "resultado": recycling_info, # <-- Devolvemos la información completa de reciclaje
            "puntos_ganados": puntos_ganados,
            "filename": file.filename,
            "fecha": clasificacion_data["fecha"]
        }
        
    except Exception as e:
        # Manejo de errores general para cumplir con el response_model
        # Asegúrate de haber importado HTTPException y status de fastapi
        # Si no quieres importar HTTPException, simplemente retorna un error compatible:
        return {
            "mensaje": "Error en la clasificación",
            "resultado": RECYCLING_MAP["other"], # <-- Retorna el fallback
            "puntos_ganados": 0,
            "filename": file.filename if 'file' in locals() else 'N/A',
            "fecha": datetime.now().isoformat()
        }


# ... [El resto de tus rutas de API: login, register, obtener_historial_usuario, etc.]


# -------- Obtener Clasificaciones ----------------------
@app.get("/clasificaciones")
def obtener_clasificaciones():
    """Obtiene todas las clasificaciones realizadas"""
    clasificaciones = list(db.clasificaciones.find({}, {"_id": 0}))
    clasificaciones.sort(key=lambda x: x.get("fecha", datetime.min), reverse=True)
    return {
        "total": len(clasificaciones),
        "clasificaciones": clasificaciones
    }


# -------- Obtener Clasificaciones con filtros ----------
@app.get("/clasificaciones/filtradas")
def obtener_clasificaciones_filtradas(limite: int = 10, categoria: str = None):
    """Obtiene clasificaciones con filtros opcionales"""
    filtro = {}
    if categoria:
        filtro["resultado.categoria"] = categoria
    
    clasificaciones = list(db.clasificaciones.find(filtro, {"_id": 0}).limit(limite))
    clasificaciones.sort(key=lambda x: x.get("fecha", datetime.min), reverse=True)
    
    return {
        "total": len(clasificaciones),
        "filtros_aplicados": {
            "limite": limite,
            "categoria": categoria
        },
        "clasificaciones": clasificaciones
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
