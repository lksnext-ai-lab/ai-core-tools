from flask import Flask, render_template
from flask_restful import Api, Resource

app = Flask(__name__)
api = Api(app)


@app.route('/')
def index():
    print('aaa')
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
