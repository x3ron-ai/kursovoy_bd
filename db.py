import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
import subprocess
load_dotenv()

def load_db_dump():
	subprocess.run( ["pg_dump", "-U", os.getenv('DB_USER'), "-d", os.getenv('DB_NAME'), "-F", "p", "-f", 'backup.dump'], check=True)

def get_db_connection():
	return psycopg2.connect(
		dbname=os.getenv('DB_NAME'),
		user=os.getenv('DB_USER'),
		password=os.getenv('DB_PASSWORD'),
		host=os.getenv('DB_HOST'),
		port=os.getenv('DB_PORT')
	)

def get_user_by_email(email):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT id FROM users WHERE email = %s", (email,))
	result = cur.fetchone()
	cur.close()
	conn.close()
	return result

def get_all_users():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT id, name, email, role FROM users")
	users = cur.fetchall()
	cur.close()
	conn.close()
	return users

def delete_user(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
	conn.commit()
	cur.close()
	conn.close()

def create_user(name, email, password, role):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s) RETURNING id", 
			(name, email, password, role))
	user_id = cur.fetchone()[0]
	conn.commit()
	cur.close()
	conn.close()
	return user_id

def get_user_by_credentials(email, password):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT id, name, role FROM users WHERE email = %s AND password = %s", (email, password))
	result = cur.fetchone()
	cur.close()
	conn.close()
	return result

