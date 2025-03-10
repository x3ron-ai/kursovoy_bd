async function register() {
	let name = document.getElementById("name").value;
	let email = document.getElementById("email").value;
	let password = document.getElementById("password").value;
	let role = document.getElementById("role").value;

	let response = await fetch("/api/register", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ name, email, password, role })
	});

	let result = await response.json();
	document.getElementById("message").innerText = result.message || result.error;
	if (response.ok) setTimeout(() => window.location.href = "/login", 1000);
}

async function login() {
	let email = document.getElementById("email").value;
	let password = document.getElementById("password").value;

	let response = await fetch("/api/login", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ email, password })
	});

	let result = await response.json();
	document.getElementById("message").innerText = result.message || result.error;
	if (response.ok) {
		document.cookie = `token=${result.token}; path=/`;
		setTimeout(() => window.location.href = "/", 1000);
	}
}

