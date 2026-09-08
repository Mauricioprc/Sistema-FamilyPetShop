/**
 * modules/pacotes.js — Cálculo de preço dinâmico do wizard de agendamento
 * Responsabilidade: calcular e exibir o preço estimado.
 * Depende de: Formatter
 */

const Pacotes = (() => {

    // Tabela de preço total por serviço x faixa de peso (em kg).
    // Cada serviço tem sua própria progressão de preço; um serviço sem
    // faixa cadastrada para o peso do pet é considerado indisponível
    // (trava — não atendemos esse porte para esse serviço).
    const PRECOS_SERVICO = {
        servico_banho: [
            { max: 5,   preco: 40.00  },
            { max: 10,  preco: 60.00  },
            { max: 25,  preco: 80.00  },
            { max: 40,  preco: 100.00 },
            { max: 999, preco: 150.00 }
        ],
        servico_higiene: [
            { max: 5,   preco: 50.00  },
            { max: 10,  preco: 70.00  },
            { max: 25,  preco: 90.00  },
            { max: 40,  preco: 110.00 },
            { max: 999, preco: 160.00 }
        ],
        servico_maquina: [
            { max: 5,   preco: 140.00 },
            { max: 10,  preco: 140.00 },
            { max: 25,  preco: 160.00 },
            { max: 40,  preco: 160.00 },
            { max: 999, preco: 190.00 }
        ],
        // Banho & Tosa Tesoura: não atendemos pets acima de 10kg.
        servico_tesoura: [
            { max: 5,   preco: 160.00 },
            { max: 10,  preco: 160.00 }
        ]
    };

    const LIMITE_PESO_TESOURA = 10;

    let _pesoRange, _pesoValor, _servicoSelector, _precoFinalInput, _precoDisplay;

    /**
     * Inicializa o módulo.
     * @param {object} refs - referências aos elementos DOM relevantes
     */
    function init(refs) {
        _pesoRange       = refs.pesoRange;
        _pesoValor       = refs.pesoValor;
        _servicoSelector = refs.servicoSelector;
        _precoFinalInput = refs.precoFinalInput;
        _precoDisplay    = refs.precoDisplay;

        // Sincroniza range ↔ input numérico
        if (_pesoRange && _pesoValor) {
            _pesoRange.addEventListener('input', () => {
                _pesoValor.value = _pesoRange.value;
                _atualizarTravaTesoura();
                calcular();
            });
            _pesoValor.addEventListener('input', () => {
                let v = parseInt(_pesoValor.value, 10);
                if (isNaN(v) || v < 1)  v = 1;
                if (v > 50)             v = 50;
                _pesoValor.value = v;
                _pesoRange.value = v;
                _atualizarTravaTesoura();
                calcular();
            });
            // Valor inicial
            _pesoValor.value = _pesoRange.value || 10;
        }

        _atualizarTravaTesoura();

        // Serviço principal
        if (_servicoSelector) {
            _servicoSelector.addEventListener('change', calcular);
        }

        // Adicionais (checkboxes)
        document.querySelectorAll('.minimal-optional-group input[type="checkbox"]')
            .forEach(cb => cb.addEventListener('change', calcular));

        // Transporte
        document.querySelectorAll('input[name="transporte"]')
            .forEach(r => r.addEventListener('change', calcular));

        calcular();
    }

    /**
     * Desabilita a opção "Banho & Tosa Tesoura" quando o peso do pet
     * ultrapassa o limite atendido (trava do sistema) e, se ela estava
     * selecionada, força o cliente a escolher outro serviço.
     */
    function _atualizarTravaTesoura() {
        const tesouraInput = document.getElementById('servico_tesoura');
        if (!tesouraInput || !_pesoRange) return;

        const peso      = parseFloat(_pesoRange.value || 0);
        const label     = document.querySelector('label[for="servico_tesoura"]');
        const excedeu   = peso > LIMITE_PESO_TESOURA;

        tesouraInput.disabled = excedeu;
        label?.classList.toggle('disabled', excedeu);

        if (excedeu && tesouraInput.checked) {
            tesouraInput.checked = false;
        }
    }

    /** Calcula e exibe o preço total estimado. */
    function calcular() {
        if (!_pesoRange || !_servicoSelector) return;

        const peso    = parseFloat(_pesoRange.value || 0);
        const servico = _servicoSelector.querySelector('input[name="nome_servico"]:checked');

        if (!servico) {
            _atualizar(0);
            return;
        }

        const tiers = PRECOS_SERVICO[servico.id] || [];
        const regra = tiers.find(t => peso <= t.max);

        if (!regra) {
            // Peso fora da faixa atendida por este serviço (trava).
            _atualizar(0, true);
            return;
        }

        // Adicionais selecionados
        let adicionalServicos = 0;
        document.querySelectorAll('.minimal-optional-group input[type="checkbox"]:checked')
            .forEach(cb => {
                adicionalServicos += parseFloat(cb.getAttribute('data-adicional-price') || 0);
            });

        // Táxi Dog
        const taxiDog = document.getElementById('transporte_taxi');
        const adicionalTaxi = (taxiDog?.checked)
            ? parseFloat(taxiDog.getAttribute('data-taxi-price') || 0)
            : 0;

        _atualizar(regra.preco + adicionalServicos + adicionalTaxi);
    }

    function _atualizar(total, indisponivel) {
        const formatado = indisponivel ? 'Indisponível' : Formatter.currency(total);
        if (_precoDisplay)    _precoDisplay.textContent = formatado;
        if (_precoFinalInput) _precoFinalInput.value    = indisponivel ? '0.00' : total.toFixed(2);
    }

    return { init, calcular };

})();
