from app import app, metrics

if __name__ == "__main__":
	metrics.start_http_server(5724)
	app.run('0.0.0.0', 5723, debug=True, threaded=True)
