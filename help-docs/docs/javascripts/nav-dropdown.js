document.addEventListener("DOMContentLoaded", function () {
  var logo = document.querySelector("a.md-header__button.md-logo");
  if (!logo) return;

  // Derive site root from the logo href — works for both local dev and gh-pages
  var base = new URL(logo.href, window.location.href).pathname;
  if (!base.endsWith("/")) base += "/";

  var items = [
    ["Getting Started",         "getting-started/"],
    ["Managing Repositories",   "usage/managing-repos/"],
    ["Upgrade Workflow",        "usage/upgrade-workflow/"],
    ["Annotations",             "usage/annotations/"],
    ["Configuration",           "reference/config/"],
    ["Changelog",               "changelog/"],
    ["Developer API Reference", "developers/"],
  ];

  var wrapper = document.createElement("div");
  wrapper.className = "rp-nav-dropdown";

  var btn = document.createElement("button");
  btn.className = "rp-nav-dropdown__btn md-header__button";
  btn.setAttribute("aria-label", "Site navigation menu");
  btn.setAttribute("aria-expanded", "false");
  btn.innerHTML =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">' +
    '<path fill="currentColor" d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>' +
    "</svg>";

  var menu = document.createElement("ul");
  menu.className = "rp-nav-dropdown__menu";
  menu.setAttribute("role", "menu");

  items.forEach(function (item) {
    var li = document.createElement("li");
    var a = document.createElement("a");
    a.href = base + item[1];
    a.textContent = item[0];
    a.setAttribute("role", "menuitem");
    li.appendChild(a);
    menu.appendChild(li);
  });

  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    var open = wrapper.classList.toggle("rp-nav-dropdown--open");
    btn.setAttribute("aria-expanded", String(open));
  });

  document.addEventListener("click", function () {
    wrapper.classList.remove("rp-nav-dropdown--open");
    btn.setAttribute("aria-expanded", "false");
  });

  // Close on Escape
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      wrapper.classList.remove("rp-nav-dropdown--open");
      btn.setAttribute("aria-expanded", "false");
    }
  });

  wrapper.appendChild(btn);
  wrapper.appendChild(menu);

  logo.parentNode.insertBefore(wrapper, logo.nextSibling);
});
