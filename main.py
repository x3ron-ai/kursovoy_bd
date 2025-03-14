from app import app
from prometheus_flask_exporter import PrometheusMetrics, Gauge

if __name__ == "__main__":
	metrics = PrometheusMetrics(app)
	app.run('0.0.0.0', 5723, debug=True, threaded=True)
