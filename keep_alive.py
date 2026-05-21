from flask import Flask
from threading import Thread

app =Flask(__name__)

@app.route('/')
def index():
    return "Alive"

def run():
    # app.run(host='0.0.0.0', port=8080)
    app.run(host='0.0.0.0', port=10000)   # For Render port is 10000

def keep_alive():
    t = Thread(target=run)
    t.daemon = True              # uncomment this for if you use above render port
    t.start()
