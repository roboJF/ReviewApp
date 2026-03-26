function showLoading() {
    document.getElementById("generate-btn").disabled = true;
    document.getElementById("generate-btn").textContent = "Loading...";
    document.getElementById("loading-msg").style.display = "block";
}