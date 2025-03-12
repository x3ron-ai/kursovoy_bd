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
	get_product_quantity, get_product_seller, create_product, update_product,
	get_seller_products, update_product_quantity, add_product_image,
	delete_product, add_to_cart, remove_from_cart, get_cart_items, clear_cart,
	get_user_orders, get_all_orders, get_seller_orders, create_order,
	add_order_item, update_product_quantity, get_cart_for_checkout,
	get_active_courier_orders, get_available_orders, assign_order_to_courier,
	update_delivery_status, check_courier_assignment, update_order_status,
	update_user_address, create_warehouse, get_warehouses_by_seller,
	update_warehouse, delete_warehouse, add_product_to_warehouse,
	get_products_by_warehouse, update_product_quantity_in_warehouse,
	remove_product_from_warehouse, get_warehouse_orders,
	create_parent_order, get_parent_order, update_parent_order_status,
	get_user_parent_orders, create_warehouse_worker, get_sub_orders,
	get_warehouse_orders_for_user, get_product_quantity_in_warehouse
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

		if role not in ['customer', 'seller', 'courier']:  # Убрана роль warehouseman
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
		if action == 'checkout':
			try:
				cart_items = get_cart_for_checkout(session['user_id'])
				if not cart_items:
					flash('Your cart is empty')
					return redirect(url_for('customer_profile'))
				
				items_by_seller = {}
				for item in cart_items:
					product_id, quantity, price, seller_id = item
					if seller_id not in items_by_seller:
						items_by_seller[seller_id] = []
					items_by_seller[seller_id].append((product_id, quantity, price))
				
				delivery_address = request.form.get('delivery_address')
				name, role, default_address = get_user_info(session['user_id'])
				if not delivery_address and default_address:
					delivery_address = default_address
				elif not delivery_address:
					flash('Please provide a delivery address or set a default address')
					return redirect(url_for('customer_profile'))
				
				total_price = sum(item[1] * item[2] for item in cart_items)
				parent_order_id = create_parent_order(session['user_id'], total_price, delivery_address)
				
				sub_order_ids = []
				# Если только один продавец и все товары на одном складе
				if len(items_by_seller) == 1:
					seller_id = next(iter(items_by_seller))
					items = items_by_seller[seller_id]
					warehouses = get_warehouses_by_seller(seller_id)
					if len(warehouses) == 1 and all(
						get_product_quantity_in_warehouse(warehouses[0][0], item[0]) >= item[1] 
						for item in items
					):
						# Один подзаказ
						warehouse_id = warehouses[0][0]
						order_id = create_order(session['user_id'], total_price, delivery_address, warehouse_id, parent_order_id, seller_id)
						sub_order_ids.append(order_id)
						for product_id, quantity, price in items:
							add_order_item(order_id, product_id, quantity, price)
							update_product_quantity_in_warehouse(warehouse_id, product_id, -quantity)
					else:
						# Дробление по складам
						for warehouse in warehouses:
							warehouse_id = warehouse[0]
							sub_items = []
							remaining_items = []
							for product_id, quantity, price in items:
								available = get_product_quantity_in_warehouse(warehouse_id, product_id)
								if available >= quantity:
									sub_items.append((product_id, quantity, price))
								elif available > 0:
									sub_items.append((product_id, available, price))
									remaining_items.append((product_id, quantity - available, price))
								else:
									remaining_items.append((product_id, quantity, price))
							
							if sub_items:
								sub_total = sum(q * p for _, q, p in sub_items)
								order_id = create_order(session['user_id'], sub_total, delivery_address, warehouse_id, parent_order_id, seller_id)
								sub_order_ids.append(order_id)
								for product_id, quantity, price in sub_items:
									add_order_item(order_id, product_id, quantity, price)
									update_product_quantity_in_warehouse(warehouse_id, product_id, -quantity)
							items = remaining_items
				else:
					# Несколько продавцов
					for seller_id, items in items_by_seller.items():
						seller_total = sum(item[1] * item[2] for item in items)
						warehouses = get_warehouses_by_seller(seller_id)
						if not warehouses:
							raise Exception(f"No warehouses found for seller {seller_id}")
						for warehouse in warehouses:
							warehouse_id = warehouse[0]
							sub_items = []
							remaining_items = []
							for product_id, quantity, price in items:
								available = get_product_quantity_in_warehouse(warehouse_id, product_id)
								if available >= quantity:
									sub_items.append((product_id, quantity, price))
								elif available > 0:
									sub_items.append((product_id, available, price))
									remaining_items.append((product_id, quantity - available, price))
								else:
									remaining_items.append((product_id, quantity, price))
							
							if sub_items:
								sub_total = sum(q * p for _, q, p in sub_items)
								order_id = create_order(session['user_id'], sub_total, delivery_address, warehouse_id, parent_order_id, seller_id)
								sub_order_ids.append(order_id)
								for product_id, quantity, price in sub_items:
									add_order_item(order_id, product_id, quantity, price)
									update_product_quantity_in_warehouse(warehouse_id, product_id, -quantity)
							items = remaining_items
				
				# Обновление статуса после оплаты
				for order_id in sub_order_ids:
					update_order_status(order_id, 'paid')
				update_parent_order_status(parent_order_id, 'paid')
				
				clear_cart(session['user_id'])
				log_action(session['user_id'], f'Parent order {parent_order_id} created')
				flash('Order placed successfully')
			except Exception as e:
				flash(f'Checkout failed: {str(e)}')
	
	cart_items = get_cart_items(session['user_id'])
	orders = get_user_parent_orders(session['user_id'])
	name, role, default_address = get_user_info(session['user_id'])
	return render_template('customer_profile.html', cart_items=cart_items, orders=orders, default_address=default_address)

