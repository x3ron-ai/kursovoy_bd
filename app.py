from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response
import psycopg2
import hashlib
import secrets
from db import get_db_connection

app = Flask(__name__)

# Генерация токена для сессий
def generate_token():
	return secrets.token_hex(64)

# Хеширование пароля (SHA-256)
def hash_password(password):
	return hashlib.sha256(password.encode()).hexdigest()

# Получение пользователя по токену
def get_user_by_token(token):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT users.id, users.role FROM users
		JOIN sessions ON users.id = sessions.user_id
		WHERE sessions.token = %s
	""", (token,))
	user = cur.fetchone()
	cur.close()
	conn.close()
	return user

# Главная страница (магазин)
@app.route('/')
def home():
	return render_template('index.html')

# Страница авторизации
@app.route('/login', methods=['GET', 'POST'])
def login_page():
	if request.method == 'POST':
		data = request.form
		login = data.get('login')
		password = hash_password(data.get('password'))

		conn = get_db_connection()
		cur = conn.cursor()
		cur.execute("SELECT id FROM users WHERE login = %s AND password = %s", (login, password))
		user = cur.fetchone()

		if user:
			token = generate_token()
			cur.execute("INSERT INTO sessions (user_id, token) VALUES (%s, %s)", (user[0], token))
			conn.commit()
			cur.close()
			conn.close()

			resp = make_response(redirect(url_for('profile')))
			resp.set_cookie('token', token, httponly=True)
			return resp
		else:
			cur.close()
			conn.close()
			return jsonify({'error': 'Неверный логин или пароль'}), 401

	return render_template('login.html')

# Страница регистрации
@app.route('/register', methods=['GET', 'POST'])
def register_page():
	if request.method == 'POST':
		data = request.form
		login = data.get('login')
		password = hash_password(data.get('password'))
		role = 'user'

		conn = get_db_connection()
		cur = conn.cursor()
		try:
			cur.execute("INSERT INTO users (login, password, role) VALUES (%s, %s, %s) RETURNING id", (login, password, role))
			user_id = cur.fetchone()[0]
			token = generate_token()
			cur.execute("INSERT INTO sessions (user_id, token) VALUES (%s, %s)", (user_id, token))
			conn.commit()
			resp = make_response(redirect(url_for('profile')))
			resp.set_cookie('token', token, httponly=True)
		except psycopg2.Error:
			conn.rollback()
			resp = jsonify({'error': 'Ошибка регистрации'})
		finally:
			cur.close()
			conn.close()
		
		return resp

	return render_template('register.html')

# Страница профиля (для покупателя)
@app.route('/profile')
def profile():
	token = request.cookies.get('token')
	user = get_user_by_token(token)
	if not user:
		return redirect(url_for('login_page'))
	return render_template('profile.html')

if __name__ == '__main__':
	app.run(debug=True)

