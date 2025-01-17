from flask import session, Blueprint, request, jsonify, request
from app.agents.ocrAgent import process_pdf
from app.model.agent import Agent
import app.tools.modelTools as modelTools
from app.extensions import db
import os
from app.model.api_key import APIKey
from app.model.app import App
from datetime import datetime
import logging

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

api_blueprint = Blueprint('api', __name__, url_prefix='/api')
MSG_LIST = "MSG_LIST"


def is_valid_api_key(app_id,api_key):
    
    if api_key is None:
        return False
    else:
        api_key_obj = db.session.query(APIKey).filter(
            APIKey.app_id == app_id, 
            APIKey.key == api_key, 
            APIKey.active == True
        ).first()
        if api_key_obj is None:
            return False
        else:
            api_key_obj.last_used = datetime.now()
            db.session.commit()
            return True
    
def check_session_permission(app_id):
    if session.get('user') is None:
        return False
    else:
        app = db.session.query(App).filter(
            App.app_id == int(app_id), 
            App.user_id == int(session.get('user_id'))
        ).first()
        if app is None:
            return False
        else:
            return True

'''
API
'''
@api_blueprint.route('/<string:app_id>/call/<int:agent_id>', methods=['GET', 'POST'])
def api(app_id, agent_id):

    print("session: ", request.cookies.get('session_id'))
    print(session)

    api_key = request.headers.get('X-API-KEY')  
    if not check_session_permission(app_id) and not is_valid_api_key(app_id, api_key):
        return jsonify({"error": "Invalid or missing API key"}), 401
    
    
    
    in_data = request.get_json()
    question = in_data.get('question')
    #agent_id = int(in_data.get('agent_id'))

    agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
    result =""
    if agent is None:
        return jsonify({"error": "Agent not found"})
    #elif agent.repository is not None and agent.has_memory:
    elif agent.has_memory:
        result = modelTools.invoke_ConversationalRetrievalChain(agent, question, session)
    elif agent.repository is not None:
        result = modelTools.invoke_rag_with_repo(agent, question)
    else:
        result = modelTools.invoke(agent, question)
    print("result: ", result)
    data = {
        "input": question,
        "generated_text": result,
        "control": {
            "temperature": 0.8,
            "max_tokens": 100,
            "top_p": 0.9,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.5,
            "stop_sequence": "\n\n"
        },
        "metadata": {
            "model_name": agent.model.name,
            "timestamp": "2024-04-04T12:00:00Z"
        }
    }

    if MSG_LIST not in session:
        session[MSG_LIST] = []
    session[MSG_LIST].append(result)
    print(session[MSG_LIST])


    return jsonify(data)
    
@api_blueprint.route('/<string:app_id>/ocr', methods=['POST'])
def process_ocr(app_id):
    logger.info(f"Iniciando proceso OCR para app_id: {app_id}")
    
    api_key = request.headers.get('X-API-KEY')
    '''if not api_key or not is_valid_api_key(app_id, api_key):
        return jsonify({"error": "Invalid or missing API key"}), 401

    if 'pdf' not in request.files:
        logger.error("No se proporcionó archivo PDF en la solicitud")
        return jsonify({'error': 'No se proporcionó archivo PDF'}), 400
    ''' 
    pdf_file = request.files['pdf']
    agent_id = request.form.get('agent_id')
    
    if not pdf_file or not agent_id:
        logger.error(f"Datos incompletos - pdf_file: {bool(pdf_file)}, agent_id: {agent_id}")
        return jsonify({'error': 'Faltan datos requeridos'}), 400
    
    # Obtener rutas desde variables de entorno
    downloads_dir = os.getenv('DOWNLOADS_PATH', '/app/temp/downloads/')
    images_dir = os.getenv('IMAGES_PATH', '/app/temp/images/')
    
    logger.info(f"Usando directorios - downloads: {downloads_dir}, images: {images_dir}")

    os.makedirs(downloads_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
        
    # Guardar temporalmente el PDF
    pdf_filename = pdf_file.filename
    temp_path = os.path.join(downloads_dir, pdf_filename)
    images_path = os.path.join(images_dir, pdf_filename.split('.')[0])
    
    logger.info(f"Procesando archivo: {pdf_filename}")
    logger.debug(f"Rutas completas - temp_path: {temp_path}, images_path: {images_path}")
    
    # Limpiar archivos antiguos si existen
    if os.path.exists(temp_path):
        logger.info(f"Eliminando archivo temporal existente: {temp_path}")
        os.remove(temp_path)
    
    pdf_file.save(temp_path)
    logger.info(f"Archivo PDF guardado en: {temp_path}")
    
    try:
        logger.info(f"Iniciando procesamiento OCR con agent_id: {agent_id}")
        result = process_pdf(int(agent_id), temp_path, images_path)
        logger.info("Proceso OCR completado exitosamente")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error durante el procesamiento OCR: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    