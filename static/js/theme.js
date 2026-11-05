(function () {
  var btn = document.getElementById("themeToggle");
  if (!btn) return;
  btn.addEventListener("click", function () {
    var atual = document.documentElement.getAttribute("data-bs-theme");
    var novo = atual === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-bs-theme", novo);
    try { localStorage.setItem("ba-theme", novo); } catch (e) {}
  });
})();
