from flask import Flask, request, render_template, redirect, url_for, session, flash
import hashlib
import secrets
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from db import (
	get_db_connection, get_user_by_email, create_user, get_user_by_credentials,
	get_user_info, get_all_users, create_session, delete_session, log_action,
	get_all_products, get_products_by_seller, get_all_products_with_seller,
	get_product_quantity, get_product_seller, add_product, update_product,
	delete_product, add_to_cart, remove_from_cart, get_cart_items, clear_cart,
	get_user_orders, get_all_orders, get_seller_orders, create_order,
	add_order_item, update_product_quantity, get_cart_for_checkout,
	get_active_courier_orders, get_available_orders, assign_order_to_courier,
	update_delivery_status, check_courier_assignment, update_order_status,
	update_user_address
)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

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
	if request.method == 'POST' and session['role'] == 'customer':
		product_id = request.form.get('product_id')
		quantity = int(request.form.get('quantity', 1))
		
		try:
			available = get_product_quantity(product_id)
			if quantity > available:
				flash(f'Only {available} items available')
			else:
				add_to_cart(session['user_id'], product_id, quantity)
				flash('Product added to cart')
		except Exception as e:
			flash(f'Error adding to cart: {str(e)}')
	
	products = get_all_products()
	name, role, default_address = get_user_info(session['user_id'])
	return render_template('index.html', products=products, name=name, role=role)

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

		if get_user_by_email(email):
			flash('Email already exists')
			return render_template('register.html')

		try:
			user_id = create_user(name, email, hashed_password, role)
			log_action(user_id, f'User {name} registered')
			flash('Registration successful! Please login.')
			return redirect(url_for('login'))
		except Exception as e:
			flash(f'Registration failed: {str(e)}')
			return render_template('register.html')
	
	return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		email = request.form.get('email')
		password = request.form.get('password')
		hashed_password = hashlib.sha256(password.encode()).hexdigest()

		user = get_user_by_credentials(email, hashed_password)
		if not user:
			flash('Invalid credentials')
			return render_template('login.html')

		user_id, name, role = user
		
		try:
			token = secrets.token_hex(16)
			create_session(user_id, token)
			log_action(user_id, f'User {name} logged in')
			
			session['user_id'] = user_id
			session['role'] = role
			session['token'] = token
			
			return redirect(url_for('index'))
		except Exception as e:
			flash(f'Login failed: {str(e)}')
			return render_template('login.html')
	
	return render_template('login.html')

@app.route('/logout')
@login_required()
def logout():
	try:
		delete_session(session['user_id'])
		log_action(session['user_id'], 'User logged out')
	except Exception:
		flash('Error during logout')
	
	session.clear()
	flash('You have been logged out')
	return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required('customer')
def customer_profile():
	if request.method == 'POST':
		action = request.form.get('action')
		
		if action == 'remove':
			product_id = request.form.get('product_id')
			try:
				remove_from_cart(session['user_id'], product_id)
				flash('Product removed from cart')
			except Exception as e:
				flash(f'Error removing product: {str(e)}')
		
		elif action == 'checkout':
			try:
				cart_items = get_cart_for_checkout(session['user_id'])
				if not cart_items:
					flash('Your cart is empty')
					return redirect(url_for('customer_profile'))
				
				total_price = sum(item[1] * item[2] for item in cart_items)
				delivery_address = request.form.get('delivery_address')
				name, role, default_address = get_user_info(session['user_id'])
				if not delivery_address and default_address:
					delivery_address = default_address
				elif not delivery_address:
					flash('Please provide a delivery address or set a default address')
					return redirect(url_for('customer_profile'))
				
				order_id = create_order(session['user_id'], total_price, delivery_address)
				
				for item in cart_items:
					product_id, quantity, price = item
					add_order_item(order_id, product_id, quantity, price)
					update_product_quantity(product_id, quantity)
				
				clear_cart(session['user_id'])
				log_action(session['user_id'], f'Order {order_id} created')
				flash('Order placed successfully')
			except Exception as e:
				flash(f'Checkout failed: {str(e)}')
		
		elif action == 'pay':
			order_id = request.form.get('order_id')
			try:
				update_order_status(order_id, 'paid')
				log_action(session['user_id'], f'Order {order_id} paid')
				flash('Order marked as paid')
			except Exception as e:
				flash(f'Error marking order as paid: {str(e)}')
		
		elif action == 'update_address':
			default_address = request.form.get('default_address')
			try:
				update_user_address(session['user_id'], default_address)
				flash('Default address updated successfully')
			except Exception as e:
				flash(f'Error updating address: {str(e)}')
	
	cart_items = get_cart_items(session['user_id'])
	orders = get_user_orders(session['user_id'])
	name, role, default_address = get_user_info(session['user_id'])
	return render_template('customer_profile.html', cart_items=cart_items, orders=orders, default_address=default_address)

@app.route('/admin')
@login_required('admin')
def admin_panel():
	return render_template('admin_panel.html')

@app.route('/admin/users')
@login_required('admin')
def admin_users():
	users = get_all_users()
	return render_template('admin_users.html', users=users)