def get_user_info(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT name, role FROM users WHERE id = %s", (user_id,))
	result = cur.fetchone()
	cur.close()
	conn.close()
	return result if result else (None, None)

def get_all_products(search=''):
	conn = get_db_connection()
	cur = conn.cursor()
	query = """
		SELECT p.id, p.name, p.description, p.price, p.quantity, p.image_urls, u.name 
		FROM products p 
		LEFT JOIN users u ON p.seller_id = u.id
		WHERE p.name ILIKE %s OR p.description ILIKE %s
	"""
	cur.execute(query, (f'%{search}%', f'%{search}%'))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_products_by_seller(seller_id, search=''):
	conn = get_db_connection()
	cur = conn.cursor()
	query = """
		SELECT id, name, description, price, quantity, image_urls 
		FROM products 
		WHERE seller_id = %s AND (name ILIKE %s OR description ILIKE %s)
	"""
	cur.execute(query, (seller_id, f'%{search}%', f'%{search}%'))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def add_product(name, description, price, quantity, image_urls, seller_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("INSERT INTO products (name, description, price, quantity, image_urls, seller_id) VALUES (%s, %s, %s, %s, %s, %s)", 
			(name, description, price, quantity, image_urls, seller_id))
	conn.commit()
	cur.close()
	conn.close()

def update_product(product_id, name, description, price, quantity, image_urls):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("UPDATE products SET name = %s, description = %s, price = %s, quantity = %s, image_urls = %s WHERE id = %s", 
			(name, description, price, quantity, image_urls, product_id))
	conn.commit()
	cur.close()
	conn.close()

def delete_product(product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
	conn.commit()
	cur.close()
	conn.close()

def get_product_seller(product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT seller_id FROM products WHERE id = %s", (product_id,))
	result = cur.fetchone()[0]
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

def add_to_cart(user_id, product_id, quantity):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (%s, %s, %s) ON CONFLICT (user_id, product_id) DO UPDATE SET quantity = cart.quantity + %s", 
			(user_id, product_id, quantity, quantity))
	conn.commit()
	cur.close()
	conn.close()

def get_cart_items(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT p.id, p.name, p.price, c.quantity FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = %s", (user_id,))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def remove_from_cart(user_id, product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("DELETE FROM cart WHERE user_id = %s AND product_id = %s", (user_id, product_id))
	conn.commit()
	cur.close()
	conn.close()

def clear_cart(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))
	conn.commit()
	cur.close()
	conn.close()

def get_cart_for_checkout(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT c.product_id, c.quantity, p.price FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = %s", (user_id,))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_user_orders(user_id, status_filter=''):
	conn = get_db_connection()
	cur = conn.cursor()
	query = "SELECT id, status, total_price, delivery_address, created_at FROM orders WHERE user_id = %s"
	params = [user_id]
	if status_filter:
		query += " AND status = %s"
		params.append(status_filter)
	query += " ORDER BY created_at DESC"
	cur.execute(query, params)
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_all_orders(status_filter=''):
	conn = get_db_connection()
	cur = conn.cursor()
	query = "SELECT o.id, o.status, o.total_price, o.created_at, u.name FROM orders o JOIN users u ON o.user_id = u.id"
	params = []
	if status_filter:
		query += " WHERE o.status = %s"
		params.append(status_filter)
	query += " ORDER BY o.created_at DESC"
	cur.execute(query, params)
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_seller_orders(seller_id, status_filter=''):
	conn = get_db_connection()
	cur = conn.cursor()
	query = """
		SELECT DISTINCT o.id, o.status, o.total_price, o.delivery_address, o.created_at, u.name, 
						array_agg(p.name) as products
		FROM orders o 
		JOIN order_items oi ON o.id = oi.order_id 
		JOIN products p ON oi.product_id = p.id 
		JOIN users u ON o.user_id = u.id 
		WHERE p.seller_id = %s
	"""
	params = [seller_id]
	if status_filter:
		query += " AND o.status = %s"
		params.append(status_filter)
	query += " GROUP BY o.id, u.name ORDER BY o.created_at DESC"
	cur.execute(query, params)
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def update_order_status(order_id, status):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
	conn.commit()
	cur.close()
	conn.close()

def assign_order_to_courier(order_id, courier_id, estimated_delivery):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("INSERT INTO delivery (order_id, courier_id, status, estimated_delivery) VALUES (%s, %s, 'assigned', %s)", 
			(order_id, courier_id, estimated_delivery))
	cur.execute("UPDATE orders SET status = 'in_delivery' WHERE id = %s", (order_id,))
	conn.commit()
	cur.close()
	conn.close()

def get_active_courier_orders(courier_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, o.delivery_address, d.status, d.estimated_delivery 
		FROM orders o
		JOIN delivery d ON o.id = d.order_id
		WHERE d.courier_id = %s AND d.status NOT IN ('delivered', 'cancelled')
	""", (courier_id,))
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def get_available_orders():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, o.delivery_address 
		FROM orders o 
		WHERE o.status = 'paid' AND NOT EXISTS (SELECT 1 FROM delivery d WHERE d.order_id = o.id)
	""")
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def update_delivery_status(order_id, courier_id, status):
	conn = get_db_connection()
	cur = conn.cursor()
	if status == 'delivered':
		cur.execute("UPDATE delivery SET status = %s, delivered_at = %s WHERE order_id = %s AND courier_id = %s", 
				(status, datetime.now(), order_id, courier_id))
		cur.execute("UPDATE orders SET status = 'completed' WHERE id = %s", (order_id,))
	else:
		cur.execute("UPDATE delivery SET status = %s WHERE order_id = %s AND courier_id = %s", 
				(status, order_id, courier_id))
	conn.commit()
	cur.close()
	conn.close()

def check_courier_assignment(order_id, courier_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT COUNT(*) FROM delivery WHERE order_id = %s AND courier_id = %s", (order_id, courier_id))
	result = cur.fetchone()[0] > 0
	cur.close()
	conn.close()
	return result

def cancel_delivery(order_id, courier_id, reason):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("UPDATE delivery SET status = 'cancelled', cancel_reason = %s WHERE order_id = %s AND courier_id = %s", 
			(reason, order_id, courier_id))
	cur.execute("UPDATE orders SET status = 'paid' WHERE id = %s", (order_id,))
	conn.commit()
	cur.close()
	conn.close()

def log_action(user_id, action):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("INSERT INTO logs (user_id, action) VALUES (%s, %s)", (user_id, action))
	conn.commit()
	cur.close()
	conn.close()

def get_logs(action_filter=''):
	conn = get_db_connection()
	cur = conn.cursor()
	query = "SELECT l.id, u.name, l.action, l.timestamp FROM logs l JOIN users u ON l.user_id = u.id"
	params = []
	if action_filter:
		query += " WHERE l.action ILIKE %s"
		params.append(f'%{action_filter}%')
	query += " ORDER BY l.timestamp DESC"
	cur.execute(query, params)
	result = cur.fetchall()
	cur.close()
	conn.close()
	return result

def create_session(user_id, session_code):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute(
		"INSERT INTO sessions (user_id, session_code, created_at) VALUES (%s, %s, %s) RETURNING id",
		(user_id, session_code, datetime.now())
	)
	session_id = cur.fetchone()[0]
	conn.commit()
	cur.close()
	conn.close()
	return session_id

def get_session_by_code(session_code):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT user_id FROM sessions WHERE session_code = %s", (session_code,))
	result = cur.fetchone()
	cur.close()
	conn.close()
	return result[0] if result else None

def delete_session(session_code):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("DELETE FROM sessions WHERE session_code = %s", (session_code,))
	conn.commit()
	cur.close()
	conn.close()
