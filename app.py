from flask import Flask, request, render_template, redirect, url_for, session, flash
import psycopg2
from db import get_db_connection
import hashlib
import secrets
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Конфигурация для загрузки файлов
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Проверка расширения файла
def allowed_file(filename):
	return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Middleware для проверки авторизации и роли
def login_required(role=None):
	def decorator(f):
		def wrapper(*args, **kwargs):
			if 'user_id' not in session:
				flash('Please login first')
				return redirect(url_for('login'))
			if role and session.get('role') != role:
				flash('Access denied')
				return redirect(url_for('index'))
			return f(*args, **kwargs)
		wrapper.__name__ = f.__name__
		return wrapper
	return decorator

# Главная страница с товарами
@app.route('/', methods=['GET', 'POST'])
@login_required()
def index():
	conn = get_db_connection()
	cur = conn.cursor()
	
	if request.method == 'POST' and session['role'] == 'customer':
		product_id = request.form.get('product_id')
		quantity = int(request.form.get('quantity', 1))
		
		try:
			# Проверка наличия достаточного количества
			cur.execute("SELECT quantity FROM products WHERE id = %s", (product_id,))
			available = cur.fetchone()[0]
			if quantity > available:
				flash(f'Only {available} items available')
			else:
				cur.execute("""
					INSERT INTO cart (user_id, product_id, quantity)
					VALUES (%s, %s, %s)
					ON CONFLICT (user_id, product_id)
					DO UPDATE SET quantity = cart.quantity + %s
				""", (session['user_id'], product_id, quantity, quantity))
				conn.commit()
				flash('Product added to cart')
		except psycopg2.Error as e:
			conn.rollback()
			flash(f'Error adding to cart: {str(e)}')
	
	cur.execute("""
		SELECT p.id, p.name, p.description, p.price, p.quantity, p.image_urls, u.name
		FROM products p
		JOIN users u ON p.seller_id = u.id
	""")
	products = cur.fetchall()
	
	cur.execute("SELECT name, role FROM users WHERE id = %s", (session['user_id'],))
	name, role = cur.fetchone()
	
	cur.close()
	conn.close()
	return render_template('index.html', products=products, name=name, role=role)

# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
	if request.method == 'POST':
		name = request.form.get('name')
		email = request.form.get('email')
		password = request.form.get('password')
		role = request.form.get('role', 'customer')

		if not all([name, email, password]):
			flash('All fields are required')
			return render_template('register.html')

		if role not in ['customer', 'seller', 'courier']:
			flash('Invalid role selected')
			return render_template('register.html')

		hashed_password = hashlib.sha256(password.encode()).hexdigest()

		conn = get_db_connection()
		cur = conn.cursor()
		
		try:
			cur.execute("SELECT id FROM users WHERE email = %s", (email,))
			if cur.fetchone():
				flash('Email already exists')
				return render_template('register.html')

			cur.execute("""
				INSERT INTO users (name, email, password, role)
				VALUES (%s, %s, %s, %s) RETURNING id
			""", (name, email, hashed_password, role))
			
			user_id = cur.fetchone()[0]
			conn.commit()
			
			cur.execute("""
				INSERT INTO logs (user_id, action)
				VALUES (%s, %s)
			""", (user_id, f'User {name} registered'))
			conn.commit()
			
			flash('Registration successful! Please login.')
			return redirect(url_for('login'))
			
		except psycopg2.Error as e:
			conn.rollback()
			flash(f'Registration failed: {str(e)}')
			return render_template('register.html')
		finally:
			cur.close()
			conn.close()
	
	return render_template('register.html')

# Авторизация
@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		email = request.form.get('email')
		password = request.form.get('password')
		hashed_password = hashlib.sha256(password.encode()).hexdigest()

		conn = get_db_connection()
		cur = conn.cursor()
		
		try:
			cur.execute("""
				SELECT id, name, role FROM users 
				WHERE email = %s AND password = %s
			""", (email, hashed_password))
			
			user = cur.fetchone()
			if not user:
				flash('Invalid credentials')
				return render_template('login.html')

			user_id, name, role = user
			
			token = secrets.token_hex(16)
			cur.execute("""
				INSERT INTO sessions (user_id, token)
				VALUES (%s, %s)
			""", (user_id, token))
			
			cur.execute("""
				INSERT INTO logs (user_id, action)
				VALUES (%s, %s)
			""", (user_id, f'User {name} logged in'))
			
			conn.commit()
			
			session['user_id'] = user_id
			session['role'] = role
			session['token'] = token
			
			return redirect(url_for('index'))
				
		except psycopg2.Error as e:
			conn.rollback()
			flash(f'Login failed: {str(e)}')
			return render_template('login.html')
		finally:
			cur.close()
			conn.close()
	
	return render_template('login.html')

