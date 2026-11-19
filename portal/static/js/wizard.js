// JavaScript for the Create Order wizard. Everything here is a convenience:
// the server re-checks every rule, so the wizard still works without it.
//
//   1. toasts fade out by themselves
//   2. "unsaved changes" chip
//   3. masking of sensitive numbers (shown as ****1234 when you leave the box)
//   4. customer type toggles the "required" stars
//   5. choosing a rate plan fills in the monthly price
//   6. device "None" disables the device fields
//   7. live order summary
//   8. character counters
//   9. file upload: choose a file or drag and drop it onto a row
//  10. the Submit confirmation pop-up

(function () {
  "use strict";
  var form = document.getElementById("wizard-form");

  // 1. toasts ------------------------------------------------------------
  document.querySelectorAll(".toast").forEach(function (t) {
    setTimeout(function () {
      t.classList.add("leaving");
      setTimeout(function () { t.remove(); }, 400);
    }, 4500);
  });
  function toast(title, body, kind) {
    var box = document.getElementById("toasts");
    var el = document.createElement("div");
    el.className = "toast toast-" + (kind || "error");
    el.innerHTML = "<b></b><span></span>";
    el.children[0].textContent = title;
    el.children[1].textContent = body || "";
    box.appendChild(el);
    setTimeout(function () { el.remove(); }, 4500);
  }

  // 2. unsaved changes chip ---------------------------------------------
  var chip = document.getElementById("save-chip");
  if (form && chip) {
    form.addEventListener("input", function () {
      chip.classList.add("dirty");
      chip.textContent = "Unsaved changes";
    });
  }

  // 3. masking of sensitive fields ---------------------------------------
  // The box shows a masked value; the real value is kept in data-real and
  // put back just before the form is sent, so the server gets the truth.
  function mask(kind, v) {
    if (!v) return v;
    if (kind === "brn") return v.length > 6 ? v.slice(0, 4) + "*".repeat(v.length - 6) + v.slice(-2) : v;
    if (kind === "account") return v.length > 4 ? "*".repeat(v.length - 4) + v.slice(-4) : v;
    // id: keep punctuation, show only the last four digits
    var total = (v.match(/\d/g) || []).length, seen = 0;
    return v.replace(/\d/g, function (d) { seen++; return seen > total - 4 ? d : "*"; });
  }
  var sensitive = document.querySelectorAll("[data-sensitive]");
  sensitive.forEach(function (input) {
    var kind = input.dataset.sensitive;
    input.dataset.real = input.value;
    input.dataset.revealed = "";
    function showMasked() {
      input.dataset.real = input.value.indexOf("*") === -1 ? input.value : input.dataset.real;
      if (!input.dataset.revealed) input.value = mask(kind, input.dataset.real);
    }
    input.addEventListener("focus", function () { input.value = input.dataset.real; });
    input.addEventListener("input", function () { input.dataset.real = input.value; });
    input.addEventListener("blur", showMasked);
    showMasked();
  });
  document.querySelectorAll("[data-reveal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.dataset.reveal);
      if (input.dataset.revealed) {
        input.dataset.revealed = "";
        input.value = mask(input.dataset.sensitive, input.dataset.real);
      } else {
        input.dataset.revealed = "1";
        input.value = input.dataset.real;
      }
    });
  });
  if (form) {
    form.addEventListener("submit", function () {
      sensitive.forEach(function (input) { input.value = input.dataset.real; });
    });
  }

  // 4. customer type -------------------------------------------------------
  document.querySelectorAll('input[name="customer_type"]').forEach(function (r) {
    r.addEventListener("change", function () { form.dataset.ctype = r.value; });
  });

  // 5-7. subscription lines -----------------------------------------------
  var prices = {};
  try { prices = JSON.parse(form.dataset.prices || "{}"); } catch (e) {}

  function num(el) { return el && el.value ? parseFloat(el.value.replace(/,/g, "")) || 0 : 0; }
  function rm(n) { return "RM " + n.toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

  function updateSummary() {
    var lines = 0, items = 0, monthly = 0, upfront = 0, cards = document.querySelectorAll("[data-line]");
    if (!cards.length) return;
    cards.forEach(function (card) {
      function f(suffix) { return card.querySelector('[name$="_' + suffix + '"]'); }
      var n = num(f("num_lines"));
      lines += n; items += 1;
      monthly += n * num(f("monthly"));
      var hasDevice = f("device_model") && f("device_model").value;
      upfront += (hasDevice ? num(f("device_qty")) * num(f("device_price")) : 0) + num(f("upfront")) + num(f("deposit"));
    });
    function set(k, v) { var e = document.querySelector('[data-sum="' + k + '"]'); if (e) e.textContent = v; }
    set("lines", lines); set("items", items); set("monthly", rm(monthly)); set("upfront", rm(upfront));
  }

  document.querySelectorAll("[data-line]").forEach(function (card) {
    var plan = card.querySelector("[data-plan]");
    var monthly = card.querySelector('[name$="_monthly"]');
    var device = card.querySelector("[data-device]");
    function deviceFields() {
      return ["device_qty", "device_price"].map(function (s) { return card.querySelector('[name$="_' + s + '"]'); });
    }
    plan.addEventListener("change", function () {
      if (prices[plan.value] !== undefined) monthly.value = prices[plan.value];
      updateSummary();
    });
    function syncDevice() {
      var none = !device.value;
      deviceFields().forEach(function (el) {
        el.disabled = none;
        if (none) el.dataset.was = el.value;
      });
    }
    device.addEventListener("change", function () {
      var q = deviceFields()[0];
      if (device.value && (!q.value || q.value === "0")) q.value = "1";
      syncDevice(); updateSummary();
    });
    syncDevice();
  });
  if (form) {
    form.addEventListener("input", updateSummary);
    form.addEventListener("change", updateSummary);
    // A disabled box is not sent by the browser; enable them before sending.
    form.addEventListener("submit", function () {
      form.querySelectorAll("input:disabled").forEach(function (el) { el.disabled = false; });
    });
  }
  updateSummary();

  // 8. character counters --------------------------------------------------
  document.querySelectorAll("textarea[data-count]").forEach(function (ta) {
    var counter = document.querySelector('[data-counter-for="' + ta.id + '"]');
    var max = ta.dataset.count;
    function update() { if (counter) counter.textContent = ta.value.length + " / " + max; }
    ta.addEventListener("input", update);
    update();
  });

  // 9. uploads -------------------------------------------------------------
  document.querySelectorAll("[data-autosubmit]").forEach(function (input) {
    input.addEventListener("change", function () { if (input.files.length) input.form.submit(); });
  });
  document.querySelectorAll(".dropzone").forEach(function (row) {
    var input = row.querySelector("[data-autosubmit]");
    ["dragenter", "dragover"].forEach(function (ev) {
      row.addEventListener(ev, function (e) { e.preventDefault(); row.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      row.addEventListener(ev, function (e) { e.preventDefault(); row.classList.remove("dragover"); });
    });
    row.addEventListener("drop", function (e) {
      if (input && e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        input.form.submit();
      }
    });
  });

  // 10. submit pop-up ------------------------------------------------------
  var open = document.getElementById("open-submit");
  var dialog = document.getElementById("submit-dialog");
  if (open && dialog) {
    open.addEventListener("click", function () {
      if (open.dataset.ready !== "1") {
        toast("Order is not ready", "Fix the items listed at the top of this page first.");
        return;
      }
      dialog.showModal();
    });
    document.getElementById("cancel-submit").addEventListener("click", function () { dialog.close(); });
    dialog.querySelector("form").addEventListener("submit", function (e) {
      if (!document.getElementById("declaration").checked) {
        e.preventDefault();
        document.getElementById("declaration-error").hidden = false;
      }
    });
  }
})();