@app.route('/admin/products', methods=['GET', 'POST'])
@login_required('admin')
def admin_products():
	if request.method == 'POST':
		action = request.form.get('action')
		
		if action == 'add':
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
				add_product(name, description, price, quantity, image_urls, None)
				flash('Product added successfully')
			except Exception as e:
				flash(f'Error adding product: {str(e)}')
		
		elif action == 'edit':
			product_id = request.form.get('product_id')
			name = request.form.get('name')
			description = request.form.get('description')
			price = float(request.form.get('price'))
			quantity = int(request.form.get('quantity'))
			files = request.files.getlist('images')
			
			image_urls = request.form.getlist('existing_images')
			for file in files:
				if file and allowed_file(file.filename):
					filename = secure_filename(file.filename)
					file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
					file.save(file_path)
					image_urls.append(f"/{file_path}")
			
			try:
				update_product(product_id, name, description, price, quantity, image_urls)
				flash('Product updated successfully')
			except Exception as e:
				flash(f'Error updating product: {str(e)}')
		
		elif action == 'delete':
			product_id = request.form.get('product_id')
			try:
				delete_product(product_id)
				flash('Product deleted successfully')
			except Exception as e:
				flash(f'Error deleting product: {str(e)}')
	
	products = get_all_products_with_seller()
	return render_template('admin_products.html', products=products)

@app.route('/admin/orders')
@login_required('admin')
def admin_orders():
	orders = get_all_orders()
	return render_template('admin_orders.html', orders=orders)

@app.route('/seller', methods=['GET', 'POST'])
@login_required('seller')
def seller_profile():
	if request.method == 'POST':
		action = request.form.get('action')
		
		if action == 'add':
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
				add_product(name, description, price, quantity, image_urls, session['user_id'])
				flash('Product added successfully')
			except Exception as e:
				flash(f'Error adding product: {str(e)}')
		
		elif action == 'edit':
			product_id = request.form.get('product_id')
			name = request.form.get('name')
			description = request.form.get('description')
			price = float(request.form.get('price'))
			quantity = int(request.form.get('quantity'))
			files = request.files.getlist('images')
			
			seller_id = get_product_seller(product_id)
			if seller_id != session['user_id']:
				flash('You can only edit your own products')
				return redirect(url_for('seller_profile'))
			
			image_urls = request.form.getlist('existing_images')
			for file in files:
				if file and allowed_file(file.filename):
					filename = secure_filename(file.filename)
					file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
					file.save(file_path)
					image_urls.append(f"/{file_path}")
			
			try:
				update_product(product_id, name, description, price, quantity, image_urls)
				flash('Product updated successfully')
			except Exception as e:
				flash(f'Error updating product: {str(e)}')
		
		elif action == 'delete':
			product_id = request.form.get('product_id')
			seller_id = get_product_seller(product_id)
			if seller_id != session['user_id']:
				flash('You can only delete your own products')
				return redirect(url_for('seller_profile'))
			
			try:
				delete_product(product_id)
				flash('Product deleted successfully')
			except Exception as e:
				flash(f'Error deleting product: {str(e)}')
	
	products = get_products_by_seller(session['user_id'])
	return render_template('seller_profile.html', products=products)

@app.route('/seller/orders')
@login_required('seller')
def seller_orders():
	orders = get_seller_orders(session['user_id'])
	return render_template('seller_orders.html', orders=orders)

@app.route('/courier', methods=['GET', 'POST'])
@login_required('courier')
def courier_orders():
	if request.method == 'POST':
		action = request.form.get('action')
		
		if action == 'assign':
			order_id = request.form.get('order_id')
			estimated_delivery_str = request.form.get('estimated_delivery')
			if not estimated_delivery_str:  # Добавлена проверка на None или пустую строку
				flash('Please provide an estimated delivery time')
				return redirect(url_for('courier_orders'))
			try:
				estimated_delivery = datetime.strptime(estimated_delivery_str, '%Y-%m-%dT%H:%M')
				if estimated_delivery < datetime.now():
					flash('Estimated delivery cannot be in the past')
				else:
					assign_order_to_courier(order_id, session['user_id'], estimated_delivery)
					log_action(session['user_id'], f'Order {order_id} assigned to courier')
					flash('Order assigned successfully')
			except ValueError:
				flash('Invalid date format. Use YYYY-MM-DD HH:MM')
			except Exception as e:
				flash(f'Error assigning order: {str(e)}')
		
		elif action == 'update_status':
			order_id = request.form.get('order_id')
			new_status = request.form.get('new_status')
			if new_status not in ['in transit', 'delivered']:
				flash('Invalid status')
				return redirect(url_for('courier_orders'))
			
			if not check_courier_assignment(order_id, session['user_id']):
				flash('You can only update your own deliveries')
				return redirect(url_for('courier_orders'))
			
			try:
				update_delivery_status(order_id, session['user_id'], new_status)
				log_action(session['user_id'], f'Delivery status for order {order_id} updated to {new_status}')
				flash(f'Delivery status updated to {new_status}')
			except Exception as e:
				flash(f'Error updating status: {str(e)}')
		
		elif action == 'cancel':
			order_id = request.form.get('order_id')
			if not check_courier_assignment(order_id, session['user_id']):
				flash('You can only cancel your own deliveries')
				return redirect(url_for('courier_orders'))
			
			try:
				cancel_delivery(order_id, session['user_id'])
				log_action(session['user_id'], f'Delivery for order {order_id} cancelled')
				flash('Delivery cancelled successfully')
			except Exception as e:
				flash(f'Error cancelling delivery: {str(e)}')
	
	active_orders = get_active_courier_orders(session['user_id'])
	available_orders = get_available_orders()
	return render_template('courier_orders.html', active_orders=active_orders, available_orders=available_orders)

if __name__ == '__main__':
	if not os.path.exists(UPLOAD_FOLDER):
		os.makedirs(UPLOAD_FOLDER)
	app.run(debug=True)
