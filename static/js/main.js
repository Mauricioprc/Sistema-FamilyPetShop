/**
 * main.js — Inicialização do wizard de agendamento público
 * Orquestra os módulos: Agenda, Pacotes, Clientes, Financeiro, Validator
 *
 * Carregado após todos os módulos (incluídos via <script> no template).
 */

(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {

        /* ------------------------------------------------------------------ */
        /* 1. REFERÊNCIAS DOM                                                   */
        /* ------------------------------------------------------------------ */
        const form           = document.getElementById('agendamento-form');
        const formSteps      = document.querySelectorAll('.form-step');
        const stepIndicators = document.querySelectorAll('.step-item');
        const prevBtn        = document.getElementById('prev-btn');
        const nextBtn        = document.getElementById('next-btn');
        const submitBtn      = document.getElementById('btn-finalizar');
        const totalSteps     = formSteps.length;

        let currentStep = 1;

        if (!form) return; // Página sem wizard — sai silenciosamente

        /* ------------------------------------------------------------------ */
        /* 2. MÁSCARA DE TELEFONE                                               */
        /* ------------------------------------------------------------------ */
        const phoneInput = document.getElementById('telefone');
        if (phoneInput && typeof IMask !== 'undefined') {
            IMask(phoneInput, { mask: '(00) 00000-0000' });
        }

        /* ------------------------------------------------------------------ */
        /* 3. CALENDÁRIO (módulo Agenda)                                        */
        /* ------------------------------------------------------------------ */
        Agenda.init({
            grid:             document.getElementById('calendar-days'),
            monthDisplay:     document.getElementById('current-month-year'),
            dataInput:        document.getElementById('data'),
            dataDisplay:      document.getElementById('data-selecionada-display'),
            horarioContainer: document.getElementById('horario-container'),
            onSelect: () => form.classList.remove('was-validated')
        });

        /* ------------------------------------------------------------------ */
        /* 4. CÁLCULO DE PREÇO (módulo Pacotes)                                */
        /* ------------------------------------------------------------------ */
        Pacotes.init({
            pesoRange:       document.getElementById('peso_pet'),
            pesoValor:       document.getElementById('peso_valor'),
            servicoSelector: document.getElementById('servico_selector'),
            precoFinalInput: document.getElementById('preco_final'),
            precoDisplay:    document.getElementById('preco_calculado')
        });

        /* ------------------------------------------------------------------ */
        /* 5. TRANSPORTE / ENDEREÇO (módulo Clientes)                          */
        /* ------------------------------------------------------------------ */
        Clientes.init();

        /* ------------------------------------------------------------------ */
        /* 6. CHECKBOX DE CIÊNCIA (trava de segurança no passo 5)              */
        /* ------------------------------------------------------------------ */
        const checkboxCiencia = document.getElementById('check-ciencia');
        if (checkboxCiencia && submitBtn) {
            checkboxCiencia.addEventListener('change', function () {
                submitBtn.disabled      = !this.checked;
                submitBtn.style.opacity = this.checked ? '1'   : '0.5';
                submitBtn.style.cursor  = this.checked ? 'pointer' : 'not-allowed';
            });
        }

        /* ------------------------------------------------------------------ */
        /* 7. ENVIO DO FORMULÁRIO (spinner + prevenção de duplo clique)        */
        /* ------------------------------------------------------------------ */
        form.addEventListener('submit', function (e) {
            if (!checkboxCiencia?.checked) {
                e.preventDefault();
                alert('Você precisa declarar que leu o aviso para continuar.');
                return;
            }

            if (submitBtn) {
                submitBtn.innerHTML = `
                    <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                    Enviando Solicitação...`;
                submitBtn.disabled     = true;
                submitBtn.style.opacity = '0.8';
                submitBtn.style.cursor = 'not-allowed';
            }
        });

        /* ------------------------------------------------------------------ */
        /* 8. WIZARD: NAVEGAÇÃO ENTRE PASSOS                                   */
        /* ------------------------------------------------------------------ */
        function goToStep(step) {
            currentStep = step;
            _updateUI();
            window.scrollTo(0, 0);
        }

        // Expõe globalmente (usado pelo botão "Ajustar informações")
        window.goToStep = goToStep;

        function _updateUI() {
            formSteps.forEach((s, i) => {
                s.classList.toggle('d-none', i + 1 !== currentStep);
            });

            stepIndicators.forEach((ind, i) => {
                ind.classList.remove('active', 'completed');
                if (i + 1 < currentStep)      ind.classList.add('completed');
                else if (i + 1 === currentStep) ind.classList.add('active');
            });

            prevBtn.style.visibility = currentStep === 1          ? 'hidden' : 'visible';
            nextBtn.style.display    = currentStep === totalSteps ? 'none'   : 'inline-block';

            if (submitBtn) {
                submitBtn.style.display = currentStep === totalSteps ? 'block' : 'none';
            }
        }

        nextBtn.addEventListener('click', function () {
            const stepEl = formSteps[currentStep - 1];

            if (!Validator.validateContainer(stepEl)) return;

            // Verificação extra: horário obrigatório no passo 4
            if (currentStep === 4) {
                const horario = document.getElementById('horario_preferido')?.value;
                if (!horario) {
                    alert('Por favor, selecione um horário antes de prosseguir.');
                    return;
                }
                Financeiro.atualizarRevisaoPasso5(form);
            }

            if (currentStep === 3) {
                Financeiro.atualizarResumoPasso4(form);
            }

            if (currentStep < totalSteps) {
                goToStep(currentStep + 1);
            }
        });

        prevBtn.addEventListener('click', function () {
            if (currentStep > 1) goToStep(currentStep - 1);
        });

        // Botões de edição "voltar para passo X"
        document.querySelectorAll('.edit-step-btn').forEach(btn => {
            btn.addEventListener('click', function () {
                goToStep(parseInt(this.dataset.step, 10));
            });
        });

        /* Renderização inicial */
        _updateUI();

    });

})();
