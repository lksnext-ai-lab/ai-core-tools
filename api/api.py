from flask import Flask, render_template, session, Blueprint, request, redirect, jsonify
from flask import request
from model.agent import Agent
import tools.modelTools as modelTools

api_blueprint = Blueprint('api', __name__)

'''
API
'''
@api_blueprint.route('/api', methods=['GET', 'POST'])
def api():
    in_data = request.get_json()
    question = in_data.get('question')
    agent_id = in_data.get('agent_id')
    agent = Agent.query.filter_by(agent_id=agent_id).first()
    
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
            "timestamp": "2024-04-02T12:00:00Z"
        }
    }

    print()

    return jsonify(data)
    