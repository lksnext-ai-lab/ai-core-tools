from flask import Flask, render_template, session, Blueprint, request, redirect, jsonify, request
from flask import request
from app.model.agent import Agent
import app.tools.modelTools as modelTools


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
    agent = Agent.query.filter_by(agent_id=agent_id).first()
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
    