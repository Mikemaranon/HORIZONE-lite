export function store_token(token) {
    return token || null;
}

export function getToken() {
    return null;
}

export function delete_token() {
    return null;
}

export async function login(username, password) {
    const endpoint = "/login";
    if (!username || !password) {
        throw new Error("Username and password are required.");
    }

    const options = {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        credentials: "same-origin",
        body: JSON.stringify({ username, password })
    };

    try {
        const response = await fetch(endpoint, options);
        return response;
    } catch (error) {
        throw error;
    }
}

export async function send_API_request(method, endpoint, body = null, requestOptions = {}) {
    const options = {
        method: method.toUpperCase(),
        headers: {
            "Content-Type": "application/json",
        },
        credentials: "same-origin",
    };

    if (body && method.toUpperCase() !== "GET") {
        options.body = JSON.stringify(body);
    }

    if (requestOptions.signal) {
        options.signal = requestOptions.signal;
    }

    try {
        return await fetch(endpoint, options);
    } catch (error) {
        throw error;
    }
}

export async function loadPage(url) {
    window.location.href = url;
}
