/* Presentation mode switch.
 *
 * Runs in <head> on every page, before first paint, so a reader who chose the
 * dashboard view last time does not watch the engineering view flash past.
 *
 * The switch changes one attribute on <html>. It never touches the data, so
 * both views always show the same figures. presentation.css does the rest.
 */
(function () {
  var KEY = "flightdeck:view";
  var DEFAULT = "engineering";

  function read() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "dashboard" || v === "engineering" ? v : DEFAULT;
    } catch (e) {
      // Private windows and blocked site data both throw here. Neither is a
      // reason to fail: fall back to the view the site has always had.
      return DEFAULT;
    }
  }

  function write(v) {
    try {
      localStorage.setItem(KEY, v);
    } catch (e) {
      /* The choice still applies to this page load. */
    }
  }

  function apply(v) {
    document.documentElement.setAttribute("data-view", v);
  }

  apply(read());

  function build() {
    if (document.getElementById("view-switch")) return;

    var box = document.createElement("div");
    box.id = "view-switch";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Choose a view");

    [
      ["dashboard", "Dashboard"],
      ["engineering", "Engineering"]
    ].forEach(function (pair) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = pair[1];
      b.setAttribute("data-view-choice", pair[0]);
      b.addEventListener("click", function () {
        apply(pair[0]);
        write(pair[0]);
        sync();
      });
      box.appendChild(b);
    });

    document.body.appendChild(box);
    sync();
  }

  function sync() {
    var current = document.documentElement.getAttribute("data-view");
    var buttons = document.querySelectorAll("#view-switch button");
    for (var i = 0; i < buttons.length; i++) {
      var choice = buttons[i].getAttribute("data-view-choice");
      buttons[i].setAttribute("aria-pressed", String(choice === current));
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