# Выход
@app.route('/logout')
@login_required()
def logout():
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("DELETE FROM sessions WHERE user_id = %s", (session['user_id'],))
		cur.execute("""
			INSERT INTO logs (user_id, action)
			VALUES (%s, %s)
		""", (session['user_id'], 'User logged out'))
		conn.commit()
	except psycopg2.Error:
		conn.rollback()
	finally:
		cur.close()
		conn.close()
	
	session.clear()
	flash('You have been logged out')
	return redirect(url_for('login'))

# Профиль покупателя (корзина и заказы)
@app.route('/profile', methods=['GET', 'POST'])
@login_required('customer')
def customer_profile():
	conn = get_db_connection()
	cur = conn.cursor()
	
	if request.method == 'POST':
		action = request.form.get('action')
		
		if action == 'remove':
			product_id = request.form.get('product_id')
			try:
				cur.execute("""
					DELETE FROM cart
					WHERE user_id = %s AND product_id = %s
				""", (session['user_id'], product_id))
				conn.commit()
				flash('Product removed from cart')
			except psycopg2.Error as e:
				conn.rollback()
				flash(f'Error removing product: {str(e)}')
		
		elif action == 'checkout':
			try:
				# Получаем товары из корзины
				cur.execute("""
					SELECT c.product_id, c.quantity, p.price
					FROM cart c
					JOIN products p ON c.product_id = p.id
					WHERE c.user_id = %s
				""", (session['user_id'],))
				cart_items = cur.fetchall()
				
				if not cart_items:
					flash('Your cart is empty')
					cur.close()
					conn.close()
					return redirect(url_for('customer_profile'))
				
				# Вычисляем общую стоимость
				total_price = sum(item[1] * item[2] for item in cart_items)
				
				# Создаём заказ
				cur.execute("""
					INSERT INTO orders (user_id, status, total_price)
					VALUES (%s, 'pending', %s) RETURNING id
				""", (session['user_id'], total_price))
				order_id = cur.fetchone()[0]
				
				# Добавляем товары в order_items и обновляем количество
				for item in cart_items:
					product_id, quantity, price = item
					cur.execute("""
						INSERT INTO order_items (order_id, product_id, quantity, price)
						VALUES (%s, %s, %s, %s)
					""", (order_id, product_id, quantity, price))
					cur.execute("""
						UPDATE products
						SET quantity = quantity - %s
						WHERE id = %s
					""", (quantity, product_id))
				
				# Очищаем корзину
				cur.execute("DELETE FROM cart WHERE user_id = %s", (session['user_id'],))
				
				# Логируем
				cur.execute("""
					INSERT INTO logs (user_id, action)
					VALUES (%s, %s)
				""", (session['user_id'], f'Order {order_id} created'))
				
				conn.commit()
				flash('Order placed successfully')
			except psycopg2.Error as e:
				conn.rollback()
				flash(f'Checkout failed: {str(e)}')
	
	cur.execute("""
		SELECT p.id, p.name, p.price, c.quantity
		FROM cart c
		JOIN products p ON c.product_id = p.id
		WHERE c.user_id = %s
	""", (session['user_id'],))
	cart_items = cur.fetchall()
	
	cur.execute("""
		SELECT id, status, total_price, created_at
		FROM orders
		WHERE user_id = %s
		ORDER BY created_at DESC
	""", (session['user_id'],))
	orders = cur.fetchall()
	
	cur.close()
	conn.close()
	return render_template('customer_profile.html', cart_items=cart_items, orders=orders)

# Admin: Панель
@app.route('/admin')
@login_required('admin')
def admin_panel():
	return render_template('admin_panel.html')

# Admin: Пользователи
@app.route('/admin/users')
@login_required('admin')
def admin_users():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT id, name, email, role FROM users")
	users = cur.fetchall()
	cur.close()
	conn.close()
	return render_template('admin_users.html', users=users)