@app.route('/seller', methods=['GET', 'POST'])
@login_required('seller')
def seller_profile():
	if request.method == 'POST':
		action = request.form.get('action')
		
		if action == 'add_warehouse':
			address = request.form.get('address')
			try:
				create_warehouse(session['user_id'], address)
				flash('Warehouse added successfully')
			except Exception as e:
				flash(f'Error adding warehouse: {str(e)}')
		
		elif action == 'add_warehouseman':
			email = request.form.get('email')
			name = request.form.get('name')
			password = request.form.get('password')
			warehouse_id = request.form.get('warehouse_id')
			try:
				create_warehouse_worker(session['user_id'], email, name, password, warehouse_id)
				flash('Warehouseman added successfully')
			except Exception as e:
				flash(f'Error adding warehouseman: {str(e)}')
		
		elif action == 'mark_assembled':
			order_id = request.form.get('order_id')
			try:
				update_order_status(order_id, 'assembled')
				sub_order = next(o for o in get_seller_orders(session['user_id']) if o[0] == int(order_id))
				parent_order_id = sub_order[6]
				sub_orders = get_sub_orders(parent_order_id)
				if all(o[1] == 'assembled' for o in sub_orders):
					update_parent_order_status(parent_order_id, 'assembled')
				log_action(session['user_id'], f'Order {order_id} marked as assembled')
				flash('Order marked as assembled')
			except Exception as e:
				flash(f'Error marking order as assembled: {str(e)}')
		
		elif action == 'add_product':
			name = request.form.get('name')
			description = request.form.get('description')
			price = float(request.form.get('price'))
			quantity = int(request.form.get('quantity'))
			warehouse_id = request.form.get('warehouse_id')
			try:
				product_id = create_product(session['user_id'], name, description, price, warehouse_id, quantity)
				if 'images' in request.files:
					files = request.files.getlist('images')
					for file in files:
						if file and allowed_file(file.filename):
							filename = secure_filename(file.filename)
							file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
							file.save(file_path)
							add_product_image(product_id, url_for('static', filename='uploads/' + filename))
				flash('Product added successfully')
			except Exception as e:
				flash(f'Error adding product: {str(e)}')
		
		elif action == 'update_product':
			product_id = int(request.form.get('product_id'))
			name = request.form.get('name')
			description = request.form.get('description')
			price = float(request.form.get('price'))
			quantity = int(request.form.get('quantity'))
			warehouse_id = request.form.get('warehouse_id')
			try:
				update_product(product_id, session['user_id'], name, description, price, warehouse_id, quantity)
				if 'images' in request.files:
					files = request.files.getlist('images')
					for file in files:
						if file and allowed_file(file.filename):
							filename = secure_filename(file.filename)
							file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
							file.save(file_path)
							add_product_image(product_id, url_for('static', filename='uploads/' + filename))
				flash('Product updated successfully')
			except Exception as e:
				flash(f'Error updating product: {str(e)}')
		
		elif action == 'delete_product':
			product_id = int(request.form.get('product_id'))
			try:
				delete_product(product_id, session['user_id'])
				flash('Product deleted successfully')
			except Exception as e:
				flash(f'Error deleting product: {str(e)}')
	
	warehouses = get_warehouses_by_seller(session['user_id'])
	orders = get_seller_orders(session['user_id'])
	products = get_seller_products(session['user_id'])
	if orders is None:
		print("Warning: orders is None")
		orders = []
	return render_template('seller_profile.html', warehouses=warehouses, orders=orders, products=products)

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
			if not estimated_delivery_str:
				flash('Please provide an estimated delivery time')
				return redirect(url_for('courier_orders'))
			try:
				estimated_delivery = datetime.strptime(estimated_delivery_str, '%Y-%m-%dT%H:%M')
				if estimated_delivery < datetime.now():
					flash('Estimated delivery cannot be in the past')
				else:
					assign_order_to_courier(order_id, session['user_id'], estimated_delivery)
					update_order_status(order_id, 'in delivery')
					sub_order = next(o for o in get_available_orders() if o[0] == int(order_id))
					parent_order_id = sub_order[6]
					sub_orders = get_sub_orders(parent_order_id)
					if all(any(a[0] == s[0] for a in get_active_courier_orders(session['user_id'])) for s in sub_orders):
						update_parent_order_status(parent_order_id, 'in delivery')
					log_action(session['user_id'], f'Order {order_id} assigned to courier')
					flash('Order assigned successfully')
			except ValueError:
				flash('Invalid date format. Use YYYY-MM-DD HH:MM')
			except Exception as e:
				flash(f'Error assigning order: {str(e)}')
		
		elif action == 'update_status':
			order_id = request.form.get('order_id')
			new_status = request.form.get('new_status')
			if new_status not in ['in delivery', 'delivered']:
				flash('Invalid status')
				return redirect(url_for('courier_orders'))
			if not check_courier_assignment(order_id, session['user_id']):
				flash('You can only update your own deliveries')
				return redirect(url_for('courier_orders'))
			try:
				update_delivery_status(order_id, session['user_id'], new_status)
				if new_status == 'delivered':
					update_order_status(order_id, 'delivered')
					sub_order = next(o for o in get_active_courier_orders(session['user_id']) if o[0] == int(order_id))
					parent_order_id = sub_order[6]
					sub_orders = get_sub_orders(parent_order_id)
					if all(any(a[0] == s[0] and a[3] == 'delivered' for a in get_active_courier_orders(session['user_id'])) for s in sub_orders):
						update_parent_order_status(parent_order_id, 'delivered')
				log_action(session['user_id'], f'Delivery status for order {order_id} updated to {new_status}')
				flash(f'Delivery status updated to {new_status}')
			except Exception as e:
				flash(f'Error updating status: {str(e)}')
	
	active_orders = get_active_courier_orders(session['user_id'])
	available_orders = get_available_orders()
	return render_template('courier_orders.html', active_orders=active_orders, available_orders=available_orders)

@app.route('/warehouseman', methods=['GET', 'POST'])
@login_required('warehouseman')
def warehouseman_profile():
	if request.method == 'POST':
		action = request.form.get('action')
		if action == 'mark_assembled':
			order_id = request.form.get('order_id')
			try:
				update_order_status(order_id, 'in assembly')  # Начинаем сборку
				update_order_status(order_id, 'assembled')	# Завершаем сборку
				sub_order = next(o for o in get_warehouse_orders_for_user(session['user_id']) if o[0] == int(order_id))
				parent_order_id = sub_order[6]
				sub_orders = get_sub_orders(parent_order_id)
				if all(o[1] == 'assembled' for o in sub_orders):
					update_parent_order_status(parent_order_id, 'assembled')
				log_action(session['user_id'], f'Order {order_id} marked as assembled by warehouseman')
				flash('Order marked as assembled')
			except Exception as e:
				flash(f'Error marking order as assembled: {str(e)}')
	
	orders = get_warehouse_orders_for_user(session['user_id'])
	return render_template('warehouseman_profile.html', orders=orders)

if __name__ == '__main__':
	if not os.path.exists(UPLOAD_FOLDER):
		os.makedirs(UPLOAD_FOLDER)
	app.run(debug=True)
