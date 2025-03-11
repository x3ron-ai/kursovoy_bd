import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

def get_db_connection():
	return psycopg2.connect(
		dbname=os.getenv('DB_NAME'),
		user=os.getenv('DB_USER'),
		password=os.getenv('DB_PASSWORD'),
		host=os.getenv('DB_HOST'),
		port=os.getenv('DB_PORT')
	)

# Пользователи
def get_user_by_email(email):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT id FROM users WHERE email = %s", (email,))
	result = cur.fetchone()
	cur.close()
	conn.close()
	return result

def create_user(name, email, password, role):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO users (name, email, password, role)
			VALUES (%s, %s, %s, %s) RETURNING id
		""", (name, email, password, role))
		user_id = cur.fetchone()[0]
		conn.commit()
		return user_id
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_user_by_credentials(email, password):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT id, name, role FROM users 
		WHERE email = %s AND password = %s
	""", (email, password))
	result = cur.fetchone()
	cur.close()
	conn.close()
	return result

def get_user_info(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT name, role, default_address FROM users WHERE id = %s", (user_id,))
	result = cur.fetchone()
	cur.close()
	conn.close()
	return result if result else (None, None, None)

def update_user_address(user_id, default_address):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			UPDATE users
			SET default_address = %s
			WHERE id = %s
		""", (default_address, user_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_all_users():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT id, name, email, role FROM users")
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

# Сессии
def create_session(user_id, token):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO sessions (user_id, token)
			VALUES (%s, %s)
		""", (user_id, token))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def delete_session(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

# Логи
def log_action(user_id, action):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO logs (user_id, action)
			VALUES (%s, %s)
		""", (user_id, action))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

# Товары
def get_all_products():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT p.id, p.name, p.description, p.price, p.quantity, p.image_urls, u.name
		FROM products p
		JOIN users u ON p.seller_id = u.id
	""")
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_products_by_seller(seller_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT p.id, p.name, p.description, p.price, p.quantity, p.image_urls, u.name
		FROM products p
		JOIN users u ON p.seller_id = u.id
		WHERE p.seller_id = %s
	""", (seller_id,))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_all_products_with_seller():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT p.id, p.name, p.description, p.price, p.quantity, p.image_urls, u.name
		FROM products p
		LEFT JOIN users u ON p.seller_id = u.id
	""")
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_product_quantity(product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT quantity FROM products WHERE id = %s", (product_id,))
	result = cur.fetchone()[0]
	cur.close()
	conn.close()
	return result

def get_product_seller(product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT seller_id FROM products WHERE id = %s", (product_id,))
	result = cur.fetchone()[0]
	cur.close()
	conn.close()
	return result

def add_product(name, description, price, quantity, image_urls, seller_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO products (name, description, price, quantity, image_urls, seller_id)
			VALUES (%s, %s, %s, %s, %s, %s)
		""", (name, description, price, quantity, image_urls, seller_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def update_product(product_id, name, description, price, quantity, image_urls):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			UPDATE products
			SET name = %s, description = %s, price = %s, quantity = %s, image_urls = %s
			WHERE id = %s
		""", (name, description, price, quantity, image_urls, product_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def delete_product(product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

# Корзина
def add_to_cart(user_id, product_id, quantity):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO cart (user_id, product_id, quantity)
			VALUES (%s, %s, %s)
			ON CONFLICT (user_id, product_id)
			DO UPDATE SET quantity = cart.quantity + %s
		""", (user_id, product_id, quantity, quantity))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def remove_from_cart(user_id, product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			DELETE FROM cart
			WHERE user_id = %s AND product_id = %s
		""", (user_id, product_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_cart_items(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT p.id, p.name, p.price, c.quantity
		FROM cart c
		JOIN products p ON c.product_id = p.id
		WHERE c.user_id = %s
	""", (user_id,))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def clear_cart(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

# Заказы
def update_order_status(order_id, new_status):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			UPDATE orders
			SET status = %s
			WHERE id = %s
		""", (new_status, order_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_user_orders(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT id, status, total_price, delivery_address, created_at
		FROM orders
		WHERE user_id = %s
		ORDER BY created_at DESC
	""", (user_id,))
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return orders

def get_all_orders():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, o.created_at, u.name
		FROM orders o
		JOIN users u ON o.user_id = u.id
		ORDER BY o.created_at DESC
	""")
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_seller_orders(seller_id):
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
	""", (seller_id,))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def create_order(user_id, total_price, delivery_address):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO orders (user_id, status, total_price, delivery_address)
			VALUES (%s, 'pending', %s, %s)
			RETURNING id
		""", (user_id, total_price, delivery_address))
		order_id = cur.fetchone()[0]
		conn.commit()
		return order_id
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def add_order_item(order_id, product_id, quantity, price):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO order_items (order_id, product_id, quantity, price)
			VALUES (%s, %s, %s, %s)
		""", (order_id, product_id, quantity, price))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def update_product_quantity(product_id, quantity):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			UPDATE products
			SET quantity = quantity - %s
			WHERE id = %s
		""", (quantity, product_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_cart_for_checkout(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT c.product_id, c.quantity, p.price
		FROM cart c
		JOIN products p ON c.product_id = p.id
		WHERE c.user_id = %s
	""", (user_id,))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

# Курьеры
def get_active_courier_orders(courier_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, d.status as delivery_status, d.estimated_delivery, d.delivered_at
		FROM orders o
		JOIN delivery d ON o.id = d.order_id
		WHERE d.courier_id = %s AND d.status != 'delivered'
	""", (courier_id,))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_available_orders():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price
		FROM orders o
		WHERE o.status = 'paid' AND NOT EXISTS (
			SELECT 1 FROM delivery d WHERE d.order_id = o.id
		)
	""")
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def assign_order_to_courier(order_id, courier_id, estimated_delivery):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO delivery (order_id, courier_id, status, estimated_delivery)
			VALUES (%s, %s, 'assigned', %s)
		""", (order_id, courier_id, estimated_delivery))
		cur.execute("""
			UPDATE orders
			SET status = 'in_delivery'
			WHERE id = %s
		""", (order_id,))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def update_delivery_status(order_id, courier_id, new_status):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		if new_status == 'delivered':
			cur.execute("""
				UPDATE delivery
				SET status = %s, delivered_at = %s
				WHERE order_id = %s AND courier_id = %s
			""", (new_status, datetime.now(), order_id, courier_id))
			cur.execute("""
				UPDATE orders
				SET status = 'completed'
				WHERE id = %s
			""", (order_id,))
		else:
			cur.execute("""
				UPDATE delivery
				SET status = %s
				WHERE order_id = %s AND courier_id = %s
			""", (new_status, order_id, courier_id))
			cur.execute("""
				UPDATE orders
				SET status = 'in_delivery'
				WHERE id = %s
			""", (order_id,))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def check_courier_assignment(order_id, courier_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT COUNT(*) 
		FROM delivery 
		WHERE order_id = %s AND courier_id = %s
	""", (order_id, courier_id))
	result = cur.fetchone()[0]
	cur.close()
	conn.close()
	return result > 0
