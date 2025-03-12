import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timedelta
import hashlib

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
		SELECT p.id, p.name, p.description, p.price, COALESCE(SUM(wp.quantity), 0), 
		       array_agg(pi.image_url) FILTER (WHERE pi.image_url IS NOT NULL)
		FROM products p
		LEFT JOIN warehouse_products wp ON p.id = wp.product_id
		LEFT JOIN product_images pi ON p.id = pi.product_id
		GROUP BY p.id, p.name, p.description, p.price
	""")
	products = cur.fetchall()
	cur.close()
	conn.close()
	return products

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

def update_product_quantity(seller_id, product_id, warehouse_id, quantity):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		# Проверяем, что товар принадлежит продавцу
		cur.execute("SELECT seller_id FROM products WHERE id = %s", (product_id,))
		if cur.fetchone()[0] != seller_id:
			raise ValueError("Product does not belong to this seller")
		# Обновляем или добавляем количество на складе
		cur.execute("""
			INSERT INTO warehouse_products (warehouse_id, product_id, quantity)
			VALUES (%s, %s, %s)
			ON CONFLICT (warehouse_id, product_id)
			DO UPDATE SET quantity = %s
		""", (warehouse_id, product_id, quantity, quantity))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
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

def get_seller_products(seller_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT p.id, p.name, p.description, p.price, COALESCE(wp.quantity, 0), 
		       COALESCE(array_agg(pi.image_url) FILTER (WHERE pi.image_url IS NOT NULL), '{}')
		FROM products p
		LEFT JOIN warehouse_products wp ON p.id = wp.product_id
		LEFT JOIN product_images pi ON p.id = pi.product_id
		WHERE p.seller_id = %s
		GROUP BY p.id, p.name, p.description, p.price, wp.quantity
	""", (seller_id,))
	products = cur.fetchall()
	cur.close()
	conn.close()
	return products

def add_product_image(product_id, image_url):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO product_images (product_id, image_url)
			VALUES (%s, %s)
		""", (product_id, image_url))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def create_product(seller_id, name, description, price, warehouse_id, quantity):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO products (seller_id, name, description, price)
			VALUES (%s, %s, %s, %s)
			RETURNING id
		""", (seller_id, name, description, price))
		product_id = cur.fetchone()[0]
		# Добавляем количество на склад
		cur.execute("""
			INSERT INTO warehouse_products (warehouse_id, product_id, quantity)
			VALUES (%s, %s, %s)
		""", (warehouse_id, product_id, quantity))
		conn.commit()
		return product_id
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def update_product(product_id, seller_id, name, description, price, warehouse_id, quantity):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			UPDATE products
			SET name = %s, description = %s, price = %s
			WHERE id = %s AND seller_id = %s
		""", (name, description, price, product_id, seller_id))
		cur.execute("""
			INSERT INTO warehouse_products (warehouse_id, product_id, quantity)
			VALUES (%s, %s, %s)
			ON CONFLICT (warehouse_id, product_id)
			DO UPDATE SET quantity = %s
		""", (warehouse_id, product_id, quantity, quantity))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def delete_product(product_id, seller_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("DELETE FROM product_images WHERE product_id = %s", (product_id,))
		cur.execute("DELETE FROM warehouse_products WHERE product_id = %s", (product_id,))
		cur.execute("DELETE FROM products WHERE id = %s AND seller_id = %s", (product_id, seller_id))
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
	try:
		cur.execute("""
			SELECT id, status, total_price, delivery_address, warehouse_id, created_at, parent_order_id
			FROM orders
			WHERE seller_id = %s
			AND status IN ('created', 'paid', 'in assembly', 'assembled')
		""", (seller_id,))
		orders = cur.fetchall() or []
	except psycopg2.Error as e:
		print(f"Database error: {str(e)}")
		orders = []
	finally:
		cur.close()
		conn.close()
	return orders

def create_order(user_id, total_price, delivery_address, warehouse_id, parent_order_id, seller_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO orders (user_id, status, total_price, delivery_address, warehouse_id, parent_order_id, seller_id)
			VALUES (%s, 'created', %s, %s, %s, %s, %s)
			RETURNING id
		""", (user_id, total_price, delivery_address, warehouse_id, parent_order_id, seller_id))
		order_id = cur.fetchone()[0]
		conn.commit()
		return order_id
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()
def get_product_quantity_in_warehouse(warehouse_id, product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT quantity
		FROM warehouse_products
		WHERE warehouse_id = %s AND product_id = %s
	""", (warehouse_id, product_id))
	result = cur.fetchone()
	cur.close()
	conn.close()
	return result[0] if result else 0

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
		SELECT c.product_id, c.quantity, p.price, p.seller_id
		FROM cart c
		JOIN products p ON c.product_id = p.id
		WHERE c.user_id = %s
	""", (user_id,))
	items = cur.fetchall()
	cur.close()
	conn.close()
	return items

