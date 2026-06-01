const TOKEN_KEY = "auth_token";

export function store_token(token) {
    if (!token) {
        return;
    }
    try {
        delete_token(); // Clear any existing token
    } catch (error) {
        console.error("Error deleting existing token:", error);
    }
    localStorage.setItem(TOKEN_KEY, token);
    console.log("Token stored:", token);
}

export function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

export function delete_token() {
    localStorage.removeItem(TOKEN_KEY);
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
        body: JSON.stringify({ username, password })
    };

    console.log("loging... :", endpoint, options);

    try {
        const response = await fetch(endpoint, options);
        return response;
    } catch (error) {
        console.error("Error in API request:", error);
        throw error;
    }
}

export async function send_API_request(method, endpoint, body = null, requestOptions = {}) {
    const token = localStorage.getItem(TOKEN_KEY);

    const options = {
        method: method.toUpperCase(),
        headers: {
            "Content-Type": "application/json",
        },
        credentials: "same-origin",
    };

    if (token) {
        options.headers.Authorization = "Bearer " + token;
    }
    
    if (body && method.toUpperCase() !== "GET") {
        options.body = JSON.stringify(body);
    }

    if (requestOptions.signal) {
        options.signal = requestOptions.signal;
    }

    console.log("Fetching:", endpoint, options);

    try {
        return await fetch(endpoint, options);
    } catch (error) {
        console.error("Error in API request:", error);
        throw error;
    }
}

export async function loadPage(url) {
    try {
        window.location.href = url;
    } catch (error) {
        console.error("Error loading page:", error);
    }
}
