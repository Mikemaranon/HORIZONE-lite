import { loadPage, login, store_token } from "./SERVER_CONN/token-handler.js";

async function handleLoginSubmit(event) {
    event.preventDefault(); // Prevent default form submission

    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const errorMessage = document.getElementById("error-message");
    errorMessage.textContent = "";

    try {
        const response = await login(username, password)

        const data = await response.json();
        console.log(data);

        if (response.ok) {
            store_token(data.token);
            loadPage("/index");
        } else {
            errorMessage.textContent = data.error || "An error occurred.";
        }
    } catch (error) {
        console.error("Error during login:", error);
        errorMessage.textContent = "Incorrect user, please try again.";
    }
}

document.addEventListener("DOMContentLoaded", function () {
    const loginForm = document.getElementById("login-form");
    
    loginForm.addEventListener("submit", handleLoginSubmit);
});