# Курьеры
def get_active_courier_orders(courier_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, o.delivery_address, d.estimated_delivery, d.delivered_at
		FROM orders o
		JOIN delivery d ON o.id = d.order_id
		WHERE d.courier_id = %s
		AND o.status IN ('in delivery')
	""", (courier_id,))
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return orders

def get_available_orders():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, o.delivery_address, o.warehouse_id
		FROM orders o
		LEFT JOIN delivery d ON o.id = d.order_id
		WHERE o.status = 'assembled'
		AND d.order_id IS NULL
	""")
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return orders

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
# --- Функции для складов ---
def create_warehouse(seller_id, address):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO warehouses (seller_id, address)
			VALUES (%s, %s)
			RETURNING id
		""", (seller_id, address))
		warehouse_id = cur.fetchone()[0]
		conn.commit()
		return warehouse_id
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_warehouses_by_seller(seller_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT id, address
		FROM warehouses
		WHERE seller_id = %s
	""", (seller_id,))
	warehouses = cur.fetchall()
	cur.close()
	conn.close()
	return warehouses

def update_warehouse(warehouse_id, address):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			UPDATE warehouses
			SET address = %s
			WHERE id = %s
		""", (address, warehouse_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def delete_warehouse(warehouse_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("DELETE FROM warehouse_products WHERE warehouse_id = %s", (warehouse_id,))
		cur.execute("DELETE FROM warehouses WHERE id = %s", (warehouse_id,))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

# --- Функции для товаров на складах ---
def add_product_to_warehouse(warehouse_id, product_id, quantity):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO warehouse_products (warehouse_id, product_id, quantity)
			VALUES (%s, %s, %s)
			ON CONFLICT (warehouse_id, product_id)
			DO UPDATE SET quantity = warehouse_products.quantity + %s
		""", (warehouse_id, product_id, quantity, quantity))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_products_by_warehouse(warehouse_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT p.id, p.name, p.description, p.price, wp.quantity, p.image_urls
		FROM products p
		JOIN warehouse_products wp ON p.id = wp.product_id
		WHERE wp.warehouse_id = %s
	""", (warehouse_id,))
	products = cur.fetchall()
	cur.close()
	conn.close()
	return products

def update_product_quantity_in_warehouse(warehouse_id, product_id, quantity):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			UPDATE warehouse_products
			SET quantity = %s
			WHERE warehouse_id = %s AND product_id = %s
		""", (quantity, warehouse_id, product_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def remove_product_from_warehouse(warehouse_id, product_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			DELETE FROM warehouse_products
			WHERE warehouse_id = %s AND product_id = %s
		""", (warehouse_id, product_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

# складмены
def get_warehouse_orders(warehouse_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, o.delivery_address, o.warehouse_id, o.created_at
		FROM orders o
		WHERE o.warehouse_id = %s
		AND o.status IN ('under assembly', 'paid')
	""", (warehouse_id,))
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return orders

def get_warehouse_orders_for_user(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
 	   SELECT o.id, o.status, o.total_price, o.delivery_address, o.warehouse_id, o.created_at
 	   FROM orders o
 	   JOIN warehouse_workers ww ON o.warehouse_id = ww.warehouse_id
 	   WHERE ww.user_id = %s
 	   AND o.status IN ('under assembly', 'paid')
	""", (user_id,))
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return orders

def create_parent_order(user_id, total_price, delivery_address):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			INSERT INTO parent_orders (user_id, status, total_price, delivery_address)
			VALUES (%s, 'created', %s, %s)
			RETURNING id
		""", (user_id, total_price, delivery_address))
		parent_order_id = cur.fetchone()[0]
		conn.commit()
		return parent_order_id
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_parent_order(parent_order_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT id, user_id, status, total_price, delivery_address, created_at
		FROM parent_orders
		WHERE id = %s
	""", (parent_order_id,))
	order = cur.fetchone()
	cur.close()
	conn.close()
	return order

def update_parent_order_status(parent_order_id, status):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		cur.execute("""
			UPDATE parent_orders
			SET status = %s
			WHERE id = %s
		""", (status, parent_order_id))
		conn.commit()
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_user_parent_orders(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT id, status, total_price, delivery_address, created_at
		FROM parent_orders
		WHERE user_id = %s
	""", (user_id,))
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return orders

def create_warehouse_worker(seller_id, email, name, password, warehouse_id):
	conn = get_db_connection()
	cur = conn.cursor()
	try:
		hashed_password = hashlib.sha256(password.encode()).hexdigest()
		cur.execute("""
			INSERT INTO users (name, email, password, role)
			VALUES (%s, %s, %s, 'warehouseman')
			RETURNING id
		""", (name, email, hashed_password))
		user_id = cur.fetchone()[0]
		cur.execute("""
			INSERT INTO warehouse_workers (user_id, warehouse_id)
			VALUES (%s, %s)
		""", (user_id, warehouse_id))
		conn.commit()
		return user_id
	except psycopg2.Error as e:
		conn.rollback()
		raise e
	finally:
		cur.close()
		conn.close()

def get_warehouse_orders_for_user(user_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT o.id, o.status, o.total_price, o.delivery_address, o.warehouse_id, o.created_at, o.parent_order_id, o.seller_id
		FROM orders o
		JOIN warehouse_workers ww ON o.warehouse_id = ww.warehouse_id
		WHERE ww.user_id = %s
		AND o.status IN ('paid', 'in assembly')
	""", (user_id,))
	orders = cur.fetchall()
	cur.close()
	conn.close()
	return orders

def get_sub_orders(parent_order_id):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("""
		SELECT id, status, total_price, delivery_address, warehouse_id, created_at, seller_id
		FROM orders
		WHERE parent_order_id = %s
	""", (parent_order_id,))
	sub_orders = cur.fetchall()
	cur.close()
	conn.close()
	return sub_orders
