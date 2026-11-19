// The only JavaScript in Stage 1-2. Two small conveniences:
//   1. show/hide the password on the sign-in page
//   2. copy a reference ID to the clipboard

// 1. Password eye button: <button data-toggle-password="password">
document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
  button.addEventListener("click", function () {
    var input = document.getElementById(button.dataset.togglePassword);
    input.type = input.type === "password" ? "text" : "password";
  });
});

// 2. Copy button: <button data-copy="REF-MVP-77310">
document.querySelectorAll("[data-copy]").forEach(function (button) {
  button.addEventListener("click", function () {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(button.dataset.copy);
    }
    button.classList.add("copied");
    setTimeout(function () { button.classList.remove("copied"); }, 1200);
  });
});