# Admin: Товары
@app.route('/admin/products', methods=['GET', 'POST'])
@login_required('admin')
def admin_products():
	conn = get_db_connection()
	cur = conn.cursor()
	
	if request.method == 'POST':
		name = request.form.get('name')
		description = request.form.get('description')
		price = float(request.form.get('price'))
		quantity = int(request.form.get('quantity'))
		files = request.files.getlist('images')
		
		image_urls = []
		for file in files:
			if file and allowed_file(file.filename):
				filename = secure_filename(file.filename)
				file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
				file.save(file_path)
				image_urls.append(f"/{file_path}")
		
		try:
			cur.execute("""
				INSERT INTO products (name, description, price, quantity, image_urls, seller_id)
				VALUES (%s, %s, %s, %s, %s, NULL)
			""", (name, description, price, quantity, image_urls))
			conn.commit()
			flash('Product added successfully')
		except psycopg2.Error as e:
			conn.rollback()
			flash(f'Error adding product: {str(e)}')
	
	cur.execute("""
		SELECT p.id, p.name, p.description, p.price, p.quantity, p.image_urls, u.name
		FROM products p
		LEFT JOIN users u ON p.seller_id = u.id
	""")
	products = cur.fetchall()
	cur.close()
	conn.close()
	return render_template('admin_products.html', products=products)

# Admin: Заказы
@app.route('/admin/orders')
@login_required('admin')
def admin_orders():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, o.created_at, u.name
		FROM orders o
		JOIN users u ON o.user_id = u.id
		ORDER BY o.created_at DESC
	""")
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return render_template('admin_orders.html', orders=orders)

# Seller: Профиль
@app.route('/seller', methods=['GET', 'POST'])
@login_required('seller')
def seller_profile():
	conn = get_db_connection()
	cur = conn.cursor()
	
	if request.method == 'POST':
		name = request.form.get('name')
		description = request.form.get('description')
		price = float(request.form.get('price'))
		quantity = int(request.form.get('quantity'))
		files = request.files.getlist('images')
		
		image_urls = []
		for file in files:
			if file and allowed_file(file.filename):
				filename = secure_filename(file.filename)
				file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
				file.save(file_path)
				image_urls.append(f"/{file_path}")
		
		try:
			cur.execute("""
				INSERT INTO products (name, description, price, quantity, image_urls, seller_id)
				VALUES (%s, %s, %s, %s, %s, %s)
			""", (name, description, price, quantity, image_urls, session['user_id']))
			conn.commit()
			flash('Product added successfully')
		except psycopg2.Error as e:
			conn.rollback()
			flash(f'Error adding product: {str(e)}')
	
	cur.execute("""
		SELECT p.id, p.name, p.description, p.price, p.quantity, p.image_urls, u.name
		FROM products p
		JOIN users u ON p.seller_id = u.id
		WHERE p.seller_id = %s
	""", (session['user_id'],))
	products = cur.fetchall()
	cur.close()
	conn.close()
	return render_template('seller_profile.html', products=products)

# Seller: Заказы
@app.route('/seller/orders')
@login_required('seller')
def seller_orders():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT DISTINCT o.id, o.status, o.total_price, o.created_at, u.name
		FROM orders o
		JOIN users u ON o.user_id = u.id
		JOIN order_items oi ON o.id = oi.order_id
		JOIN products p ON oi.product_id = p.id
		WHERE p.seller_id = %s AND o.status != 'cancelled'
		ORDER BY o.created_at DESC
	""", (session['user_id'],))
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return render_template('seller_orders.html', orders=orders)

# Courier: Заказы
@app.route('/courier')
@login_required('courier')
def courier_orders():
	conn = get_db_connection()
	cur = conn.cursor()
	
	cur.execute("""
		SELECT o.id, o.status, o.total_price, d.status as delivery_status
		FROM orders o
		JOIN delivery d ON o.id = d.order_id
		WHERE d.courier_id = %s AND d.status != 'delivered'
	""", (session['user_id'],))
	active_orders = cur.fetchall()
	
	cur.execute("""
		SELECT o.id, o.status, o.total_price
		FROM orders o
		WHERE o.status = 'paid' AND NOT EXISTS (
			SELECT 1 FROM delivery d WHERE d.order_id = o.id
		)
	""")
	available_orders = cur.fetchall()
	
	cur.close()
	conn.close()
	return render_template('courier_orders.html', active_orders=active_orders, available_orders=available_orders)

if __name__ == '__main__':
	if not os.path.exists(UPLOAD_FOLDER):
		os.makedirs(UPLOAD_FOLDER)
	app.run('0.0.0.', 5723, debug=True)
