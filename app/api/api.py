from flask import session, Blueprint, request, jsonify, request
from flask import request
from agents.ocrAgent import process_pdf
from model.agent import Agent
import tools.modelTools as modelTools
from extensions import db
import os


api_blueprint = Blueprint('api', __name__)
MSG_LIST = "MSG_LIST"

'''
API
'''
@api_blueprint.route('/api', methods=['GET', 'POST'])
def api():
    print("session: ", request.cookies.get('session_id'))
    print(session)
    in_data = request.get_json()
    question = in_data.get('question')
    agent_id = in_data.get('agent_id')

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
    
@api_blueprint.route('/api/ocr', methods=['POST'])
def process_ocr():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No se proporcionó archivo PDF'}), 400
        
    pdf_file = request.files['pdf']
    print("pdf_file: ", pdf_file)
    agent_id = request.form.get('agent_id')
    
    if not pdf_file or not agent_id:
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    # Guardar temporalmente el PDF
    temp_path = os.path.join('./downloads/', pdf_file.filename)
    print("temp_path: ", temp_path)
    
    # Si existe un archivo diferente, eliminarlo antes de guardar el nuevo
    if os.path.exists(temp_path) and os.path.basename(temp_path) != pdf_file.filename:
        os.remove(temp_path)
    
    # Guardar el nuevo archivo solo si no existe
    if not os.path.exists(temp_path):
        pdf_file.save(temp_path)
    
    try:
        # Procesar el PDF usando el agente OCR
        result = process_pdf(int(agent_id), temp_path)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    