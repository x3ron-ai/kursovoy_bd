from flask import Flask, request, render_template, redirect, url_for, session, flash, send_file
from prometheus_flask_exporter import PrometheusMetrics, Gauge
import hashlib
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import subprocess
from db import (
	get_db_connection, get_user_by_email, create_user, get_user_by_credentials,
	get_user_info, get_all_products, get_products_by_seller, add_product,
	update_product, delete_product, get_product_seller, get_product_quantity,
	add_to_cart, get_cart_items, remove_from_cart, clear_cart,
	get_cart_for_checkout, get_user_orders, get_all_orders, get_seller_orders,
	update_order_status, assign_order_to_courier, get_active_courier_orders,
	get_available_orders, update_delivery_status, check_courier_assignment,
	cancel_delivery, log_action, get_logs, load_db_dump
)

app = Flask(__name__)

########### МЕТРИКИ ###########



metrics = PrometheusMetrics(app, path=None)




########### МЕТРИКИ ###########
app.secret_key = os.urandom(16)

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
	return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

@app.route('/', methods=['GET', 'POST'])
@login_required()
def index():
	search = request.args.get('search', '')
	products = get_all_products(search)
	if request.method == 'POST' and session['role'] == 'customer':
		product_id = request.form.get('product_id')
		quantity = int(request.form.get('quantity', 1))
		available = get_product_quantity(product_id)
		if quantity > available:
			flash(f'Only {available} items available')
		else:
			add_to_cart(session['user_id'], product_id, quantity)
			log_action(session['user_id'], f"Added {quantity} of product {product_id} to cart")
			flash('Product added to cart')
	name, role = get_user_info(session['user_id'])
	return render_template('index.html', products=products, name=name, role=role, search=search)

@app.route('/register', methods=['GET', 'POST'])
def register():
	if request.method == 'POST':
		name = request.form.get('name')
		email = request.form.get('email')
		password = hashlib.sha256(request.form.get('password').encode()).hexdigest()
		role = request.form.get('role')
		if get_user_by_email(email):
			flash('Email already exists')
		else:
			user_id = create_user(name, email, password, role)
			log_action(user_id, f"User {name} registered")
			flash('Registration successful! Please login.')
			return redirect(url_for('login'))
	return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		email = request.form.get('email')
		password = hashlib.sha256(request.form.get('password').encode()).hexdigest()
		user = get_user_by_credentials(email, password)
		if user:
			session['user_id'] = user[0]
			session['role'] = user[2]
			log_action(user[0], f"User {user[1]} logged in")
			flash('Logged in successfully')
			return redirect(url_for('index'))
		flash('Invalid credentials')
	return render_template('login.html')

@app.route('/logout')
@login_required()
def logout():
	log_action(session['user_id'], "User logged out")
	session.clear()
	flash('Logged out')
	return redirect(url_for('login'))

@app.route('/customer', methods=['GET', 'POST'])
@login_required('customer')
def customer_profile():
	if request.method == 'POST':
		action = request.form.get('action')
		if action == 'remove':
			product_id = request.form.get('product_id')
			remove_from_cart(session['user_id'], product_id)
			log_action(session['user_id'], f"Removed product {product_id} from cart")
			flash('Item removed from cart')
		elif action == 'checkout':
			cart_items = get_cart_for_checkout(session['user_id'])
			if not cart_items:
				flash('Cart is empty')
			else:
				cart_array = [[item[0], item[1]] for item in cart_items]
				conn = get_db_connection()
				cur = conn.cursor()
				try:
					cur.execute("CALL create_order_with_items(%s, %s, %s)", 
							(session['user_id'], request.form.get('delivery_address'), cart_array))
					conn.commit()
					flash('Order placed successfully')
				except psycopg2.Error as e:
					conn.rollback()
					flash(f'Error placing order: {str(e)}')
				finally:
					cur.close()
					conn.close()
		elif action == 'pay':
			order_id = request.form.get('order_id')
			update_order_status(order_id, 'paid')
			log_action(session['user_id'], f"Order {order_id} paid")
			flash('Order paid')
	cart_items = get_cart_items(session['user_id'])
	status_filter = request.args.get('status', '')
	orders = get_user_orders(session['user_id'], status_filter)
	return render_template('customer_profile.html', cart_items=cart_items, orders=orders, status_filter=status_filter)

@app.route('/admin')
@login_required('admin')
def admin_panel():
	return render_template('admin_panel.html')

@app.route('/admin/backup', methods=['GET'])
@login_required('admin')
def admin_backup():
	load_db_dump()
	return send_file('backup.dump', as_attachment=True)

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required('admin')
def admin_users():
	if request.method == 'POST':
		action = request.form.get('action')
		if action == 'add':
			name = request.form.get('name')
			email = request.form.get('email')
			password = hashlib.sha256(request.form.get('password').encode()).hexdigest()  # Хешируем пароль
			role = request.form.get('role')
			if get_user_by_email(email):
				flash('Email already exists')
			else:
				user_id = create_user(name, email, password, role)
				log_action(request.user_id, f"Admin added user {name} with ID {user_id}")
				flash('User added successfully')
		elif action == 'delete':
			user_id = request.form.get('user_id')
			delete_user(user_id)
			log_action(request.user_id, f"Admin deleted user with ID {user_id}")
			flash('User deleted successfully')
	users = get_all_users()
	return render_template('admin_users.html', users=users)

