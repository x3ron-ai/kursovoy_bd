-- Таблицы (без изменений, для полноты)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('customer', 'seller', 'courier', 'admin'))
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    price DECIMAL NOT NULL,
    quantity INTEGER NOT NULL,
    image_urls TEXT[],
    seller_id INTEGER REFERENCES users(id)
);

CREATE TABLE cart (
    user_id INTEGER REFERENCES users(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    PRIMARY KEY (user_id, product_id)
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    total_price DECIMAL NOT NULL,
    delivery_address TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    price DECIMAL NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE delivery (
    order_id INTEGER REFERENCES orders(id) PRIMARY KEY,
    courier_id INTEGER REFERENCES users(id),
    status TEXT NOT NULL,
    estimated_delivery TIMESTAMP,
    delivered_at TIMESTAMP,
    cancel_reason TEXT
);

CREATE TABLE logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Представление (без изменений)
CREATE VIEW order_summary AS
    SELECT o.id, o.status, o.total_price, o.created_at, u.name AS customer
    FROM orders o
    JOIN users u ON o.user_id = u.id;

-- Индексы для ускорения поиска и фильтрации
CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_delivery_status ON delivery(status);
CREATE INDEX idx_logs_user_id ON logs(user_id);
CREATE INDEX idx_logs_timestamp ON logs(timestamp);

-- Функция: проверка доступного количества товара
CREATE OR REPLACE FUNCTION check_product_quantity()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.quantity > (SELECT quantity FROM products WHERE id = NEW.product_id) THEN
        RAISE EXCEPTION 'Not enough products in stock for product %', NEW.product_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер: проверка количества перед добавлением в корзину
CREATE TRIGGER trg_check_cart_quantity
BEFORE INSERT OR UPDATE ON cart
FOR EACH ROW
EXECUTE FUNCTION check_product_quantity();

-- Функция: логирование действий над товарами
CREATE OR REPLACE FUNCTION log_product_action()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO logs (user_id, action)
        VALUES (NEW.seller_id, 'Added product: ' || NEW.name);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO logs (user_id, action)
        VALUES (NEW.seller_id, 'Updated product: ' || NEW.name);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO logs (user_id, action)
        VALUES (OLD.seller_id, 'Deleted product: ' || OLD.name);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Триггер: логирование действий с товарами
CREATE TRIGGER trg_log_product_action
AFTER INSERT OR UPDATE OR DELETE ON products
FOR EACH ROW
EXECUTE FUNCTION log_product_action();

-- Функция: обновление количества товара после создания заказа
CREATE OR REPLACE FUNCTION update_product_quantity_on_order()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE products
    SET quantity = quantity - NEW.quantity
    WHERE id = NEW.product_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер: обновление количества после добавления в order_items
CREATE TRIGGER trg_update_product_quantity
AFTER INSERT ON order_items
FOR EACH ROW
EXECUTE FUNCTION update_product_quantity_on_order();

-- Хранимая процедура: создание заказа с транзакцией
CREATE OR REPLACE PROCEDURE create_order_with_items(
    p_user_id INTEGER,
    p_delivery_address TEXT,
    p_cart_items INTEGER[][] -- Массив пар {product_id, quantity}
)
LANGUAGE plpgsql AS $$
DECLARE
    v_order_id INTEGER;
    v_total_price DECIMAL := 0;
    v_product_id INTEGER;
    v_quantity INTEGER;
    v_price DECIMAL;
BEGIN
    -- Начало транзакции
    BEGIN
        -- Создание заказа
        INSERT INTO orders (user_id, total_price, delivery_address, status)
        VALUES (p_user_id, 0, p_delivery_address, 'pending')
        RETURNING id INTO v_order_id;

        -- Обработка элементов корзины
        FOR i IN 1..array_length(p_cart_items, 1) LOOP
            v_product_id := p_cart_items[i][1];
            v_quantity := p_cart_items[i][2];
            
            -- Проверка количества
            IF v_quantity > (SELECT quantity FROM products WHERE id = v_product_id) THEN
                RAISE EXCEPTION 'Not enough stock for product %', v_product_id;
            END IF;

            -- Получение цены
            SELECT price INTO v_price FROM products WHERE id = v_product_id;
            v_total_price := v_total_price + (v_price * v_quantity);

            -- Добавление в order_items
            INSERT INTO order_items (order_id, product_id, quantity, price)
            VALUES (v_order_id, v_product_id, v_quantity, v_price);
        END LOOP;

        -- Обновление общей суммы заказа
        UPDATE orders
        SET total_price = v_total_price
        WHERE id = v_order_id;

        -- Очистка корзины
        DELETE FROM cart WHERE user_id = p_user_id;

        -- Логирование
        INSERT INTO logs (user_id, action)
        VALUES (p_user_id, 'Created order ' || v_order_id);

        COMMIT;
    EXCEPTION WHEN OTHERS THEN
        ROLLBACK;
        RAISE NOTICE 'Order creation failed: %', SQLERRM;
        RAISE;
    END;
END;
$$;

-- Функция: подсчёт заказов пользователя
CREATE OR REPLACE FUNCTION get_user_order_count(p_user_id INTEGER)
RETURNS INTEGER AS $$
BEGIN
    RETURN (SELECT COUNT(*) FROM orders WHERE user_id = p_user_id);
END;
$$ LANGUAGE plpgsql;

-- Триггер: логирование доставки
CREATE OR REPLACE FUNCTION log_delivery_action()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO logs (user_id, action)
        VALUES (NEW.courier_id, 'Assigned delivery for order ' || NEW.order_id);
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.status = 'delivered' THEN
            INSERT INTO logs (user_id, action)
            VALUES (NEW.courier_id, 'Delivered order ' || NEW.order_id);
        ELSIF NEW.status = 'cancelled' THEN
            INSERT INTO logs (user_id, action)
            VALUES (NEW.courier_id, 'Cancelled delivery for order ' || NEW.order_id || ' - Reason: ' || NEW.cancel_reason);
        ELSE
            INSERT INTO logs (user_id, action)
            VALUES (NEW.courier_id, 'Updated delivery status for order ' || NEW.order_id || ' to ' || NEW.status);
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_log_delivery_action
AFTER INSERT OR UPDATE ON delivery
FOR EACH ROW
EXECUTE FUNCTION log_delivery_action();
