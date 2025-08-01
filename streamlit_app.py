import streamlit as st
import sys
from pathlib import Path
from PIL import Image
import numpy as np
from datetime import datetime
import requests
import threading
import time
import subprocess
import os
import re

# ==================== CONFIGURACIÓN DE LA PÁGINA (DEBE SER PRIMERO) ====================
# Agregar directorio padre al path ANTES de importar configuración
sys.path.append(str(Path(__file__).parent))

from config import STREAMLIT_CONFIG, MESSAGES, RETRAINING_CONFIG

st.set_page_config(
    page_title=STREAMLIT_CONFIG["page_title"],
    page_icon=STREAMLIT_CONFIG["page_icon"],
    layout=STREAMLIT_CONFIG["layout"],
    initial_sidebar_state=STREAMLIT_CONFIG["initial_sidebar_state"]
)

# ==================== IMPORTS DEL MODELO (DESPUÉS DE set_page_config) ====================
try:
    from model.prediction import session_manager, verificar_sistema_prediccion
    from utils.firebase_config import obtener_info_planta_basica, firestore_manager
except ImportError as e:
    st.error(f"❌ Error importando módulos: {e}")
    st.stop()

# ==================== CSS PERSONALIZADO ====================

st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #2E8B57, #98FB98);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    
    .prediction-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #28a745;
        margin: 1rem 0;
    }
    
    .info-card {
        background: #e8f5e9;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    
    .species-card {
        background: #f0f8ff;
        padding: 1rem;
        border-radius: 8px;
        border: 2px solid #e0e0e0;
        margin: 0.5rem 0;
        text-align: center;
        transition: all 0.3s;
    }
    
    .species-card:hover {
        border-color: #28a745;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    .debug-info {
        background: #fff3cd;
        color: #856404;
        padding: 0.75rem;
        border-radius: 5px;
        border: 1px solid #ffeaa7;
        margin: 0.5rem 0;
        font-size: 0.9em;
    }
    
    .error-message {
        background: #f8d7da;
        color: #721c24;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #f5c6cb;
        margin: 1rem 0;
    }
    
    .success-message {
        background: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #c3e6cb;
        margin: 1rem 0;
    }
    
    .firestore-status {
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.5rem 0;
        font-size: 0.9rem;
    }
    
    .firestore-connected {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    
    .firestore-disconnected {
        background: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    
    .confidence-bar {
        background: #e9ecef;
        border-radius: 10px;
        height: 20px;
        margin: 0.5rem 0;
        overflow: hidden;
    }
    
    .confidence-fill {
        background: linear-gradient(90deg, #28a745, #20c997);
        height: 100%;
        transition: width 0.3s ease;
    }
</style>
""", unsafe_allow_html=True)

# ==================== FUNCIONES DE INICIALIZACIÓN ====================

@st.cache_resource
def inicializar_firestore_app():
    """Inicializa Firestore una sola vez usando cache"""
    try:
        print("🔥 Inicializando Firestore...")
        
        # Intentar usar secrets (funciona en local y cloud)
        if "firebase" in st.secrets:
            import firebase_admin
            from firebase_admin import credentials, firestore
            
            # Verificar si ya está inicializado
            if not firebase_admin._apps:
                # Convertir secrets a diccionario
                firebase_creds = dict(st.secrets["firebase"])
                cred = credentials.Certificate(firebase_creds)
                firebase_admin.initialize_app(cred)
            
            firestore_manager.db = firestore.client()
            firestore_manager.initialized = True
            print("✅ Firestore inicializado desde secrets")
            return True
        else:
            print("❌ No se encontraron secrets de Firebase")
            return False
            
    except Exception as e:
        print(f"❌ Excepción inicializando Firestore: {e}")
        return False
    
def iniciar_api_background():
    """Inicia la API con Ngrok en background"""
    try:
        project_dir = Path(__file__).parent
        os.chdir(project_dir)
        
        print("🚀 Iniciando API con Ngrok en background...")
        subprocess.Popen([sys.executable, "api_server.py"], cwd=project_dir)
        time.sleep(5)
        print("✅ API iniciada en background")
        
    except Exception as e:
        print(f"❌ Error iniciando API: {e}")

def verificar_y_iniciar_api():
    """Verifica si la API está corriendo, si no la inicia"""
    try:
        response = requests.get("http://localhost:5000/", timeout=3)
        if response.status_code == 200:
            print("✅ API ya está corriendo")
            return True
    except:
        pass
    
    # Solo intentar iniciar API en desarrollo local
    if "firebase" not in st.secrets:  # Si NO estamos en Streamlit Cloud
        print("🔄 API no detectada, iniciando...")
        thread = threading.Thread(target=iniciar_api_background, daemon=True)
        thread.start()
        
        for i in range(30):
            try:
                response = requests.get("http://localhost:5000/", timeout=2)
                if response.status_code == 200:
                    print("✅ API lista y funcionando")
                    return True
            except:
                pass
            time.sleep(1)
    
    print("⚠️ API no disponible (normal en Streamlit Cloud)")
    return False

# ==================== INICIALIZACIÓN DE ESTADO ====================

def inicializar_estado():
    """Inicializa todos los estados necesarios"""
    if 'firestore_initialized' not in st.session_state:
        st.session_state.firestore_initialized = inicializar_firestore_app()
    
    if 'api_initialized' not in st.session_state:
        st.session_state.api_initialized = verificar_y_iniciar_api()
    
    if 'session_id' not in st.session_state:
        st.session_state.session_id = None
    if 'imagen_actual' not in st.session_state:
        st.session_state.imagen_actual = None
    if 'especies_descartadas' not in st.session_state:
        st.session_state.especies_descartadas = set()
    if 'intento_actual' not in st.session_state:
        st.session_state.intento_actual = 1
    if 'resultado_actual' not in st.session_state:
        st.session_state.resultado_actual = None
    if 'mostrar_top_especies' not in st.session_state:
        st.session_state.mostrar_top_especies = False
    if 'max_intentos' not in st.session_state:
        st.session_state.max_intentos = RETRAINING_CONFIG["max_attempts_per_prediction"]

def limpiar_sesion():
    """Limpia la sesión actual completamente"""
    st.session_state.session_id = None
    st.session_state.imagen_actual = None
    st.session_state.especies_descartadas = set()
    st.session_state.intento_actual = 1
    st.session_state.resultado_actual = None
    st.session_state.mostrar_top_especies = False
    st.cache_data.clear()

# Inicializar estado
inicializar_estado()

# ==================== FUNCIONES AUXILIARES MEJORADAS ====================

def mostrar_header():
    """Muestra el header principal de la aplicación"""
    st.markdown('<h1 class="main-header">🌱 BucaraFlora - Identificador de Plantas IA</h1>', unsafe_allow_html=True)
    st.markdown("**Sube una foto de tu planta y descubre qué especie es**")
    
    # Mostrar estado de servicios
    col1, col2 = st.columns(2)
    with col1:
        if st.session_state.get('api_initialized'):
            st.markdown('<div class="firestore-connected">✅ API Activa</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="firestore-disconnected">⚠️ API Local No Disponible</div>', unsafe_allow_html=True)
    
    with col2:
        if st.session_state.get('firestore_initialized'):
            st.markdown('<div class="firestore-connected">✅ Base de Datos Conectada</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="firestore-disconnected">❌ Base de Datos Desconectada</div>', unsafe_allow_html=True)

def buscar_info_planta_firestore(nombre_cientifico):
    """
    Busca información de la planta en Firestore con múltiples formatos
    """
    try:
        print(f"🔍 Buscando en Firestore: {nombre_cientifico}")
        
        # Usar la función básica mejorada
        info = obtener_info_planta_basica(nombre_cientifico)
        
        # Verificar si encontramos datos reales
        if info.get('fuente_datos') == 'firestore':
            print(f"✅ Datos encontrados en Firestore para: {nombre_cientifico}")
            return {
                "exito": True,
                "datos": info,
                "fuente": "firestore"
            }
        else:
            print(f"⚠️ No se encontraron datos en Firestore para: {nombre_cientifico}")
            return {
                "exito": False,
                "datos": info,
                "fuente": info.get('fuente_datos', 'no_encontrado')
            }
            
    except Exception as e:
        print(f"❌ Error buscando en Firestore: {e}")
        return {
            "exito": False,
            "datos": {
                "nombre_cientifico": nombre_cientifico,
                "nombre_comun": "Error de conexión",
                "descripcion": f"No se pudo conectar con la base de datos: {str(e)}",
                "fuente_datos": "error"
            },
            "fuente": "error"
        }

def mostrar_info_planta_completa(info_planta):
    """
    Muestra la información completa de la planta de forma visualmente atractiva
    """
    datos = info_planta.get('datos', {})
    fuente = info_planta.get('fuente', 'desconocido')
    
    # Indicador de fuente de datos
    if fuente == 'firestore':
        st.success("✅ Información verificada de la base de datos")
    elif fuente == 'no_encontrado':
        st.warning("⚠️ Especie no encontrada en la base de datos")
    else:
        st.error("❌ Error al obtener información de la base de datos")
    
    # Contenedor principal
    with st.container():
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Nombre común y científico
            st.markdown(f"### 🌿 {datos.get('nombre_comun', 'Nombre no disponible')}")
            st.markdown(f"**Nombre científico:** *{datos.get('nombre_cientifico', 'N/A')}*")
            
            # Descripción
            descripcion = datos.get('descripcion', '')
            if descripcion and fuente == 'firestore':
                st.markdown("#### 📝 Descripción")
                st.markdown(f'<div class="info-card">{descripcion}</div>', unsafe_allow_html=True)
            
            # Información adicional
            if datos.get('fecha_observacion'):
                st.markdown(f"**📅 Fecha de observación:** {datos.get('fecha_observacion')}")
            
            if datos.get('fuente'):
                st.markdown(f"**📚 Fuente:** {datos.get('fuente')}")
        
        with col2:
            # Imagen de referencia
            imagen_url = datos.get('imagen_referencia')
            if imagen_url and fuente == 'firestore':
                try:
                    st.image(imagen_url, caption="Imagen de referencia", use_container_width=True)
                except:
                    st.info("📷 Imagen no disponible")
            else:
                st.info("📷 Sin imagen de referencia")
    
    # Información taxonómica
    if datos.get('taxonomia') and fuente == 'firestore':
        with st.expander("🧬 Ver Clasificación Taxonómica"):
            taxonomia = datos.get('taxonomia', {})
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Clasificación Superior:**")
                st.write(f"• **Reino:** {taxonomia.get('reino', 'N/A')}")
                st.write(f"• **Filo:** {taxonomia.get('filo', 'N/A')}")
                st.write(f"• **Clase:** {taxonomia.get('clase', 'N/A')}")
            
            with col2:
                st.markdown("**Clasificación Inferior:**")
                st.write(f"• **Orden:** {taxonomia.get('orden', 'N/A')}")
                st.write(f"• **Familia:** {taxonomia.get('familia', 'N/A')}")
                st.write(f"• **Género:** {taxonomia.get('genero', 'N/A')}")
                st.write(f"• **Especie:** {taxonomia.get('especie', 'N/A')}")

def hacer_prediccion_con_info(imagen, especies_excluir=None):
    """
    Hace predicción y obtiene información de Firestore
    """
    try:
        # Hacer predicción con el modelo
        resultado = session_manager.predictor.predecir_planta(imagen, especies_excluir)
        
        if resultado.get("exito"):
            especie_predicha = resultado["especie_predicha"]
            
            # Buscar información en Firestore
            info_planta = buscar_info_planta_firestore(especie_predicha)
            
            # Combinar resultados
            resultado_completo = {
                "exito": True,
                "especie_predicha": especie_predicha,
                "confianza": resultado["confianza"],
                "info_planta": info_planta,
                "top_predicciones": resultado.get("top_predicciones", []),
                "timestamp": datetime.now().isoformat()
            }
            
            return resultado_completo
        else:
            return resultado
            
    except Exception as e:
        return {
            "exito": False,
            "error": str(e),
            "mensaje": "Error en la predicción"
        }

# ==================== PANTALLAS PRINCIPALES ====================

def pantalla_upload_imagen():
    """Pantalla inicial para subir imagen"""
    st.markdown("### 📸 Sube una foto de tu planta")
    
    # Área de carga
    uploaded_file = st.file_uploader(
        "Selecciona una imagen",
        type=STREAMLIT_CONFIG["allowed_extensions"],
        help="Formatos soportados: JPG, JPEG, PNG. Máximo 10MB."
    )
    
    if uploaded_file is not None:
        # Validar tamaño
        if uploaded_file.size > STREAMLIT_CONFIG["max_file_size"] * 1024 * 1024:
            st.error(f"❌ Archivo muy grande. Máximo {STREAMLIT_CONFIG['max_file_size']}MB.")
            return
        
        try:
            # Cargar y mostrar imagen
            imagen = Image.open(uploaded_file)
            
            # Mostrar imagen con columnas para centrarla
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image(imagen, caption="Tu planta", use_container_width=True)
            
            # Botón de análisis
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🔍 Identificar Planta", type="primary", use_container_width=True):
                    with st.spinner("🧠 Analizando tu planta..."):
                        # Limpiar estado anterior
                        limpiar_sesion()
                        
                        # Establecer nueva sesión
                        st.session_state.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                        st.session_state.imagen_actual = imagen
                        st.session_state.intento_actual = 1
                        st.session_state.especies_descartadas = set()
                        
                        # Hacer predicción con información
                        resultado = hacer_prediccion_con_info(imagen, None)
                        
                        if resultado.get("exito"):
                            st.session_state.resultado_actual = resultado
                            st.rerun()
                        else:
                            st.error(f"❌ {resultado.get('mensaje', 'Error en la predicción')}")
                            
        except Exception as e:
            st.error(f"❌ Error cargando imagen: {e}")

def pantalla_prediccion_feedback():
    """Pantalla de predicción con botones de feedback"""
    resultado = st.session_state.resultado_actual
    
    # Mostrar imagen del usuario
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(st.session_state.imagen_actual, caption="Tu planta", use_container_width=True)
    
    # Card de predicción
    st.markdown('<div class="prediction-card">', unsafe_allow_html=True)
    
    # Mostrar información de la planta
    info_planta = resultado.get("info_planta", {})
    mostrar_info_planta_completa(info_planta)
    
    # Barra de confianza
    confianza = resultado["confianza"]
    porcentaje = int(confianza * 100)
    
    st.markdown(f"""
    <div class="confidence-bar">
        <div class="confidence-fill" style="width: {porcentaje}%;"></div>
    </div>
    <p style="text-align: center; margin: 0.5rem 0; font-weight: bold;">
        Confianza de la predicción: {porcentaje}%
    </p>
    """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Botones de feedback
    st.markdown("---")
    st.markdown("### ¿Es correcta esta identificación?")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("✅ ¡Sí, es correcta!", type="primary", use_container_width=True):
            with st.spinner("💾 Guardando tu confirmación..."):
                # Aquí puedes agregar lógica para guardar en Firestore
                st.success(MESSAGES["prediction_success"])
                st.success(MESSAGES["image_saved"])
                st.balloons()
                
                # Botón para nueva identificación
                if st.button("🔄 Identificar otra planta", use_container_width=True):
                    limpiar_sesion()
                    st.rerun()
    
    with col2:
        if st.button("❌ No, es incorrecta", type="secondary", use_container_width=True):
            # Procesar feedback negativo
            especie_rechazada = resultado["especie_predicha"]
            st.session_state.especies_descartadas.add(especie_rechazada)
            st.session_state.intento_actual += 1
            
            # Mostrar directamente las top 5 especies
            st.session_state.mostrar_top_especies = True
            st.rerun()

def pantalla_top_especies():
    """Pantalla de selección manual de las top 5 especies"""
    st.markdown("### 🤔 ¿Tal vez sea una de estas?")
    st.info("Selecciona la especie correcta de las siguientes opciones:")
    
    # Obtener top 5 especies
    with st.spinner("🔍 Buscando especies similares..."):
        especies_excluir = list(st.session_state.especies_descartadas)
        top_especies = session_manager.predictor.obtener_top_especies(
            st.session_state.imagen_actual,
            cantidad=5,  # Solo top 5
            especies_excluir=especies_excluir
        )
    
    if not top_especies:
        st.error("❌ Error obteniendo especies similares")
        return
    
    # Mostrar imagen original
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(st.session_state.imagen_actual, caption="Tu planta", use_column_width=True)
    
    st.markdown("---")
    
    # Variable para controlar si se seleccionó algo
    seleccionado = False
    
    # Mostrar las 5 especies en un layout mejorado
    for i, especie_data in enumerate(top_especies):
        # Buscar información de la especie
        info_planta = buscar_info_planta_firestore(especie_data["especie"])
        datos = info_planta.get('datos', {})
        
        # Card para cada especie
        st.markdown(f'<div class="species-card">', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 3, 1])
        
        with col1:
            # Número de opción
            st.markdown(f"### {i+1}")
        
        with col2:
            # Info de la especie
            st.markdown(f"**{datos.get('nombre_comun', 'N/A')}**")
            st.markdown(f"*{especie_data['especie']}*")
            
            # Barra de confianza mini
            porcentaje = int(especie_data["confianza"] * 100)
            st.markdown(f"""
            <div class="confidence-bar" style="height: 10px;">
                <div class="confidence-fill" style="width: {porcentaje}%;"></div>
            </div>
            <p style="text-align: center; font-size: 0.9em; margin: 0;">
                Confianza: {porcentaje}%
            </p>
            """, unsafe_allow_html=True)
        
        with col3:
            # Botón de selección
            if st.button(
                "✅ Es esta", 
                key=f"select_{i}",
                use_container_width=True,
                type="primary" if i == 0 else "secondary"
            ):
                with st.spinner("💾 Guardando tu selección..."):
                    st.success(f"🎉 ¡Gracias! Has identificado tu planta como **{datos.get('nombre_comun', especie_data['especie'])}**")
                    st.success(MESSAGES["image_saved"])
                    st.balloons()
                    
                    # Esperar un momento para que el usuario vea el mensaje
                    time.sleep(2)
                    
                    # Limpiar y volver al inicio
                    limpiar_sesion()
                    st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Opción "No es ninguna de estas"
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("❌ No es ninguna de estas", type="secondary", use_container_width=True):
            # Mostrar mensaje de disculpa
            st.warning("😔 Lo sentimos, no pudimos identificar tu planta.")
            st.info("💡 **Sugerencia:** Intenta con otra foto desde un ángulo diferente, asegurándote de que se vean claramente las hojas o flores.")
            
            # Esperar un momento para que lea el mensaje
            time.sleep(3)
            
            # Limpiar y volver al inicio
            limpiar_sesion()
            st.rerun()

def pantalla_error_sistema():
    """Pantalla cuando el sistema no está disponible"""
    st.markdown('<div class="error-message">', unsafe_allow_html=True)
    st.markdown("### ❌ Sistema No Disponible")
    st.markdown("El modelo de identificación no está cargado o entrenado.")
    st.markdown("**Posibles soluciones:**")
    st.markdown("- Entrenar el modelo inicial: `python model/train_model.py`")
    st.markdown("- Verificar que existe el archivo del modelo")
    st.markdown("- Contactar al administrador del sistema")
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.button("🔄 Verificar sistema nuevamente"):
        st.rerun()

# ==================== FUNCIÓN PRINCIPAL ====================

def main():
    """Función principal de la aplicación"""
    # Mostrar header
    mostrar_header()
    
    # Verificar sistema
    estado_sistema = verificar_sistema_prediccion()
    
    if not estado_sistema["disponible"]:
        pantalla_error_sistema()
        return
    
    # Determinar qué pantalla mostrar
    if st.session_state.mostrar_top_especies:
        pantalla_top_especies()
    elif st.session_state.resultado_actual:
        pantalla_prediccion_feedback()
    else:
        pantalla_upload_imagen()
    
    # Sidebar con información
    with st.sidebar:
        st.markdown("### ℹ️ Información del Sistema")
        st.markdown(f"🌿 **Especies:** {estado_sistema.get('especies', 'N/A')}")
        st.markdown(f"⏱️ **Actualización:** {datetime.now().strftime('%H:%M:%S')}")
        
        # Estado de servicios
        st.markdown("---")
        st.markdown("### 🔌 Estado de Servicios")
        
        if st.session_state.get('firestore_initialized'):
            st.success("✅ Base de Datos: Conectada")
        else:
            st.error("❌ Base de Datos: Desconectada")
        
        if st.session_state.get('api_initialized'):
            st.success("✅ API Local: Funcionando")
        else:
            st.warning("⚠️ API Local: No disponible")
        
        # Botón de reset
        st.markdown("---")
        if st.button("🔄 Nueva Consulta", use_container_width=True):
            limpiar_sesion()
            st.rerun()
        
        # Debug info
        with st.expander("🔧 Debug Info"):
            st.write(f"**Session ID:** {st.session_state.session_id}")
            st.write(f"**Intento:** {st.session_state.intento_actual}")
            st.write(f"**Descartadas:** {len(st.session_state.especies_descartadas)}")
            if st.session_state.resultado_actual:
                st.write(f"**Especie actual:** {st.session_state.resultado_actual.get('especie_predicha')}")

# ==================== EJECUCIÓN ====================

if __name__ == "__main__":
    main()