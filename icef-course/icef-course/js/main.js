/** courel **/





	
 $(document).ready(function () {
  var t = $("#services__accordion > .accordion .accordion__body").hide(),
    e = $("#accordion__img > img").hide();
  t.first().show(), e.first().show(), $("#services__accordion .accordion").click(function () {
    var i = $(this),
      s = i.attr("tab-name"),
      o = $("#" + s + "-img");
    return t.slideUp(), $("#services__accordion .accordion").removeClass("active"), i.addClass("active"), e.slideUp(), i.find(".accordion__body").slideDown(), o.slideDown(), !1
  })
}), $(document).ready(function () {
  document.querySelectorAll(".counter").forEach(function (t) {
    ! function e() {
      var i = parseInt(t.getAttribute("data-target")),
        s = parseInt(t.innerText),
        o = Math.trunc(i / 200);
      s < i ? (t.innerText = s + o, setTimeout(e, 1)) : t.innerText = i
    }()
  })
})


// Toggle to show and hide navbar menu
document.addEventListener('DOMContentLoaded', function() {
  // Select burgerMenu and navbarMenu after DOM is fully loaded
  const burgerMenu = document.getElementById('burger-menu');
  const navbarMenu = document.getElementById('navbar-menu');

  // Check if elements are found before adding event listener
  if (burgerMenu && navbarMenu) {
      burgerMenu.addEventListener("click", () => {
          navbarMenu.classList.toggle("is-active");
          burgerMenu.classList.toggle("is-active");
      });
  } else {
      console.error('burgerMenu or navbarMenu not found');
  }
});

// Toggle to show and hide dropdown menu
const dropdown = document.querySelectorAll(".dropdown");

dropdown.forEach((item) => {
  const dropdownToggle = item.querySelector(".dropdown-toggle");

  dropdownToggle.addEventListener("click", () => {
    const dropdownShow = document.querySelector(".dropdown-show");
    toggleDropdownItem(item);

    // Remove 'dropdown-show' class from other dropdown
    if (dropdownShow && dropdownShow != item) {
      toggleDropdownItem(dropdownShow);
    }
  });
});

// Function to display the dropdown menu
const toggleDropdownItem = (item) => {
  const dropdownContent = item.querySelector(".dropdown-content");

  // Remove other dropdown that have 'dropdown-show' class
  if (item.classList.contains("dropdown-show")) {
    dropdownContent.removeAttribute("style");
    item.classList.remove("dropdown-show");
  } else {
    // Added max-height on active 'dropdown-show' class
    dropdownContent.style.height = dropdownContent.scrollHeight + "px";
    item.classList.add("dropdown-show");
  }
};

// Fixed dropdown menu on window resizing
window.addEventListener("resize", () => {
  if (window.innerWidth > 992) {
    document.querySelectorAll(".dropdown-content").forEach((item) => {
      item.removeAttribute("style");
    });
    dropdown.forEach((item) => {
      item.classList.remove("dropdown-show");
    });
  }
});

// Fixed navbar menu on window resizing
window.addEventListener("resize", () => {
  if (window.innerWidth > 992) {
    if (navbarMenu.classList.contains("is-active")) {
      navbarMenu.classList.remove("is-active");
      burgerMenu.classList.remove("is-active");
    }
  }
});





