/* The header, and the presentation mode switch inside it.
 *
 * Framework's sidebar is off, so this builds the navigation that replaces it:
 * the wordmark, one link per page, and the view switch. The page list is not
 * written here. observablehq.config.js publishes its own `pages` array as
 * window.__flightdeckPages, so the header and the config can never disagree
 * about what the site contains.
 *
 * The attribute runs first, in <head>, before first paint, so a reader who
 * chose the dashboard view last time does not watch the engineering view flash
 * past. The header itself waits for <body>.
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

  // Which page is open. Framework writes internal links as "./four-clocks"
  // relative to the site root, which is "/" under `npm run dev` and
  // "/flightdeck/" once built, so comparing the last segment is the one test
  // that holds under both.
  function currentSegment() {
    var path = location.pathname.replace(/\.html$/, "").replace(/\/index$/, "/");
    return path.slice(path.lastIndexOf("/") + 1);
  }

  function pageLinks() {
    var pages = window.__flightdeckPages || [];
    var here = currentSegment();
    var nav = document.createElement("nav");
    nav.className = "sections";
    nav.setAttribute("aria-label", "Pages");
    pages.forEach(function (page) {
      var segment = page.path === "/" ? "" : page.path.slice(1);
      var a = document.createElement("a");
      a.href = "./" + segment;
      a.textContent = page.name;
      if (segment === here) a.setAttribute("aria-current", "page");
      nav.appendChild(a);
    });
    return nav;
  }

  function viewSwitch() {
    var box = document.createElement("div");
    box.id = "view-switch";
    box.className = "switch";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Choose a view");

    [
      ["engineering", "Engineering", "SQL above every result, dark panel"],
      ["dashboard", "Dashboard", "Answers only, light page"]
    ].forEach(function (choice) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = choice[1];
      b.title = choice[2];
      b.setAttribute("data-view-choice", choice[0]);
      b.addEventListener("click", function () {
        apply(choice[0]);
        write(choice[0]);
        sync();
      });
      box.appendChild(b);
    });
    return box;
  }

  function brand() {
    var a = document.createElement("a");
    a.className = "brand";
    a.href = "./";
    a.appendChild(document.createElement("i"));
    a.appendChild(document.createTextNode("flightdeck "));
    var small = document.createElement("small");
    small.textContent = "\u00b7 Crow Archer telemetry";
    a.appendChild(small);
    return a;
  }

  function build() {
    if (document.getElementById("site-header")) return;

    var wrap = document.createElement("div");
    wrap.className = "wrap";
    wrap.appendChild(brand());
    wrap.appendChild(pageLinks());
    wrap.appendChild(viewSwitch());

    var header = document.createElement("header");
    header.id = "site-header";
    header.className = "top";
    header.appendChild(wrap);

    document.body.insertBefore(header, document.body.firstChild);
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
