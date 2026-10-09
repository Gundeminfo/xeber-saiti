(function () {
  var input = document.getElementById("q");
  var status = document.getElementById("status");
  var list = document.getElementById("results");
  var data = null;
  var map = { "ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c", "i̇": "i" };

  function norm(s) {
    return s.toLocaleLowerCase("az").replace(/i̇|[əıöüğşç]/g, function (c) { return map[c] || c; });
  }
  function esc(s) {
    return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  function load() {
    if (data) return Promise.resolve(data);
    status.textContent = "Yüklənir…";
    return fetch("axtaris.json").then(function (r) { return r.json(); }).then(function (d) {
      data = d;
      return d;
    }).catch(function () {
      status.textContent = "Axtarış məlumatı yüklənmədi. Səhifəni yeniləyin.";
      return [];
    });
  }

  function run() {
    var q = norm(input.value.trim());
    if (q.length < 2) {
      list.innerHTML = "";
      status.textContent = "Axtarmaq üçün ən azı 2 hərf yazın.";
      return;
    }
    load().then(function (d) {
      var words = q.split(/\s+/);
      var hits = d.filter(function (x) {
        return words.every(function (w) { return x.k.indexOf(w) !== -1; });
      }).slice(0, 60);
      status.textContent = hits.length
        ? hits.length + (hits.length === 60 ? "+" : "") + " xəbər tapıldı"
        : "“" + input.value.trim() + "” üzrə xəbər tapılmadı. Başqa söz yoxlayın.";
      list.innerHTML = hits.map(function (x) {
        return '<li class="entry" style="--c:' + esc(x.c) + '"><span class="entry-time">' + esc(x.d.slice(-5)) +
          '</span><div class="entry-body"><p class="entry-meta"><span class="src">' + esc(x.s) +
          '</span><span class="cat">' + esc(x.d.replace(/, \d\d:\d\d$/, "")) +
          '</span></p><h3 class="entry-title"><a href="' + esc(x.u) + '">' + esc(x.t) + "</a></h3></div></li>";
      }).join("");
    });
  }

  var timer;
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(run, 150);
  });
  var initial = new URLSearchParams(location.search).get("q");
  if (initial) { input.value = initial; run(); }
})();