@app.route('/admin/products', methods=['GET', 'POST'])
@login_required('admin')
def admin_products():
	search = request.args.get('search', '')
	if request.method == 'POST':
		action = request.form.get('action')
		if action == 'add':
			name = request.form.get('name')
			description = request.form.get('description')
			price = float(request.form.get('price'))
			quantity = int(request.form.get('quantity'))
			seller_id = int(request.form.get('seller_id'))  # Получаем seller_id из формы
			files = request.files.getlist('images')
			image_urls = []
			for f in files:
				if f and allowed_file(f.filename):
					filename = secure_filename(f.filename)
					file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
					f.save(file_path)
					image_urls.append(file_path)
			add_product(name, description, price, quantity, image_urls, seller_id)  # Передаём seller_id
			flash('Product added')
		elif action == 'edit':
			product_id = request.form.get('product_id')
			name = request.form.get('name')
			description = request.form.get('description')
			price = float(request.form.get('price'))
			quantity = int(request.form.get('quantity'))
			image_urls = request.form.getlist('existing_images')
			files = request.files.getlist('images')
			for f in files:
				if f and allowed_file(f.filename):
					filename = secure_filename(f.filename)
					file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
					f.save(file_path)
					image_urls.append(file_path)
			update_product(product_id, name, description, price, quantity, image_urls)
			flash('Product updated')
		elif action == 'delete':
			product_id = request.form.get('product_id')
			delete_product(product_id)
			flash('Product deleted')
	products = get_all_products(search)
	# Получаем список продавцов
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT id, name FROM users WHERE role = 'seller'")
	sellers = cur.fetchall()
	cur.close()
	conn.close()
	return render_template('admin_products.html', products=products, search=search, sellers=sellers)

@app.route('/admin/orders')
@login_required('admin')
def admin_orders():
	status_filter = request.args.get('status', '')
	orders = get_all_orders(status_filter)
	return render_template('admin_orders.html', orders=orders, status_filter=status_filter)

@app.route('/admin/logs')
@login_required('admin')
def admin_logs():
	action_filter = request.args.get('action', '')
	logs = get_logs(action_filter)
	return render_template('admin_logs.html', logs=logs, action_filter=action_filter)

@app.route('/seller', methods=['GET', 'POST'])
@login_required('seller')
def seller_profile():
	search = request.args.get('search', '')
	if request.method == 'POST':
		action = request.form.get('action')
		if action == 'add':
			name = request.form.get('name')
			description = request.form.get('description')
			price = float(request.form.get('price'))
			quantity = int(request.form.get('quantity'))
			files = request.files.getlist('images')
			image_urls = []
			for f in files:
				if f and allowed_file(f.filename):
					filename = secure_filename(f.filename)
					file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
					f.save(file_path)
					image_urls.append(file_path)
			add_product(name, description, price, quantity, image_urls, session['user_id'])
			flash('Product added')
		elif action == 'edit' and get_product_seller(request.form.get('product_id')) == session['user_id']:
			product_id = request.form.get('product_id')
			name = request.form.get('name')
			description = request.form.get('description')
			price = float(request.form.get('price'))
			quantity = int(request.form.get('quantity'))
			image_urls = request.form.getlist('existing_images')
			files = request.files.getlist('images')
			for f in files:
				if f and allowed_file(f.filename):
					filename = secure_filename(f.filename)
					file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
					f.save(file_path)
					image_urls.append(file_path)
			update_product(product_id, name, description, price, quantity, image_urls)
			flash('Product updated')
		elif action == 'delete' and get_product_seller(request.form.get('product_id')) == session['user_id']:
			product_id = request.form.get('product_id')
			delete_product(product_id)
			flash('Product deleted')
	products = get_products_by_seller(session['user_id'], search)
	return render_template('seller_profile.html', products=products, search=search)

@app.route('/seller/orders')
@login_required('seller')
def seller_orders():
	status_filter = request.args.get('status', '')
	orders = get_seller_orders(session['user_id'], status_filter)
	return render_template('seller_orders.html', orders=orders, status_filter=status_filter)

@app.route('/courier', methods=['GET', 'POST'])
@login_required('courier')
def courier_orders():
	if request.method == 'POST':
		action = request.form.get('action')
		if action == 'assign':
			order_id = request.form.get('order_id')
			estimated_delivery = request.form.get('estimated_delivery')
			assign_order_to_courier(order_id, session['user_id'], estimated_delivery)
			flash('Order assigned')
		elif action == 'update_status' and check_courier_assignment(request.form.get('order_id'), session['user_id']):
			order_id = request.form.get('order_id')
			new_status = request.form.get('new_status')
			update_delivery_status(order_id, session['user_id'], new_status)
			flash('Status updated')
		elif action == 'cancel' and check_courier_assignment(request.form.get('order_id'), session['user_id']):
			order_id = request.form.get('order_id')
			reason = request.form.get('reason', 'No reason provided')
			cancel_delivery(order_id, session['user_id'], reason)
			flash('Delivery cancelled')
	active_orders = get_active_courier_orders(session['user_id'])
	available_orders = get_available_orders()
	return render_template('courier_orders.html', active_orders=active_orders, available_orders=available_orders)

if __name__ == '__main__':
	if not os.path.exists(UPLOAD_FOLDER):
		os.makedirs(UPLOAD_FOLDER)
	app.run(debug=True)
