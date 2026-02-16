from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import sqlite3
import json
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import re

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuración de Twilio
ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

client = Client(ACCOUNT_SID, AUTH_TOKEN)

# Jugadores
PLAYERS = {
    '1': {'name': 'Mako', 'phone': ''},
    '2': {'name': 'Fercho', 'phone': ''},
    '3': {'name': 'Leo Gómez', 'phone': ''},
    '4': {'name': 'Leo Villa', 'phone': ''},
    '5': {'name': 'Zulu', 'phone': ''},
    '6': {'name': 'Junes', 'phone': ''}
}

def init_db():
    conn = sqlite3.connect('votacion.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (id TEXT PRIMARY KEY, name TEXT, phone TEXT, proposals TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS games
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, round INTEGER, name TEXT, 
                  proposer TEXT, duration TEXT, votes INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS votes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, round INTEGER, voter TEXT, 
                  game_id INTEGER, vote_date DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS rounds
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, round_number INTEGER, 
                  start_date DATETIME, end_date DATETIME, status TEXT, winners TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/api/players', methods=['GET'])
def get_players():
    return jsonify(PLAYERS)

@app.route('/api/current-round', methods=['GET'])
def get_current_round():
    conn = sqlite3.connect('votacion.db')
    c = conn.cursor()
    c.execute('SELECT * FROM rounds WHERE status = ? ORDER BY id DESC LIMIT 1', ('active',))
    row = c.fetchone()
    conn.close()
    
    if row:
        return jsonify({'id': row[0], 'round': row[1], 'status': row[3]})
    return jsonify({'id': None, 'round': None, 'status': 'no_active'})

@app.route('/api/games', methods=['GET'])
def get_games():
    round_id = request.args.get('round', 1)
    conn = sqlite3.connect('votacion.db')
    c = conn.cursor()
    c.execute('''SELECT id, name, proposer, duration, votes FROM games 
                 WHERE round = ? ORDER BY duration, votes DESC''', (round_id,))
    games = c.fetchall()
    conn.close()
    
    result = []
    for game in games:
        result.append({
            'id': game[0],
            'name': game[1],
            'proposer': game[2],
            'duration': game[3],
            'votes': game[4]
        })
    return jsonify(result)

@app.route('/api/vote', methods=['POST'])
def vote():
    data = request.json
    voter = data.get('voter')
    game_id = data.get('game_id')
    round_id = data.get('round')
    
    conn = sqlite3.connect('votacion.db')
    c = conn.cursor()
    
    # Verificar si ya votó
    c.execute('''SELECT COUNT(*) FROM votes WHERE round = ? AND voter = ? AND game_id = ?''', 
              (round_id, voter, game_id))
    if c.fetchone()[0] > 0:
        conn.close()
        return jsonify({'error': 'Ya votaste por este juego'}), 400
    
    # Contar votos del jugador en esta categoría
    c.execute('''SELECT duration FROM games WHERE id = ?''', (game_id,))
    duration = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(*) FROM votes v 
                 JOIN games g ON v.game_id = g.id 
                 WHERE v.round = ? AND v.voter = ? AND g.duration = ?''', 
              (round_id, voter, duration))
    vote_count = c.fetchone()[0]
    
    if vote_count >= 2:
        conn.close()
        return jsonify({'error': f'Ya votaste por 2 juegos de {duration}'}), 400
    
    c.execute('''INSERT INTO votes (round, voter, game_id) VALUES (?, ?, ?)''', 
              (round_id, voter, game_id))
    c.execute('''UPDATE games SET votes = votes + 1 WHERE id = ?''', (game_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/add-game', methods=['POST'])
def add_game():
    data = request.json
    name = data.get('name')
    proposer = data.get('proposer')
    duration = data.get('duration')  # 'largo' o 'corto'
    round_id = data.get('round')
    
    if not all([name, proposer, duration, round_id]):
        return jsonify({'error': 'Faltan datos'}), 400
    
    conn = sqlite3.connect('votacion.db')
    c = conn.cursor()
    c.execute('''INSERT INTO games (round, name, proposer, duration) 
                 VALUES (?, ?, ?, ?)''', (round_id, name, proposer, duration))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/finish-round', methods=['POST'])
def finish_round():
    data = request.json
    round_id = data.get('round')
    
    conn = sqlite3.connect('votacion.db')
    c = conn.cursor()
    
    # Obtener ganadores
    c.execute('''SELECT id, name, duration, votes FROM games 
                 WHERE round = ? ORDER BY duration, votes DESC''', (round_id,))
    games = c.fetchall()
    
    winners = {}
    for duration in ['largo', 'corto']:
        top_game = next((g for g in games if g[2] == duration), None)
        if top_game:
            winners[duration] = {'id': top_game[0], 'name': top_game[1], 'proposer': top_game[3]}
    
    # Actualizar round
    c.execute('''UPDATE rounds SET status = ?, winners = ? WHERE id = ?''', 
              ('finished', json.dumps(winners), round_id))
    
    # Crear nueva ronda con juegos restantes
    c.execute('''INSERT INTO rounds (round_number, start_date, end_date, status) 
                 VALUES (?, ?, ?, ?)''', 
              (int(round_id) + 1, datetime.now(), datetime.now() + timedelta(days=7), 'active'))
    new_round = c.lastrowid
    
    # Copiar juegos no ganadores
    for game in games:
        if game[0] not in [winners.get('largo', {}).get('id'), winners.get('corto', {}).get('id')]:
            c.execute('''INSERT INTO games (round, name, proposer, duration, votes) 
                         VALUES (?, ?, ?, ?, 0)''', 
                      (new_round, game[1], game[2], game[3]))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'winners': winners, 'new_round': new_round})

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip()
    sender = request.values.get('From', '')
    
    response = MessagingResponse()
    
    if incoming_msg.lower() == 'menu':
        menu_text = '''🎲 *VOTACIÓN DE JUEGOS DE MESA*

1️⃣ Ver juegos
2️⃣ Votar
3️⃣ Mis votos
4️⃣ Proponer juego
5️⃣ Ver ganadores

Escribe el número de la opción'''
        response.message(menu_text)
    
    elif incoming_msg == '1':
        # Ver juegos
        conn = sqlite3.connect('votacion.db')
        c = conn.cursor()
        c.execute('''SELECT id, name, proposer, duration, votes FROM games 
                     WHERE round = (SELECT id FROM rounds WHERE status = 'active' LIMIT 1)
                     ORDER BY duration, votes DESC''')
        games = c.fetchall()
        conn.close()
        
        msg = "📋 *JUEGOS DISPONIBLES:*\n\n"
        for game in games:
            msg += f"ID: {game[0]}\n{game[1]} ({game[3]})\nProponente: {game[2]}\nVotos: {game[4]}\n\n"
        response.message(msg)
    
    return str(response)

if __name__ == '__main__':
    app.run(debug=True, port=5000