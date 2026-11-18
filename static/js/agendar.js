/* Agendamento em etapas: profissional → serviço → dia/horário → recado.
   Os horários vêm do servidor (cadastrados pelo profissional); o cliente só escolhe. */
(function () {
  var form = document.getElementById("formAgendar");
  if (!form) return;

  var campo = {
    prof: document.getElementById("id_profissional"),
    serv: document.getElementById("id_servico"),
    hor: document.getElementById("id_horario")
  };
  var el = {
    s2: document.getElementById("step2"), s3: document.getElementById("step3"), s4: document.getElementById("step4"),
    servicos: document.getElementById("listaServicos"), dias: document.getElementById("listaDias"),
    horarios: document.getElementById("listaHorarios"), msg: document.getElementById("msgHorarios"),
    resProf: document.getElementById("resProf"), resServ: document.getElementById("resServ"),
    resQuando: document.getElementById("resQuando"), resValor: document.getElementById("resValor"),
    btn: document.getElementById("btnConfirmar")
  };
  var estado = { servico: null, diaRotulo: "", hora: "", fim: "" };

  function url(base, id) { return base.replace("/0/", "/" + id + "/"); }
  function brl(v) { return Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }
  function trava(step, travar) { step.classList.toggle("is-locked", travar); }
  function pronto(step, ok) { step.classList.toggle("is-done", ok); }
  function limpa(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function texto(node, t, vazio) { node.textContent = t; node.classList.toggle("vazio", !!vazio); }
  function cria(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt) e.textContent = txt; return e; }
  function marca(container, alvo) {
    container.querySelectorAll("[aria-pressed]").forEach(function (b) { b.setAttribute("aria-pressed", b === alvo ? "true" : "false"); });
  }

  function atualizaResumo() {
    var s = estado.servico;
    if (s) { texto(el.resServ, s.nome + " · " + s.duracao + " min", false); texto(el.resValor, brl(s.preco), false); }
    else { texto(el.resServ, "Ainda não escolhido", true); texto(el.resValor, "—", true); }
    if (campo.hor.value && estado.hora) texto(el.resQuando, estado.diaRotulo + " às " + estado.hora, false);
    else texto(el.resQuando, "Ainda não escolhido", true);
    el.btn.disabled = !(campo.prof.value && campo.serv.value && campo.hor.value);
  }

  function resetaHorario() {
    campo.hor.value = ""; estado.hora = ""; estado.fim = ""; estado.diaRotulo = "";
    limpa(el.dias); limpa(el.horarios);
    trava(el.s4, true); pronto(el.s3, false);
  }

  function escolherHorario(btn, diaRotulo, h) {
    marca(el.horarios, btn);
    campo.hor.value = h.id; estado.hora = h.hora; estado.fim = h.fim; estado.diaRotulo = diaRotulo;
    pronto(el.s3, true); trava(el.s4, false); atualizaResumo();
  }

  function mostrarDia(dia, chip, restaurar) {
    marca(el.dias, chip); limpa(el.horarios);
    dia.horarios.forEach(function (h) {
      var b = cria("button", "slot-btn", h.hora);
      b.type = "button"; b.setAttribute("aria-pressed", "false");
      b.title = h.hora + " às " + h.fim;
      b.addEventListener("click", function () { escolherHorario(b, dia.rotulo, h); });
      el.horarios.appendChild(b);
      if (restaurar && String(h.id) === String(restaurar)) escolherHorario(b, dia.rotulo, h);
    });
  }

  function carregarHorarios(restaurar) {
    resetaHorario(); atualizaResumo();
    if (!campo.prof.value || !campo.serv.value) return;
    el.msg.textContent = "Buscando horários livres…";
    fetch(url(form.dataset.urlHorarios, campo.prof.value) + "?servico=" + campo.serv.value)
      .then(function (r) { return r.json(); })
      .then(function (dados) {
        if (!dados.dias.length) {
          el.msg.textContent = "Este profissional não tem horários livres para esse serviço. Tente outro serviço ou outro profissional.";
          return;
        }
        el.msg.textContent = "Escolha o dia e depois o horário.";
        var achou = false;
        dados.dias.forEach(function (dia) {
          var chip = cria("button", "day-chip");
          chip.type = "button"; chip.setAttribute("aria-pressed", "false");
          chip.appendChild(document.createTextNode(dia.rotulo));
          chip.appendChild(cria("small", "", dia.horarios.length + (dia.horarios.length === 1 ? " horário" : " horários")));
          chip.addEventListener("click", function () {
            campo.hor.value = ""; estado.hora = ""; pronto(el.s3, false); trava(el.s4, true); atualizaResumo();
            mostrarDia(dia, chip);
          });
          el.dias.appendChild(chip);
          if (restaurar && !achou && dia.horarios.some(function (h) { return String(h.id) === String(restaurar); })) {
            achou = true; mostrarDia(dia, chip, restaurar);
          }
        });
      })
      .catch(function () { el.msg.textContent = "Não foi possível carregar os horários. Atualize a página e tente de novo."; });
  }

  function escolherServico(s, btn, restaurarHorario) {
    marca(el.servicos, btn);
    estado.servico = s; campo.serv.value = s.id;
    pronto(el.s2, true); trava(el.s3, false); atualizaResumo();
    carregarHorarios(restaurarHorario);
  }

  function carregarServicos(restaurarServ, restaurarHor) {
    limpa(el.servicos); estado.servico = null; campo.serv.value = "";
    pronto(el.s2, false); trava(el.s3, true); resetaHorario();
    el.msg.textContent = "Escolha um serviço para ver os horários livres.";
    atualizaResumo();
    if (!campo.prof.value) return;
    el.servicos.appendChild(cria("p", "text-secondary mb-0", "Carregando serviços…"));
    fetch(url(form.dataset.urlServicos, campo.prof.value))
      .then(function (r) { return r.json(); })
      .then(function (lista) {
        limpa(el.servicos);
        if (!lista.length) { el.servicos.appendChild(cria("p", "text-secondary mb-0", "Este profissional ainda não tem serviços cadastrados.")); return; }
        trava(el.s2, false);
        lista.forEach(function (s) {
          var b = cria("button", "pick-card"); b.type = "button"; b.setAttribute("aria-pressed", "false");
          var info = cria("span");
          info.appendChild(cria("span", "fw-semibold d-block", s.nome));
          info.appendChild(cria("span", "meta d-block", s.categoria + " · " + s.duracao + " min"));
          b.appendChild(info); b.appendChild(cria("span", "price", brl(s.preco)));
          b.addEventListener("click", function () { escolherServico(s, b, null); });
          el.servicos.appendChild(b);
          if (restaurarServ && String(s.id) === String(restaurarServ)) escolherServico(s, b, restaurarHor);
        });
      })
      .catch(function () { limpa(el.servicos); el.servicos.appendChild(cria("p", "text-danger mb-0", "Não foi possível carregar os serviços.")); });
  }

  function escolherProfissional(card, restaurarServ, restaurarHor) {
    marca(document.getElementById("step1"), card);
    campo.prof.value = card.dataset.id;
    texto(el.resProf, card.dataset.nome, false);
    pronto(document.getElementById("step1"), true);
    trava(el.s2, false);
    carregarServicos(restaurarServ, restaurarHor);
  }

  document.querySelectorAll("#step1 .pick-card").forEach(function (card) {
    card.addEventListener("click", function () { escolherProfissional(card, null, null); });
  });

  // restaura as escolhas quando o formulário volta com erro, ou quando veio de ?profissional=ID
  if (campo.prof.value) {
    var card = document.querySelector('#step1 .pick-card[data-id="' + campo.prof.value + '"]');
    if (card) escolherProfissional(card, campo.serv.value, campo.hor.value);
  }
  atualizaResumo();
})();
