
(function () {
  var fonte = document.getElementById("dados-grafico");
  if (!fonte) return;
  var dados = JSON.parse(fonte.textContent);
  var graficos = [];

  if (typeof Chart === "undefined") {
    document.querySelectorAll(".chart-box").forEach(function (b) {
      b.textContent = "Não foi possível carregar os gráficos (sem conexão com a internet).";
    });
    return;
  }

  function css(nome) { return getComputedStyle(document.documentElement).getPropertyValue(nome).trim(); }
  function brl(v) { return Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }

  function montar() {
    graficos.forEach(function (g) { g.destroy(); });
    graficos = [];

    var texto = css("--bs-body-color"), grade = css("--bs-border-color");
    Chart.defaults.color = texto;
    Chart.defaults.font.family = css("--bs-body-font-family");
    Chart.defaults.borderColor = grade;

    var eixoX = { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } };
    var eixoYmoeda = { beginAtZero: true, grid: { color: grade }, ticks: { callback: function (v) { return "R$ " + v; } } };

    var receita = document.getElementById("gReceita");
    if (receita) {
      graficos.push(new Chart(receita, {
        type: "bar",
        data: {
          labels: dados.dias,
          datasets: [
            { label: "Concluído", data: dados.concluido, backgroundColor: css("--bs-primary"), borderRadius: 3, stack: "r" },
            { label: "A receber", data: dados.previsto, backgroundColor: css("--ba-forecast"), borderRadius: 3, stack: "r" }
          ]
        },
        options: {
          maintainAspectRatio: false,
          scales: { x: Object.assign({ stacked: true }, eixoX), y: Object.assign({ stacked: true }, eixoYmoeda) },
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
            tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + brl(c.parsed.y); } } }
          }
        }
      }));
    }

    var status = document.getElementById("gStatus");
    if (status) {
      graficos.push(new Chart(status, {
        type: "doughnut",
        data: {
          labels: dados.status.rotulos,
          datasets: [{ data: dados.status.valores, backgroundColor: ["#E0A526", "#7A62C9", "#2F9E83", "#9A93A3"], borderColor: css("--ba-card-bg"), borderWidth: 2 }]
        },
        options: { maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } } } }
      }));
    }

    var servicos = document.getElementById("gServicos");
    if (servicos) {
      graficos.push(new Chart(servicos, {
        type: "bar",
        data: { labels: dados.servicos.rotulos, datasets: [{ label: "Agendamentos", data: dados.servicos.valores, backgroundColor: css("--bs-primary"), borderRadius: 4 }] },
        options: {
          indexAxis: "y", maintainAspectRatio: false,
          scales: { x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: grade } }, y: { grid: { display: false } } },
          plugins: { legend: { display: false } }
        }
      }));
    }

    var profs = document.getElementById("gProfissionais");
    if (profs) {
      graficos.push(new Chart(profs, {
        type: "bar",
        data: {
          labels: dados.profissionais.rotulos,
          datasets: [
            { label: "Faturado", data: dados.profissionais.concluido, backgroundColor: css("--bs-primary"), borderRadius: 3, stack: "p" },
            { label: "A receber", data: dados.profissionais.a_receber, backgroundColor: css("--ba-forecast"), borderRadius: 3, stack: "p" }
          ]
        },
        options: {
          indexAxis: "y", maintainAspectRatio: false,
          scales: {
            x: { stacked: true, beginAtZero: true, grid: { color: grade }, ticks: { callback: function (v) { return "R$ " + v; } } },
            y: { stacked: true, grid: { display: false } }
          },
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
            tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + brl(c.parsed.x); } } }
          }
        }
      }));
    }

    var semana = document.getElementById("gSemana");
    if (semana) {
      var maximo = Math.max.apply(null, dados.semana.valores);
      graficos.push(new Chart(semana, {
        type: "bar",
        data: {
          labels: dados.semana.rotulos,
          datasets: [{
            label: "Agendamentos", data: dados.semana.valores, borderRadius: 4,
            // o dia mais movimentado fica em destaque
            backgroundColor: dados.semana.valores.map(function (v) { return v === maximo ? css("--bs-primary") : css("--ba-forecast"); })
          }]
        },
        options: {
          maintainAspectRatio: false,
          scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: grade } } },
          plugins: { legend: { display: false } }
        }
      }));
    }
  }

  montar();
  new MutationObserver(montar).observe(document.documentElement, { attributes: true, attributeFilter: ["data-bs-theme"] });
})();
